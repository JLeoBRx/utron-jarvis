import threading
import time
import unittest

import helpers

from ultron.config.settings import Settings, SettingsManager
from ultron.core.events import EventType
from ultron.core.lifecycle import LifecycleManager
from ultron.core.runtime import CancellationToken, CancelledError, RetryPolicy, WorkerPool, run_with_timeout
from ultron.core.state import StateStore
from ultron.personality import dialogue, short_for_voice, stylize


class SettingsTest(unittest.TestCase):
    def test_ranges_and_choices_are_enforced(self):
        s = Settings()
        changed = s.apply({"volume": 7, "speech_speed": 0.1, "autonomy_level": "insano", "unknown": 1})
        self.assertEqual(s.volume, 1.0)
        self.assertEqual(s.speech_speed, 0.6)
        self.assertEqual(s.autonomy_level, "balanced")       # valor inválido rejeitado
        self.assertIn("volume", changed)

    def test_persistence_and_listeners(self):
        path = helpers.temp_dir() / "settings.json"
        manager = SettingsManager(path)
        manager.load()
        seen = []
        manager.on_change(lambda changed, s: seen.append(tuple(changed)))
        manager.update(model="qwen2.5:7b", volume=0.5)
        again = SettingsManager(path)
        again.load()
        self.assertEqual(again.settings.model, "qwen2.5:7b")
        self.assertEqual(again.settings.volume, 0.5)
        self.assertEqual(seen, [("model", "volume")])

    def test_required_fields_exist(self):
        names = Settings.field_names()
        for required in ("model", "vision_model", "voice", "volume", "speech_speed", "memory", "vision_interval",
                         "network_interval", "privacy_mode", "autonomy_level", "theme", "startup", "debug"):
            self.assertIn(required, names)


class StateTest(unittest.TestCase):
    def test_single_state_with_change_events(self):
        bus, state = helpers.make_bus_state()
        seen = []
        bus.subscribe(EventType.STATE_CHANGED, lambda e: seen.append(e.get("changed")))
        state.update(current_application="VS Code")
        state.merge("voice_state", {"speaking": True})
        self.assertEqual(state.get("current_application"), "VS Code")
        self.assertTrue(state.get("voice_state")["speaking"])
        self.assertIn(["current_application"], seen)
        with self.assertRaises(KeyError):
            state.update(campo_inexistente=1)
        with self.assertRaises(ValueError):
            state.set_runtime_state("DANÇANDO")

    def test_snapshots_are_copies(self):
        state = StateStore()
        state.update(world_model={"a": [1]})
        snap = state.get("world_model")
        snap["a"].append(2)
        self.assertEqual(state.get("world_model"), {"a": [1]})


class _Comp:
    def __init__(self, name, log, *, fail=False, critical=False):
        self.name, self._log, self._fail, self.critical = name, log, fail, critical

    def start(self):
        if self._fail:
            raise RuntimeError("falha de inicialização")
        self._log.append(("start", self.name))

    def stop(self):
        self._log.append(("stop", self.name))


class LifecycleTest(unittest.TestCase):
    def test_topological_order_and_isolated_failure(self):
        bus, _state = helpers.make_bus_state()
        events = []
        bus.subscribe([EventType.COMPONENT_STARTED, EventType.COMPONENT_FAILED], lambda e: events.append(
            (e.type.value, e.get("component"))))
        log = []
        manager = LifecycleManager(bus)
        manager.register(_Comp("voice", log), depends_on=("audio",))
        manager.register(_Comp("audio", log, fail=True))
        manager.register(_Comp("memory", log))
        statuses = manager.start_all()
        self.assertEqual(statuses["audio"], "FAILED")
        self.assertEqual(statuses["voice"], "RUNNING", "dependência não crítica falhou: segue degradado")
        self.assertLess(manager.names().index("audio"), manager.names().index("voice"))
        self.assertIn(("COMPONENT_FAILED", "audio"), events)
        manager.stop_all()
        self.assertEqual([x for x in log if x[0] == "stop"][0], ("stop", "memory"))

    def test_critical_failure_blocks_dependents(self):
        log = []
        manager = LifecycleManager()
        manager.register(_Comp("db", log, fail=True, critical=True))
        manager.register(_Comp("goals", log), depends_on=("db",))
        with self.assertRaises(RuntimeError):
            manager.start_all()


class RuntimeTest(unittest.TestCase):
    def test_worker_priority_and_failures(self):
        pool = WorkerPool(("ai",))
        pool.start()
        try:
            gate = threading.Event()
            order = []
            pool.submit("ai", gate.wait, 2)
            pool.submit("ai", lambda: order.append("baixa"), priority=90)
            pool.submit("ai", lambda: order.append("alta"), priority=10)
            failing = pool.submit("ai", lambda: 1 / 0)
            gate.set()
            with self.assertRaises(ZeroDivisionError):
                failing.result(3)
            time.sleep(0.1)
            self.assertEqual(order, ["alta", "baixa"])
        finally:
            pool.stop()

    def test_scheduler_never_overlaps_runs(self):
        pool = WorkerPool(("perception", "memory"))
        running, overlaps, runs = [0], [0], [0]

        def job():
            running[0] += 1
            overlaps[0] += running[0] > 1
            time.sleep(0.08)
            runs[0] += 1
            running[0] -= 1

        pool.scheduler.every("job", 0.01, job, worker="perception")
        pool.start()
        time.sleep(0.6)
        pool.stop()
        self.assertGreater(runs[0], 2)
        self.assertEqual(overlaps[0], 0)

    def test_cancellation_and_bounded_retry(self):
        token = CancellationToken()
        child = token.child()
        token.cancel("pare")
        self.assertTrue(child.cancelled)
        with self.assertRaises(CancelledError):
            child.raise_if_cancelled()
        attempts = []
        with self.assertRaises(ValueError):
            RetryPolicy(max_attempts=3, base_delay=0.01).run(lambda n: attempts.append(n) or (_ for _ in ()).throw(
                ValueError("sempre falha")))
        self.assertEqual(attempts, [1, 2, 3])

    def test_run_with_timeout(self):
        self.assertEqual(run_with_timeout(lambda: 42, 1.0), 42)
        started = time.perf_counter()
        with self.assertRaises(TimeoutError):
            run_with_timeout(time.sleep, 0.2, 5)
        self.assertLess(time.perf_counter() - started, 1.0)


class PersonalityTest(unittest.TestCase):
    def test_style_removes_forbidden_expressions_and_emojis(self):
        text = stylize("Claro! Perfeito! 😀 Ótimo, vou abrir o Chrome!!")
        for banned in ("Claro", "Perfeito", "Ótimo", "😀", "!"):
            self.assertNotIn(banned, text)
        self.assertTrue(text)

    def test_dialogue_and_voice_shortening(self):
        self.assertIn(dialogue.say("done"), dialogue.LINES["done"])
        long_text = "Primeira frase curta. " + "Segunda frase muito longa " * 30
        self.assertLessEqual(len(short_for_voice(long_text)), 400)

    def test_identity_never_jarvis(self):
        from ultron.personality import identity
        prompt = identity.system_prompt()
        self.assertIn("ULTRON", prompt)
        self.assertNotIn("JARVIS", prompt)


class NeuralCoreTest(unittest.TestCase):
    """Boot real do Neural Core (sem voz e sem percepção) com um servidor que imita o Ollama."""

    def test_boot_submit_and_shutdown(self):
        from fake_ollama import FakeOllama
        from ultron.core.neural_core import NeuralCore

        with FakeOllama(["qwen2.5:3b"], responder=lambda p: "Resposta local.") as fake:
            manager = SettingsManager(helpers.temp_dir() / "settings.json")
            manager.load()
            manager.settings.ollama_url = fake.url
            manager.settings.network_discovery = False
            core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
            responses = []
            done = threading.Event()

            def on_response(event):
                responses.append(event.payload)
                if not event.get("partial"):
                    done.set()

            core.bus.subscribe(EventType.RESPONSE_READY, on_response)
            statuses = core.boot()
            try:
                self.assertTrue(all(st == "RUNNING" for st in statuses.values()), statuses)
                self.assertEqual(core.state.runtime_state, "IDLE")
                core.submit("que horas são?")
                self.assertTrue(done.wait(10))
                self.assertTrue(responses[-1]["text"].startswith("São "))
                done.clear()
                core.submit("o que é um buraco negro?")
                self.assertTrue(done.wait(10))
                self.assertEqual(responses[-1]["text"], "Resposta local.")
                done.clear()
                core.submit("fale mais devagar")
                self.assertTrue(done.wait(10))
                self.assertAlmostEqual(manager.settings.speech_speed, 0.8, places=2)
                done.clear()
                core.submit("cancelar")
                self.assertTrue(done.wait(5))
                self.assertIn("nada em andamento", responses[-1]["text"])
                report = core.health.check_all()
                self.assertEqual(report["checks"]["OLLAMA"]["status"], "WARN")   # sem modelo de visão: dito
            finally:
                core.shutdown()


if __name__ == "__main__":
    unittest.main()
