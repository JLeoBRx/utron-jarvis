"""ULTRON_STATE — o estado global estruturado.

Existe um único estado. Módulos escrevem por ``StateStore.update`` e leem cópias
(``snapshot``). Assim nenhum módulo mantém sua própria versão divergente do mundo.
"""
from __future__ import annotations

import copy
import threading
import time
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from .events import EventType

# Estados de runtime (o que o ULTRON está fazendo agora). A HUD traduz cada um em
# um comportamento visual; nenhum outro módulo inventa estados próprios.
RUNTIME_STATES = (
    "BOOTING", "IDLE", "LISTENING", "THINKING", "PLANNING", "EXECUTING", "VERIFYING",
    "RECOVERY", "SPEAKING", "IMAGINING", "SIMULATING", "DREAMING", "NETWORK",
    "AWAITING_AUTHORIZATION", "ERROR", "SHUTDOWN",
)

# Fases cognitivas exibidas durante processamento (nunca o raciocínio em si).
COGNITIVE_PHASES = ("", "ANALYZING", "CONNECTING", "EVALUATING", "PLANNING", "SELECTING",
                    "EXECUTING", "VERIFYING", "EXPLORING CONNECTIONS", "NEW CONCEPT FOUND")


@dataclass
class UltronState:
    identity: dict = field(default_factory=dict)
    runtime_state: str = "BOOTING"
    runtime_reason: str = ""
    cognitive_phase: str = ""
    current_goal: dict | None = None
    current_task: dict | None = None
    current_subtask: dict | None = None
    current_action: dict | None = None
    current_plan: dict | None = None
    current_application: str = ""
    current_window: str = ""
    current_processes: list = field(default_factory=list)
    world_model: dict = field(default_factory=dict)
    network_state: dict = field(default_factory=dict)
    device_state: dict = field(default_factory=dict)
    memory_state: dict = field(default_factory=dict)
    vision_state: dict = field(default_factory=dict)
    voice_state: dict = field(default_factory=dict)
    active_model: str = ""
    active_skills: list = field(default_factory=list)
    confidence: float = 0.0
    risk: str = "none"
    last_action: dict | None = None
    last_result: dict | None = None
    last_error: dict | None = None
    imagination_state: dict = field(default_factory=dict)
    simulation_state: dict = field(default_factory=dict)
    health: dict = field(default_factory=dict)
    telemetry: dict = field(default_factory=dict)
    privacy: dict = field(default_factory=dict)
    models: dict = field(default_factory=dict)
    pending_authorization: dict | None = None
    boot: dict = field(default_factory=dict)
    updated_at: float = field(default_factory=time.time)
    version: int = 0


_FIELDS = {f.name for f in fields(UltronState)}


class StateStore:
    def __init__(self, bus=None):
        self._state = UltronState()
        self._lock = threading.RLock()
        self._bus = bus

    def attach_bus(self, bus) -> None:
        self._bus = bus

    def snapshot(self) -> UltronState:
        with self._lock:
            return copy.deepcopy(self._state)

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(asdict(self._state))

    def get(self, name: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(getattr(self._state, name, default))

    def update(self, *, _source: str = "", **changes: Any) -> list[str]:
        unknown = set(changes) - _FIELDS
        if unknown:
            raise KeyError(f"campos inexistentes no ULTRON_STATE: {sorted(unknown)}")
        changed = []
        with self._lock:
            for key, value in changes.items():
                if getattr(self._state, key) != value:
                    setattr(self._state, key, copy.deepcopy(value))
                    changed.append(key)
            if changed:
                self._state.version += 1
                self._state.updated_at = time.time()
                version = self._state.version
        if changed and self._bus is not None:
            self._bus.publish(EventType.STATE_CHANGED,
                              {"changed": changed, "version": version}, source=_source or "state")
        return changed

    def merge(self, name: str, values: dict, *, _source: str = "") -> list[str]:
        """Atualiza parcialmente um campo do tipo dicionário."""
        with self._lock:
            current = dict(getattr(self._state, name) or {})
            current.update(values)
        return self.update(_source=_source, **{name: current})

    def set_runtime_state(self, state: str, reason: str = "", *, source: str = "") -> bool:
        if state not in RUNTIME_STATES:
            raise ValueError(f"estado de runtime desconhecido: {state}")
        changed = self.update(_source=source, runtime_state=state, runtime_reason=reason)
        return "runtime_state" in changed

    def set_cognitive_phase(self, phase: str, *, source: str = "") -> None:
        if phase not in COGNITIVE_PHASES:
            raise ValueError(f"fase cognitiva desconhecida: {phase}")
        if "cognitive_phase" in self.update(_source=source, cognitive_phase=phase) and self._bus:
            self._bus.publish(EventType.COGNITIVE_PHASE, {"phase": phase}, source=source or "state")

    @property
    def runtime_state(self) -> str:
        with self._lock:
            return self._state.runtime_state
