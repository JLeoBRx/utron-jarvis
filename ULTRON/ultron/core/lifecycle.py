"""Ciclo de vida dos componentes do ULTRON.

Cada componente declara dependências; o ``LifecycleManager`` inicia em ordem topológica,
publica ``COMPONENT_STARTED``/``COMPONENT_FAILED`` (que a HUD usa na inicialização
cinematográfica) e para em ordem inversa. Um componente que falha não derruba o sistema:
o ULTRON segue em modo degradado e informa a ausência.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from .events import EventType

log = logging.getLogger("ultron.lifecycle")


@dataclass
class HealthStatus:
    status: str = "UNKNOWN"          # OK | WARN | FAIL | UNAVAILABLE | UNKNOWN
    detail: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "detail": self.detail, "data": dict(self.data)}


class Component:
    """Base opcional para componentes com ciclo de vida."""

    name: str = "component"
    critical: bool = False

    def start(self) -> None:  # pragma: no cover - implementação padrão vazia
        pass

    def stop(self) -> None:  # pragma: no cover
        pass

    def health(self) -> HealthStatus:
        return HealthStatus("OK")


@dataclass
class _Entry:
    component: Any
    depends_on: tuple[str, ...]
    status: str = "REGISTERED"       # REGISTERED | STARTING | RUNNING | FAILED | STOPPED
    error: str = ""
    started_at: float = 0.0
    start_seconds: float = 0.0


class LifecycleManager:
    def __init__(self, bus=None):
        self._entries: dict[str, _Entry] = {}
        self._order: list[str] = []
        self._lock = threading.RLock()
        self._bus = bus

    def register(self, component: Any, *, depends_on: tuple[str, ...] = ()) -> None:
        name = getattr(component, "name", None) or type(component).__name__
        with self._lock:
            if name in self._entries:
                raise ValueError(f"componente já registrado: {name}")
            self._entries[name] = _Entry(component, tuple(depends_on))

    def _resolve_order(self) -> list[str]:
        order: list[str] = []
        visiting: set[str] = set()

        def visit(name: str) -> None:
            if name in order:
                return
            if name in visiting:
                raise ValueError(f"dependência circular envolvendo {name}")
            visiting.add(name)
            for dep in self._entries[name].depends_on:
                if dep in self._entries:
                    visit(dep)
            visiting.discard(name)
            order.append(name)

        for name in self._entries:
            visit(name)
        return order

    def _publish(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="lifecycle")

    def start_all(self, *, on_progress: Callable[[str, str], None] | None = None) -> dict[str, str]:
        with self._lock:
            self._order = self._resolve_order()
            order = list(self._order)
        for name in order:
            entry = self._entries[name]
            failed_deps = [d for d in entry.depends_on
                           if d in self._entries and self._entries[d].status == "FAILED"
                           and getattr(self._entries[d].component, "critical", False)]
            if failed_deps:
                entry.status, entry.error = "FAILED", f"dependência crítica falhou: {failed_deps}"
                self._publish(EventType.COMPONENT_FAILED, component=name, error=entry.error)
                continue
            entry.status = "STARTING"
            started = time.perf_counter()
            try:
                start = getattr(entry.component, "start", None)
                if callable(start):
                    start()
                entry.status = "RUNNING"
                entry.started_at = time.time()
                entry.start_seconds = time.perf_counter() - started
                health = self.health_of(name)
                self._publish(EventType.COMPONENT_STARTED, component=name,
                              seconds=round(entry.start_seconds, 3), health=health.to_dict())
            except Exception as exc:
                entry.status, entry.error = "FAILED", f"{type(exc).__name__}: {exc}"
                log.exception("componente %s falhou ao iniciar", name)
                self._publish(EventType.COMPONENT_FAILED, component=name, error=entry.error)
                if getattr(entry.component, "critical", False):
                    raise
            if on_progress:
                on_progress(name, entry.status)
        return self.statuses()

    def stop_all(self, timeout_each: float = 3.0) -> None:
        with self._lock:
            order = list(reversed(self._order or list(self._entries)))
        for name in order:
            entry = self._entries[name]
            if entry.status != "RUNNING":
                continue
            stop = getattr(entry.component, "stop", None)
            if not callable(stop):
                entry.status = "STOPPED"
                continue
            done = threading.Event()
            errors: list[BaseException] = []

            def runner() -> None:
                try:
                    stop()
                except BaseException as exc:  # registrado abaixo
                    errors.append(exc)
                finally:
                    done.set()

            threading.Thread(target=runner, name=f"stop-{name}", daemon=True).start()
            if not done.wait(timeout_each):
                log.warning("componente %s não parou em %.1fs", name, timeout_each)
            elif errors:
                log.warning("componente %s falhou ao parar: %s", name, errors[0])
            entry.status = "STOPPED"
            self._publish(EventType.COMPONENT_STOPPED, component=name)

    def health_of(self, name: str) -> HealthStatus:
        entry = self._entries.get(name)
        if entry is None:
            return HealthStatus("UNKNOWN", "não registrado")
        if entry.status == "FAILED":
            return HealthStatus("FAIL", entry.error)
        probe = getattr(entry.component, "health", None)
        if callable(probe):
            try:
                result = probe()
                if isinstance(result, HealthStatus):
                    return result
                if isinstance(result, dict):
                    return HealthStatus(result.get("status", "OK"), result.get("detail", ""),
                                        result.get("data", {}))
            except Exception as exc:
                return HealthStatus("FAIL", f"health check falhou: {exc}")
        return HealthStatus("OK" if entry.status == "RUNNING" else "UNKNOWN", entry.status)

    def statuses(self) -> dict[str, str]:
        with self._lock:
            return {name: e.status for name, e in self._entries.items()}

    def get(self, name: str) -> Any:
        entry = self._entries.get(name)
        return entry.component if entry else None

    def names(self) -> list[str]:
        return list(self._order or self._entries)
