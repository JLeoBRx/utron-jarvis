"""Entrada e saída de áudio.

* ``AudioOutput``: mixer com canais ``voice`` (fala, interrompível/pausável), ``sfx``
  (identidade sonora, atenuada durante a fala) e ``bed`` (zumbido contínuo em laço, com
  volume que desliza até o alvo). Backend PyAudio em modo callback; sem PyAudio, ``sounddevice``;
  sem nenhum, ``winsound`` (sem mixagem: efeitos são suprimidos durante a fala); sem
  dispositivo, o backend nulo registra que não há saída de áudio.
* ``open_microphone``: seleção de microfone por nome, índice e padrão (lógica do JARVIS).
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque
from typing import Callable

import numpy as np

from .dsp import to_int16

log = logging.getLogger("ultron.audio")

MIXER_RATE = 22050
BLOCK = 512


def mix_block(voice: np.ndarray | None, effects: list[np.ndarray], *, voice_gain: float, sfx_gain: float,
              bed: np.ndarray | None = None, bed_gain: float = 0.0) -> np.ndarray:
    """Soma um bloco de voz, efeitos e zumbido com limitação suave (sem estalos).

    Durante a fala os efeitos são atenuados (a voz tem prioridade)."""
    size = max([len(voice) if voice is not None else 0] + [len(e) for e in effects]
               + [len(bed) if bed is not None and bed_gain > 0 else 0] + [0])
    out = np.zeros(size, dtype=np.float32)
    speaking = voice is not None and len(voice) > 0
    if speaking:
        out[: len(voice)] += voice * voice_gain
    duck = 0.45 if speaking else 1.0
    for effect in effects:
        out[: len(effect)] += effect * sfx_gain * duck
    if bed is not None and bed_gain > 0:
        out[: len(bed)] += bed * bed_gain * sfx_gain * duck
    return np.tanh(out * 1.1) / np.tanh(1.1) if size else out


class _Utterance:
    def __init__(self, samples: np.ndarray, ident: int):
        self.samples = samples
        self.pos = 0
        self.id = ident
        self.done = threading.Event()


class AudioOutput:
    name = "audio_output"

    def __init__(self, rate: int = MIXER_RATE):
        self.rate = rate
        self.backend = "none"
        self.reason = ""
        self.voice_volume = 0.9
        self.sfx_volume = 0.35
        self._lock = threading.Lock()
        self._voice: deque[_Utterance] = deque()
        self._effects: list[list] = []          # [samples, pos]
        self._bed: np.ndarray | None = None     # laço contínuo (zumbido neural)
        self._bed_pos = 0
        self._bed_gain = 0.0
        self.bed_target = 0.0
        self._paused = False
        self._ids = 0
        self._stream = None
        self._pa = None
        self._thread: threading.Thread | None = None
        self._running = False
        self.level = 0.0                         # nível de saída (para a HUD)

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        errors = []
        for label, opener in (("PyAudio", self._open_pyaudio), ("sounddevice", self._open_sounddevice)):
            try:
                if opener():
                    self.reason = ""
                    return
            except ImportError:
                errors.append(f"{label} não instalado")
            except Exception as exc:
                errors.append(f"{label}: {exc}")
        self.reason = "; ".join(errors)
        if sys.platform == "win32":
            self.backend = "winsound"
            self._running = True
            self._thread = threading.Thread(target=self._winsound_loop, name="ultron-winsound", daemon=True)
            self._thread.start()
            return
        self.backend = "none"
        self.reason = self.reason or "nenhum dispositivo de saída de áudio disponível"

    def stop(self) -> None:
        self._running = False
        self.stop_voice()
        try:
            if self._stream is not None:
                self._stream.stop_stream() if hasattr(self._stream, "stop_stream") else self._stream.stop()
                self._stream.close()
            if self._pa is not None:
                self._pa.terminate()
        except Exception:
            pass

    @property
    def available(self) -> bool:
        return self.backend != "none"

    def _open_pyaudio(self) -> bool:
        import pyaudio
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(format=pyaudio.paInt16, channels=1, rate=self.rate, output=True,
                                     frames_per_buffer=BLOCK, stream_callback=self._pa_callback)
        self._stream.start_stream()
        self.backend = "pyaudio"
        return True

    def _open_sounddevice(self) -> bool:
        import sounddevice as sd
        self._stream = sd.OutputStream(samplerate=self.rate, channels=1, dtype="int16", blocksize=BLOCK,
                                       callback=self._sd_callback)
        self._stream.start()
        self.backend = "sounddevice"
        return True

    # ------------------------------------------------------------ mixagem
    def _next_block(self, frames: int) -> np.ndarray:
        with self._lock:
            voice_chunk = None
            if self._voice and not self._paused:
                utt = self._voice[0]
                voice_chunk = utt.samples[utt.pos: utt.pos + frames]
                utt.pos += frames
                if utt.pos >= len(utt.samples):
                    self._voice.popleft()
                    utt.done.set()
            effects = []
            alive = []
            for item in self._effects:
                samples, pos = item
                effects.append(samples[pos: pos + frames])
                item[1] = pos + frames
                if item[1] < len(samples):
                    alive.append(item)
            self._effects = alive
            voice_gain, sfx_gain = self.voice_volume, self.sfx_volume
            bed_chunk, bed_gain = None, 0.0
            if self._bed is not None and (self._bed_gain > 1e-4 or self.bed_target > 0):
                step = frames / self.rate / 1.5                   # ~1,5 s para ir de 0 a 1
                self._bed_gain += max(-step, min(step, self.bed_target - self._bed_gain))
                idx = (np.arange(frames) + self._bed_pos) % len(self._bed)
                bed_chunk, bed_gain = self._bed[idx], self._bed_gain
                self._bed_pos = int((self._bed_pos + frames) % len(self._bed))
        block = mix_block(voice_chunk, effects, voice_gain=voice_gain, sfx_gain=sfx_gain,
                          bed=bed_chunk, bed_gain=bed_gain)
        if len(block) < frames:
            block = np.concatenate([block, np.zeros(frames - len(block), dtype=np.float32)])
        self.level = float(np.sqrt(np.mean(block ** 2))) if len(block) else 0.0
        return block

    def _pa_callback(self, _in, frames, _time, _status):
        import pyaudio
        return to_int16(self._next_block(frames)), pyaudio.paContinue

    def _sd_callback(self, outdata, frames, _time, _status):
        block = self._next_block(frames)
        outdata[:, 0] = (np.clip(block, -1, 1) * 32767).astype(np.int16)

    def _winsound_loop(self) -> None:
        """Fallback sem PyAudio: arquivo WAV temporário tocado de forma assíncrona (interrompível)."""
        import wave
        import winsound

        from ..config import paths
        temp = paths.data_file("voice_out.wav")
        while self._running:
            with self._lock:
                utt = self._voice[0] if self._voice and not self._paused else None
            if utt is None:
                time.sleep(0.05)
                continue
            with wave.open(str(temp), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(self.rate)
                wav.writeframes(to_int16(utt.samples, self.voice_volume))
            winsound.PlaySound(str(temp), winsound.SND_FILENAME | winsound.SND_ASYNC)
            deadline = time.monotonic() + len(utt.samples) / self.rate + 0.1
            while time.monotonic() < deadline and not utt.done.is_set() and self._running:
                time.sleep(0.03)
            if utt.done.is_set():
                winsound.PlaySound(None, 0)             # interrompido por stop_voice()
            with self._lock:
                if self._voice and self._voice[0] is utt:
                    self._voice.popleft()
            utt.done.set()

    # ------------------------------------------------------------ API
    def play_voice(self, samples: np.ndarray) -> _Utterance:
        with self._lock:
            self._ids += 1
            utt = _Utterance(samples.astype(np.float32, copy=False), self._ids)
            if self.backend == "none":
                utt.done.set()
            else:
                self._voice.append(utt)
        return utt

    @property
    def mixes_effects(self) -> bool:
        return self.backend in ("pyaudio", "sounddevice")

    def play_effect(self, samples: np.ndarray, gain: float = 1.0) -> bool:
        if not self.mixes_effects:
            return False                             # winsound não mistura: a fala tem prioridade
        with self._lock:
            if len(self._effects) >= 12:
                return False
            self._effects.append([(samples * gain).astype(np.float32, copy=False), 0])
        return True

    def set_bed(self, samples: np.ndarray | None) -> None:
        with self._lock:
            self._bed = None if samples is None else samples.astype(np.float32, copy=False)
            self._bed_pos = 0

    def stop_voice(self) -> None:
        with self._lock:
            pending = list(self._voice)
            self._voice.clear()
            self._paused = False
        for utt in pending:
            utt.done.set()                      # o laço do winsound interrompe a reprodução ao ver isto

    def pause(self) -> None:
        with self._lock:
            self._paused = True

    def resume(self) -> None:
        with self._lock:
            self._paused = False

    @property
    def speaking(self) -> bool:
        with self._lock:
            return bool(self._voice) and not self._paused

    @property
    def paused(self) -> bool:
        return self._paused


def open_microphone(*, rate: int = 16000, chunk: int = 4000, name_hint: str = "", index: int = -1,
                    log_fn: Callable[[str], None] | None = None):
    """Abre o microfone: por nome, depois índice e por fim o padrão do sistema."""
    import pyaudio
    audio = pyaudio.PyAudio()

    def usable(i: int) -> bool:
        try:
            return int(audio.get_device_info_by_index(i)["maxInputChannels"]) > 0
        except Exception:
            return False

    candidates: list[int] = []
    if name_hint:
        for i in range(audio.get_device_count()):
            if usable(i) and name_hint.lower() in str(audio.get_device_info_by_index(i)["name"]).lower():
                candidates.append(i)
    if index >= 0 and usable(index) and index not in candidates:
        candidates.append(index)
    try:
        default = int(audio.get_default_input_device_info()["index"])
        if default not in candidates:
            candidates.append(default)
    except Exception:
        pass
    last_error = None
    for i in candidates:
        try:
            stream = audio.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True, input_device_index=i,
                                frames_per_buffer=chunk)
            name = str(audio.get_device_info_by_index(i)["name"])
            if log_fn:
                log_fn(f"Microfone: {name} (índice {i}).")
            return audio, stream, name
        except Exception as exc:
            last_error = exc
    audio.terminate()
    raise RuntimeError(f"nenhum microfone disponível ({last_error})" if last_error else "nenhum microfone disponível")
