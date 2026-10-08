"""EXECUTION ENGINE — executa ações estruturadas. Nunca decide o "quê"; apenas o "como".

Entrada::

    Action(skill="app.open", args={"name": "Visual Studio Code"})

Saída::

    ExecutionRecord(status="executed", result=SkillResult(success=True, evidence=[...]))

Um registro "executed" significa que a ação foi realizada — NÃO que o objetivo foi
alcançado. A confirmação é responsabilidade do Verification Engine.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..core.events import EventType
from ..core.runtime import CancelledError, run_with_timeout
from ..skills.base import Skill, SkillContext, SkillResult, VerificationResult
from ..skills.registry import FORBIDDEN, SkillRegistry
from .autonomy import AuthorizationManager, AutonomyPolicy

log = logging.getLogger("ultron.execution")
_ids = itertools.count(1)


@dataclass
class Action:
    skill: str
    args: dict = field(default_factory=dict)
    description: str = ""
    origin: str = "user"                 # user | plan | agent | recovery | proactive | automation
    goal_id: str = ""
    step_id: str = ""
    id: int = field(default_factory=lambda: next(_ids))

    def fingerprint(self) -> str:
        raw = json.dumps({"s": self.skill, "a": self.args}, sort_keys=True, default=str)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionRecord:
    action: Action
    status: str                          # executed | skipped | failed | refused | denied | cancelled | unavailable
    result: SkillResult
    risk: str = "low"
    authorization: dict | None = None
    verification: VerificationResult | None = None
    started: float = field(default_factory=time.time)
    finished: float = 0.0

    @property
    def executed(self) -> bool:
        return self.status == "executed" and self.result.success

    @property
    def verified(self) -> bool:
        return self.verification is not None and self.verification.verified

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action.to_dict(), "status": self.status, "result": self.result.to_dict(),
                "risk": self.risk, "authorization": self.authorization,
                "verification": self.verification.to_dict() if self.verification else None,
                "started": self.started, "finished": self.finished}


def classify_exception(exc: BaseException) -> str:
    if isinstance(exc, (TimeoutError,)):
        return "TIMEOUT"
    if isinstance(exc, PermissionError):
        return "PERMISSION_ERROR"
    if isinstance(exc, (ConnectionError,)):
        return "NETWORK_ERROR"
    if isinstance(exc, (FileNotFoundError, NotADirectoryError, IsADirectoryError)):
        return "FILE_NOT_FOUND"
    if isinstance(exc, ImportError):
        return "DEPENDENCY_ERROR"
    if isinstance(exc, CancelledError):
        return "CANCELLED"
    return "UNKNOWN_ERROR"


class ExecutionEngine:
    def __init__(self, registry: SkillRegistry, *, autonomy: AutonomyPolicy, authorizations: AuthorizationManager,
                 context_factory: Callable[[Any], SkillContext], bus=None, state=None, audit=None,
                 personality_say: Callable[..., str] | None = None):
        self.registry = registry
        self.autonomy = autonomy
        self.authorizations = authorizations
        self._ctx = context_factory
        self._bus = bus
        self._state = state
        self._audit = audit
        self._say = personality_say

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="execution")

    def context(self, cancel=None) -> SkillContext:
        return self._ctx(cancel)

    def execute(self, action: Action, *, cancel=None, on_authorization: Callable[[str], None] | None = None
                ) -> ExecutionRecord:
        started = time.time()
        skill = self.registry.get(action.skill) if action.skill not in FORBIDDEN else None
        if skill is None:
            return self._finish(ExecutionRecord(action, "refused", SkillResult(
                False, error=f"skill '{action.skill}' não existe ou não é permitida", error_kind="REFUSED"), started=started))
        ok, reason = skill.available()
        if not ok:
            return self._finish(ExecutionRecord(action, "unavailable", SkillResult(
                False, error=f"{skill.name} indisponível: {reason}", error_kind="UNSUPPORTED"), started=started))
        try:
            args = skill.validate(dict(action.args or {}))
        except ValueError as exc:
            return self._finish(ExecutionRecord(action, "refused", SkillResult(
                False, error=f"argumentos inválidos: {exc}", error_kind="INVALID_ARGUMENT"), started=started))
        action.args = args
        try:
            skip_reason = skill.precheck(self._ctx(cancel), args)
        except Exception:
            skip_reason = None
        if skip_reason:
            return self._finish(ExecutionRecord(action, "skipped", SkillResult(
                True, skip_reason, [skip_reason], {"skipped": True}), started=started))
        risk = skill.risk_for(args)
        decision = self.autonomy.decide(risk, reversible=skill.reversible, origin=action.origin)
        record = ExecutionRecord(action, "pending", SkillResult(False), risk.value, started=started)
        if decision.action == "refuse":
            record.status, record.result = "refused", SkillResult(False, error=decision.reason, error_kind="REFUSED")
            return self._finish(record)
        if decision.action == "authorize":
            specific = type(skill).describe_action is not Skill.describe_action
            description = skill.describe_action(args) if specific or not action.description else action.description
            req = self.authorizations.request(description, skill=skill.name, risk=risk.value,
                                              args={k: str(v)[:80] for k, v in args.items()})
            if req.status == "pending":                        # pré-aprovado (sugestão aceita) não pergunta de novo
                if self._state is not None:
                    self._state.set_runtime_state("AWAITING_AUTHORIZATION", description, source="execution")
                if on_authorization is not None:
                    on_authorization(description)
            approved = self.authorizations.wait(req, cancel)
            record.authorization = req.to_dict()
            if not approved:
                record.status = "cancelled" if req.status == "cancelled" else "denied"
                record.result = SkillResult(False, error=f"autorização {req.status}", error_kind="NOT_AUTHORIZED")
                return self._finish(record)
            if self._state is not None:
                self._state.set_runtime_state("EXECUTING", description, source="execution")
        if cancel is not None and getattr(cancel, "cancelled", False):
            record.status, record.result = "cancelled", SkillResult(False, error="cancelado", error_kind="CANCELLED")
            return self._finish(record)
        self._emit(EventType.ACTION_STARTED, id=action.id, skill=skill.name, risk=risk.value,
                   description=action.description or skill.describe_action(args), origin=action.origin,
                   category=skill.category)
        self._emit(EventType.SKILL_ACTIVATED, skill=skill.name, category=skill.category)
        if self._state is not None:
            self._state.update(_source="execution", current_action={
                "id": action.id, "skill": skill.name, "args": {k: str(v)[:60] for k, v in args.items()},
                "description": action.description, "risk": risk.value, "started": time.time()},
                active_skills=[skill.name])
        ctx = self._ctx(cancel)
        call_started = time.perf_counter()
        try:
            result = run_with_timeout(lambda: skill.execute(ctx, **args), skill.timeout)
            if not isinstance(result, SkillResult):
                result = SkillResult(False, error="a skill não devolveu um resultado estruturado",
                                     error_kind="UNKNOWN_ERROR")
        except BaseException as exc:          # a falha de uma skill nunca derruba o núcleo
            kind = classify_exception(exc)
            log.warning("skill %s falhou: %s", skill.name, exc)
            result = SkillResult(False, error=f"{type(exc).__name__}: {exc}"[:400], error_kind=kind)
        result.seconds = round(time.perf_counter() - call_started, 3)
        record.result = result
        record.status = "executed" if result.success else "failed"
        self._emit(EventType.ACTION_FINISHED, id=action.id, skill=skill.name, executed=result.success,
                   error=result.error[:200], error_kind=result.error_kind, seconds=result.seconds)
        self._emit(EventType.SKILL_COMPLETED, skill=skill.name, executed=result.success)
        if not result.success:
            self._emit(EventType.ERROR_DETECTED, skill=skill.name, error=result.error[:300],
                       error_kind=result.error_kind, action_id=action.id)
        return self._finish(record)

    def _finish(self, record: ExecutionRecord) -> ExecutionRecord:
        record.finished = time.time()
        if self._state is not None:
            self._state.update(_source="execution", last_action=record.to_dict()["action"],
                               last_result={"status": record.status, "success": record.result.success,
                                            "result": record.result.result[:300], "error": record.result.error[:300]},
                               current_action=None, active_skills=[])
            if not record.result.success:
                self._state.update(_source="execution", last_error={"skill": record.action.skill,
                                                                    "error": record.result.error[:300],
                                                                    "kind": record.result.error_kind,
                                                                    "at": record.finished})
        if self._audit is not None:
            try:
                self._audit("execution", record.action.skill,
                            f"{record.status}: {record.result.result or record.result.error}"[:400], None)
            except Exception:
                pass
        return record
