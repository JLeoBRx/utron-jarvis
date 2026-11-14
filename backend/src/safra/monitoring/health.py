"""Registro de saúde: cada componente declara uma verificação; uma verificação que falha não derruba as outras."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from ..core.logging import get_logger

Status = Literal["ok", "degraded", "failed"]
log = get_logger("monitoring.health")


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    critical: bool
    detail: str = ""
    elapsed_ms: float = 0.0


@dataclass(frozen=True)
class HealthReport:
    status: Status
    checks: tuple[CheckResult, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {"status": self.status,
                "checks": [{"name": c.name, "ok": c.ok, "critical": c.critical, "detail": c.detail,
                            "elapsed_ms": c.elapsed_ms} for c in self.checks]}


class HealthRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, tuple[Callable[[], bool | tuple[bool, str]], bool]] = {}

    def register(self, name: str, check: Callable[[], bool | tuple[bool, str]], *, critical: bool = True) -> None:
        """``check`` devolve ``True``/``False`` ou ``(ok, detalhe)``. Lançar exceção conta como falha."""
        if name in self._checks:
            raise ValueError(f"verificação de saúde já registrada: {name}")
        self._checks[name] = (check, critical)

    def report(self) -> HealthReport:
        results: list[CheckResult] = []
        for name, (check, critical) in self._checks.items():
            started = time.perf_counter()
            try:
                outcome = check()
                ok, detail = outcome if isinstance(outcome, tuple) else (bool(outcome), "")
            except Exception as exc:                          # uma verificação quebrada não derruba o relatório
                log.warning("verificação de saúde lançou exceção", extra={"check": name, "error": type(exc).__name__})
                ok, detail = False, f"a verificação falhou ({type(exc).__name__})"
            results.append(CheckResult(name, bool(ok), critical, str(detail),
                                       round((time.perf_counter() - started) * 1000, 2)))
        if any(not r.ok and r.critical for r in results):
            status: Status = "failed"
        elif any(not r.ok for r in results):
            status = "degraded"
        else:
            status = "ok"
        return HealthReport(status, tuple(results))
