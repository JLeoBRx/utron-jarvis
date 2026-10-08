import threading
import time
import unittest

import helpers

from ultron.agent.autonomy import AuthorizationManager, AutonomyPolicy, classify_reply
from ultron.agent.execution import Action, ExecutionEngine
from ultron.core.events import EventType
from ultron.skills.base import Risk, Skill, SkillContext, SkillResult, VerificationResult, check, schema, string
from ultron.skills.registry import SkillRegistry


class Counter(Skill):
    name = "test.counter"
    description = "conta execuções"
    inputs = schema({"label": string(20)})
    risk = Risk.LOW

    def __init__(self):
        self.calls = 0

    def execute(self, ctx, label: str = ""):
        self.calls += 1
        return SkillResult(True, f"contado {label}", [f"chamada {self.calls}"])

    def verify(self, ctx, args, result):
        return VerificationResult.from_checks([check("calls", self.calls > 0, "execução observada")])


class Dangerous(Counter):
    name = "test.dangerous"
    risk = Risk.CRITICAL
    reversible = False

    def describe_action(self, args):
        return f"apagar tudo de {args.get('label', '?')}"


class AlreadyDone(Counter):
    name = "test.already"

    def precheck(self, ctx, args):
        return "já está no estado desejado"


class Slow(Counter):
    name = "test.slow"
    timeout = 0.3

    def execute(self, ctx, label: str = ""):
        time.sleep(2)
        return SkillResult(True, "tarde demais")


class Broken(Counter):
    name = "test.broken"

    def execute(self, ctx, label: str = ""):
        raise PermissionError("acesso negado ao recurso")


class Lying(Counter):
    name = "test.lying"

    def execute(self, ctx, label: str = ""):
        return SkillResult(False, "", error="nada aconteceu", error_kind="APPLICATION_ERROR")


class ExecutorTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.settings = helpers.make_settings(autonomy_level="balanced")
        self.registry = SkillRegistry()
        self.skills = {cls.name: cls() for cls in (Counter, Dangerous, AlreadyDone, Slow, Broken, Lying)}
        for skill in self.skills.values():
            self.registry.register(skill)
        self.auth = AuthorizationManager(bus=self.bus, state=self.state, timeout_getter=lambda: 2.0)
        self.engine = ExecutionEngine(self.registry, autonomy=AutonomyPolicy(lambda: self.settings),
                                      authorizations=self.auth, context_factory=lambda c: SkillContext(cancel=c),
                                      bus=self.bus, state=self.state)
        self.events = []
        self.bus.subscribe(None, lambda e: self.events.append(e.type))

    def _reply_later(self, text: str, delay: float = 0.05):
        threading.Timer(delay, lambda: self.auth.handle_reply(text, by="teste")).start()

    def test_low_risk_executes_without_asking(self):
        record = self.engine.execute(Action("test.counter", {"label": "a"}))
        self.assertEqual(record.status, "executed")
        self.assertNotIn(EventType.AUTHORIZATION_REQUIRED, self.events)
        self.assertIn(EventType.ACTION_STARTED, self.events)
        self.assertIn(EventType.ACTION_FINISHED, self.events)

    def test_sensitive_action_requires_explicit_yes(self):
        self._reply_later("sim")
        approved = self.engine.execute(Action("test.dangerous", {"label": "x"}))
        self.assertEqual(approved.status, "executed")
        self.assertIn("apagar tudo de x", approved.authorization["description"])
        self._reply_later("não")
        denied = self.engine.execute(Action("test.dangerous", {"label": "y"}))
        self.assertEqual(denied.status, "denied")
        self.assertEqual(self.skills["test.dangerous"].calls, 1, "negado = nada executado")

    def test_authorization_expiry_means_no(self):
        record = self.engine.execute(Action("test.dangerous", {"label": "z"}))
        self.assertEqual(record.status, "denied")
        self.assertEqual(record.authorization["status"], "expired")

    def test_pre_approval_is_single_use_and_exact(self):
        self.auth.pre_approve("test.dangerous", {"label": "x"})
        first = self.engine.execute(Action("test.dangerous", {"label": "x"}))
        self.assertEqual(first.status, "executed")
        second = self.engine.execute(Action("test.dangerous", {"label": "x"}))
        self.assertEqual(second.status, "denied", "pré-aprovação vale uma única vez")

    def test_precheck_skip_invalid_args_unknown_skill(self):
        skipped = self.engine.execute(Action("test.already"))
        self.assertEqual(skipped.status, "skipped")
        self.assertEqual(self.skills["test.already"].calls, 0)
        invalid = self.engine.execute(Action("test.counter", {"inexistente": 1}))
        self.assertEqual(invalid.status, "refused", "argumentos inválidos: recusado antes de executar")
        self.assertEqual(invalid.result.error_kind, "INVALID_ARGUMENT")
        self.assertEqual(self.skills["test.counter"].calls, 0)
        unknown = self.engine.execute(Action("nao.existe"))
        self.assertEqual(unknown.status, "refused")
        shell = self.engine.execute(Action("shell", {"command": "rm -rf /"}))
        self.assertEqual(shell.status, "refused", "nunca há shell com texto livre")

    def test_timeout_and_errors_are_classified(self):
        started = time.perf_counter()
        slow = self.engine.execute(Action("test.slow"))
        self.assertLess(time.perf_counter() - started, 1.5)
        self.assertEqual(slow.result.error_kind, "TIMEOUT")
        broken = self.engine.execute(Action("test.broken"))
        self.assertEqual(broken.status, "failed")
        self.assertEqual(broken.result.error_kind, "PERMISSION_ERROR")

    def test_failure_is_never_reported_as_success(self):
        record = self.engine.execute(Action("test.lying"))
        self.assertEqual(record.status, "failed")
        self.assertFalse(record.executed)

    def test_reply_classification(self):
        for text in ("sim", "pode", "autorizo", "Sim, pode."):
            self.assertEqual(classify_reply(text), "yes", text)
        for text in ("não", "nao", "negativo", "cancela"):
            self.assertEqual(classify_reply(text), "no", text)
        self.assertIsNone(classify_reply("abra o chrome"))


class AutonomyPolicyTest(unittest.TestCase):
    def test_policy_by_risk_origin_and_level(self):
        settings = helpers.make_settings(autonomy_level="balanced")
        policy = AutonomyPolicy(lambda: settings)
        self.assertEqual(policy.decide(Risk.NONE, reversible=True, origin="agent").action, "execute")
        self.assertEqual(policy.decide(Risk.LOW, reversible=True, origin="user").action, "execute")
        self.assertEqual(policy.decide(Risk.HIGH, reversible=True, origin="user").action, "authorize")
        self.assertEqual(policy.decide(Risk.CRITICAL, reversible=False, origin="user").action, "authorize")
        self.assertEqual(policy.decide(Risk.MEDIUM, reversible=True, origin="proactive").action, "authorize",
                         "proatividade nunca age sozinha acima de baixo risco")
        settings.apply({"autonomy_level": "autonomous"})
        self.assertEqual(policy.decide(Risk.HIGH, reversible=True, origin="user").action, "authorize",
                         "ação sensível pede autorização mesmo no modo autônomo")


if __name__ == "__main__":
    unittest.main()
