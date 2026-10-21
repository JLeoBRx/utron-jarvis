"""Histórico de atividades: protocolo comum, ações ligadas ao pedido, verificação e privacidade."""
import threading
import time
import unittest

import helpers

from ultron.agent.autonomy import AuthorizationManager, AutonomyPolicy
from ultron.agent.execution import Action, ExecutionEngine
from ultron.agent.permissions import PermissionPolicy
from ultron.agent.verification import VerificationEngine
from ultron.config.settings import SettingsManager
from ultron.core.activity import ActivityLog
from ultron.core.events import EventType
from ultron.skills.base import Risk, Skill, SkillContext, SkillResult, VerificationResult, check, schema, string
from ultron.skills.registry import SkillRegistry


def wait_until(condition, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


class Note(Skill):
    name = "test.note"
    inputs = schema({"text": string(80)})
    risk = Risk.LOW
    permission = "arquivos"

    def execute(self, ctx, text: str = ""):
        return SkillResult(True, f"anotado: {text}", [text])

    def verify(self, ctx, args, result):
        return VerificationResult.from_checks([check("saved", True, "nota relida")])


class Wipe(Note):
    name = "test.wipe"
    risk = Risk.CRITICAL
    reversible = False
    permission = "apagar_dados"


class ActivityLogTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.memory = helpers.make_memory()
        self.addCleanup(self.memory.db.close)
        self.settings = helpers.make_settings()
        self.log = ActivityLog(self.memory.db, bus=self.bus, settings_getter=lambda: self.settings)

    def test_protocol_fields_states_and_duration(self):
        events = []
        self.bus.subscribe(EventType.ACTIVITY_UPDATED, lambda e: events.append(e.payload))
        request = self.log.begin("pedido", "abra o bloco de notas", origin="voice", input="abra o bloco de notas")
        item = self.log.get(request)
        self.assertEqual((item["kind"], item["origin"], item["state"]), ("pedido", "voz", "recebido"))
        self.assertIsNone(item["finished_at"])
        self.assertFalse(item["final"])
        self.log.update(request, state="executando")
        time.sleep(0.01)
        self.log.update(request, state="verificado", result="Bloco de notas aberto.")
        item = self.log.get(request)
        self.assertEqual(item["state_label"], "verificado")
        self.assertTrue(item["final"])
        self.assertGreater(item["seconds"], 0)
        self.assertEqual(item["result"], "Bloco de notas aberto.")
        self.assertEqual([e["state"] for e in events], ["recebido", "executando", "verificado"],
                         "cada mudança chega à interface")

    def test_secrets_are_redacted_and_disabled_history_writes_nothing(self):
        aid = self.log.record("pedido", "anote minha senha 1234", origin="text", input="minha senha é 1234")
        item = self.log.get(aid)
        self.assertNotIn("1234", item["title"] + item["input"])
        self.assertIn("redigido", item["input"])
        self.settings.apply({"activity_history": False}, source="teste")
        self.assertEqual(self.log.begin("pedido", "qualquer", origin="text"), "")
        self.assertEqual(self.log.count(), 1)

    def test_search_filters_children_and_retention(self):
        parent = self.log.begin("pedido", "organize a pasta", origin="text")
        with self.log.scope(parent):
            self.assertEqual(self.log.current(), parent)
        self.assertEqual(self.log.current(), "")
        self.log.record("acao", "criar pasta Relatórios", origin="agent", parent=parent)
        self.log.record("erro", "Componente VOZ falhou", origin="system", state="falhou", error="sem microfone")
        self.assertEqual([i["title"] for i in self.log.children(parent)], ["criar pasta Relatórios"])
        self.assertEqual(len(self.log.recent(kinds=["erro"])), 1)
        self.assertEqual(len(self.log.recent(search="Relatórios")), 1)
        self.assertEqual(len(self.log.recent(states=["falhou"])), 1)
        self.settings.apply({"activity_keep": 100}, source="teste")
        for index in range(120):
            self.log.record("aviso", f"aviso {index}", origin="core", state="aviso")
        self.log.trim()
        self.assertEqual(self.log.count(), 100, "os mais antigos saem primeiro")
        self.assertEqual(self.log.recent(1)[0]["title"], "aviso 119")
        self.assertEqual(self.log.clear(), 100)


class ExecutorActivityTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.memory = helpers.make_memory()
        self.addCleanup(self.memory.db.close)
        self.settings = helpers.make_settings()
        self.log = ActivityLog(self.memory.db, bus=self.bus, settings_getter=lambda: self.settings)
        self.log.attach()
        self.registry = SkillRegistry()
        for cls in (Note, Wipe):
            self.registry.register(cls())
        self.auth = AuthorizationManager(bus=self.bus, state=self.state, timeout_getter=lambda: 2.0)
        self.engine = ExecutionEngine(self.registry, autonomy=AutonomyPolicy(lambda: self.settings),
                                      authorizations=self.auth, context_factory=lambda c: SkillContext(cancel=c),
                                      bus=self.bus, state=self.state,
                                      permissions=PermissionPolicy(lambda: self.settings), activity=self.log)
        self.verifier = VerificationEngine(self.registry, bus=self.bus, state=self.state)

    def test_action_is_linked_to_the_request_and_verified(self):
        request = self.log.begin("pedido", "anote o teste", origin="text")
        with self.log.scope(request):
            record = self.engine.execute(Action("test.note", {"text": "teste"}, origin="user"))
        self.verifier.verify(record, SkillContext())
        actions = self.log.children(request)
        self.assertEqual(len(actions), 1)
        self.assertTrue(wait_until(lambda: self.log.get(actions[0]["id"])["state"] == "verificado"))
        item = self.log.get(actions[0]["id"])
        self.assertEqual(item["result"], "anotado: teste")
        self.assertEqual(item["detail"]["verification"], "VERIFIED")

    def test_denied_and_refused_actions_are_recorded_honestly(self):
        threading.Timer(0.05, lambda: self.auth.handle_reply("não", by="teste")).start()
        denied = self.engine.execute(Action("test.wipe", {"text": "tudo"}))
        self.assertEqual(denied.status, "denied")
        refused = self.engine.execute(Action("nao.existe"))
        self.assertEqual(refused.status, "refused")
        rows = {r["title"]: r for r in self.log.recent(kinds=["acao"])}
        wipe = next(r for r in rows.values() if r["detail"].get("skill") == "test.wipe")
        self.assertEqual(wipe["state"], "negado")
        self.assertEqual(wipe["detail"]["authorization"], "denied")
        self.assertEqual(wipe["detail"]["permission"], "apagar_dados")
        self.assertEqual(rows["nao.existe"]["state"], "recusado")
        self.verifier.verify(denied, SkillContext())
        time.sleep(0.2)
        self.assertEqual(self.log.get(wipe["id"])["state"], "negado", "a verificação não muda uma ação negada")


class CoreActivityTest(unittest.TestCase):
    def test_requests_from_text_end_with_the_real_response(self):
        from fake_ollama import FakeOllama
        from ultron.core.neural_core import NeuralCore

        with FakeOllama(["qwen2.5:3b"], responder=lambda p: "Resposta local.") as fake:
            manager = SettingsManager(helpers.temp_dir() / "settings.json")
            manager.load()
            manager.settings.ollama_url = fake.url
            manager.settings.network_discovery = False
            core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
            core.boot()
            try:
                self.assertTrue(wait_until(lambda: core.activity.recent(kinds=["sistema"])))
                core.submit("que horas são?", source="text")
                self.assertTrue(wait_until(lambda: any(r["final"] for r in core.activity.recent(kinds=["pedido"]))))
                request = core.activity.recent(kinds=["pedido"])[0]
                self.assertEqual((request["origin"], request["input"]), ("texto", "que horas são?"))
                self.assertIn(request["state"], ("concluido", "verificado"))
                self.assertTrue(request["result"].startswith("São "))
                core.submit("cancelar", source="voice")
                self.assertTrue(wait_until(lambda: core.activity.recent(kinds=["pedido"])[0]["input"] == "cancelar"))
                core.set_privacy_shield(True, by="hud")
                core.set_privacy_shield(False, by="hud")
                titles = [r["title"] for r in core.activity.recent(kinds=["sistema"])]
                self.assertIn("Modo privacidade ativado", titles)
                self.assertIn("Modo privacidade desligado", titles)
            finally:
                core.shutdown()


if __name__ == "__main__":
    unittest.main()
