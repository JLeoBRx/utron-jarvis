from __future__ import annotations
import threading
from typing import Any

import context_state
import goal_manager
import initiative_engine
import learning_engine
import orchestrator
import permission_engine

from .contracts import RuntimeSnapshot, GoalRequest, InitiativeRequest


class JarvisBrain:
    """Fachada única para o estado cognitivo do J.A.R.V.I.S.

    O Brain coordena os subsistemas; não contém automação de baixo nível.
    A execução continua pertencendo às camadas de ação/orquestração existentes.
    """
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._started = False

    def start(self) -> RuntimeSnapshot:
        with self._lock:
            if not self._started:
                context_state.status()
                goal_manager.summary()
                initiative_engine.status()
                permission_engine.summary()
                learning_engine.initialize()
                self._started = True
            return self.snapshot()

    def stop(self) -> None:
        with self._lock:
            self._started = False

    def snapshot(self) -> RuntimeSnapshot:
        ctx = context_state.snapshot()
        orch = orchestrator.status()
        goal = goal_manager.active()
        perms = permission_engine.summary()
        initiative = initiative_engine.status()
        state = str(orch.get("state") or ctx.get("state") or "IDLE")
        return RuntimeSnapshot(
            state=state,
            assistant_active=bool(ctx.get("assistant_active", False)),
            current_goal=goal,
            orchestrator=orch,
            context=ctx,
            permissions=perms,
            initiative=initiative,
        )

    def create_goal(self, request: GoalRequest | str, **kwargs: Any) -> dict[str, Any]:
        if isinstance(request, str):
            request = GoalRequest(title=request, **kwargs)
        return goal_manager.create(
            request.title,
            request.description,
            request.priority,
            list(request.depends_on),
            request.source,
        )

    def activate_next_goal(self) -> dict[str, Any] | None:
        return goal_manager.activate()

    def checkpoint_goal(self, goal_id: str, **kwargs: Any) -> dict[str, Any] | None:
        return goal_manager.checkpoint(goal_id, **kwargs)

    def finish_goal(self, goal_id: str, result: str = "") -> dict[str, Any] | None:
        return goal_manager.finish(goal_id, result)

    def start_objective(self, objective: str, source: str = "brain") -> dict[str, Any]:
        return orchestrator.start(objective, source=source, context=context_state.snapshot())

    def update_context(self, **kwargs: Any) -> dict[str, Any]:
        if "observation" in kwargs:
            context_state.update_observation(kwargs.pop("observation"), **kwargs)
        else:
            context_state.update_structured(**kwargs)
        return context_state.snapshot()

    def consider(self, request: InitiativeRequest | dict[str, Any]) -> dict[str, Any]:
        candidate = request.__dict__ if isinstance(request, InitiativeRequest) else dict(request)
        return initiative_engine.consider(candidate)

    def recall_strategy(self, goal: str, application: str = "") -> str:
        return learning_engine.prompt_context(goal, application=application)

    def permissions(self) -> dict[str, Any]:
        return permission_engine.summary()

    def set_permission_mode(self, mode: str) -> dict[str, Any]:
        return permission_engine.set_mode(mode)

    def set_initiative_mode(self, mode: str) -> dict[str, Any]:
        return initiative_engine.set_mode(mode)

    def set_initiative_enabled(self, enabled: bool) -> dict[str, Any]:
        return initiative_engine.set_enabled(enabled)
