"""RECOVERY ENGINE — ERRO → DIAGNÓSTICO → PLANO DE RECUPERAÇÃO → NOVA TENTATIVA → VERIFICAÇÃO.

Tipos de erro: TIMEOUT, APPLICATION_ERROR, NETWORK_ERROR, PERMISSION_ERROR,
DEPENDENCY_ERROR, VISION_ERROR, MODEL_ERROR, AUDIO_ERROR, UNKNOWN_ERROR.

Limites (contra loops infinitos e ações duplicadas):

* no máximo ``max_attempts`` recuperações para a mesma ação;
* disjuntor por skill: muitas falhas recentes suspendem novas tentativas dela;
* resultados "não confirmados" nunca disparam repetição;
* erros de permissão e de argumentos nunca são "contornados".

Exemplo (abrir aplicação falhou)::

    1. verificar processo  2. encerrar processo travado  3. aguardar  4. iniciar novamente  5. verificar
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.events import EventType
from .execution import Action, ExecutionRecord

ERROR_TYPES = ("TIMEOUT", "APPLICATION_ERROR", "NETWORK_ERROR", "PERMISSION_ERROR", "DEPENDENCY_ERROR",
               "VISION_ERROR", "MODEL_ERROR", "AUDIO_ERROR", "UNKNOWN_ERROR")

_KIND_TO_TYPE = {
    "TIMEOUT": "TIMEOUT", "APPLICATION_ERROR": "APPLICATION_ERROR", "NOT_RUNNING": "APPLICATION_ERROR",
    "NOT_FOUND": "APPLICATION_ERROR", "FILE_NOT_FOUND": "APPLICATION_ERROR", "SYNTAX_ERROR": "APPLICATION_ERROR",
    "ALREADY_EXISTS": "APPLICATION_ERROR", "NETWORK_ERROR": "NETWORK_ERROR", "PERMISSION_ERROR": "PERMISSION_ERROR",
    "DEPENDENCY_ERROR": "DEPENDENCY_ERROR", "VISION_ERROR": "VISION_ERROR", "MODEL_ERROR": "MODEL_ERROR",
    "AUDIO_ERROR": "AUDIO_ERROR",
}
# Situações que não se resolvem tentando de novo: exigem o usuário.
NON_RECOVERABLE = {"INVALID_ARGUMENT", "AMBIGUOUS", "UNSUPPORTED", "CANCELLED", "NOT_AUTHORIZED", "REFUSED", "BUSY"}


@dataclass
class Diagnosis:
    error_type: str
    cause: str
    recoverable: bool
    evidence: list = field(default_factory=list)
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RecoveryPlan:
    strategy: str
    reason: str
    steps: list = field(default_factory=list)          # [Action]
    retry_original: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"strategy": self.strategy, "reason": self.reason, "retry_original": self.retry_original,
                "steps": [s.to_dict() for s in self.steps]}


class RecoveryEngine:
    def __init__(self, *, bus=None, state=None, max_attempts: int = 2, breaker_failures: int = 4,
                 breaker_window: float = 600.0):
        self._bus = bus
        self._state = state
        self.max_attempts = max_attempts
        self.breaker_failures = breaker_failures
        self.breaker_window = breaker_window
        self._attempts: dict[str, int] = defaultdict(int)
        self._failures: dict[str, deque] = defaultdict(deque)

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="recovery")

    # ------------------------------------------------------------ diagnóstico
    def diagnose(self, record: ExecutionRecord) -> Diagnosis:
        result = record.result
        verification = record.verification
        kind = result.error_kind or ""
        if record.status in ("denied", "cancelled"):
            return Diagnosis("UNKNOWN_ERROR", f"ação {record.status} pelo usuário", False)
        if kind in NON_RECOVERABLE:
            return Diagnosis(_KIND_TO_TYPE.get(kind, "UNKNOWN_ERROR"), result.error or kind, False,
                             data={"kind": kind, **result.data})
        if record.status == "executed" and verification is not None and verification.status == "FAILED":
            error_type = "APPLICATION_ERROR" if record.action.skill.startswith(("app.", "window.")) else "UNKNOWN_ERROR"
            if record.action.skill.startswith("network."):
                error_type = "NETWORK_ERROR"
            return Diagnosis(error_type, f"pós-condição não confirmada: {verification.reason}", True,
                             verification.evidence, {"verification": verification.to_dict()})
        error_type = _KIND_TO_TYPE.get(kind, "UNKNOWN_ERROR")
        if error_type == "PERMISSION_ERROR":
            return Diagnosis(error_type, result.error or "permissão negada", False, result.evidence, result.data)
        return Diagnosis(error_type, result.error or "falha sem detalhes", True, result.evidence, result.data)

    # ------------------------------------------------------------ disjuntor
    def _breaker_open(self, skill: str) -> bool:
        window = self._failures[skill]
        now = time.time()
        while window and now - window[0] > self.breaker_window:
            window.popleft()
        return len(window) >= self.breaker_failures

    def note_failure(self, skill: str) -> None:
        self._failures[skill].append(time.time())

    # ------------------------------------------------------------ planejamento
    def plan(self, record: ExecutionRecord, diagnosis: Diagnosis, *, goal_id: str = "") -> RecoveryPlan | None:
        action = record.action
        key = f"{goal_id}:{action.fingerprint()}"
        self.note_failure(action.skill)
        if not diagnosis.recoverable:
            return None
        if self._breaker_open(action.skill):
            self._emit(EventType.RECOVERY_FINISHED, skill=action.skill, recovered=False,
                       reason="disjuntor aberto: falhas repetidas recentes")
            return None
        if self._attempts[key] >= self.max_attempts:
            return None
        self._attempts[key] += 1
        attempt = self._attempts[key]
        plan = self._strategy(action, diagnosis, attempt)
        if plan is not None:
            self._emit(EventType.RECOVERY_STARTED, skill=action.skill, error_type=diagnosis.error_type,
                       strategy=plan.strategy, attempt=attempt, steps=[s.skill for s in plan.steps])
            if self._state is not None:
                self._state.set_runtime_state("RECOVERY", plan.reason, source="recovery")
        return plan

    def _make(self, skill: str, args: dict, description: str, action: Action) -> Action:
        return Action(skill, args, description, origin="recovery", goal_id=action.goal_id, step_id=action.step_id)

    def _strategy(self, action: Action, diagnosis: Diagnosis, attempt: int) -> RecoveryPlan | None:
        t, skill, args = diagnosis.error_type, action.skill, dict(action.args)
        if skill == "app.open" and t in ("APPLICATION_ERROR", "TIMEOUT"):
            name = args.get("name", "")
            if diagnosis.data.get("kind") == "NOT_FOUND" or "não encontrado" in diagnosis.cause:
                return None
            return RecoveryPlan("restart_application", "a aplicação não abriu corretamente; reiniciando", [
                self._make("app.check", {"name": name}, "verificar processo", action),
                self._make("app.terminate", {"name": name}, f"encerrar {name} travado", action),
                self._make("system.wait", {"seconds": 2}, "aguardar", action),
            ])
        if t == "DEPENDENCY_ERROR" and skill == "dev.run_project":
            diag = (diagnosis.data.get("diagnosis") or {})
            module = diag.get("module") or ""
            if not module:
                return None
            from ..skills.development import MODULE_TO_PACKAGE
            package = MODULE_TO_PACKAGE.get(module.split(".")[0], module.split(".")[0])
            path = args.get("path", "")
            return RecoveryPlan("install_missing_dependency", f"módulo {module} ausente; instalar {package}", [
                self._make("dev.install_dependency", {"path": path, "package": package, "module": module.split(".")[0]},
                           f"instalar {package}", action),
            ])
        if t == "DEPENDENCY_ERROR" and skill == "dev.install_dependency" and diagnosis.data.get("needs_venv"):
            return RecoveryPlan("create_virtualenv", "criar ambiente virtual antes de instalar", [
                self._make("dev.create_venv", {"path": args.get("path", "")}, "criar .venv", action),
            ])
        if t == "NETWORK_ERROR":
            return RecoveryPlan("network_check", "falha de rede; diagnosticando antes de repetir", [
                self._make("network.diagnose", {}, "diagnosticar rede", action),
                self._make("system.wait", {"seconds": 3}, "aguardar", action),
            ])
        if t == "VISION_ERROR" and skill == "vision.inspect_screen":
            return RecoveryPlan("ocr_fallback", "visão indisponível; usando leitura de texto (OCR)", [
                self._make("vision.read_text", {}, "ler texto da tela", action),
            ], retry_original=False)
        if t == "MODEL_ERROR":
            return RecoveryPlan("wait_model", "modelo indisponível momentaneamente; aguardando", [
                self._make("system.wait", {"seconds": 3}, "aguardar o modelo", action),
            ]) if attempt == 1 else None
        if t == "TIMEOUT" and attempt == 1:
            return RecoveryPlan("retry_after_timeout", "tempo esgotado; nova tentativa", [
                self._make("system.wait", {"seconds": 2}, "aguardar", action),
            ])
        if t in ("APPLICATION_ERROR", "UNKNOWN_ERROR") and attempt == 1 and skill.startswith(("window.", "web.")):
            return RecoveryPlan("simple_retry", "nova tentativa após breve espera", [
                self._make("system.wait", {"seconds": 1}, "aguardar", action),
            ])
        return None

    def finished(self, action: Action, recovered: bool, reason: str = "") -> None:
        self._emit(EventType.RECOVERY_FINISHED, skill=action.skill, recovered=recovered, reason=reason[:200])

    def reset_goal(self, goal_id: str) -> None:
        for key in [k for k in self._attempts if k.startswith(f"{goal_id}:")]:
            del self._attempts[key]
