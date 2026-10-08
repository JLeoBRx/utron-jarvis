"""J.A.R.V.I.S. // AUTONOMOUS AGENT RUNTIME

Orquestrador central da missão. Une percepção, World Model, roteamento,
execução e verificação sem substituir as camadas especializadas.

O Runtime é um coordenador: não concede novas permissões e não executa
shell arbitrário. A execução continua passando pelo execution_loop/tools.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, asdict


@dataclass
class RuntimeSnapshot:
    status: str = "IDLE"
    mission_id: str = ""
    objective: str = ""
    cycle: int = 0
    started: float = 0.0
    last_observation: float = 0.0
    last_verification: str = ""
    route: str = ""
    error: str = ""

    def to_dict(self):
        return asdict(self)


_LOCK = threading.RLock()
_ACTIVE = False
_SNAPSHOT = RuntimeSnapshot()


def active() -> bool:
    with _LOCK:
        return _ACTIVE


def snapshot() -> dict:
    with _LOCK:
        return _SNAPSHOT.to_dict()


def _set(**changes):
    with _LOCK:
        for key, value in changes.items():
            if hasattr(_SNAPSHOT, key):
                setattr(_SNAPSHOT, key, value)
        return _SNAPSHOT.to_dict()


def _emit(emit, kind, **data):
    if emit:
        try:
            emit(kind, **data)
        except Exception:
            pass


def observe_now(*, emit=None):
    """Obtém uma percepção estrutural/visual atual sem executar ações."""
    _set(last_observation=time.time())
    try:
        import windows_state_adapter
        windows = windows_state_adapter.snapshot(include_windows=True)
    except Exception as exc:
        windows = {"available": False, "error": str(exc)[:180]}

    package = {"timestamp": time.time(), "windows_state": windows, "runtime_observation": True}
    try:
        import world_model
        world_model.update(package)
        if windows:
            world_model.update_windows_state(windows)
        package["world_model"] = world_model.snapshot()
    except Exception as exc:
        package["world_model_error"] = str(exc)[:180]

    _emit(emit, "observation", package=package)
    return package


def run(goal, conversation, *, context=None, on_execute=None, on_error=None,
        on_thinking=None, on_timeline=None, on_log=None,
        on_verification=None, on_recovery=None, max_replans=2):
    """Executa uma missão através do único ciclo operacional do JARVIS."""
    global _ACTIVE, _SNAPSHOT
    with _LOCK:
        if _ACTIVE:
            return "Senhor, já existe uma missão em execução."
        _ACTIVE = True
        _SNAPSHOT = RuntimeSnapshot(
            status="STARTING", objective=str(goal), started=time.time(), cycle=0
        )

    on_timeline = on_timeline or (lambda *a, **k: None)
    on_log = on_log or (lambda *a, **k: None)
    on_verification = on_verification or (lambda *a, **k: None)
    on_recovery = on_recovery or (lambda *a, **k: None)

    try:
        _set(status="PERCEIVING", cycle=1)
        observe_now(emit=lambda k, **d: _emit(None, k, **d))
        on_timeline("observe", "runtime", "Estado inicial da missão capturado.")

        _set(status="ROUTING")
        import human_in_loop
        auth = human_in_loop.classify(goal)
        _emit(on_log, "authorization", authorization=auth.to_dict())
        if auth.mode == "BLOCK":
            _set(status="WAITING", error=auth.reason)
            on_timeline("pause", "human-in-loop", "Missão bloqueada pela política de segurança.")
            return "Senhor, esta missão foi bloqueada pela política de segurança."
        import intelligence_router
        route_decision = intelligence_router.decide(goal, context or {})
        _set(route=getattr(route_decision, "route", ""), status="PLANNING")
        on_log("Runtime: rota de inteligência selecionada.")

        import execution_loop

        def timeline(kind, subject, message):
            state_map = {
                "plan": "PLANNING", "validate": "EXECUTING",
                "observe": "VERIFYING", "verification": "VERIFYING",
                "error": "RECOVERY", "recovery": "RECOVERY",
                "pause": "WAITING", "done": "DONE",
            }
            _set(status=state_map.get(kind, "EXECUTING"), cycle=_SNAPSHOT.cycle + 1)
            on_timeline(kind, subject, message)

        def execute(*args, **kwargs):
            _set(status="EXECUTING")
            if on_execute:
                return on_execute(*args, **kwargs)
            return None

        def error(*args, **kwargs):
            _set(status="RECOVERY")
            if on_error:
                return on_error(*args, **kwargs)
            return None

        def thinking(*args, **kwargs):
            _set(status="PLANNING")
            return on_thinking(*args, **kwargs) if on_thinking else None

        def verification(info):
            status = str((info or {}).get("status", "UNKNOWN"))
            _set(status="VERIFYING", last_verification=status)
            on_verification(info)

        def recovery(info):
            _set(status="RECOVERY")
            on_recovery(info)

        runtime_context = dict(context or {})
        runtime_context["authorization"] = auth.to_dict()
        result = execution_loop.run(
            goal, conversation,
            on_execute=execute,
            on_error=error,
            on_thinking=thinking,
            on_timeline=timeline,
            on_log=on_log,
            on_verification=verification,
            on_recovery=recovery,
            max_replans=max_replans,
            context=runtime_context,
        )

        _set(status="VERIFYING", cycle=_SNAPSHOT.cycle + 1)
        observe_now(emit=None)
        _set(status="DONE")
        on_timeline("done", "runtime", "Ciclo da missão encerrado.")
        return result
    except Exception as exc:
        _set(status="ERROR", error=str(exc)[:500])
        on_timeline("error", "runtime", str(exc)[:180])
        raise
    finally:
        with _LOCK:
            _ACTIVE = False


class Runtime:
    """Interface orientada a objeto para o mesmo Runtime global."""
    def run(self, goal, conversation, **kwargs):
        return run(goal, conversation, **kwargs)

    def observe(self, **kwargs):
        return observe_now(**kwargs)

    def snapshot(self):
        return snapshot()
