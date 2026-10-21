"""TTS — síntese de fala com o perfil de voz do JARVIS.

Motores, em ordem:

1. **Piper** (neural, offline) com a voz ``pt_BR-faber-medium`` (masculina);
2. **SAPI/pyttsx3** (Windows), preferindo voz masculina, renderizada em WAV e processada
   pelo mesmo DSP.

``Speaker`` roda em thread própria: fila de falas, interrupção imediata (barge-in), pausa,
retomada, volume e velocidade. Publica ``VOICE_STARTED``/``VOICE_FINISHED``. Sem
dispositivo de saída, informa claramente e não finge ter falado.

Boca e legenda: cada fala ganha uma trilha labial (``voice.lipsync``) feita do áudio FINAL; o
avatar lê ``mouth()`` e ``caption()``, calculados pela posição REAL de reprodução informada pelo
mixer (amostras entregues ao dispositivo, descontada a latência de saída). Pausa ou interrupção:
a boca fecha no mesmo quadro.
"""
from __future__ import annotations

import io
import logging
import os
import queue
import sys
import tempfile
import threading
import time
import wave
from collections import deque
from typing import Any, Callable

import numpy as np

from ..config import paths
from ..core.events import EventType
from ..personality.voice_profile import VoiceProfile
from . import dsp
from .lipsync import CLOSED, LipSyncTrack, Segment, mouth_dict
from .profile import effective_profile

log = logging.getLogger("ultron.tts")


def _read_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data)) as wav:
        rate, width, channels = wav.getframerate(), wav.getsampwidth(), wav.getnchannels()
        raw = wav.readframes(wav.getnframes())
    if width != 2:
        raise ValueError("formato WAV inesperado")
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


class PiperSynth:
    name = "piper"

    def __init__(self, voice_path: str):
        from piper import PiperVoice
        self.voice = PiperVoice.load(voice_path)
        self.voice_path = voice_path

    def synthesize_segments(self, text: str, *, length_scale: float = 1.0
                            ) -> tuple[np.ndarray, int, list[Segment] | None]:
        """Áudio + trechos por frase com os fonemas (e o alinhamento, se o modelo de voz o exportar)."""
        if not hasattr(self.voice, "synthesize_wav"):                      # piper-tts 1.2: só o áudio
            samples, rate = self.synthesize(text, length_scale=length_scale)
            return samples, rate, None
        from piper import SynthesisConfig
        config = SynthesisConfig(length_scale=length_scale)
        try:
            chunks = list(self.voice.synthesize(text, syn_config=config, include_alignments=True))
        except TypeError:                                                  # sem alinhamento nesta versão
            chunks = list(self.voice.synthesize(text, syn_config=config))
        parts: list[np.ndarray] = []
        segments: list[Segment] = []
        position, rate = 0, 0
        for chunk in chunks:
            audio = np.asarray(chunk.audio_float_array, dtype=np.float32).reshape(-1)
            rate = rate or int(chunk.sample_rate)
            alignment = None
            if getattr(chunk, "phoneme_alignments", None):
                alignment = [(str(a.phoneme), int(a.num_samples)) for a in chunk.phoneme_alignments]
            segments.append(Segment(position, position + len(audio), list(chunk.phonemes or []), alignment))
            parts.append(audio)
            position += len(audio)
        if not parts:
            return np.zeros(0, dtype=np.float32), rate or 22050, []
        return np.concatenate(parts), rate, segments

    def synthesize(self, text: str, *, length_scale: float = 1.0) -> tuple[np.ndarray, int]:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            if hasattr(self.voice, "synthesize_wav"):                     # piper-tts 1.3+
                try:
                    from piper import SynthesisConfig
                    config = SynthesisConfig(length_scale=length_scale)
                except ImportError:
                    config = None
                self.voice.synthesize_wav(text, wav, syn_config=config)
            else:                                                       # piper-tts 1.2
                self.voice.synthesize(text, wav, length_scale=length_scale)
        return _read_wav(buffer.getvalue())


class SapiSynth:
    name = "sapi"

    def __init__(self, profile: VoiceProfile):
        import pyttsx3
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", profile.sapi_rate)
        chosen = None
        for voice in self._engine.getProperty("voices"):
            label = f"{voice.name} {getattr(voice, 'languages', '')}".lower()
            portuguese = "portugu" in label or "brazil" in label or "pt-br" in label or "pt_br" in label
            male = any(n in label for n in ("daniel", "male", "masculin", "ricardo", "antonio"))
            if portuguese and (male or chosen is None):
                chosen = voice.id
                if male:
                    break
        if chosen:
            self._engine.setProperty("voice", chosen)
        self._lock = threading.Lock()

    def synthesize(self, text: str, *, length_scale: float = 1.0) -> tuple[np.ndarray, int]:
        path = os.path.join(tempfile.gettempdir(), f"ultron_tts_{os.getpid()}.wav")
        with self._lock:
            self._engine.save_to_file(text, path)
            self._engine.runAndWait()
        with open(path, "rb") as handle:
            data = handle.read()
        try:
            os.remove(path)
        except OSError:
            pass
        samples, rate = _read_wav(data)
        if abs(length_scale - 1.0) > 0.02:
            samples = dsp.resample(samples, length_scale)
        return samples, rate


def com_initialize() -> Callable[[], None]:
    """Inicializa o COM nesta thread (Windows) — a voz SAPI (pyttsx3) depende dele, como o JARVIS original
    fazia na thread de fala. Devolve a função que desfaz a inicialização (nada a fazer fora do Windows)."""
    if sys.platform != "win32":
        return lambda: None
    try:
        import pythoncom                                  # pywin32
        pythoncom.CoInitialize()
        return pythoncom.CoUninitialize
    except Exception:
        pass
    try:
        import ctypes
        ole32 = ctypes.windll.ole32
        if ole32.CoInitializeEx(None, 0x2) in (0, 1):    # COINIT_APARTMENTTHREADED; 1 = já inicializado
            return ole32.CoUninitialize
    except Exception as exc:
        log.warning("COM não pôde ser inicializado na thread de voz: %s", exc)
    return lambda: None


def load_synth(voice_name: str, profile: VoiceProfile) -> tuple[Any | None, str]:
    path = paths.voices_dir() / f"{voice_name}.onnx"
    errors = []
    if path.is_file():
        try:
            return PiperSynth(str(path)), ""
        except Exception as exc:
            errors.append(f"Piper: {exc}")
    else:
        errors.append(f"voz neural {voice_name} não encontrada em assets/voices")
    try:
        return SapiSynth(profile), ""
    except Exception as exc:
        errors.append(f"SAPI: {exc}")
    return None, "; ".join(errors)


class Speaker:
    """Fila de fala com interrupção, pausa e retomada."""

    name = "speaker"
    OUTPUT_LATENCY = 0.05                 # bloco do mixer + buffer do dispositivo (s)
    CAPTION_HOLD = 1.6                    # a legenda fica na tela depois da fala (s)

    def __init__(self, output, *, bus=None, state=None, settings_getter: Callable[[], Any] | None = None,
                 synth_loader: Callable[[], tuple] | None = None):
        self.output = output
        self._bus = bus
        self._state = state
        self._settings = settings_getter
        self._loader = synth_loader
        self.synth = None
        self.reason = ""
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        self._interrupt = threading.Event()
        self.speaking = False
        self.current_text = ""
        self.last_spoken_at = 0.0
        self.muted = False
        self._ready = threading.Event()
        self._recent: deque = deque(maxlen=6)          # (instante, texto) — base do filtro de eco
        self._track: LipSyncTrack | None = None        # boca da fala atual
        self._utterance = None
        self._play_started = 0.0
        self._caption = {"text": "", "until": 0.0, "progress": 0.0}
        self.lipsync_method = ""

    MAX_PAUSE_SECONDS = 60.0              # uma fala pausada e esquecida é descartada

    def profile(self) -> VoiceProfile:
        return effective_profile(self._settings() if self._settings else None)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="ultron-speaker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self.interrupt()
        self._queue.put(None)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(2.0)                     # encerramento ordenado: a síntese em curso termina ou é cortada
        self._thread = None

    def wait_ready(self, timeout: float = 30.0) -> bool:
        return self._ready.wait(timeout)

    @property
    def available(self) -> bool:
        return self.synth is not None and self.output is not None and self.output.available

    def say(self, text: str) -> bool:
        text = " ".join(str(text or "").split())
        if not text or self.muted:
            return False
        self._queue.put(text)
        return True

    def interrupt(self) -> None:
        """Interrompe a fala atual e descarta a fila (barge-in / 'pare')."""
        self._interrupt.set()
        self._track = None                       # a boca fecha já no próximo quadro
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        if self.output is not None:
            self.output.stop_voice()

    def pause(self) -> bool:
        if self.output is None or not self.speaking:
            return False
        self.output.pause()
        return True

    def resume(self) -> bool:
        if self.output is None or not self.output.paused:
            return False
        self.output.resume()
        return True

    @property
    def paused(self) -> bool:
        return bool(self.output is not None and self.output.paused and self.speaking)

    # ------------------------------------------------------------ boca e legenda (lidos pelo avatar)
    def playback_seconds(self) -> float | None:
        """Instante da fala que está SAINDO no alto-falante agora (None = nada tocando)."""
        utterance, track = self._utterance, self._track
        if utterance is None or track is None or not self.speaking:
            return None
        if self.output is not None and getattr(self.output, "backend", "") in ("pyaudio", "sounddevice"):
            position = int(getattr(utterance, "pos", 0))
            if position <= 0:
                return 0.0
            return max(0.0, position / float(self.output.rate) - self.OUTPUT_LATENCY)
        return max(0.0, time.monotonic() - self._play_started)      # winsound: sem posição do dispositivo

    def audible(self) -> bool:
        """Há fala saindo agora (posição real > 0 e antes do fim; pausada não conta)."""
        seconds = self.playback_seconds()
        track = self._track
        return bool(seconds is not None and track is not None and 0.0 < seconds < track.duration
                    and not self.paused)

    def mouth(self) -> dict:
        """Forma da boca agora (abertura, largura, arredondamento, pressão, dentes, energia)."""
        track = self._track
        seconds = self.playback_seconds()
        if track is None or seconds is None or self.paused:
            return dict(CLOSED)
        params, energy, _word = track.at(seconds)
        return mouth_dict(params, energy)

    def caption(self) -> dict:
        """Legenda sincronizada: o texto da fala e a fração das palavras já ditas."""
        track = self._track
        seconds = self.playback_seconds()
        if track is not None and seconds is not None and self.current_text:
            progress = track.word_progress(seconds)
            self._caption = {"text": self.current_text, "until": time.monotonic() + self.CAPTION_HOLD,
                             "progress": progress}
            return {"text": self.current_text, "progress": progress, "active": True}
        if self._caption["text"] and time.monotonic() < self._caption["until"]:
            return {"text": self._caption["text"], "progress": self._caption["progress"], "active": False}
        return {"text": "", "progress": 0.0, "active": False}

    def recent_text(self, window: float = 15.0) -> str:
        """Texto falado agora e nos últimos ``window`` segundos (o microfone pode captá-lo)."""
        limit = time.time() - window
        parts = [text for at, text in list(self._recent) if at >= limit]
        if self.current_text and self.current_text not in parts:
            parts.append(self.current_text)
        return " ".join(parts)

    def _publish(self, kind: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(kind, payload, source="voice")

    def _loop(self) -> None:
        uninit = com_initialize()
        try:
            self._run()
        finally:
            uninit()

    def _run(self) -> None:
        try:
            if self._loader is not None:
                self.synth, self.reason = self._loader()
            else:
                s = self._settings() if self._settings else None
                self.synth, self.reason = load_synth(getattr(s, "voice", "pt_BR-faber-medium"), self.profile())
        except Exception as exc:
            self.synth, self.reason = None, str(exc)
        self._ready.set()
        if self._state is not None:
            self._state.merge("voice_state", {"tts": getattr(self.synth, "name", None), "tts_reason": self.reason,
                                              "output": getattr(self.output, "backend", "none")}, _source="voice")
        while self._running:
            text = self._queue.get()
            if text is None:
                break
            self._interrupt.clear()
            self._speak(text)

    def _speak(self, text: str) -> None:
        profile = self.profile()
        if self.synth is None or self.output is None or not self.output.available:
            log.info("fala não reproduzida (%s): %s", self.reason or "sem saída de áudio", text)
            self._publish(EventType.VOICE_FINISHED, text=text[:200], spoken=False,
                          reason=self.reason or getattr(self.output, "reason", "sem saída de áudio"))
            return
        try:
            started = time.perf_counter()
            segments = None
            length_scale = dsp.length_scale_for(profile)
            if hasattr(self.synth, "synthesize_segments"):
                samples, rate, segments = self.synth.synthesize_segments(text, length_scale=length_scale)
            else:
                samples, rate = self.synth.synthesize(text, length_scale=length_scale)
            samples = dsp.process(samples, rate, profile)
            if rate != self.output.rate:
                samples = dsp.resample(samples, self.output.rate / rate)
            scale = dsp.time_scale(profile) * (self.output.rate / rate)
            for segment in segments or ():
                segment.start, segment.end = int(segment.start * scale), int(segment.end * scale)
                segment.scale = scale
            track = LipSyncTrack(samples, self.output.rate, segments)
        except Exception as exc:
            log.warning("síntese falhou: %s", exc)
            self._publish(EventType.VOICE_FINISHED, text=text[:200], spoken=False, reason=f"síntese falhou: {exc}")
            return
        if self._interrupt.is_set():
            return
        self.output.voice_volume = profile.volume
        self.speaking, self.current_text = True, text
        self._recent.append((time.time(), text))
        if self._state is not None:
            self._state.merge("voice_state", {"speaking": True, "text": text[:200]}, _source="voice")
            if self._state.runtime_state in ("IDLE", "LISTENING"):
                self._state.set_runtime_state("SPEAKING", text[:80], source="voice")
        self.lipsync_method = track.method
        self._publish(EventType.VOICE_STARTED, text=text[:200], seconds=round(len(samples) / self.output.rate, 2),
                      synth_ms=round((time.perf_counter() - started) * 1000), lipsync=track.method)
        self._track = track
        self._play_started = time.monotonic()
        utterance = self.output.play_voice(samples)
        self._utterance = utterance
        paused_since = 0.0
        while not utterance.done.wait(0.05):
            if self._interrupt.is_set() or not self._running:
                self.output.stop_voice()
                break
            if self.output.paused:
                paused_since = paused_since or time.monotonic()
                if time.monotonic() - paused_since > self.MAX_PAUSE_SECONDS:
                    self._interrupt.set()
                    self.output.stop_voice()
                    break
            else:
                paused_since = 0.0
        interrupted = self._interrupt.is_set()
        self.last_spoken_at = time.time()
        self._track, self._utterance = None, None
        self.speaking, self.current_text = False, ""
        if self._state is not None:
            self._state.merge("voice_state", {"speaking": False}, _source="voice")
            if self._state.runtime_state == "SPEAKING" and self._queue.empty():
                self._state.set_runtime_state("IDLE", "", source="voice")
        self._publish(EventType.VOICE_FINISHED, text=text[:200], spoken=True, interrupted=interrupted,
                      pending=self._queue.qsize())
