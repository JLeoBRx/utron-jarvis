"""Vocabulário da cognição: COMMAND → INTENT → GOAL → TASK → SUBTASK → ACTION → RESULT.

Exemplo: "Prepare meu projeto" é um COMMAND; a INTENT é ``goal``; o GOAL é "Preparar projeto";
as TASKs são os passos do plano (localizar, verificar ambiente, ...); cada TASK executa uma
ACTION (skill + argumentos) e produz um RESULT verificado.
"""
from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

INTENT_KINDS = ("command", "goal", "question", "conversation", "memory_store", "memory_recall", "imagination",
                "world", "scenario", "explore", "image", "dream", "control", "cancel", "response", "unknown")


@dataclass
class Command:
    text: str
    source: str = "text"            # text | voice | proactive | automation
    display_text: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Intent:
    kind: str
    text: str
    confidence: float = 0.0
    skill: str | None = None
    args: dict = field(default_factory=dict)
    template: str = ""
    goal: str = ""
    response: str = ""
    entities: dict = field(default_factory=dict)
    ambiguity: str = ""
    reason: str = ""
    source: str = "rules"            # rules | llm | automation | memory

    @property
    def is_action(self) -> bool:
        return bool(self.skill or self.template)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_step_ids = itertools.count(1)


@dataclass
class PlanStep:
    description: str
    skill: str | None = None
    args: dict = field(default_factory=dict)
    kind: str = "skill"              # skill | agentic | respond
    when: str = "always"             # always | if_failed:<id> | if_succeeded:<id>
    args_from: dict = field(default_factory=dict)   # {"path": "<step_id>.data.path"}
    id: str = field(default_factory=lambda: f"s{next(_step_ids)}")
    status: str = "PENDING"          # PENDING | RUNNING | DONE | UNCONFIRMED | FAILED | SKIPPED | CANCELLED
    attempts: int = 0
    result: dict = field(default_factory=dict)
    verification: dict = field(default_factory=dict)
    optional: bool = False
    recover: bool = True              # False quando o próprio plano trata a falha
    origin: str = "plan"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Plan:
    goal_id: str
    goal_text: str
    steps: list = field(default_factory=list)
    strategy: str = "direct"         # direct | template | procedural | llm | agentic
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    revision: int = 0
    status: str = "READY"            # READY | EXECUTING | DONE | FAILED | CANCELLED
    created: float = field(default_factory=time.time)
    history: list = field(default_factory=list)
    template: str = ""

    def step(self, step_id: str) -> PlanStep | None:
        return next((s for s in self.steps if s.id == step_id), None)

    def index(self, step_id: str) -> int:
        for i, s in enumerate(self.steps):
            if s.id == step_id:
                return i
        raise KeyError(step_id)

    def _log(self, change: str, **data: Any) -> None:
        self.revision += 1
        self.history.append({"revision": self.revision, "change": change, "at": time.time(), **data})

    # ------------------------------------------------------------ adaptação
    def add_step(self, step: PlanStep, *, after: str | None = None) -> PlanStep:
        position = len(self.steps) if after is None else self.index(after) + 1
        self.steps.insert(position, step)
        self._log("add", step=step.id, description=step.description, position=position)
        return step

    def remove_step(self, step_id: str) -> None:
        step = self.steps.pop(self.index(step_id))
        self._log("remove", step=step.id, description=step.description)

    def move_step(self, step_id: str, new_index: int) -> None:
        step = self.steps.pop(self.index(step_id))
        new_index = max(0, min(len(self.steps), new_index))
        self.steps.insert(new_index, step)
        self._log("reorder", step=step.id, position=new_index)

    def replace_step(self, step_id: str, step: PlanStep) -> None:
        self.steps[self.index(step_id)] = step
        self._log("replace", old=step_id, new=step.id, description=step.description)

    def pending(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == "PENDING"]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "goal_id": self.goal_id, "goal": self.goal_text, "strategy": self.strategy,
                "template": self.template, "revision": self.revision, "status": self.status,
                "steps": [s.to_dict() for s in self.steps], "history": list(self.history[-20:])}
