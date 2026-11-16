import time
import unittest

import helpers

from ultron.agent.execution import Action, ExecutionRecord
from ultron.agent.verification import VerificationEngine
from ultron.core.events import EventType
from ultron.skills.base import Skill, SkillContext, SkillResult, VerificationResult, check
from ultron.skills.registry import SkillRegistry


class FileWriter(Skill):
    """Verificação real: observa o sistema de arquivos de novo, sem confiar no execute()."""

    name = "test.write"

    def verify(self, ctx, args, result):
        path = args["path"]
        exists = path.is_file()
        content_ok = exists and path.read_text() == args["content"]
        return VerificationResult.from_checks([check("exists", exists, f"{path} existe"),
                                               check("content", content_ok, "conteúdo confere")])


class NoVerify(Skill):
    name = "test.noverify"


class Exploding(Skill):
    name = "test.exploding"

    def verify(self, ctx, args, result):
        raise RuntimeError("sensor quebrado")


class Sleepy(Skill):
    name = "test.sleepy"
    timeout = 0.2

    def verify(self, ctx, args, result):
        time.sleep(2)
        return VerificationResult("VERIFIED", 1.0)


class VerifierTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.registry = SkillRegistry()
        for cls in (FileWriter, NoVerify, Exploding, Sleepy):
            self.registry.register(cls())
        self.verifier = VerificationEngine(self.registry, bus=self.bus, state=self.state, timeout=0.3)
        self.events = []
        self.bus.subscribe([EventType.VERIFICATION_SUCCESS, EventType.VERIFICATION_FAILED,
                            EventType.VERIFICATION_UNCONFIRMED], lambda e: self.events.append(e.type))

    def _record(self, skill, args=None, status="executed", success=True):
        return ExecutionRecord(Action(skill, args or {}), status, SkillResult(success, "ok" if success else "",
                                                                              error="" if success else "falhou"))

    def test_postcondition_is_observed_again(self):
        path = helpers.temp_dir() / "relatorio.txt"
        args = {"path": path, "content": "dados"}
        path.write_text("dados")
        ok = self.verifier.verify(self._record("test.write", args), SkillContext())
        self.assertEqual(ok.status, "VERIFIED")
        path.write_text("outro")
        bad = self.verifier.verify(self._record("test.write", args), SkillContext())
        self.assertEqual(bad.status, "FAILED", "execute() disse sucesso, mas o mundo diz outra coisa")
        self.assertEqual(self.events, [EventType.VERIFICATION_SUCCESS, EventType.VERIFICATION_FAILED])

    def test_without_independent_check_result_is_unconfirmed(self):
        result = self.verifier.verify(self._record("test.noverify"), SkillContext())
        self.assertEqual(result.status, "UNCONFIRMED")
        self.assertIn(EventType.VERIFICATION_UNCONFIRMED, self.events)

    def test_not_executed_is_failed_and_skipped_is_verified(self):
        failed = self.verifier.verify(self._record("test.write", status="failed", success=False), SkillContext())
        self.assertEqual(failed.status, "FAILED")
        skipped = self.verifier.verify(ExecutionRecord(Action("test.write"), "skipped",
                                                       SkillResult(True, "já estava aberto")), SkillContext())
        self.assertEqual(skipped.status, "VERIFIED")

    def test_broken_or_slow_verification_never_becomes_success(self):
        broken = self.verifier.verify(self._record("test.exploding"), SkillContext())
        self.assertEqual(broken.status, "UNCONFIRMED")
        started = time.perf_counter()
        slow = self.verifier.verify(self._record("test.sleepy"), SkillContext())
        self.assertEqual(slow.status, "UNCONFIRMED")
        self.assertLess(time.perf_counter() - started, 1.5)

    def test_from_checks_semantics(self):
        self.assertEqual(VerificationResult.from_checks([]).status, "UNCONFIRMED")
        self.assertEqual(VerificationResult.from_checks([check("a", True), check("b", False, "não")]).status, "FAILED")
        self.assertEqual(VerificationResult.from_checks([check("a", True), check("b", None)]).status, "UNCONFIRMED")


if __name__ == "__main__":
    unittest.main()
