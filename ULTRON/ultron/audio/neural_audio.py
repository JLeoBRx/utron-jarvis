"""NEURAL AUDIO — a identidade sonora do ULTRON.

Sons procedurais (numpy), sintetizados uma vez no início, sem arquivos externos:

* ``LOW HUM``              zumbido grave contínuo (laço de 4 s) enquanto o ULTRON trabalha;
* ``NEURAL PULSE``         pulso grave com transiente — atenção, ativação, insight;
* ``LOW FREQUENCY``        ondulação subgrave lenta — boot, escuta, sonho;
* ``ELECTRONIC RESONANCE`` ressonância metálica inarmônica — confirmação;
* ``DATA CLICK``           estalo curto de dados — componentes, conexões do grafo;
* ``ENERGY SURGE``         subida de energia — sistema pronto, conceito novo.

Cada som é disparado por um evento real do Event Bus (nunca por temporizador decorativo).
Em repouso o ULTRON fica em silêncio. Os efeitos são atenuados durante a fala e
respeitam ``sound_effects``/``sfx_volume``.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Callable

import numpy as np

from ..core.events import EventType

log = logging.getLogger("ultron.neural_audio")

RATE = 22050
BUSY_BED = {"THINKING": 0.55, "PLANNING": 0.55, "EXECUTING": 0.6, "VERIFYING": 0.5, "RECOVERY": 0.65,
            "IMAGINING": 0.5, "SIMULATING": 0.5, "NETWORK": 0.4, "DREAMING": 0.3, "LISTENING": 0.2,
            "AWAITING_AUTHORIZATION": 0.35}


# ---------------------------------------------------------------- síntese
def _t(seconds: float) -> np.ndarray:
    return np.arange(int(RATE * seconds), dtype=np.float32) / RATE


def _env(n: int, attack: float, release: float) -> np.ndarray:
    a = max(1, int(RATE * attack))
    r = max(1, int(RATE * release))
    env = np.ones(n, dtype=np.float32)
    env[:a] = np.linspace(0, 1, min(a, n), dtype=np.float32)[: min(a, n)]
    if r < n:
        env[-r:] *= np.linspace(1, 0, r, dtype=np.float32) ** 2
    return env


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    spec = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / RATE)
    return np.fft.irfft(spec / np.sqrt(1 + (freqs / cutoff) ** 4), n=len(x)).astype(np.float32)


def _norm(x: np.ndarray, peak: float) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return (x / m * peak).astype(np.float32)


def low_hum() -> np.ndarray:
    """4 s em laço perfeito (todas as frequências completam ciclos inteiros)."""
    t = _t(4.0)
    tone = (np.sin(2 * np.pi * 55 * t) + 0.35 * np.sin(2 * np.pi * 110 * t) + 0.12 * np.sin(2 * np.pi * 165 * t)
            + 0.05 * np.sin(2 * np.pi * 220.5 * t))
    breath = 0.75 + 0.25 * np.sin(2 * np.pi * 0.25 * t)            # respiração lenta (0,25 Hz)
    return _norm(tone * breath, 0.5)


def neural_pulse(base: float = 82.0, drop: float = 0.72) -> np.ndarray:
    t = _t(0.55)
    freq = base * (drop + (1 - drop) * np.exp(-t * 9))              # queda de altura
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    body = np.sin(phase) + 0.3 * np.sin(2 * phase)
    body *= np.exp(-t * 6.5)
    click = np.random.default_rng(3).standard_normal(len(t)).astype(np.float32) * np.exp(-t * 180) * 0.35
    shimmer = 0.08 * np.sin(2 * np.pi * 440 * t + 2.0 * np.sin(2 * np.pi * 7 * t)) * np.exp(-t * 10)
    return _norm(_lowpass(body + click + shimmer, 3000) * _env(len(t), 0.002, 0.05), 0.8)


def low_frequency() -> np.ndarray:
    t = _t(1.4)
    tone = np.sin(2 * np.pi * (42 + 6 * t) * t) + 0.25 * np.sin(2 * np.pi * 84 * t)
    return _norm(tone * _env(len(t), 0.45, 0.6), 0.7)


def electronic_resonance() -> np.ndarray:
    t = _t(1.6)
    partials = ((196.0, 1.0, 2.4), (296.5, 0.55, 3.2), (447.0, 0.32, 4.1), (671.0, 0.18, 5.5), (1006.0, 0.08, 7.0))
    tone = sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in partials)
    return _norm(_lowpass(tone, 2400) * _env(len(t), 0.004, 0.2), 0.55)


def data_click(variant: int = 0) -> np.ndarray:
    t = _t(0.045)
    rng = np.random.default_rng(11 + variant)
    noise = rng.standard_normal(len(t)).astype(np.float32)
    tick = np.sin(2 * np.pi * (1800 + 260 * variant) * t)
    x = (0.6 * noise + tick) * np.exp(-t * (140 + 25 * variant))
    return _norm(_lowpass(x, 5200), 0.35)


def energy_surge() -> np.ndarray:
    t = _t(1.9)
    freq = 60 + 180 * (t / t[-1]) ** 2
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    tone = np.tanh(1.8 * (np.sin(phase) + 0.4 * np.sin(2 * phase)))
    riser = _lowpass(np.random.default_rng(5).standard_normal(len(t)).astype(np.float32), 1800) * (t / t[-1]) ** 3
    env = _env(len(t), 0.9, 0.5)
    return _norm((tone + 0.25 * riser) * env, 0.65)


def pulse_low() -> np.ndarray:
    """Pulso dissonante (falha, erro detectado)."""
    a, b = neural_pulse(70.0, 0.8), neural_pulse(74.0, 0.8)
    return _norm(a + 0.8 * b, 0.75)


def double_pulse() -> np.ndarray:
    first = neural_pulse(88.0)
    gap = np.zeros(int(RATE * 0.12), dtype=np.float32)
    return np.concatenate([first[: int(RATE * 0.3)], gap, neural_pulse(78.0)])


CUES: dict[str, Callable[[], np.ndarray]] = {
    "pulse": neural_pulse, "low_frequency": low_frequency, "resonance": electronic_resonance,
    "surge": energy_surge, "pulse_low": pulse_low, "double_pulse": double_pulse,
    "click0": lambda: data_click(0), "click1": lambda: data_click(1), "click2": lambda: data_click(2),
}

# evento → (som, ganho, intervalo mínimo entre repetições em segundos)
EVENT_CUES: dict[EventType, tuple[str, float, float]] = {
    EventType.SYSTEM_BOOT: ("low_frequency", 0.9, 5.0),
    EventType.COMPONENT_STARTED: ("click", 0.55, 0.06),
    EventType.COMPONENT_FAILED: ("pulse_low", 0.6, 0.5),
    EventType.SYSTEM_READY: ("surge", 0.85, 10.0),
    EventType.WAKE_WORD: ("pulse", 0.8, 0.8),
    EventType.LISTENING_STARTED: ("low_frequency", 0.45, 2.0),
    EventType.COGNITIVE_PHASE: ("click", 0.35, 0.25),
    EventType.GRAPH_NODE_ADDED: ("click", 0.25, 0.15),
    EventType.VERIFICATION_SUCCESS: ("resonance", 0.5, 0.8),
    EventType.VERIFICATION_FAILED: ("pulse_low", 0.55, 1.0),
    EventType.ERROR_DETECTED: ("pulse_low", 0.5, 1.5),
    EventType.AUTHORIZATION_REQUIRED: ("double_pulse", 0.8, 2.0),
    EventType.CONCEPT_CREATED: ("surge", 0.5, 3.0),
    EventType.WORLD_CREATED: ("surge", 0.6, 3.0),
    EventType.IMAGE_GENERATED: ("resonance", 0.6, 2.0),
    EventType.DREAM_STARTED: ("low_frequency", 0.35, 10.0),
    EventType.INSIGHT: ("pulse", 0.6, 5.0),
}


class NeuralAudio:
    name = "neural_audio"

    def __init__(self, output, *, bus, state=None, settings_getter: Callable[[], Any] | None = None):
        self.output = output
        self._bus = bus
        self._state = state
        self._settings = settings_getter or (lambda: None)
        self._sounds: dict[str, np.ndarray] = {}
        self._last: dict[str, float] = {}
        self._click = 0
        self._subs: list = []
        self._lock = threading.Lock()
        self.played = 0
        self.reason = ""

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        started = time.perf_counter()
        self._sounds = {name: build() for name, build in CUES.items()}
        hum = low_hum()
        log.debug("sons neurais sintetizados em %.0f ms", (time.perf_counter() - started) * 1000)
        if self.output is None or not getattr(self.output, "mixes_effects", False):
            backend = getattr(self.output, "backend", "none")
            self.reason = f"saída de áudio sem mixagem ({backend}): efeitos neurais desativados"
        else:
            self.output.set_bed(hum)
        self._subs = [self._bus.subscribe(list(EVENT_CUES), self._on_event, name="neural_audio.cues"),
                      self._bus.subscribe(EventType.STATE_CHANGED, self._on_state, name="neural_audio.bed")]

    def stop(self) -> None:
        for sub in self._subs:
            sub.unsubscribe()
        self._subs = []
        if self.output is not None and hasattr(self.output, "bed_target"):
            self.output.bed_target = 0.0

    def health(self) -> dict:
        if self.reason:
            return {"status": "UNAVAILABLE", "detail": self.reason}
        if not self._enabled():
            return {"status": "WARN", "detail": "efeitos sonoros desativados"}
        return {"status": "OK", "detail": f"{len(self._sounds)} sons; {self.played} reproduzidos"}

    # ------------------------------------------------------------ reprodução
    def _enabled(self) -> bool:
        return bool(getattr(self._settings(), "sound_effects", True))

    def sound(self, name: str) -> np.ndarray | None:
        if name == "click":
            self._click = (self._click + 1) % 3
            name = f"click{self._click}"
        return self._sounds.get(name)

    def play(self, name: str, gain: float = 1.0, *, min_gap: float = 0.0) -> bool:
        if self.reason or not self._enabled():
            return False
        now = time.monotonic()
        with self._lock:
            if now - self._last.get(name, 0.0) < min_gap:
                return False
            self._last[name] = now
        samples = self.sound(name)
        if samples is None:
            return False
        if self.output is not None:
            self.output.sfx_volume = float(getattr(self._settings(), "sfx_volume", 0.35))
        played = bool(self.output.play_effect(samples, gain)) if self.output is not None else False
        self.played += int(played)
        return played

    def _on_event(self, event) -> None:
        cue = EVENT_CUES.get(event.type)
        if cue is None:
            return
        if event.type == EventType.COGNITIVE_PHASE and not event.get("phase"):
            return                                            # fim de fase: silêncio
        name, gain, gap = cue
        self.play(name, gain, min_gap=gap)

    def _on_state(self, event) -> None:
        if "runtime_state" not in (event.get("changed") or ()) or self._state is None:
            return
        runtime = self._state.runtime_state
        target = BUSY_BED.get(runtime, 0.0) if self._enabled() and not self.reason else 0.0
        if self.output is not None and hasattr(self.output, "bed_target"):
            self.output.bed_target = target


def render_preview(path: str) -> dict[str, float]:
    """Grava todos os sons em sequência num WAV (inspeção manual da identidade sonora)."""
    import wave

    from ..voice.dsp import to_int16
    parts, report = [], {}
    gap = np.zeros(int(RATE * 0.35), dtype=np.float32)
    for name, build in list(CUES.items()) + [("low_hum", low_hum)]:
        samples = build()
        report[name] = round(len(samples) / RATE, 3)
        parts.extend([samples, gap])
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(to_int16(np.concatenate(parts), 0.9))
    return report


def spectral_centroid(samples: np.ndarray) -> float:
    spec = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), 1 / RATE)
    return float((spec * freqs).sum() / max(1e-9, spec.sum())) if len(samples) else math.nan
