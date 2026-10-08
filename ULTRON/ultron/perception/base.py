"""Contratos da percepção.

Todo sensor produz um ``Percept`` com ``source``, ``timestamp``, ``confidence`` e ``data``.
Sensores indisponíveis informam o motivo; nenhum sensor inventa leitura.
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Percept:
    source: str
    type: str
    data: dict = field(default_factory=dict)
    confidence: float = 1.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def age(self) -> float:
        return time.time() - self.timestamp


class SensorUnavailable(RuntimeError):
    """O sensor não pode operar neste sistema (dependência ou hardware ausente)."""


class Sensor:
    name = "sensor"
    kind = "telemetry"
    worker = "perception"

    def __init__(self, interval: float = 5.0):
        self.interval = float(interval)
        self.enabled = True
        self.last: Percept | None = None
        self.status = "IDLE"             # IDLE | OK | UNAVAILABLE | ERROR | DISABLED
        self.reason = ""
        self.errors = 0
        self.runs = 0

    def available(self) -> tuple[bool, str]:
        return True, ""

    def sense(self) -> Percept | None:  # pragma: no cover - implementado pelos sensores
        raise NotImplementedError

    def poll(self) -> Percept | None:
        """Executa uma leitura com contabilidade de estado. Nunca levanta exceção."""
        if not self.enabled:
            self.status = "DISABLED"
            return None
        ok, reason = self.available()
        if not ok:
            self.status, self.reason = "UNAVAILABLE", reason
            return None
        try:
            percept = self.sense()
            self.runs += 1
            self.status, self.reason = "OK", ""
            if percept is not None:
                self.last = percept
            return percept
        except SensorUnavailable as exc:
            self.status, self.reason = "UNAVAILABLE", str(exc)
            return None
        except Exception as exc:
            self.errors += 1
            self.status, self.reason = "ERROR", f"{type(exc).__name__}: {exc}"[:240]
            return None

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "kind": self.kind, "status": self.status, "reason": self.reason,
                "interval": self.interval, "runs": self.runs, "errors": self.errors,
                "last": self.last.timestamp if self.last else None}
