"""TARDIS integrada ao JARVIS: "JARVIS, consulte a TARDIS", sugestões que só rodam com "sim", categorias que
pedem confirmação própria (robô), cancelamento, modo "operação" do rotor e a SALA DE CONTROLE na plataforma
(Qt offscreen, Ollama simulado por HTTP, banco temporário).

Não é teste de GPU, de janela real do Windows, de microfone nem de robô: a skill do Noctário aqui é um
falso registrado só para provar que a TARDIS PROPÕE e o JARVIS pede confirmação antes de qualquer comando.
"""
import threading
import time
import unittest

import helpers

from fake_ollama import FakeOllama
from ultron.skills.base import Risk, Skill, SkillResult, VerificationResult, check, schema
from ultron.tardis.protocol import ProposedAction, TaskResult

LLM_HTML = "<b>Atlas</b> tem uma ideia registrada: painel solar portátil [1]."


def responder(payload):
    system = str((payload.get("messages") or [{}])[0].get("content", ""))
    return LLM_HTML if "TARDIS" in system else "Resposta local."


class FakeRobotParams(Skill):
    """Falso de teste: registra o pedido, não fala com robô nenhum."""

    name = "noctario.set_params"
    description = "teste"
    category = "devices"
    inputs = schema({"kd": {"type": "number"}, "kp": {"type": "number"}})
    risk = Risk.MEDIUM
    permission = "robo"
    calls = []

    def execute(self, ctx, **args) -> SkillResult:
        FakeRobotParams.calls.append(args)
        return SkillResult(True, "parâmetros enviados (falso de teste)", [], {"args": args})

    def verify(self, ctx, args, result):
        return VerificationResult("VERIFIED", 0.9, [check("fake", True, "falso de teste")])


class IntentsTest(unittest.TestCase):
    def test_tardis_phrases(self):
        from ultron.cognition.intent_engine import IntentEngine
        engine = IntentEngine()
        cases = {
            "JARVIS, consulte a TARDIS sobre o projeto Atlas": ("tardis.consult", {"kind": "consulta",
                                                                                   "question": "o projeto Atlas"}),
            "pergunte à TARDIS como organizar meu estudo": ("tardis.consult", {"kind": "consulta",
                                                                              "question": "como organizar meu estudo"}),
            "TARDIS, organize minha memória": ("tardis.consult", {"kind": "organizacao"}),
            "peça à TARDIS um plano para montar o robô": ("tardis.consult", {"kind": "planejamento",
                                                                            "goal": "montar o robô"}),
            "TARDIS, diagnostique o sistema": ("tardis.consult", {"kind": "diagnostico"}),
            "peça à TARDIS para analisar a telemetria do Noctário": ("tardis.consult", {"kind": "telemetria"}),
            "TARDIS, quais são minhas rotinas?": ("tardis.consult", {"kind": "rotinas"}),
            "TARDIS, estado dos módulos": ("tardis.consult", {"kind": "coordenacao"}),
            "mostre a memória de projeto do Noctario": ("tardis.consult", {"kind": "projeto", "project": "Noctario"}),
            "anote na TARDIS que o Kd 0,1 funcionou melhor": ("tardis.note", {"text": "o Kd 0,1 funcionou melhor",
                                                                             "kind": "nota"}),
            "anote na TARDIS uma decisão: usar pista de 3 metros": ("tardis.note", {"text": "usar pista de 3 metros",
                                                                                   "kind": "decisao"}),
        }
        for text, (skill, args) in cases.items():
            intent = engine.classify(text)
            self.assertEqual((intent.kind, intent.skill, intent.args), ("command", skill, args), text)
        self.assertEqual(engine.classify("abra a TARDIS").args, {"open_view": "tardis"})
        self.assertEqual(engine.classify("abra o segundo cérebro").args, {"open_view": "second_brain"})
        self.assertEqual(engine.classify("consulte a TARDIS").kind, "response", "sem assunto: pergunta de volta")
        self.assertEqual(engine.classify("o que é a TARDIS?").kind, "unknown", "pergunta sobre a TARDIS: conversa")


class CoreIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ultron.config.settings import SettingsManager
        from ultron.core.events import EventType
        from ultron.core.neural_core import NeuralCore
        cls.EventType = EventType
        cls.fake = FakeOllama(["qwen2.5:3b"], responder=responder)
        cls.fake.__enter__()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = cls.fake.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        cls.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
        cls.core.registry.register(FakeRobotParams())
        cls.responses = []
        cls.core.bus.subscribe(EventType.RESPONSE_READY, lambda e: cls.responses.append(e.payload), name="t")
        cls.core.boot()

    @classmethod
    def tearDownClass(cls):
        cls.core.shutdown()
        cls.fake.__exit__(None, None, None)

    def ask(self, text, seconds=30):
        self.responses.clear()
        self.assertTrue(self.core.submit(text, source="text"))
        end = time.time() + seconds
        while time.time() < end:
            final = [r for r in self.responses if not r.get("partial")]
            if final:
                return final[-1]
            time.sleep(0.02)
        self.fail(f"sem resposta para: {text}")

    def test_1_consult_answers_with_sources_and_the_same_model(self):
        self.core.second_brain.create("idea", "Painel solar portátil", project="Atlas")
        response = self.ask("JARVIS, consulte a TARDIS sobre o projeto Atlas")
        self.assertIn("TARDIS — consulta contextual", response["text"])
        self.assertIn("qwen2.5:3b (o mesmo do JARVIS)", response["text"])
        self.assertIn("Fontes:", response["text"])
        task = next(t for t in self.core.tardis.recent(5) if t.kind == "consulta")
        self.assertEqual((task.origin, task.chain), ("jarvis", ["jarvis"]))
        records = self.core.activity.recent(20)
        request = next(a for a in records if a["kind"] == "pedido" and "consulte a TARDIS" in a["title"])
        tardis = next(a for a in records if a["kind"] == "tardis" and a["ref"] == task.id)
        action = next(a for a in records if a["id"] == tardis["parent"])
        self.assertEqual((action["kind"], action["parent"]), ("acao", request["id"]),
                         "pedido → ação tardis.consult → tarefa da TARDIS, ligados no histórico")
        self.assertEqual(self.core.health.check_all()["checks"]["TARDIS"]["status"], "OK")

    def test_2_proposed_archive_runs_only_after_yes(self):
        sb = self.core.second_brain
        first = sb.create("task", "Trocar o filtro")
        copy = sb.create("task", "trocar o filtro")
        response = self.ask("TARDIS, organize minha memória")
        self.assertIn("A TARDIS propõe: arquivar a cópia", response["text"])
        time.sleep(0.3)
        self.assertIsNone(sb.get(copy.id).archived_at, "proposta não é execução")
        suggestion = self.core._suggestion
        self.assertEqual(suggestion["suggestion"], {"skill": "secondbrain.archive", "args": {"ref": copy.id}})
        self.assertEqual(suggestion["action"], "authorize", "o 'sim' descreve exatamente esta ação reversível")
        answer = self.ask("sim")
        self.assertIn("Arquivado", answer["text"])
        self.assertIsNotNone(sb.get(copy.id).archived_at)
        self.assertIsNone(sb.get(first.id).archived_at)

    def test_3_robot_proposal_still_needs_its_own_confirmation(self):
        def analyzer(run, data):
            return TaskResult("Oscilação alta (dados de teste).", actions=[
                ProposedAction("ajustar no Noctário: kd = 0.115", "noctario.set_params", {"kd": 0.115},
                               "hipótese de teste")])
        engine = self.core.tardis
        original = engine._analyzers["telemetria"]
        engine._analyzers["telemetria"] = analyzer
        requests = []
        sub = self.core.bus.subscribe(self.EventType.AUTHORIZATION_REQUIRED, lambda e: requests.append(e.payload),
                                      name="t.auth")
        try:
            response = self.ask("peça à TARDIS para analisar a telemetria do Noctário")
            self.assertIn("A TARDIS propõe: ajustar no Noctário", response["text"])
            time.sleep(0.3)
            self.assertEqual(self.core._suggestion["action"], "", "comando ao robô não é pré-aprovado")
            FakeRobotParams.calls.clear()
            self.core.submit("sim", source="text")
            end = time.time() + 10
            while time.time() < end and self.core.authorizations.pending() is None:
                time.sleep(0.02)
            self.assertIsNotNone(self.core.authorizations.pending(), "o executor pede a confirmação do robô")
            self.assertEqual(FakeRobotParams.calls, [], "nada foi enviado ao robô antes da confirmação")
            self.core.authorizations.resolve(False, by="teste")
            time.sleep(0.5)
            self.assertEqual(FakeRobotParams.calls, [], "negado: nada foi enviado")
            self.assertTrue(requests and requests[-1].get("permission") == "robo", requests[-1:])
        finally:
            engine._analyzers["telemetria"] = original
            self.core.bus.unsubscribe(sub) if hasattr(self.core.bus, "unsubscribe") else None

    def test_4_cancel_stops_jarvis_consultations_only(self):
        engine = self.core.tardis
        started = threading.Event()

        def slow(run, data):
            started.set()
            while True:
                run.check()
                time.sleep(0.01)

        original = engine._analyzers["rotinas"]
        engine._analyzers["rotinas"] = slow
        try:
            room_task = engine.submit("rotinas", {}, origin="usuario")
            self.assertTrue(started.wait(5))
            jarvis_task = engine.submit("rotinas", {}, origin="jarvis", chain=["jarvis"])
            self.core.submit("cancelar", source="text")
            jarvis_task = engine.wait(jarvis_task.id, 5)
            self.assertEqual(jarvis_task.state, "CANCELLED")
            self.assertFalse(engine.get(room_task.id).final, "a análise pedida na sala continua")
            engine.cancel(room_task.id)
            self.assertEqual(engine.wait(room_task.id, 5).state, "CANCELLED")
        finally:
            engine._analyzers["rotinas"] = original

    def test_5_project_note_goes_through_the_executor(self):
        outcome = self.core.run_skill("tardis.note", {"text": "decidimos usar fita branca de 19 mm",
                                                      "project": "Noctario", "kind": "decisao"})
        self.assertTrue(outcome["success"] and outcome["verified"], outcome)
        refused = self.core.run_skill("tardis.note", {"text": "o token da API é abc123"})
        self.assertFalse(refused["success"])
        self.assertIn("não guarda senhas", refused["error"])

    def test_6_backups_light_the_operation_mode(self):
        engine = self.core.tardis
        bus = self.core.bus
        bus.publish(self.EventType.ACTION_STARTED, {"id": "op1", "skill": "memory.backup",
                                                    "description": "backup do banco"}, source="teste")
        end = time.time() + 5
        while time.time() < end and engine.state()["mode"] != "operacao":
            time.sleep(0.02)
        self.assertEqual(engine.state()["operations"], ["backup do banco"])
        bus.publish(self.EventType.ACTION_FINISHED, {"id": "op1", "skill": "memory.backup"}, source="teste")
        end = time.time() + 5
        while time.time() < end and engine.state()["operations"]:
            time.sleep(0.02)
        self.assertEqual(engine.state()["operations"], [])
        bus.publish(self.EventType.ACTION_STARTED, {"id": "op2", "skill": "app.open", "description": "x"},
                    source="teste")
        time.sleep(0.2)
        self.assertEqual(engine.state()["operations"], [], "abrir um programa não é operação de dados")


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class RoomUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets

        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.hud.controller import HudController

        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.fake = FakeOllama(["qwen2.5:3b"], responder=responder)
        cls.fake.__enter__()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = cls.fake.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        cls.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
        cls.controller = HudController(cls.core)
        cls.controller.window.resize(1440, 860)
        cls.controller.show()
        threading.Thread(target=cls.core.boot, daemon=True).start()
        cls.pump_until(lambda: cls.core.booted, 30)
        cls.pump(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.controller.quit()
        cls.core.shutdown()
        cls.pump(0.3)
        cls.fake.__exit__(None, None, None)

    @classmethod
    def pump(cls, seconds):
        from PySide6 import QtCore
        end = time.time() + seconds
        while time.time() < end:
            cls.app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            time.sleep(0.005)

    @classmethod
    def pump_until(cls, condition, seconds):
        from PySide6 import QtCore
        end = time.time() + seconds
        while time.time() < end:
            cls.app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            if condition():
                return True
            time.sleep(0.005)
        return False

    def test_1_room_consult_shows_escaped_result_and_lights_the_panel(self):
        self.core.second_brain.create("idea", "Painel solar portátil", project="Atlas")
        page = self.controller.open_tardis()
        self.pump(0.2)
        room = page.room
        self.assertEqual(page.mode, "sala")
        self.assertTrue(room.isVisible())
        self.assertTrue(room._clock.isActive(), "a sala anima enquanto visível")
        room.question.setText("o que existe sobre o projeto Atlas?")
        room._consult()
        self.assertTrue(self.pump_until(lambda: any(t.kind == "consulta" and t.final
                                                    for t in self.core.tardis.recent(5)), 20))
        self.pump(0.4)
        task = next(t for t in self.core.tardis.recent(5) if t.kind == "consulta")
        self.assertEqual((task.state, task.origin), ("DONE", "usuario"))
        self.assertEqual(room.shown_task, task.id)
        text = room.result.toPlainText()
        self.assertIn("<b>Atlas</b>", text, "resposta do modelo é mostrada como texto, nunca como HTML")
        self.assertIn("qwen2.5:3b (o mesmo do JARVIS)", text)
        self.assertIn("pedida por você", text)
        self.assertGreater(room.scene.panels["analise"].flash, 0.1, "o painel ANÁLISE pulsou com a tarefa real")
        self.assertEqual(room.tasks.item(0).data(256), task.id)

    def test_2_apply_runs_the_proposed_action_through_the_core(self):
        sb = self.core.second_brain
        sb.create("task", "Calibrar sensores")
        copy = sb.create("task", "calibrar sensores")
        page = self.controller.open_tardis("analise")
        room = page.room
        room.select_panel("arquivo")
        self.pump(0.2)
        room.submit("organizacao", {})
        self.assertTrue(self.pump_until(lambda: room._action_rows, 20), "ação proposta exibida com APLICAR")
        self.assertIsNone(sb.get(copy.id).archived_at)
        button, label = room._action_rows[0]
        button.click()
        self.assertTrue(self.pump_until(lambda: "verificado" in label.text() or "não feito" in label.text(), 20),
                        label.text())
        self.assertIn("verificado", label.text())
        self.assertIsNotNone(sb.get(copy.id).archived_at)
        self.assertFalse(button.isEnabled(), "aplicada uma vez")

    def test_3_escape_archive_and_hidden_clock(self):
        page = self.controller.open_tardis()
        room = page.room
        room.select_panel("telemetria")
        self.assertEqual(room.scene.selected, "telemetria")
        unhandled = []
        room.escape_unhandled.connect(lambda: unhandled.append(True))
        room._escape()
        self.assertEqual(room.scene.selected, "", "Esc fecha o painel escolhido")
        room._escape()
        self.assertEqual(unhandled, [True], "sem painel, o Esc vai para a plataforma")
        self.assertIsNone(page.authorization, "na sala vale a barra de autorização da plataforma")
        archive = self.controller.open_archive("tasks")
        self.pump(0.3)
        self.assertEqual(page.mode, "arquivo")
        self.assertTrue(archive.isVisible())
        self.assertFalse(room.isVisible())
        self.assertIs(page.authorization, archive.authorization)
        self.assertEqual(archive.back_button.text(), "← SALA DE CONTROLE")
        archive.back_button.click()
        self.pump(0.2)
        self.assertEqual(page.mode, "sala")
        self.assertTrue(room.isVisible())
        self.controller.open_page("atividades")
        self.pump(0.15)
        self.assertFalse(room._clock.isActive(), "fora da tela: nenhum quadro")

    def test_4_renderer_picking_cache_and_profiles(self):
        from PySide6 import QtGui

        from ultron.hud.tardis_room.scene import RoomScene
        from ultron.hud.tardis_room.view import Camera, RoomRenderer, quality_for
        scene = RoomScene()
        scene.set_motes(40)
        renderer = RoomRenderer()
        image = QtGui.QImage(960, 540, QtGui.QImage.Format_RGB32)
        for name in ("economy", "balanced", "high", "cinematic"):
            for mode in ("repouso", "processando", "operacao", "jarvis", "falha"):
                scene.set_engine_state({"mode": mode, "fault": mode == "falha", "fault_text": "teste",
                                        "running": {"kind_label": "consulta"} if mode == "jarvis" else None})
                scene.step(0.1)
                painter = QtGui.QPainter(image)
                renderer.render(painter, 960, 540, scene, quality=quality_for(name), effects=name != "economy")
                painter.end()
        painter = QtGui.QPainter(image)
        renderer.render(painter, 960, 540, scene, quality=quality_for("balanced"), effects=True)
        painter.end()
        before = renderer.static_renders
        for _ in range(5):
            scene.step(1 / 30)
            painter = QtGui.QPainter(image)
            renderer.render(painter, 960, 540, scene, quality=quality_for("balanced"), effects=True)
            painter.end()
        self.assertEqual(renderer.static_renders, before, "câmera parada: paredes, piso e console vêm do cache")
        cam = Camera(scene.azimuth, 960, 540)
        geometry = {p["key"]: p for p in renderer._panel_geometry(cam)}
        front = min(geometry.values(), key=lambda p: p["depth"])
        x, y = float(front["sx"].mean()), float(front["sy"].mean())
        self.assertEqual(renderer.panel_at(x, y), front["key"], "clique no painel da frente o escolhe")
        self.assertEqual(renderer.panel_at(3, 3), "")

    def test_5_paint_cost_is_bounded(self):
        """Custo medido aqui é do contêiner offscreen (CPU), não de uma máquina Windows real."""
        from PySide6 import QtGui

        from ultron.hud.tardis_room.scene import RoomScene
        from ultron.hud.tardis_room.view import RoomRenderer, quality_for
        scene = RoomScene()
        scene.set_motes(40)
        scene.set_engine_state({"mode": "processando", "queued": 1})
        renderer = RoomRenderer()
        image = QtGui.QImage(1280, 720, QtGui.QImage.Format_RGB32)
        times = []
        for _ in range(25):
            scene.step(1 / 30)
            started = time.perf_counter()
            painter = QtGui.QPainter(image)
            renderer.render(painter, 1280, 720, scene, quality=quality_for("balanced"), effects=True)
            painter.end()
            times.append(time.perf_counter() - started)
        times.sort()
        self.assertLess(times[len(times) // 2], 0.06, f"mediana {times[len(times) // 2] * 1000:.1f} ms")


if __name__ == "__main__":
    unittest.main()
