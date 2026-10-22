"""PLANNER ENGINE — planejamento adaptativo.

Origem do plano, por ordem de preferência:

1. comando direto → plano de um passo;
2. template conhecido (ex.: "Prepare meu projeto");
3. procedimento aprendido (memória procedural com boa taxa de sucesso);
4. plano proposto pelo modelo local, validado passo a passo contra o registro de skills;
5. passo agêntico (o modelo escolhe ferramentas uma a uma, com verificação de cada uma).

O plano é vivo: passos são adicionados, removidos, reordenados e substituídos durante a
execução (``adapt``), inclusive para inserir planos de recuperação.

"Prepare meu projeto" vira::

    GOAL  Preparar projeto
     1 localizar projeto        6 observar a saída
     2 verificar ambiente       7 diagnosticar          (se a execução falhar)
     3 verificar dependências   8 corrigir              (se houver correção automática segura)
     4 abrir IDE                9 executar novamente    (se a execução falhar)
     5 executar                10 verificar resultado
"""
from __future__ import annotations

import logging

from ..core.events import EventType
from ..skills.registry import SkillRegistry
from .types import Intent, Plan, PlanStep

log = logging.getLogger("ultron.planner")


def _bind(step_id: str) -> str:
    return f"{step_id}.data.path"


def template_steps(name: str, intent: Intent) -> list[PlanStep]:
    project = (intent.entities or {}).get("project")
    locate_args = {"name": project} if project else {}
    if name == "prepare_project":
        return [
            PlanStep("localizar projeto", "dev.locate_project", locate_args, id="locate"),
            PlanStep("verificar ambiente", "dev.inspect_environment", args_from={"path": _bind("locate")}, id="env"),
            PlanStep("verificar dependências", "dev.check_dependencies", args_from={"path": _bind("locate")}, id="deps"),
            PlanStep("abrir IDE", "app.open", {"name": "visual studio code"}, args_from={"path": _bind("locate")},
                     id="ide", optional=True),
            PlanStep("executar", "dev.run_project", args_from={"path": _bind("locate")}, id="run", optional=True,
                     recover=False),
            PlanStep("observar a saída", "dev.diagnose_error", id="observe", when="if_executed:run", optional=True),
            PlanStep("diagnosticar falha", "dev.diagnose_error", id="diagnose", when="if_failed:run", optional=True),
            PlanStep("corrigir", None, kind="adapt", id="fix", when="if_failed:run", optional=True),
            PlanStep("executar novamente", "dev.run_project", args_from={"path": _bind("locate")}, id="rerun",
                     when="if_failed:run", optional=True, recover=False),
            PlanStep("verificar resultado", None, kind="verify_goal", id="verify", args={"targets": ["rerun", "run"]}),
        ]
    if name == "run_project":
        return [
            PlanStep("localizar projeto", "dev.locate_project", locate_args, id="locate"),
            PlanStep("verificar ambiente", "dev.inspect_environment", args_from={"path": _bind("locate")}, id="env"),
            PlanStep("executar", "dev.run_project", args_from={"path": _bind("locate")}, id="run"),
        ]
    if name == "open_project":
        return [
            PlanStep("localizar projeto", "dev.locate_project", locate_args, id="locate"),
            PlanStep("abrir no VS Code", "app.open", {"name": "visual studio code"}, args_from={"path": _bind("locate")},
                     id="ide"),
        ]
    if name == "check_project":
        return [
            PlanStep("localizar projeto", "dev.locate_project", locate_args, id="locate"),
            PlanStep("verificar ambiente", "dev.inspect_environment", args_from={"path": _bind("locate")}, id="env"),
            PlanStep("verificar dependências", "dev.check_dependencies", args_from={"path": _bind("locate")}, id="deps"),
        ]
    raise KeyError(f"template desconhecido: {name}")


TEMPLATES = ("prepare_project", "run_project", "open_project", "check_project")


class PlannerEngine:
    def __init__(self, registry: SkillRegistry, *, reasoning=None, memory=None, bus=None, state=None):
        self.registry = registry
        self.reasoning = reasoning
        self.memory = memory
        self._bus = bus
        self._state = state

    def _publish(self, plan: Plan, *, created: bool) -> None:
        if self._bus is not None:
            self._bus.publish(EventType.PLAN_CREATED if created else EventType.PLAN_UPDATED,
                              {"plan_id": plan.id, "goal_id": plan.goal_id, "strategy": plan.strategy,
                               "revision": plan.revision, "steps": [
                                   {"id": s.id, "description": s.description, "skill": s.skill, "status": s.status}
                                   for s in plan.steps]}, source="planner")
        if self._state is not None:
            self._state.update(_source="planner", current_plan=plan.to_dict())

    def publish(self, plan: Plan) -> None:
        self._publish(plan, created=False)

    # ------------------------------------------------------------ criação
    def create(self, goal_id: str, goal_text: str, intent: Intent, *, ctx=None, cancel=None) -> Plan:
        if self._state is not None:
            self._state.set_cognitive_phase("PLANNING", source="planner")
        plan = Plan(goal_id, goal_text)
        if intent.skill:
            plan.strategy = "direct"
            plan.steps = [PlanStep(intent.text[:120] or intent.skill, intent.skill, dict(intent.args),
                                   origin="user" if intent.source != "automation" else "automation")]
        elif intent.template in TEMPLATES:
            plan.strategy, plan.template = "template", intent.template
            plan.steps = template_steps(intent.template, intent)
        else:
            learned = self.memory.procedural.match(goal_text) if self.memory is not None else None
            if learned is not None:
                plan.strategy = "procedural"
                plan.steps = [PlanStep(s.get("description") or s["skill"], s["skill"], dict(s.get("args") or {}))
                              for s in learned.steps if self.registry.get(s.get("skill", ""))]
                plan.history.append({"revision": 0, "change": "procedimento aprendido", "procedure": learned.id})
            if not plan.steps and self.reasoning is not None and ctx is not None:
                plan.steps = self._llm_steps(goal_text, ctx, cancel)
                if plan.steps:
                    plan.strategy = "llm"
            if not plan.steps:
                plan.strategy = "agentic"
                plan.steps = [PlanStep(goal_text[:160], None, kind="agentic", origin="agent")]
        self._publish(plan, created=True)
        return plan

    def _llm_steps(self, goal_text: str, ctx, cancel) -> list[PlanStep]:
        try:
            data = self.reasoning.plan(goal_text, ctx, self.registry.catalog_text(), cancel=cancel)
        except Exception as exc:          # modelo indisponível: o passo agêntico informará
            log.info("plano via modelo indisponível: %s", exc)
            return []
        steps: list[PlanStep] = []
        for raw in (data or {}).get("steps", [])[:8]:
            if not isinstance(raw, dict):
                continue
            skill = self.registry.get(str(raw.get("skill", "")))
            if skill is None or not skill.available()[0] or not skill.expose_to_llm:
                continue                  # reservadas a pedidos diretos (ex.: mover o robô) não entram no plano
            try:
                args = skill.validate(dict(raw.get("args") or {}))
            except ValueError:
                continue
            steps.append(PlanStep(str(raw.get("description") or skill.name)[:160], skill.name, args, origin="plan"))
        return steps

    # ------------------------------------------------------------ adaptação durante a execução
    def adapt(self, plan: Plan, step: PlanStep, record) -> list[PlanStep]:
        """Ajusta o plano conforme o resultado de um passo. Devolve passos inseridos."""
        inserted: list[PlanStep] = []
        data = record.result.data if record is not None else {}
        if step.skill == "dev.check_dependencies" and data.get("missing"):
            path = (plan.step("locate").result.get("data", {}) if plan.step("locate") else {}).get("path")
            if path and data.get("venv"):
                for package in data["missing"][:5]:
                    new = PlanStep(f"instalar dependência {package}", "dev.install_dependency",
                                   {"path": path, "package": package}, optional=True, origin="plan")
                    plan.add_step(new, after=step.id)
                    inserted.append(new)
            elif path and not data.get("venv"):
                venv = PlanStep("criar ambiente virtual", "dev.create_venv", {"path": path}, optional=True, origin="plan")
                plan.add_step(venv, after=step.id)
                inserted.append(venv)
                previous = venv
                for package in data["missing"][:5]:
                    new = PlanStep(f"instalar dependência {package}", "dev.install_dependency",
                                   {"path": path, "package": package}, optional=True, origin="plan")
                    plan.add_step(new, after=previous.id)
                    previous = new
                    inserted.append(new)
        if step.id == "diagnose" and record is not None:
            diagnosis = data.get("diagnosis") or {}
            fix = plan.step("fix")
            path = (plan.step("locate").result.get("data", {}) if plan.step("locate") else {}).get("path")
            if fix is not None and fix.status == "PENDING":
                if diagnosis.get("category") == "DEPENDENCY_ERROR" and diagnosis.get("module") and path:
                    package = diagnosis.get("package") or diagnosis["module"].split(".")[0]
                    plan.replace_step("fix", PlanStep(f"instalar {package}", "dev.install_dependency",
                                                      {"path": path, "package": package,
                                                       "module": diagnosis["module"].split(".")[0]},
                                                      id="fix", when="if_failed:run", optional=True))
                else:
                    fix.status = "SKIPPED"
                    fix.result = {"result": "não há correção automática segura para este erro; requer o usuário",
                                  "diagnosis": diagnosis}
                    rerun = plan.step("rerun")
                    if rerun is not None and rerun.status == "PENDING":
                        rerun.status = "SKIPPED"
        if inserted or step.id == "diagnose":
            self._publish(plan, created=False)
        return inserted

    def insert_recovery(self, plan: Plan, failed: PlanStep, recovery) -> list[PlanStep]:
        """Insere os passos de um plano de recuperação e a nova tentativa do passo que falhou."""
        inserted: list[PlanStep] = []
        anchor = failed.id
        for action in recovery.steps:
            step = PlanStep(action.description or action.skill, action.skill, dict(action.args), origin="recovery",
                            optional=True)
            plan.add_step(step, after=anchor)
            inserted.append(step)
            anchor = step.id
        if recovery.retry_original and failed.skill:
            retry = PlanStep(f"{failed.description} (nova tentativa)", failed.skill, dict(failed.args),
                             args_from=dict(failed.args_from), optional=failed.optional, origin=failed.origin)
            retry.attempts = failed.attempts
            plan.add_step(retry, after=anchor)
            inserted.append(retry)
        plan.history.append({"revision": plan.revision, "change": "recovery", "strategy": recovery.strategy})
        self._publish(plan, created=False)
        return inserted
