from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class RuntimeSnapshot:
    state: str
    assistant_active: bool
    current_goal: dict[str, Any] | None = None
    orchestrator: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    permissions: dict[str, Any] = field(default_factory=dict)
    initiative: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class InitiativeRequest:
    kind: str
    summary: str
    confidence: float = 0.0
    urgency: str = "normal"
    suggested_action: str = ""
    risk: str = "low"
    evidence: tuple[str, ...] = ()

@dataclass(frozen=True)
class GoalRequest:
    title: str
    description: str = ""
    priority: str = "normal"
    depends_on: tuple[str, ...] = ()
    source: str = "user"
