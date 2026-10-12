"""ORCHESTRATOR — o fluxo cognitivo de um pedido.

    COMMAND → INTENT → DECISION → GOAL → PLAN → SKILL → EXECUTION → VERIFICATION
            → (RECOVERY → nova tentativa) → RESULT → MEMORY

O orquestrador conduz; cada responsabilidade pertence ao seu módulo. Ele roda no worker
"ai" (nunca na thread da interface) e respeita cancelamento, limites de passos e de
recuperações.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..agent.execution import Action, ExecutionEngine, ExecutionRecord
from ..agent.recovery import RecoveryEngine
from ..agent.verification import VerificationEngine
from ..cognition.context_engine import ContextEngine
from ..cognition.decision_engine import DecisionEngine
from ..cognition.goal_manager import GoalManager, InvalidTransition
from ..cognition.intent_engine import IntentEngine, norm
from ..cognition.planner_engine import PlannerEngine
from ..cognition.reasoning_engine import ReasoningEngine
from ..cognition.types import Command, Intent, Plan, PlanStep
from ..graph.concepts import extract
from ..models.ollama_client import OllamaError
from ..models.router import ModelUnavailable
from ..personality import dialogue, short_for_voice, stylize

log = logging.getLogger("ultron.orchestrator")

MAX_STEPS_PER_GOAL = 30
MAX_RECOVERIES_PER_GOAL = 3
QUESTION_RE = re.compile(r"^(o que|oque|qual|quais|quem|quando|onde|por que|porque|como funciona|explique|explica|"
                         r"me (fale|explique|conte|diga)|conte|defina|diferenca|voce (acha|sabe|conhece)|"
                         r"quanto|sera que|e verdade)\b")
ACTION_HINT_RE = re.compile(r"\b(abr\w*|fech\w*|cri\w*|apag\w*|mov\w*|copi\w*|execut\w*|rod\w*|instal\w*|"
                            r"configur\w*|ativ\w*|desativ\w*|lig\w*|deslig\w*|envi\w*|baix\w*|salv\w*|escrev\w*|"
                            r"digit\w*|clic\w*|organiz\w*)\b")


@dataclass
class Response:
    text: str
    kind: str = "answer"            # answer | result | error | question | refusal | info
    spoken: str = ""
    goal_id: str | None = None
    success: bool | None = None
    verified: bool | None = None
    data: dict = field(default_factory=dict)

    def __post_init__(self):
        self.text = stylize(self.text)
        if not self.spoken:
            self.spoken = short_for_voice(self.text)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe(value: Any, depth: int = 0) -> Any:
    """Cópia JSON-segura e limitada de dados de resultado (para estado, plano e memória)."""
    if depth > 4:
        return str(value)[:200]
    if isinstance(value, dict):
        return {str(k): _safe(v, depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        return [_safe(v, depth + 1) for v in list(value)[:50]]
    if isinstance(value, str):
        return value if len(value) <= 2000 else value[:2000] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:500]


class Orchestrator:
    def __init__(self, *, bus, state, memory, goals: GoalManager, intents: IntentEngine, decisions: DecisionEngine,
                 context: ContextEngine, reasoning: ReasoningEngine, planner: PlannerEngine, executor: ExecutionEngine,
                 verifier: VerificationEngine, recovery: RecoveryEngine, registry, router,
                 control: Callable[[Intent], Response] | None = None,
                 imagine: Callable[[Intent, Any], Response] | None = None,
                 progress: Callable[[str], None] | None = None):
        self.bus = bus
        self.state = state
        self.memory = memory
        self.goals = goals
        self.intents = intents
        self.decisions = decisions
        self.context = context
        self.reasoning = reasoning
        self.planner = planner
        self.executor = executor
        self.verifier = verifier
        self.recovery = recovery
        self.registry = registry
        self.router = router
        self._control = control
        self._imagine = imagine
        self._progress = progress or (lambda text: None)

    # ------------------------------------------------------------ entrada
    def handle(self, command: Command, cancel) -> Response:
        text = command.text
        self.state.set_runtime_state("PERCEIVING", "interpretando pedido", source="orchestrator")
        self.state.set_cognitive_phase("ANALYZING", source="orchestrator")
        self.memory.working.add("input", text, salience=0.6, source=command.source)
        concept_ids = self.link_concepts(text)
        intent = self.intents.classify(text)
        self.state.set_runtime_state("DECIDING", "decidindo o caminho", source="orchestrator")
        decision = self.decisions.decide(intent)
        log.info("intenção %s (%s) → %s", intent.kind, intent.skill or intent.template or "-", decision.route)
        try:
            if decision.route == "respond":
                response = self._direct_response(intent)
            elif decision.route == "cancel":
                response = Response("Não há nada em andamento.", "info")
            elif decision.route == "control":
                response = self._control(intent) if self._control else Response("Controle indisponível.", "error")
            elif decision.route == "ask":
                response = Response(dialogue.say("ambiguous", question=decision.question), "question")
            elif decision.route == "imagine":
                if self._imagine is None:
                    response = Response(dialogue.say("unavailable", module="Imagination Core"), "error")
                else:
                    self.state.set_runtime_state("IMAGINING", "imaginação", source="orchestrator")
                    response = self._imagine(intent, cancel)
            elif decision.route in ("execute", "plan"):
                response = self.run_goal(intent, cancel, concept_ids=concept_ids)
            else:
                response = self._open_request(intent, cancel, concept_ids=concept_ids)
        except ModelUnavailable as exc:
            response = Response(f"Núcleo de linguagem indisponível. {exc}", "error", success=False)
        except OllamaError as exc:
            if exc.kind == "CANCELLED":
                response = Response(dialogue.say("cancelled"), "info", success=False)
            else:
                response = Response(f"O modelo local falhou ({exc.kind}). {exc}", "error", success=False)
        self.memory.working.add("response", response.text, salience=0.5)
        self.state.set_cognitive_phase("", source="orchestrator")
        return response

    # ------------------------------------------------------------ conceitos → grafo (cérebro cresce)
    def link_concepts(self, text: str) -> list[str]:
        self.state.set_cognitive_phase("CONNECTING", source="orchestrator")
        ids = []
        for mention in extract(text, max_items=8):
            try:
                ids.append(self.memory.graph.add_node(mention.type, mention.label).id)
            except (ValueError, KeyError):
                continue
        if ids:
            self.memory.graph.activate(ids, reason="input")
        return ids

    # ------------------------------------------------------------ respostas diretas
    def _direct_response(self, intent: Intent) -> Response:
        if intent.template == "help":
            categories: dict[str, int] = {}
            for skill in self.registry.available():
                categories[skill.category] = categories.get(skill.category, 0) + 1
            return Response(
                "Capacidades ativas: aplicativos e janelas; arquivos; navegador; visão da tela e leitura de texto; "
                "rede local (estado, dispositivos, diagnóstico); projetos Python (preparar, executar, diagnosticar, "
                "corrigir dependências); memória; sistema e energia; imaginação de conceitos, cenários e mundos. "
                f"{len(self.registry.available())} skills disponíveis em {len(categories)} categorias. "
                "Ações sensíveis pedem autorização. Diga 'cancelar' para interromper.", "info")
        return Response(intent.response or dialogue.say("ack"), "answer")

    def _open_request(self, intent: Intent, cancel, *, concept_ids: list[str]) -> Response:
        text = intent.text
        t = norm(text)
        self.state.set_runtime_state("CONTEXT", "recuperando contexto", source="orchestrator")
        ctx = self.context.build(text)
        self.state.set_runtime_state("THINKING", "elaborando resposta", source="orchestrator")
        if QUESTION_RE.search(t) and not ACTION_HINT_RE.search(t):
            answer = self.reasoning.respond(text, ctx, cancel=cancel)
            return Response(answer, "answer")
        return self._agentic_goal(intent, ctx, cancel, concept_ids=concept_ids)

    # ------------------------------------------------------------ objetivos
    def run_goal(self, intent: Intent, cancel, *, concept_ids: list[str] | None = None,
                 source: str = "user") -> Response:
        description = intent.goal or intent.text
        goal = self.goals.create(description, confidence=intent.confidence, source=source)
        self.recovery.reset_goal(goal.id)
        self._safe_transition(goal.id, "ANALYZING")
        if not intent.skill:
            self.state.set_runtime_state("CONTEXT", "recuperando contexto", source="orchestrator")
        ctx = self.context.build(description) if not intent.skill else None
        self._safe_transition(goal.id, "PLANNING")
        self.state.set_runtime_state("PLANNING", description[:80], source="orchestrator")
        plan = self.planner.create(goal.id, description, intent, ctx=ctx, cancel=cancel)
        self.goals.update(goal.id, tasks=[{"id": s.id, "description": s.description, "skill": s.skill}
                                          for s in plan.steps])
        if len(plan.steps) > 1:
            self._progress(dialogue.say("analyzing") if plan.strategy == "agentic" else
                           f"Plano com {len(plan.steps)} etapas.")
        self._safe_transition(goal.id, "EXECUTING")
        outcome = self.run_plan(goal.id, plan, cancel, ctx=ctx)
        return self._conclude(goal.id, plan, outcome, concept_ids or [])

    def _agentic_goal(self, intent: Intent, ctx, cancel, *, concept_ids: list[str]) -> Response:
        holder: dict[str, Any] = {}

        def ensure_goal():
            if "goal" not in holder:
                goal = self.goals.create(intent.text, confidence=0.6, source="user")
                self.recovery.reset_goal(goal.id)
                self._safe_transition(goal.id, "PLANNING")
                self.state.set_runtime_state("PLANNING", intent.text[:80], source="orchestrator")
                plan = Plan(goal.id, intent.text, strategy="agentic")
                self.planner.publish(plan)
                self._safe_transition(goal.id, "EXECUTING")
                holder["goal"], holder["plan"] = goal, plan
            return holder["goal"], holder["plan"]

        def call_tool(name: str, args: dict) -> dict:
            goal, plan = ensure_goal()
            step = plan.add_step(PlanStep(f"{name}", name, dict(args), origin="agent"))
            record = self._execute_step(goal.id, plan, step, cancel)
            if record is None:
                return {"executado": False, "erro": step.result.get("error", "passo não executado")}
            observation = {"executado": record.status in ("executed", "skipped"), "status": step.status,
                           "resultado": record.result.result[:1200], "erro": record.result.error[:300],
                           "verificacao": (record.verification.status if record.verification else "NONE"),
                           "evidencia": [str(e)[:160] for e in (record.verification.evidence if record.verification
                                                                else record.result.evidence)[:4]]}
            if record.status in ("denied", "cancelled"):
                observation["stop"] = "o usuário não autorizou"
            return observation

        tools = self.registry.schemas(names=self.registry.relevant(intent.text, limit=12))
        outcome = self.reasoning.agentic(intent.text, ctx, tools=tools, call_tool=call_tool, cancel=cancel)
        if "goal" not in holder:
            return Response(outcome.answer or dialogue.say("nothing"), "answer")
        goal, plan = holder["goal"], holder["plan"]
        result = self._evaluate(plan)
        response = self._conclude(goal.id, plan, result, concept_ids, agent_answer=outcome.answer)
        return response

    # ------------------------------------------------------------ execução do plano
    def _condition_met(self, plan: Plan, step: PlanStep) -> bool:
        if step.when == "always":
            return True
        kind, _, target_id = step.when.partition(":")
        target = plan.step(target_id)
        if target is None:
            return False
        if kind == "if_failed":
            return target.status == "FAILED"
        if kind == "if_succeeded":
            return target.status in ("DONE", "UNCONFIRMED")
        if kind == "if_executed":
            return target.status in ("DONE", "UNCONFIRMED", "FAILED")
        return False

    def _resolve_args(self, plan: Plan, step: PlanStep) -> dict | None:
        args = dict(step.args)
        for key, ref in (step.args_from or {}).items():
            step_id, _, path = ref.partition(".")
            source = plan.step(step_id)
            value: Any = source.result if source is not None else None
            for part in path.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if value in (None, ""):
                return None
            args[key] = value
        return args

    def _execute_step(self, goal_id: str, plan: Plan, step: PlanStep, cancel) -> ExecutionRecord | None:
        args = self._resolve_args(plan, step)
        if args is None:
            step.status = "FAILED"
            step.result = {"error": "dados de uma etapa anterior não estão disponíveis"}
            self.planner.publish(plan)
            return None
        self.state.update(_source="orchestrator", current_task={"id": step.id, "description": step.description,
                                                                "skill": step.skill},
                          current_subtask={"skill": step.skill, "args": {k: str(v)[:60] for k, v in args.items()}})
        step.status = "RUNNING"
        step.attempts += 1
        self.planner.publish(plan)
        self.state.set_runtime_state("EXECUTING", step.description, source="orchestrator")
        self.state.set_cognitive_phase("EXECUTING", source="orchestrator")
        action = Action(step.skill or "", args, step.description, origin=step.origin, goal_id=goal_id, step_id=step.id)
        record = self.executor.execute(action, cancel=cancel, on_authorization=self._announce_authorization)
        self._safe_transition(goal_id, "VERIFYING")
        self.state.set_runtime_state("VERIFYING", step.description, source="orchestrator")
        verification = self.verifier.verify(record, self.executor.context(cancel))
        step.result = {"status": record.status, "result": record.result.result[:1500],
                       "error": record.result.error[:400], "error_kind": record.result.error_kind,
                       "data": _safe(record.result.data)}
        step.verification = verification.to_dict()
        if verification.status == "VERIFIED":
            step.status = "DONE"
        elif verification.status == "UNCONFIRMED" and record.status == "executed" and record.result.success:
            step.status = "UNCONFIRMED"
        elif record.status in ("denied", "cancelled"):
            step.status = "CANCELLED"
        else:
            step.status = "FAILED"
        self.goals.update(goal_id, evidence={"step": step.description, "status": step.status,
                                             "reason": verification.reason[:200]})
        self._safe_transition(goal_id, "EXECUTING")
        self.planner.publish(plan)
        return record

    def run_plan(self, goal_id: str, plan: Plan, cancel, *, ctx=None) -> dict[str, Any]:
        plan.status = "EXECUTING"
        executed = recoveries = 0
        index = 0
        stop_reason = ""
        while index < len(plan.steps):
            step = plan.steps[index]
            index += 1
            if step.status != "PENDING":
                continue
            if cancel is not None and getattr(cancel, "cancelled", False):
                stop_reason = "cancelado"
                break
            if not self._condition_met(plan, step):
                step.status = "SKIPPED"
                self.planner.publish(plan)
                continue
            if executed >= MAX_STEPS_PER_GOAL:
                stop_reason = "limite seguro de etapas atingido"
                break
            if step.kind == "agentic":
                self._run_agentic_step(goal_id, plan, step, ctx, cancel)
                executed += 1
                continue
            if step.kind == "adapt":
                step.status = "SKIPPED"
                continue
            if step.kind == "verify_goal":
                self._verify_goal(plan, step)
                continue
            record = self._execute_step(goal_id, plan, step, cancel)
            executed += 1
            if record is None:
                if not step.optional:
                    stop_reason = step.result.get("error", "falha")
                    break
                continue
            if step.status == "CANCELLED":
                stop_reason = "não autorizado" if record.status == "denied" else "cancelado"
                break
            if step.status == "FAILED":
                if step.recover and recoveries < MAX_RECOVERIES_PER_GOAL:
                    diagnosis = self.recovery.diagnose(record)
                    rplan = self.recovery.plan(record, diagnosis, goal_id=goal_id)
                    if rplan is not None:
                        recoveries += 1
                        self._safe_transition(goal_id, "RECOVERING")
                        self._progress(dialogue.say("failed_retry"))
                        self.planner.insert_recovery(plan, step, rplan)
                        self._safe_transition(goal_id, "EXECUTING")
                        continue
                handled_later = any(s.when == f"if_failed:{step.id}" for s in plan.steps)
                if not step.optional and not handled_later:
                    stop_reason = record.result.error or "uma etapa obrigatória falhou"
                    break
            else:
                self.planner.adapt(plan, step, record)
        for step in plan.steps:
            if step.status == "PENDING":
                step.status = "CANCELLED" if stop_reason else "SKIPPED"
        result = self._evaluate(plan, stop_reason)
        plan.status = "DONE" if result["success"] else ("CANCELLED" if result["cancelled"] else "FAILED")
        self.planner.publish(plan)
        return result

    def _run_agentic_step(self, goal_id: str, plan: Plan, step: PlanStep, ctx, cancel) -> None:
        step.status = "RUNNING"
        self.planner.publish(plan)
        context = ctx or self.context.build(plan.goal_text)

        def call_tool(name: str, args: dict) -> dict:
            sub = plan.add_step(PlanStep(name, name, dict(args), origin="agent"), after=step.id)
            record = self._execute_step(goal_id, plan, sub, cancel)
            if record is None:
                return {"executado": False, "erro": sub.result.get("error", "")}
            obs = {"executado": record.status in ("executed", "skipped"), "status": sub.status,
                   "resultado": record.result.result[:1200], "erro": record.result.error[:300],
                   "verificacao": record.verification.status if record.verification else "NONE"}
            if record.status in ("denied", "cancelled"):
                obs["stop"] = "o usuário não autorizou"
            return obs

        tools = self.registry.schemas(names=self.registry.relevant(plan.goal_text, limit=12))
        outcome = self.reasoning.agentic(plan.goal_text, context, tools=tools, call_tool=call_tool, cancel=cancel)
        step.result = {"result": outcome.answer[:1500], "calls": len(outcome.calls), "stopped": outcome.stopped}
        step.status = "DONE" if not outcome.stopped else "FAILED"
        self.planner.publish(plan)

    def _verify_goal(self, plan: Plan, step: PlanStep) -> None:
        targets = [plan.step(t) for t in step.args.get("targets", [])]
        target = next((t for t in targets if t is not None and t.status in ("DONE", "UNCONFIRMED", "FAILED")), None)
        if target is None:
            step.status = "SKIPPED"
            step.result = {"result": "nada a verificar"}
        else:
            step.status = target.status
            step.verification = dict(target.verification)
            step.result = {"result": f"{target.description}: {target.status}",
                           "error": target.result.get("error", "")}
        self.planner.publish(plan)

    def _evaluate(self, plan: Plan, stop_reason: str = "") -> dict[str, Any]:
        steps = [s for s in plan.steps if s.kind != "adapt"]
        ran = [s for s in steps if s.status in ("DONE", "UNCONFIRMED", "FAILED")]
        blocking = [s for s in steps if s.status == "FAILED" and not s.optional and s.origin != "agent"]
        final = next((s for s in reversed(steps) if s.kind == "verify_goal"), None)
        final_ok = final is None or final.status not in ("FAILED", "CANCELLED")
        agentic_ok = not any(s.kind == "agentic" and s.status == "FAILED" for s in steps)
        agent_actions = [s for s in steps if s.origin == "agent" and s.skill]
        if agent_actions and agent_actions[-1].status == "FAILED":
            agentic_ok = False
        cancelled = bool(stop_reason) and any(s.status == "CANCELLED" for s in steps)
        success = bool(ran) and not blocking and final_ok and agentic_ok and not stop_reason
        unconfirmed = [s.description for s in ran if s.status == "UNCONFIRMED"]
        verified = success and not unconfirmed
        confidences = [float(s.verification.get("confidence", 0.0)) for s in ran if s.verification]
        return {"success": success, "verified": verified, "cancelled": cancelled, "stop_reason": stop_reason,
                "confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
                "failed": [s.description for s in steps if s.status == "FAILED"], "unconfirmed": unconfirmed,
                "completed": [s.description for s in steps if s.status == "DONE" and s.skill]}

    # ------------------------------------------------------------ conclusão
    def _conclude(self, goal_id: str, plan: Plan, outcome: dict[str, Any], concept_ids: list[str], *,
                  agent_answer: str = "") -> Response:
        steps = [s for s in plan.steps if s.skill or s.kind == "verify_goal"]
        last_ok = next((s for s in reversed(steps) if s.status in ("DONE", "UNCONFIRMED") and s.skill), None)
        extra: dict[str, Any] = {}
        if outcome["success"]:
            if agent_answer:
                text = agent_answer
            elif len([s for s in steps if s.skill]) <= 1 and last_ok is not None:
                text = last_ok.result.get("result") or dialogue.say("done")
            else:
                done = sum(1 for s in steps if s.status == "DONE")
                text = f"{dialogue.say('done')} {done} etapa(s) verificada(s)."
                if last_ok is not None and last_ok.result.get("result"):
                    text += " " + str(last_ok.result["result"])[:300]
            if outcome["unconfirmed"]:
                text += " Sem confirmação independente: " + ", ".join(outcome["unconfirmed"][:3]) + "."
            side_failures = [s for s in plan.steps if s.status == "FAILED" and s.optional and s.skill
                             and not any(t.when == f"if_failed:{s.id}" for t in plan.steps)]
            for failed_step in side_failures[:2]:
                text += f" Etapa não crítica falhou — {failed_step.description}: {failed_step.result.get('error', '')[:120]}."
            self._safe_complete(goal_id, text, outcome["confidence"])
            kind = "result"
            clarify = (last_ok.result.get("data") or {}) if last_ok is not None else {}
            if clarify.get("clarify"):                  # a skill pediu esclarecimento: nada foi gravado
                kind = "question"
                extra = {"clarify": {"skill": last_ok.skill, "pending": clarify.get("pending") or {},
                                     "candidates": clarify.get("candidates") or []}}
        elif outcome["cancelled"]:
            blocked = next((s for s in plan.steps if s.status == "CANCELLED" and s.result), None)
            if "autoriz" in outcome["stop_reason"]:
                text = f"Não autorizado{': ' + blocked.description if blocked else ''}. Essa ação não foi executada."
            else:
                text = dialogue.say("cancelled")
            if outcome["completed"]:
                text += f" Etapas já concluídas: {', '.join(outcome['completed'][:4])}."
            self.goals.cancel(goal_id, outcome["stop_reason"] or "cancelado")
            kind = "info"
        else:
            failed = next((s for s in plan.steps if s.status == "FAILED"), None)
            reason = (failed.result.get("error") if failed else "") or outcome["stop_reason"] or "falha não identificada"
            reason = reason[:1].upper() + reason[1:]
            if failed is not None and len([s for s in steps if s.skill]) > 1:
                text = f"{dialogue.say('failed')} Etapa “{failed.description}”: {reason}"
            else:
                text = f"{dialogue.say('failed')} {reason}"
            if agent_answer and agent_answer not in text:
                text += " " + agent_answer
            try:
                self.goals.fail(goal_id, reason[:300])
            except InvalidTransition:
                pass
            kind = "error"
        self._learn(goal_id, plan, outcome, concept_ids)
        return Response(text, kind, goal_id=goal_id, success=outcome["success"], verified=outcome["verified"],
                        data={"plan": plan.id, "strategy": plan.strategy, "confidence": outcome["confidence"],
                              **extra})

    def _learn(self, goal_id: str, plan: Plan, outcome: dict[str, Any], concept_ids: list[str]) -> None:
        actions = [{"skill": s.skill, "args": _safe(s.args), "status": s.status, "description": s.description}
                   for s in plan.steps if s.skill]
        self.memory.record_episode("goal", plan.goal_text, goal_id=goal_id, actions=actions,
                                   outcome="concluído" if outcome["success"] else
                                   ("cancelado" if outcome["cancelled"] else "falhou: " + outcome["stop_reason"][:200]),
                                   success=outcome["success"],
                                   evidence=[s.verification.get("reason", "") for s in plan.steps if s.verification][:10],
                                   importance=0.7 if not outcome["success"] else 0.5)
        if outcome["success"] and outcome["verified"] and plan.strategy in ("llm", "agentic"):
            learned = [{"skill": s.skill, "args": _safe(s.args), "description": s.description}
                       for s in plan.steps if s.skill and s.status == "DONE" and s.origin != "recovery"]
            if learned:
                self.memory.procedural.learn(plan.goal_text, learned, success=True)
        graph = self.memory.graph
        skill_ids = []
        for s in plan.steps:
            if s.skill and s.status in ("DONE", "UNCONFIRMED", "FAILED"):
                try:
                    node = graph.add_node("SKILL", s.skill, {"category": s.skill.split(".")[0]})
                    skill_ids.append(node.id)
                    edge = "LEARNED" if s.status == "DONE" else "RELATED"
                    for cid in concept_ids[:4]:
                        graph.connect(cid, node.id, edge, delta=0.1)
                except (ValueError, KeyError):
                    continue
        for s in plan.steps:
            if s.skill == "dev.locate_project" and s.status == "DONE":
                project = (s.result.get("data") or {}).get("project") or {}
                if project.get("name"):
                    try:
                        node = graph.add_node("PROJECT", project["name"], {"path": project.get("path", "")})
                        for cid in concept_ids[:4] + skill_ids[:6]:
                            graph.connect(node.id, cid, "USED_WITH", delta=0.08)
                    except (ValueError, KeyError):
                        pass
            if s.skill == "dev.diagnose_error" and s.status == "DONE":
                diag = (s.result.get("data") or {}).get("diagnosis") or {}
                if diag.get("type"):
                    try:
                        err = graph.add_node("CONCEPT", f"Erro {diag['type']}", {"message": diag.get("message", "")[:120]})
                        fix = next((x for x in plan.steps if x.skill == "dev.install_dependency" and x.status == "DONE"), None)
                        if fix is not None:
                            sol = graph.add_node("MEMORY", f"Solução: instalar {fix.args.get('package')}",
                                                 {"goal": plan.goal_text[:120]})
                            graph.connect(err.id, sol.id, "LEARNED", delta=0.2)
                    except (ValueError, KeyError):
                        pass
        if len(skill_ids) > 1:
            graph.activate(skill_ids, reason="plan")

    # ------------------------------------------------------------ utilidades
    def _announce_authorization(self, description: str) -> None:
        self._progress(dialogue.say("auth_request", action=description))

    def _safe_transition(self, goal_id: str, status: str) -> None:
        try:
            self.goals.transition(goal_id, status)
        except (InvalidTransition, KeyError):
            pass

    def _safe_complete(self, goal_id: str, text: str, confidence: float) -> None:
        try:
            self.goals.complete(goal_id, text[:500], confidence=confidence)
        except InvalidTransition:
            try:
                self.goals.transition(goal_id, "EXECUTING")
                self.goals.complete(goal_id, text[:500], confidence=confidence)
            except (InvalidTransition, KeyError):
                pass
