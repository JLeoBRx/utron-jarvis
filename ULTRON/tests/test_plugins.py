"""Plugins, monitor de saúde e inteligência proativa."""
import textwrap
import time
import unittest

import helpers

from ultron.core.events import EventType
from ultron.health.monitor import HealthMonitor, format_report
from ultron.plugins import PluginContext, PluginManager
from ultron.plugins import manager as manager_module
from ultron.proactive import ProactiveIntelligence
from ultron.skills.base import SkillContext
from ultron.skills.registry import SkillRegistry


class PluginTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.registry = SkillRegistry()
        self.health = HealthMonitor()
        self.settings = helpers.make_settings()
        self.extra = helpers.temp_dir("plugins-")

    def manager(self):
        def factory(plugin):
            return PluginContext(plugin=plugin, bus=self.bus, settings=lambda: self.settings, registry=self.registry,
                                 health_monitor=self.health)
        return PluginManager(context_factory=factory, settings_getter=lambda: self.settings,
                             directories=[helpers.ROOT / "plugins", self.extra])

    def test_bundled_plugins_contract(self):
        manager = self.manager()
        manager.start()
        records = {r["name"]: r for r in manager.list()}
        self.assertEqual(records["system_uptime"]["status"], "ACTIVE")
        self.assertEqual(records["external_model_provider"]["status"], "SKIPPED", "externo: desativado por padrão")
        skill = self.registry.get("plugin.uptime")
        result = skill.execute(SkillContext())
        self.assertTrue(result.success)
        self.assertEqual(skill.verify(SkillContext(), {}, result).status, "VERIFIED")
        manager.stop()
        self.assertIsNone(self.registry.get("plugin.uptime"), "shutdown remove o que o plugin registrou")

    def test_faulty_plugins_never_break_the_system(self):
        (self.extra / "quebrado.py").write_text("raise RuntimeError('quebrado')\n")
        (self.extra / "sem_permissao.py").write_text(textwrap.dedent('''
            from ultron.plugins import Plugin
            from ultron.skills.base import Skill
            class S(Skill):
                name = "plugin.s"
            class P(Plugin):
                name = "sem_permissao"
                capabilities = ()
                def initialize(self, ctx):
                    ctx.register_skill(S())
        '''))
        (self.extra / "lento.py").write_text(textwrap.dedent('''
            import time
            from ultron.plugins import Plugin
            class P(Plugin):
                name = "lento"
                def initialize(self, ctx):
                    time.sleep(5)
        '''))
        original = manager_module.INIT_TIMEOUT
        manager_module.INIT_TIMEOUT = 0.5
        try:
            manager = self.manager()
            manager.start()
        finally:
            manager_module.INIT_TIMEOUT = original
        records = {r["name"]: r for r in manager.list()}
        self.assertEqual(records["quebrado"]["status"], "FAILED")
        self.assertIn("CapabilityError", records["sem_permissao"]["reason"])
        self.assertIn("excedeu", records["lento"]["reason"])
        self.assertIsNone(self.registry.get("plugin.s"))
        self.assertEqual(manager.health()["status"], "WARN")


class HealthTest(unittest.TestCase):
    def test_all_required_checks_with_timeouts(self):
        def slow():
            time.sleep(3)
            return {"status": "OK"}

        def broken():
            raise RuntimeError("banco corrompido")

        monitor = HealthMonitor(probes={"OLLAMA": lambda: {"status": "OK", "detail": "qwen2.5:3b"},
                                        "MEMORY": broken, "HUD": slow}, check_timeout=0.5)
        started = time.perf_counter()
        report = monitor.check_all()
        self.assertLess(time.perf_counter() - started, 3.0)
        for name in ("CPU", "RAM", "GPU", "DISK", "OLLAMA", "VOICE", "VISION", "NETWORK", "MEMORY", "HUD"):
            self.assertIn(name, report["checks"])
        self.assertEqual(report["checks"]["MEMORY"]["status"], "FAIL")
        self.assertIn("excedeu", report["checks"]["HUD"]["detail"])
        self.assertEqual(report["checks"]["VOICE"]["status"], "UNAVAILABLE")
        self.assertEqual(report["overall"], "FAIL")
        self.assertIn("SAÚDE GERAL", format_report(report))


class ProactiveTest(unittest.TestCase):
    def test_insights_need_evidence_cooldown_and_consent(self):
        bus, state = helpers.make_bus_state()
        clock = helpers.FakeClock()
        insights = []
        bus.subscribe(EventType.INSIGHT, lambda e: insights.append(e.payload))
        proactive = ProactiveIntelligence(bus=bus, state=state, clock=clock)
        proactive.start()
        weak = {"top": {"kind": "dependency_error", "description": "x", "confidence": 0.4, "sources": ["ocr"]}}
        bus.publish(EventType.PERCEPTION_FUSED, weak)
        self.assertEqual(insights, [], "evidência fraca é ignorada")
        hung = {"top": {"kind": "application_hung", "description": "Chrome não está respondendo.",
                        "confidence": 0.93, "sources": ["vision", "window"], "data": {"process": "chrome.exe"}}}
        bus.publish(EventType.PERCEPTION_FUSED, hung)
        bus.publish(EventType.PERCEPTION_FUSED, hung)
        self.assertEqual(len(insights), 1, "mesmo assunto não se repete")
        insight = insights[0]
        self.assertEqual(insight["action"], "authorize")
        self.assertEqual(insight["suggestion"], {"skill": "app.terminate", "args": {"name": "chrome.exe"}})
        self.assertIn("dados não salvos", insight["text"], "a sugestão descreve a consequência")
        clock.advance(120)
        state.set_runtime_state("EXECUTING")
        info = {"top": {"kind": "visible_error", "description": "Erro", "confidence": 0.6, "sources": ["ocr"],
                        "data": {"application": "Excel"}}}
        bus.publish(EventType.PERCEPTION_FUSED, info)
        self.assertEqual(len(insights), 1, "usuário ocupado: insight comum espera")


if __name__ == "__main__":
    unittest.main()
