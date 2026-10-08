"""VERIFICATION ENGINE — execução → observação → verificação → resultado.

Exemplo (abrir o VS Code)::

    EXECUTION      processo iniciado
    VERIFICATION   janela detectada · processo vivo · aplicação respondendo
    RESULT         VERIFIED

A verificação chama ``skill.verify`` — que observa o mundo de novo — e nunca aceita o texto
da execução como prova. ``UNCONFIRMED`` não dispara nova tentativa (evita ação duplicada).
"""
from __future__ import annotations

import logging
from typing import Any

from ..core.events import EventType
from ..core.runtime import run_with_timeout
from ..skills.base import VerificationResult
from ..skills.registry import SkillRegistry
from .execution import ExecutionRecord

log = logging.getLogger("ultron.verification")


class VerificationEngine:
    def __init__(self, registry: SkillRegistry, *, bus=None, state=None, timeout: float = 30.0):
        self.registry = registry
        self._bus = bus
        self._state = state
        self.timeout = timeout

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="verification")

    def verify(self, record: ExecutionRecord, ctx) -> VerificationResult:
        skill = self.registry.get(record.action.skill)
        self._emit(EventType.VERIFICATION_STARTED, action_id=record.action.id, skill=record.action.skill)
        if self._state is not None:
            self._state.set_cognitive_phase("VERIFYING", source="verification")
        if record.status == "skipped":
            result = VerificationResult("VERIFIED", 0.9, [{"name": "precondition", "passed": True,
                                                            "detail": record.result.result}],
                                        record.result.evidence, "nada a fazer: a condição já estava satisfeita")
        elif record.status != "executed" or skill is None:
            result = VerificationResult("FAILED", 0.95, [], record.result.evidence,
                                        record.result.error or f"ação não executada ({record.status})")
        else:
            try:
                result = run_with_timeout(lambda: skill.verify(ctx, record.action.args, record.result),
                                          max(self.timeout, skill.timeout / 2))
            except TimeoutError:
                result = VerificationResult("UNCONFIRMED", 0.3, [], record.result.evidence,
                                            "a verificação excedeu o tempo limite")
            except Exception as exc:
                log.warning("verificação de %s falhou: %s", record.action.skill, exc)
                result = VerificationResult("UNCONFIRMED", 0.3, [], record.result.evidence,
                                            f"a verificação falhou: {exc}")
        record.verification = result
        payload = {"action_id": record.action.id, "skill": record.action.skill, "status": result.status,
                   "confidence": round(result.confidence, 3), "reason": result.reason[:200],
                   "checks": result.checks[:6]}
        if result.status == "VERIFIED":
            self._emit(EventType.VERIFICATION_SUCCESS, **payload)
        elif result.status == "FAILED":
            self._emit(EventType.VERIFICATION_FAILED, **payload)
        else:
            self._emit(EventType.VERIFICATION_UNCONFIRMED, **payload)
        if self._state is not None:
            self._state.update(_source="verification", confidence=float(result.confidence))
        return result
