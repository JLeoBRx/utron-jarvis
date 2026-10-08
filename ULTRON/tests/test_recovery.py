import unittest

import helpers

from ultron.agent.execution import Action, ExecutionRecord
from ultron.agent.recovery import ERROR_TYPES, RecoveryEngine
from ultron.core.events import EventType
from ultron.skills.base import SkillResult, VerificationResult


def failed(skill, kind, error="falhou", args=None, data=None, status="failed"):
    return ExecutionRecord(Action(skill, args or {}, goal_id="g1"), status,
                           SkillResult(False, error=error, error_kind=kind, data=data or {}))


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.engine = RecoveryEngine(bus=self.bus, state=self.state)
        self.events = []
        self.bus.subscribe([EventType.RECOVERY_STARTED, EventType.RECOVERY_FINISHED],
                           lambda e: self.events.append((e.type, e.payload)))

    def test_error_taxonomy(self):
        for name in ("TIMEOUT", "APPLICATION_ERROR", "NETWORK_ERROR", "PERMISSION_ERROR", "DEPENDENCY_ERROR",
                     "VISION_ERROR", "MODEL_ERROR", "AUDIO_ERROR", "UNKNOWN_ERROR"):
            self.assertIn(name, ERROR_TYPES)

    def test_denied_or_invalid_is_not_retried(self):
        denied = failed("fs.move", "NOT_AUTHORIZED", status="denied")
        self.assertFalse(self.engine.diagnose(denied).recoverable)
        invalid = failed("fs.move", "INVALID_ARGUMENT")
        self.assertIsNone(self.engine.plan(invalid, self.engine.diagnose(invalid), goal_id="g1"))
        permission = failed("fs.write_text", "PERMISSION_ERROR")
        self.assertFalse(self.engine.diagnose(permission).recoverable)

    def test_hung_application_is_restarted(self):
        record = failed("app.open", "APPLICATION_ERROR", args={"name": "chrome"})
        plan = self.engine.plan(record, self.engine.diagnose(record), goal_id="g1")
        self.assertEqual(plan.strategy, "restart_application")
        self.assertEqual([s.skill for s in plan.steps], ["app.check", "app.terminate", "system.wait"])
        self.assertTrue(all(s.origin == "recovery" for s in plan.steps))
        self.assertEqual(self.state.runtime_state, "RECOVERY")
        self.assertEqual(self.events[0][0], EventType.RECOVERY_STARTED)

    def test_missing_dependency_becomes_install_step(self):
        record = failed("dev.run_project", "DEPENDENCY_ERROR", args={"path": "/p/atlas"},
                        data={"diagnosis": {"module": "yaml"}})
        plan = self.engine.plan(record, self.engine.diagnose(record), goal_id="g1")
        self.assertEqual(plan.strategy, "install_missing_dependency")
        step = plan.steps[0]
        self.assertEqual(step.skill, "dev.install_dependency")
        self.assertEqual(step.args["package"], "PyYAML", "módulo → pacote correto")

    def test_failed_postcondition_is_diagnosed(self):
        record = ExecutionRecord(Action("network.ping", {"host": "x"}), "executed", SkillResult(True, "ok"))
        record.verification = VerificationResult("FAILED", 0.9, reason="host não respondeu")
        diagnosis = self.engine.diagnose(record)
        self.assertEqual(diagnosis.error_type, "NETWORK_ERROR")
        self.assertTrue(diagnosis.recoverable)

    def test_retries_are_bounded_and_breaker_opens(self):
        record = failed("app.open", "APPLICATION_ERROR", args={"name": "spotify"})
        plans = [self.engine.plan(record, self.engine.diagnose(record), goal_id="g1") for _ in range(6)]
        self.assertLessEqual(sum(p is not None for p in plans), self.engine.max_attempts)
        self.assertIsNone(plans[-1])
        self.engine.reset_goal("g1")
        other = failed("web.open_url", "UNKNOWN_ERROR", args={"url": "https://exemplo.org"})
        for _ in range(self.engine.breaker_failures + 1):
            self.engine.note_failure("web.open_url")
        self.assertIsNone(self.engine.plan(other, self.engine.diagnose(other), goal_id="g2"),
                          "disjuntor aberto após falhas repetidas")

    def test_timeout_retries_once(self):
        record = failed("web.search", "TIMEOUT", args={"query": "x"})
        first = self.engine.plan(record, self.engine.diagnose(record), goal_id="g9")
        second = self.engine.plan(record, self.engine.diagnose(record), goal_id="g9")
        self.assertEqual(first.strategy, "retry_after_timeout")
        self.assertIsNone(second)


if __name__ == "__main__":
    unittest.main()
