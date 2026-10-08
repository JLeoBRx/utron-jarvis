import os
import threading
import unittest

import helpers

from ultron.cognition.decision_engine import DecisionEngine
from ultron.cognition.goal_manager import GoalManager, InvalidTransition
from ultron.cognition.intent_engine import IntentEngine
from ultron.cognition.planner_engine import PlannerEngine
from ultron.cognition.types import Intent
from ultron.skills.registry import SkillRegistry, load_builtin


class IntentTest(unittest.TestCase):
    def setUp(self):
        self.engine = IntentEngine()

    def test_routing_of_portuguese_commands(self):
        cases = {
            "Ultron, abra o bloco de notas": ("command", "app.open"),
            "quais dispositivos estão na rede": ("command", "network.scan"),
            "diagnostique a rede": ("command", "network.diagnose"),
            "aumente o volume": ("command", "audio.volume"),
            "pode parar": ("cancel", None),
            "fale mais devagar": ("control", None),
        }
        for text, (kind, skill) in cases.items():
            intent = self.engine.classify(text)
            self.assertEqual(intent.kind, kind, text)
            if skill:
                self.assertEqual(intent.skill, skill, text)

    def test_goals_and_templates(self):
        intent = self.engine.classify("Ultron, prepare meu projeto Atlas")
        self.assertEqual((intent.kind, intent.template), ("goal", "prepare_project"))
        self.assertEqual(intent.entities["project"], "Atlas")
        multi = self.engine.classify("abra o chrome e depois pesquise python")
        self.assertEqual(multi.kind, "goal")

    def test_forbidden_goals_are_refused(self):
        for text in ("desative o windows defender", "invada o wifi do vizinho", "crie um keylogger"):
            intent = self.engine.classify(text)
            self.assertEqual(intent.kind, "response", text)
            self.assertIn("Não", intent.response)

    def test_decisions(self):
        decide = DecisionEngine().decide
        self.assertEqual(decide(Intent("command", "x", skill="app.open")).route, "execute")
        self.assertEqual(decide(Intent("goal", "x", template="prepare_project")).route, "plan")
        self.assertEqual(decide(Intent("unknown", "x")).route, "agentic")
        self.assertEqual(decide(Intent("command", "x", skill="fs.delete", ambiguity="Qual pasta?")).route, "ask")
        self.assertEqual(decide(Intent("imagination", "x")).route, "imagine")


class PlannerTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.memory = helpers.make_memory(self.bus, self.state)
        self.registry = load_builtin(SkillRegistry())
        self.planner = PlannerEngine(self.registry, memory=self.memory, bus=self.bus, state=self.state)

    def tearDown(self):
        self.memory.stop()

    def test_prepare_project_becomes_ten_adaptive_tasks(self):
        intent = IntentEngine().classify("Ultron, prepare meu projeto Atlas")
        plan = self.planner.create("g1", intent.goal, intent)
        self.assertEqual(plan.strategy, "template")
        self.assertEqual(len(plan.steps), 10)
        ids = [s.id for s in plan.steps]
        self.assertEqual(ids, ["locate", "env", "deps", "ide", "run", "observe", "diagnose", "fix", "rerun", "verify"])
        by_id = {s.id: s for s in plan.steps}
        self.assertEqual(by_id["diagnose"].when, "if_failed:run")
        self.assertEqual(by_id["fix"].kind, "adapt")
        self.assertEqual(by_id["verify"].kind, "verify_goal")
        self.assertEqual(self.state.get("current_plan")["id"], plan.id, "plano publicado no ULTRON_STATE")

    def test_direct_procedural_and_agentic_strategies(self):
        direct = self.planner.create("g2", "abrir chrome", Intent("command", "abra o chrome", skill="app.open",
                                                                  args={"name": "chrome"}))
        self.assertEqual((direct.strategy, len(direct.steps)), ("direct", 1))
        self.memory.procedural.learn("organizar downloads", [{"skill": "fs.list", "args": {"path": "~/Downloads"},
                                                               "description": "listar"}], success=True)
        learned = self.planner.create("g3", "organizar downloads", Intent("goal", "organizar downloads"))
        self.assertEqual(learned.strategy, "procedural")
        agentic = self.planner.create("g4", "algo inédito", Intent("goal", "algo inédito"))
        self.assertEqual(agentic.strategy, "agentic")


class GoalManagerTest(unittest.TestCase):
    def test_lifecycle_persistence_and_restart(self):
        memory = helpers.make_memory()
        goals = GoalManager(memory.db)
        goal = goals.create("Preparar projeto Atlas")
        self.assertEqual(goal.status, "CREATED")
        for status in ("ANALYZING", "PLANNING", "EXECUTING"):
            goals.transition(goal.id, status)
        with self.assertRaises(InvalidTransition):
            goals.transition(goal.id, "CREATED")
        restarted = GoalManager(memory.db)
        restarted.start()
        self.assertEqual(restarted.get(goal.id).status, "FAILED", "objetivo interrompido por reinício é registrado")
        done = goals.create("outro")
        goals.transition(done.id, "EXECUTING")
        goals.complete(done.id, "ok", confidence=0.9)
        self.assertEqual(goals.get(done.id).status, "COMPLETED")
        memory.stop()


class PrepareProjectEndToEndTest(unittest.TestCase):
    """Fluxo real: localizar → ambiente → dependências → (IDE opcional) → executar (autorizado) → verificar."""

    def test_prepare_real_project(self):
        from ultron.agent.autonomy import AuthorizationManager, AutonomyPolicy
        from ultron.agent.execution import ExecutionEngine
        from ultron.agent.recovery import RecoveryEngine
        from ultron.agent.verification import VerificationEngine
        from ultron.cognition.context_engine import ContextEngine
        from ultron.core.events import EventType
        from ultron.core.orchestrator import Orchestrator
        from ultron.core.runtime import CancellationToken
        from ultron.cognition.types import Command
        from ultron.skills.base import SkillContext
        from ultron.world.world_model import WorldModel

        home = helpers.temp_dir("home-")
        project = home / "Projects" / "Atlas"
        project.mkdir(parents=True)
        (project / "main.py").write_text("print('Atlas OK')\n", encoding="utf-8")
        (project / "requirements.txt").write_text("", encoding="utf-8")       # marcador de projeto Python
        old_home = os.environ.get("HOME"), os.environ.get("USERPROFILE")
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(home)
        try:
            bus, state = helpers.make_bus_state()
            settings = helpers.make_settings()
            memory = helpers.make_memory(bus, state)
            world = WorldModel(helpers.temp_dir() / "w.json", save_delay=0)
            registry = load_builtin(SkillRegistry())
            auth = AuthorizationManager(bus=bus, state=state, timeout_getter=lambda: 10)
            bus.subscribe(EventType.AUTHORIZATION_REQUIRED,
                          lambda e: threading.Timer(0.05, lambda: auth.handle_reply("sim", by="teste")).start())
            executor = ExecutionEngine(registry, autonomy=AutonomyPolicy(lambda: settings), authorizations=auth,
                                       context_factory=lambda c: SkillContext(world=world, memory=memory,
                                                                              settings=settings, cancel=c,
                                                                              extras={"registry": registry}),
                                       bus=bus, state=state, audit=memory.db.audit)
            context = ContextEngine(memory=memory, world=world)
            orchestrator = Orchestrator(
                bus=bus, state=state, memory=memory, goals=GoalManager(memory.db, bus=bus, state=state),
                intents=IntentEngine(), decisions=DecisionEngine(), context=context, reasoning=None,
                planner=PlannerEngine(registry, memory=memory, bus=bus, state=state), executor=executor,
                verifier=VerificationEngine(registry, bus=bus, state=state), recovery=RecoveryEngine(bus=bus, state=state),
                registry=registry, router=None)
            response = orchestrator.handle(Command("Ultron, prepare meu projeto Atlas"), CancellationToken())
            steps = {s["id"]: s for s in state.get("current_plan")["steps"]}
            self.assertEqual(steps["locate"]["status"], "DONE", steps["locate"])
            self.assertEqual(steps["run"]["status"], "DONE", steps["run"])
            self.assertIn("Atlas OK", str(steps["run"]["result"]))
            self.assertTrue(response.success, response.text)
            self.assertTrue(response.verified)
            memory.stop()
        finally:
            for key, value in zip(("HOME", "USERPROFILE"), old_home):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
