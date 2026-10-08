"""Sensor do microfone: nível real de entrada e estado de captura.

Não abre o microfone: lê o que o pipeline de voz mede a cada bloco de áudio (RMS em dB
mapeado para 0..1, método do JARVIS preservado).
"""
from __future__ import annotations

import array
import math
from typing import Callable

from .base import Percept, Sensor


def pcm_level(data: bytes) -> float:
    """Nível de um bloco PCM 16 bits: RMS em dB (-60..-10 dB) mapeado para 0..1."""
    try:
        samples = array.array("h")
        samples.frombytes(data[: len(data) // 2 * 2])
        if not samples:
            return 0.0
        rms = math.sqrt(sum(v * v for v in samples) / len(samples))
        if rms < 1:
            return 0.0
        db = 20.0 * math.log10(rms / 32768.0)
        return max(0.0, min(1.0, (db + 60.0) / 50.0))
    except Exception:
        return 0.0


class MicrophoneSensor(Sensor):
    name = "microphone"
    kind = "auditory"

    def __init__(self, probe: Callable[[], dict], interval: float = 0.5):
        super().__init__(interval)
        self._probe = probe

    def sense(self) -> Percept:
        data = dict(self._probe() or {})
        available = bool(data.get("capturing"))
        return Percept("microphone", "auditory", data, 1.0 if available else 0.0)
