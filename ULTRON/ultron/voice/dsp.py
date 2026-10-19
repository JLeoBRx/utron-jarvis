"""Processamento de sinal da voz do JARVIS (numpy).

Cadeia: deslocamento de altura (reamostragem) → reforço de graves → corte de agudos →
rouquidão (saturação suave + ruído modulado pela envolvente) → camada sintética
desafinada → reflexões curtas e escuras → normalização.

A velocidade final é compensada na síntese (``length_scale`` do Piper), de modo que
a altura e a duração podem ser ajustadas de forma independente.
"""
from __future__ import annotations

import math

import numpy as np

from ..personality.voice_profile import VoiceProfile


def resample(signal: np.ndarray, factor: float) -> np.ndarray:
    """Reamostra por interpolação linear. factor > 1 alonga (e torna mais grave ao tocar)."""
    if abs(factor - 1.0) < 1e-3 or len(signal) < 2:
        return signal.astype(np.float32, copy=False)
    n = max(2, int(round(len(signal) * factor)))
    positions = np.linspace(0.0, len(signal) - 1, n)
    return np.interp(positions, np.arange(len(signal)), signal).astype(np.float32)


def one_pole_lowpass(signal: np.ndarray, cutoff_hz: float, rate: int) -> np.ndarray:
    if cutoff_hz <= 0 or cutoff_hz >= rate / 2:
        return signal
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz / rate)
    out = np.empty_like(signal)
    acc = 0.0
    for i, x in enumerate(signal):          # filtro recursivo simples (sinais de voz curtos)
        acc += alpha * (x - acc)
        out[i] = acc
    return out


def lowpass(signal: np.ndarray, cutoff_hz: float, rate: int) -> np.ndarray:
    """Passa-baixas de 2ª ordem via FFT (rápido para frases inteiras)."""
    if cutoff_hz <= 0 or cutoff_hz >= rate / 2 or len(signal) < 8:
        return signal
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1.0 / rate)
    response = 1.0 / np.sqrt(1.0 + (freqs / cutoff_hz) ** 4)
    return np.fft.irfft(spectrum * response, n=len(signal)).astype(np.float32)


def low_shelf(signal: np.ndarray, gain_db: float, corner_hz: float, rate: int) -> np.ndarray:
    if abs(gain_db) < 0.1 or len(signal) < 8:
        return signal
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1.0 / rate)
    gain = 10 ** (gain_db / 20.0)
    response = 1.0 + (gain - 1.0) / (1.0 + (freqs / corner_hz) ** 2)
    return np.fft.irfft(spectrum * response, n=len(signal)).astype(np.float32)


def envelope(signal: np.ndarray, rate: int, window_s: float = 0.012) -> np.ndarray:
    size = max(1, int(rate * window_s))
    kernel = np.ones(size, dtype=np.float32) / size
    return np.convolve(np.abs(signal), kernel, mode="same").astype(np.float32)


def rasp(signal: np.ndarray, amount: float, rate: int, seed: int = 7) -> np.ndarray:
    if amount <= 0:
        return signal
    drive = 1.0 + 4.0 * amount
    saturated = np.tanh(signal * drive) / math.tanh(drive)
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(len(signal)).astype(np.float32)
    noise = lowpass(noise - np.mean(noise), 3200.0, rate)
    noise = noise - lowpass(noise, 900.0, rate)              # banda de "ar" e atrito vocal
    env = envelope(signal, rate)
    peak = float(np.max(np.abs(noise))) or 1.0
    textured = saturated + (noise / peak) * env * (0.55 * amount)
    return ((1 - amount) * signal + amount * textured).astype(np.float32)


def doubling(signal: np.ndarray, amount: float, rate: int) -> np.ndarray:
    if amount <= 0:
        return signal
    layer = resample(signal, 1.012)[: len(signal)]           # camada levemente mais grave
    delay = int(rate * 0.014)
    out = signal.copy()
    out[delay:] += layer[: len(signal) - delay] * amount
    return out


def room(signal: np.ndarray, amount: float, rate: int) -> np.ndarray:
    if amount <= 0:
        return signal
    taps = ((0.029, 0.55), (0.043, 0.38), (0.067, 0.24), (0.097, 0.13))
    tail = int(rate * taps[-1][0]) + 1
    out = np.zeros(len(signal) + tail, dtype=np.float32)
    out[: len(signal)] += signal
    dark = lowpass(signal, 2600.0, rate)
    for delay, gain in taps:
        shift = int(rate * delay)
        out[shift: shift + len(signal)] += dark * gain * amount
    return out


def process(samples: np.ndarray, rate: int, profile: VoiceProfile) -> np.ndarray:
    """Aplica o perfil de voz (JARVIS por padrão). ``samples`` em float32 [-1, 1]. Devolve float32."""
    x = samples.astype(np.float32, copy=True)
    if len(x) == 0:
        return x
    x = resample(x, 1.0 / max(0.5, min(1.5, profile.pitch)))  # tocado na mesma taxa → mais grave
    x = low_shelf(x, profile.depth_db, 170.0, rate)
    x = lowpass(x, profile.air_cut_hz, rate)
    x = rasp(x, profile.rasp, rate)
    x = doubling(x, profile.doubling, rate)
    x = room(x, profile.room, rate)
    peak = float(np.max(np.abs(x))) or 1.0
    return (x / peak * 0.92).astype(np.float32)


def length_scale_for(profile: VoiceProfile) -> float:
    """``length_scale`` do Piper que resulta na velocidade final desejada após o pitch."""
    return max(0.5, min(2.0, (1.0 / profile.speed) * profile.pitch))


def estimate_pitch(samples: np.ndarray, rate: int, fmin: float = 60.0, fmax: float = 400.0) -> float | None:
    """Frequência fundamental mediana por autocorrelação (para validação do perfil)."""
    frame = int(rate * 0.04)
    hop = frame // 2
    values = []
    for start in range(0, len(samples) - frame, hop):
        seg = samples[start:start + frame].astype(np.float64)
        if np.sqrt(np.mean(seg ** 2)) < 0.02:
            continue
        seg = seg - seg.mean()
        corr = np.correlate(seg, seg, mode="full")[frame - 1:]
        lo, hi = int(rate / fmax), min(len(corr) - 1, int(rate / fmin))
        if hi <= lo:
            continue
        lag = lo + int(np.argmax(corr[lo:hi]))
        if corr[lag] > 0.3 * corr[0]:
            values.append(rate / lag)
    return float(np.median(values)) if values else None


def to_int16(samples: np.ndarray, volume: float = 1.0) -> bytes:
    clipped = np.clip(samples * volume, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16).tobytes()


def from_int16(data: bytes) -> np.ndarray:
    return np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
