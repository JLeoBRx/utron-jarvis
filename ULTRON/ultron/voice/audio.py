"""Entrada e saída de áudio.

* ``AudioOutput``: mixer com canais ``voice`` (fala, interrompível/pausável), ``sfx``
  (identidade sonora, atenuada durante a fala) e ``bed`` (zumbido contínuo em laço, com
  volume que desliza até o alvo). Backend PyAudio em modo callback; sem PyAudio, ``sounddevice``;
  sem nenhum, ``winsound`` (sem mixagem: efeitos são suprimidos durante a fala); sem
  dispositivo, o backend nulo registra que não há saída de áudio.
* ``open_microphone``: seleção de microfone por nome, índice e padrão (lógica do JARVIS original),
  com PyAudio e, na falta ou falha dele, ``sounddevice``; se o dispositivo não aceitar 16 kHz, abre
  na taxa nativa e converte. ``list_input_devices`` lista os microfones sem abrir nenhum.
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

    def __init__(self, rate: int = MIXER_RATE, *, device_name: str = "", device_index: int = -1):
        self.rate = rate
        self.backend = "none"
        self.reason = ""
        self.device_name = str(device_name or "")       # saída escolhida (vazio = padrão do sistema)
        self.device_index = int(device_index if device_index is not None else -1)
        self.device = ""                                # dispositivo realmente aberto
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
        self._stream = self._pa = None
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(1.0)                 # laço do winsound: sai no próximo ciclo (≤ 50 ms)
        self._thread = None

    @property
    def available(self) -> bool:
        return self.backend != "none"

    def set_device(self, name: str = "", index: int = -1) -> str:
        """Troca a saída de áudio (nome exato/parcial ou índice; vazio = padrão) e reabre o fluxo.
        A fala em andamento é interrompida. Devolve o dispositivo aberto ('' = nenhum)."""
        self.device_name, self.device_index = str(name or ""), int(index if index is not None else -1)
        was_running = self.backend in ("pyaudio", "sounddevice")
        if was_running:
            self.stop()
            self.start()
        return self.device

    def _choose(self, devices: list[dict], default: int | None) -> dict | None:
        """Nome escolhido → índice escolhido → padrão do sistema (nenhum outro é tentado sozinho)."""
        for candidate in _candidates(devices, default, self.device_name, self.device_index):
            return candidate
        return None

    def _open_pyaudio(self) -> bool:
        import pyaudio
        index = None
        label = "padrão do sistema"
        if self.device_name or self.device_index >= 0:
            devices, default = _pyaudio_output_devices()
            chosen = self._choose(devices, default)
            if chosen is None:
                log.warning("saída de áudio escolhida não encontrada (%s); usando a padrão",
                            self.device_name or self.device_index)
            else:
                index, label = chosen["index"], chosen["name"]
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(format=pyaudio.paInt16, channels=1, rate=self.rate, output=True,
                                     output_device_index=index, frames_per_buffer=BLOCK,
                                     stream_callback=self._pa_callback)
        self._stream.start_stream()
        self.backend = "pyaudio"
        self.device = label
        return True

    def _open_sounddevice(self) -> bool:
        import sounddevice as sd
        device = None
        label = "padrão do sistema"
        if self.device_name or self.device_index >= 0:
            devices, default = _sounddevice_output_devices()
            chosen = self._choose(devices, default)
            if chosen is not None:
                device, label = chosen["index"], chosen["name"]
        self._stream = sd.OutputStream(samplerate=self.rate, channels=1, dtype="int16", blocksize=BLOCK,
                                       device=device, callback=self._sd_callback)
        self._stream.start()
        self.backend = "sounddevice"
        self.device = label
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


class AudioBackendMissing(ImportError):
    """Nenhuma biblioteca de áudio (PyAudio ou sounddevice) está instalada."""


INPUT_BACKENDS = ("pyaudio", "sounddevice")


def _lowpass_taps(ratio: int, taps: int = 63) -> np.ndarray:
    """FIR passa-baixas (sinc janelado) para reduzir a taxa por um fator inteiro sem serrilhado."""
    cutoff = 0.45 / ratio
    n = np.arange(taps) - (taps - 1) / 2
    h = np.sinc(2 * cutoff * n) * np.hamming(taps)
    return (h / h.sum()).astype(np.float32)


class _ResamplingStream:
    """Abre o microfone na taxa nativa (ex.: 48 kHz) e entrega PCM 16 bits a 16 kHz.

    Usado só quando o dispositivo recusa 16 kHz. Fator inteiro: filtro FIR + decimação; fator
    não inteiro: filtro + interpolação linear. O estado do filtro passa de um bloco ao outro."""

    def __init__(self, inner, source_rate: int, target_rate: int = 16000):
        self.inner = inner
        self.source_rate, self.target_rate = int(source_rate), int(target_rate)
        ratio = self.source_rate / self.target_rate
        self.integer = abs(ratio - round(ratio)) < 1e-6
        self.ratio = int(round(ratio)) if self.integer else ratio
        self.taps = _lowpass_taps(max(2, int(round(ratio))))
        self._history = np.zeros(len(self.taps) - 1, dtype=np.float32)
        self._phase = 0.0

    def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
        need = int(np.ceil(frames * self.source_rate / self.target_rate))
        raw = self.inner.read(need, exception_on_overflow=False)
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        joined = np.concatenate([self._history, samples])
        filtered = np.convolve(joined, self.taps, mode="valid")
        self._history = joined[-(len(self.taps) - 1):]
        if self.integer:
            out = filtered[:: self.ratio][:frames]
        else:
            positions = np.arange(frames) * self.ratio
            positions = positions[positions < len(filtered) - 1]
            out = np.interp(positions, np.arange(len(filtered)), filtered)
        return np.clip(out, -32768, 32767).astype(np.int16).tobytes()

    def stop_stream(self) -> None:
        stop = getattr(self.inner, "stop_stream", None)
        if stop:
            stop()

    def close(self) -> None:
        self.inner.close()


class _SoundDeviceInput:
    """Adapta ``sounddevice.RawInputStream`` à interface usada pelo pipeline (read/stop_stream/close)."""

    def __init__(self, stream):
        self.stream = stream

    def read(self, frames: int, exception_on_overflow: bool = False) -> bytes:
        data, _overflowed = self.stream.read(frames)
        return bytes(data)

    def stop_stream(self) -> None:
        self.stream.stop()

    def close(self) -> None:
        self.stream.close()


class _NoHandle:
    def terminate(self) -> None:
        pass


def _pyaudio_devices():
    import pyaudio
    audio = pyaudio.PyAudio()
    devices, default = [], None
    try:
        try:
            default = int(audio.get_default_input_device_info()["index"])
        except Exception:
            default = None
        for i in range(audio.get_device_count()):
            try:
                info = audio.get_device_info_by_index(i)
            except Exception:
                continue
            if int(info.get("maxInputChannels", 0)) <= 0:
                continue
            try:
                host = audio.get_host_api_info_by_index(int(info["hostApi"]))["name"]
            except Exception:
                host = ""
            devices.append({"index": i, "name": str(info["name"]), "host_api": host,
                            "channels": int(info["maxInputChannels"]), "rate": int(info.get("defaultSampleRate", 0)),
                            "default": i == default})
    finally:
        audio.terminate()
    return devices, default


def _sounddevice_devices():
    import sounddevice as sd
    devices = []
    try:
        default = int(sd.default.device[0]) if sd.default.device[0] is not None else None
    except Exception:
        default = None
    hostapis = sd.query_hostapis()
    for i, info in enumerate(sd.query_devices()):
        if int(info.get("max_input_channels", 0)) <= 0:
            continue
        host = hostapis[info["hostapi"]]["name"] if 0 <= info.get("hostapi", -1) < len(hostapis) else ""
        devices.append({"index": i, "name": str(info["name"]), "host_api": host,
                        "channels": int(info["max_input_channels"]), "rate": int(info.get("default_samplerate", 0)),
                        "default": i == default})
    return devices, default


def _pyaudio_output_devices():
    import pyaudio
    audio = pyaudio.PyAudio()
    devices, default = [], None
    try:
        try:
            default = int(audio.get_default_output_device_info()["index"])
        except Exception:
            default = None
        for i in range(audio.get_device_count()):
            try:
                info = audio.get_device_info_by_index(i)
            except Exception:
                continue
            if int(info.get("maxOutputChannels", 0)) <= 0:
                continue
            try:
                host = audio.get_host_api_info_by_index(int(info["hostApi"]))["name"]
            except Exception:
                host = ""
            devices.append({"index": i, "name": str(info["name"]), "host_api": host,
                            "channels": int(info["maxOutputChannels"]), "default": i == default})
    finally:
        audio.terminate()
    return devices, default


def _sounddevice_output_devices():
    import sounddevice as sd
    devices = []
    try:
        default = int(sd.default.device[1]) if sd.default.device[1] is not None else None
    except Exception:
        default = None
    hostapis = sd.query_hostapis()
    for i, info in enumerate(sd.query_devices()):
        if int(info.get("max_output_channels", 0)) <= 0:
            continue
        host = hostapis[info["hostapi"]]["name"] if 0 <= info.get("hostapi", -1) < len(hostapis) else ""
        devices.append({"index": i, "name": str(info["name"]), "host_api": host,
                        "channels": int(info["max_output_channels"]), "default": i == default})
    return devices, default


def list_output_devices(backend: str = "auto") -> dict:
    """Saídas de áudio visíveis (nada é aberto)."""
    errors = []
    for name in (("pyaudio", "sounddevice") if backend == "auto" else (backend,)):
        try:
            devices, default = (_pyaudio_output_devices if name == "pyaudio" else _sounddevice_output_devices)()
            return {"backend": name, "devices": devices, "default": default, "errors": errors}
        except ImportError:
            errors.append(f"{name} não instalado")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return {"backend": None, "devices": [], "default": None, "errors": errors}


def list_input_devices(backend: str = "auto") -> dict:
    """Microfones visíveis para a biblioteca de áudio disponível (nada é aberto)."""
    errors = []
    for name in (INPUT_BACKENDS if backend == "auto" else (backend,)):
        try:
            devices, default = (_pyaudio_devices if name == "pyaudio" else _sounddevice_devices)()
            return {"backend": name, "devices": devices, "default": default, "errors": errors}
        except ImportError:
            errors.append(f"{name} não instalado")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return {"backend": None, "devices": [], "default": None, "errors": errors}


def _candidates(devices: list[dict], default: int | None, name_hint: str, index: int) -> list[dict]:
    """Ordem: nome escolhido → índice configurado → padrão do sistema. Outros dispositivos NÃO são
    tentados sozinhos (poderiam ser 'Mixagem estéreo' e captar a própria voz do JARVIS)."""
    out: list[dict] = []
    if name_hint:
        out += [d for d in devices if name_hint.lower() in d["name"].lower()]
    if index >= 0:
        out += [d for d in devices if d["index"] == index and d not in out]
    if default is not None:
        out += [d for d in devices if d["index"] == default and d not in out]
    return out


def _open_pyaudio_input(rate: int, chunk: int, name_hint: str, index: int):
    import pyaudio
    devices, default = _pyaudio_devices()
    audio = pyaudio.PyAudio()
    last_error = None
    for device in _candidates(devices, default, name_hint, index):
        for wanted in (rate, device["rate"]):
            if not wanted:
                continue
            try:
                stream = audio.open(format=pyaudio.paInt16, channels=1, rate=int(wanted), input=True,
                                    input_device_index=device["index"],
                                    frames_per_buffer=int(chunk * wanted / rate))
            except Exception as exc:
                last_error = exc
                continue
            if int(wanted) != rate:
                stream = _ResamplingStream(stream, int(wanted), rate)
            return audio, stream, device, int(wanted)
    audio.terminate()
    raise RuntimeError(_no_device_message(devices, last_error))


def _open_sounddevice_input(rate: int, chunk: int, name_hint: str, index: int):
    import sounddevice as sd
    devices, default = _sounddevice_devices()
    last_error = None
    for device in _candidates(devices, default, name_hint, index):
        for wanted in (rate, device["rate"]):
            if not wanted:
                continue
            try:
                raw = sd.RawInputStream(samplerate=int(wanted), channels=1, dtype="int16",
                                        blocksize=int(chunk * wanted / rate), device=device["index"])
                raw.start()
            except Exception as exc:
                last_error = exc
                continue
            stream = _SoundDeviceInput(raw)
            if int(wanted) != rate:
                stream = _ResamplingStream(stream, int(wanted), rate)
            return _NoHandle(), stream, device, int(wanted)
    raise RuntimeError(_no_device_message(devices, last_error))


def _no_device_message(devices: list[dict], error) -> str:
    if not devices:
        return "nenhum dispositivo de entrada de áudio encontrado"
    names = "; ".join(f"{d['index']}: {d['name']}" for d in devices[:8])
    return f"nenhum microfone pôde ser aberto ({error}); disponíveis: {names}"


def open_microphone(*, rate: int = 16000, chunk: int = 4000, name_hint: str = "", index: int = -1,
                    log_fn: Callable[[str], None] | None = None, backend: str = "auto"):
    """Abre o microfone: nome escolhido → índice → padrão do sistema; PyAudio e, se faltar ou falhar,
    sounddevice. Devolve (handle, stream, nome) com ``stream.read(n)`` → PCM 16 bits mono a ``rate``."""
    errors = []
    missing = 0
    order = INPUT_BACKENDS if backend == "auto" else (backend,)
    for name in order:
        opener = _open_pyaudio_input if name == "pyaudio" else _open_sounddevice_input
        try:
            handle, stream, device, opened_rate = opener(rate, chunk, name_hint, index)
        except ImportError:
            missing += 1
            errors.append(f"{name} não instalado")
            continue
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        label = f"{device['name']} (índice {device['index']}, {name}"
        label += f", {opened_rate} Hz convertidos para {rate} Hz)" if opened_rate != rate else ")"
        if log_fn:
            log_fn(f"Microfone: {label}.")
        return handle, stream, device["name"]
    if missing == len(order):
        raise AudioBackendMissing("nenhuma biblioteca de áudio instalada (PyAudio ou sounddevice)")
    raise RuntimeError("; ".join(errors))
