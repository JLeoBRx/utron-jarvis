"""J.A.R.V.I.S. // PLANNER ENGINE
Mantém um plano operacional explícito e recalculável.
O plano é um estado de trabalho, não uma lista fixa de ações.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from threading import RLock
import time

_LOCK = RLock()
_PLAN = None

@dataclass
class PlanStep:
    index: int
    objective: str
    status: str = "PENDING"
    evidence: str = ""
    started: float | None = None
    finished: float | None = None

@dataclass
class Plan:
    id: str
    goal: str
    strategy: str
    status: str = "READY"
    revision: int = 0
    steps: list[PlanStep] = field(default_factory=list)
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def to_dict(self):
        d = asdict(self)
        d["steps"] = [asdict(x) for x in self.steps]
        return d


def _split_goal(goal: str):
    text = str(goal or "").strip()
    low = text.lower()
    steps = []
    if any(k in low for k in ("investigue", "analise", "erro", "problema")):
        steps += ["coletar evidências do problema", "identificar causa provável"]
    if any(k in low for k in ("corrija", "resolva", "implemente", "desenvolva")):
        steps += ["aplicar uma correção permitida", "executar um teste ou verificação"]
    if not steps:
        steps = ["entender o objetivo", "executar a próxima ação permitida", "verificar o resultado"]
    return steps


def create(goal: str, plan_id: str = "") -> Plan:
    import uuid
    global _PLAN
    with _LOCK:
        _PLAN = Plan(
            id=plan_id or uuid.uuid4().hex[:8],
            goal=str(goal),
            strategy="adaptativa",
            steps=[PlanStep(i + 1, s) for i, s in enumerate(_split_goal(goal))],
        )
        return _PLAN


def current():
    with _LOCK:
        return _PLAN.to_dict() if _PLAN else None


def set_status(status: str):
    with _LOCK:
        if _PLAN:
            _PLAN.status = status
            _PLAN.updated = time.time()
            return _PLAN.to_dict()
    return None


def step_started(subject: str = ""):
    with _LOCK:
        if not _PLAN: return None
        for step in _PLAN.steps:
            if step.status in ("PENDING", "RETRY"):
                step.status = "RUNNING"; step.started = time.time()
                if subject: step.objective = subject
                _PLAN.updated = time.time(); return _PLAN.to_dict()
    return None


def step_result(verified: bool, evidence: str = ""):
    with _LOCK:
        if not _PLAN: return None
        target = next((s for s in _PLAN.steps if s.status == "RUNNING"), None)
        if target is None:
            target = next((s for s in _PLAN.steps if s.status in ("PENDING", "RETRY")), None)
        if target is None: return _PLAN.to_dict()
        target.status = "DONE" if verified else "RETRY"
        target.evidence = str(evidence or "")[:500]
        target.finished = time.time()
        _PLAN.updated = time.time(); return _PLAN.to_dict()


def replan(reason: str):
    with _LOCK:
        if not _PLAN: return None
        _PLAN.revision += 1
        _PLAN.status = "REPLANNING"
        _PLAN.updated = time.time()
        # Não apaga evidências. Apenas mantém passos não concluídos como pendentes.
        for step in _PLAN.steps:
            if step.status == "RETRY": step.status = "PENDING"
        return _PLAN.to_dict()


def finish(success: bool):
    return set_status("DONE" if success else "BLOCKED")
