"""GOAL MANAGER — objetivos persistentes com estados formais.

Estados: CREATED, ANALYZING, PLANNING, EXECUTING, VERIFYING, RECOVERING, COMPLETED, FAILED,
CANCELLED. Transições inválidas são recusadas. Objetivos interrompidos por um desligamento
são marcados como FAILED no próximo início — nunca retomados às cegas (o que poderia
repetir ações).
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.events import EventType
from ..memory.store import Database, dumps, loads

STATES = ("CREATED", "ANALYZING", "PLANNING", "EXECUTING", "VERIFYING", "RECOVERING", "COMPLETED", "FAILED",
          "CANCELLED")
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
TRANSITIONS = {
    "CREATED": {"ANALYZING", "PLANNING", "EXECUTING", "CANCELLED", "FAILED"},
    "ANALYZING": {"PLANNING", "EXECUTING", "COMPLETED", "FAILED", "CANCELLED"},
    "PLANNING": {"EXECUTING", "FAILED", "CANCELLED", "COMPLETED"},
    "EXECUTING": {"VERIFYING", "RECOVERING", "PLANNING", "COMPLETED", "FAILED", "CANCELLED"},
    "VERIFYING": {"EXECUTING", "RECOVERING", "COMPLETED", "FAILED", "CANCELLED", "PLANNING"},
    "RECOVERING": {"EXECUTING", "PLANNING", "VERIFYING", "FAILED", "CANCELLED"},
    "COMPLETED": set(), "FAILED": set(), "CANCELLED": set(),
}


@dataclass
class Goal:
    id: str
    description: str
    priority: int = 50
    status: str = "CREATED"
    confidence: float = 0.0
    risk: str = "low"
    source: str = "user"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tasks: list = field(default_factory=list)
    dependencies: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    result: str = ""
    history: list = field(default_factory=list)

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InvalidTransition(ValueError):
    pass


class GoalManager:
    name = "goals"

    def __init__(self, db: Database, *, bus=None, state=None):
        self.db = db
        self._bus = bus
        self._state = state
        self._lock = threading.RLock()

    def start(self) -> None:
        interrupted = 0
        for goal in self.list(active_only=True):
            self._write_status(goal, "FAILED", "interrompido: o ULTRON foi reiniciado durante a execução")
            interrupted += 1
        self.interrupted_on_start = interrupted

    def stop(self) -> None:
        pass

    # ------------------------------------------------------------ persistência
    def _row(self, r) -> Goal:
        return Goal(r["id"], r["description"], r["priority"], r["status"], r["confidence"], r["risk"], r["source"],
                    r["created_at"], r["updated_at"], loads(r["tasks"], []), loads(r["dependencies"], []),
                    loads(r["evidence"], []), r["result"], loads(r["history"], []))

    def _save(self, goal: Goal) -> None:
        goal.updated_at = time.time()
        self.db.execute(
            "INSERT INTO goals(id,description,priority,status,confidence,risk,source,created_at,updated_at,tasks,"
            "dependencies,evidence,result,history) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
            "description=excluded.description, priority=excluded.priority, status=excluded.status, "
            "confidence=excluded.confidence, risk=excluded.risk, updated_at=excluded.updated_at, tasks=excluded.tasks, "
            "dependencies=excluded.dependencies, evidence=excluded.evidence, result=excluded.result, "
            "history=excluded.history",
            (goal.id, goal.description, goal.priority, goal.status, goal.confidence, goal.risk, goal.source,
             goal.created_at, goal.updated_at, dumps(goal.tasks), dumps(goal.dependencies),
             dumps(goal.evidence[-50:]), goal.result[:2000], dumps(goal.history[-80:])))

    def _emit(self, event_type: EventType, goal: Goal) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, {"id": goal.id, "description": goal.description[:200],
                                           "status": goal.status, "confidence": goal.confidence, "risk": goal.risk,
                                           "result": goal.result[:300], "source": goal.source}, source="goals")
        if self._state is not None:
            current = None if goal.terminal else {"id": goal.id, "description": goal.description[:200],
                                                  "status": goal.status, "confidence": goal.confidence}
            if goal.terminal:
                active = self.active()
                if active is not None and active.id != goal.id:
                    current = {"id": active.id, "description": active.description[:200], "status": active.status,
                               "confidence": active.confidence}
            self._state.update(_source="goals", current_goal=current)

    # ------------------------------------------------------------ API
    def create(self, description: str, *, priority: int = 50, confidence: float = 0.0, risk: str = "low",
               source: str = "user", dependencies: list[str] | None = None) -> Goal:
        description = " ".join(str(description or "").split())[:500]
        if not description:
            raise ValueError("objetivo vazio")
        goal = Goal(uuid.uuid4().hex[:12], description, int(priority), "CREATED", float(confidence), risk, source,
                    dependencies=list(dependencies or []))
        goal.history.append({"status": "CREATED", "at": goal.created_at})
        with self._lock:
            self._save(goal)
        self._emit(EventType.GOAL_CREATED, goal)
        return goal

    def get(self, goal_id: str) -> Goal | None:
        row = self.db.one("SELECT * FROM goals WHERE id=?", (goal_id,))
        return self._row(row) if row else None

    def list(self, *, status: str | None = None, active_only: bool = False, limit: int = 50) -> list[Goal]:
        if active_only:
            marks = ",".join("?" * len(TERMINAL))
            rows = self.db.query(f"SELECT * FROM goals WHERE status NOT IN ({marks}) ORDER BY priority DESC, created_at "
                                 f"LIMIT ?", (*sorted(TERMINAL), limit))
        elif status:
            rows = self.db.query("SELECT * FROM goals WHERE status=? ORDER BY created_at DESC LIMIT ?", (status, limit))
        else:
            rows = self.db.query("SELECT * FROM goals ORDER BY created_at DESC LIMIT ?", (limit,))
        return [self._row(r) for r in rows]

    def active(self) -> Goal | None:
        goals = self.list(active_only=True, limit=1)
        return goals[0] if goals else None

    def dependencies_met(self, goal: Goal) -> bool:
        for dep in goal.dependencies:
            other = self.get(dep)
            if other is None or other.status != "COMPLETED":
                return False
        return True

    def _write_status(self, goal: Goal, status: str, note: str = "") -> Goal:
        goal.status = status
        goal.history.append({"status": status, "at": time.time(), **({"note": note[:200]} if note else {})})
        if status in TERMINAL and note:
            goal.result = note
        with self._lock:
            self._save(goal)
        return goal

    def transition(self, goal_id: str, status: str, *, note: str = "") -> Goal:
        if status not in STATES:
            raise InvalidTransition(f"estado desconhecido: {status}")
        goal = self.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        if status == goal.status:
            return goal
        if status not in TRANSITIONS[goal.status]:
            raise InvalidTransition(f"{goal.status} → {status} não é permitido")
        self._write_status(goal, status, note)
        event = {"COMPLETED": EventType.GOAL_COMPLETED, "FAILED": EventType.GOAL_FAILED}.get(status,
                                                                                               EventType.GOAL_UPDATED)
        self._emit(event, goal)
        return goal

    def update(self, goal_id: str, **fields: Any) -> Goal:
        goal = self.get(goal_id)
        if goal is None:
            raise KeyError(goal_id)
        for key in ("confidence", "risk", "priority", "tasks", "result"):
            if key in fields:
                setattr(goal, key, fields[key])
        if "evidence" in fields:
            goal.evidence.append(fields["evidence"])
        with self._lock:
            self._save(goal)
        self._emit(EventType.GOAL_UPDATED, goal)
        return goal

    def complete(self, goal_id: str, result: str, *, confidence: float | None = None) -> Goal:
        if confidence is not None:
            self.update(goal_id, confidence=confidence)
        goal = self.transition(goal_id, "COMPLETED", note=result)
        return goal

    def fail(self, goal_id: str, reason: str) -> Goal:
        return self.transition(goal_id, "FAILED", note=reason)

    def cancel(self, goal_id: str, reason: str = "cancelado pelo usuário") -> Goal:
        goal = self.get(goal_id)
        if goal is None or goal.terminal:
            return goal  # type: ignore[return-value]
        return self.transition(goal_id, "CANCELLED", note=reason)

    def stats(self) -> dict[str, int]:
        rows = self.db.query("SELECT status, COUNT(*) AS n FROM goals GROUP BY status")
        return {r["status"]: r["n"] for r in rows}
