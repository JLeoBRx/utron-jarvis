"""Os dois hubs com o núcleo real (Qt offscreen, Ollama simulado, banco temporário).

Cobre: abrir e fechar o JARVIS CORE e o TARDIS, regiões com dados REAIS do banco, comunicação
pelos eventos do núcleo (registro criado → TARDIS e CORE reagem), voltar ao CORE sem perder o
estado do TARDIS, ações pelo núcleo (nunca direto no banco), perfis de qualidade e encerramento
sem threads penduradas. Não é teste de GPU nem de janela real do Windows.
"""
import datetime as dt
import threading
import time
import unittest

import helpers

from fake_ollama import FakeOllama


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class HubsIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets

        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.hud.controller import HudController

        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.fake = FakeOllama(["qwen2.5:3b"], responder=lambda payload: "Resposta local.")
        cls.fake.__enter__()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = cls.fake.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        cls.threads_before = {t.ident for t in threading.enumerate()}
        cls.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
        cls.controller = HudController(cls.core)
        cls.controller.show()
        threading.Thread(target=cls.core.boot, daemon=True).start()
        cls.pump_until(lambda: cls.core.booted, 30)
        cls.pump(0.5)

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

    def test_1_tardis_regions_show_real_records(self):
        sb = self.core.second_brain
        tomorrow = sb.now_wall().replace(hour=10, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)
        sb.create("task", "Revisar contrato", when=tomorrow, priority=3)
        sb.create("task", "Pagar conta atrasada", when=sb.now_wall().date() - dt.timedelta(days=2), priority=4)
        sb.create("idea", "Painel solar portátil", project="Atlas")
        sb.create("event", "Reunião de equipe", when=tomorrow + dt.timedelta(hours=4), remind=False)
        sb.create("event", "Dentista", when=tomorrow + dt.timedelta(hours=4, minutes=30), remind=False)
        sb.create("note", "Livro recomendado: Pense de novo")
        self.controller.open_tardis()
        tardis = self.controller.second
        self.assertTrue(self.pump_until(lambda: "tardis" in tardis.loaded_once, 10), "regiões lidas do banco")
        regions = tardis.scene.regions
        self.assertEqual(regions["tasks"].count, 2)
        self.assertTrue(regions["tasks"].alert, "tarefa atrasada acende o alerta")
        self.assertEqual(regions["ideas"].count, 1)
        self.assertEqual(regions["projects"].count, 1, "o projeto Atlas nasceu com a ideia")
        self.assertEqual(regions["agenda"].count, 2)
        self.assertTrue(regions["agenda"].alert, "conflito de horário aparece na região de compromissos")
        self.assertIn("conflito", regions["agenda"].detail)
        self.assertEqual({i["title"] for i in regions["memories"].items}, {"Livro recomendado: Pense de novo"})
        self.assertTrue(tardis.isVisible())

    def test_2_real_event_reaches_both_hubs(self):
        tardis = self.controller.second or self.controller.open_tardis() or self.controller.second
        tardis.scene.pulses.clear()
        before_core = len(self.controller.scene.modules)
        self.core.second_brain.create("task", "Comprar cabos")
        self.assertTrue(self.pump_until(lambda: tardis.scene.pulses or tardis.scene.events, 5),
                        "o TARDIS recebeu o evento real")
        self.assertTrue(self.pump_until(lambda: "secondbrain" in self.controller.scene.modules, 5),
                        "o CORE mostra o módulo do Second Brain")
        self.assertGreaterEqual(len(self.controller.scene.modules), before_core)
        self.assertTrue(self.pump_until(lambda: tardis.scene.regions["tasks"].count == 3, 10),
                        "a contagem da região é relida do banco")

    def test_3_return_to_core_preserves_tardis_state(self):
        self.controller.open_tardis()
        tardis = self.controller.second
        tardis.open_region("tasks")
        self.pump(0.5)
        self.controller.return_to_core()
        self.pump(0.3)
        self.assertFalse(tardis.isVisible())
        self.assertTrue(self.controller.window.isVisible())
        self.assertEqual(tardis._region, "tasks", "a região aberta continua guardada")
        self.assertFalse(tardis._clock.isActive(), "oculto: o relógio do TARDIS para (nenhum quadro)")
        self.controller.open_tardis()
        self.pump(0.4)
        self.assertEqual(tardis._region, "tasks")
        self.assertTrue(tardis.isVisible())

    def test_4_actions_go_through_the_core_and_are_verified(self):
        tardis = self.controller.second
        tardis.capture.setText("anote uma ideia: horta vertical na varanda")
        tardis._capture()
        self.assertTrue(self.pump_until(lambda: not tardis.feedback.text().endswith("…"), 15),
                        "a ação terminou: " + tardis.feedback.text())
        found = self.core.second_brain.search("horta vertical")
        self.assertEqual(len(found), 1)
        text = tardis.feedback.text()
        self.assertIn("registrada", text.lower())
        self.assertNotIn("sem confirmação", text, "a skill releu o registro do banco (verificação independente)")
        self.assertIn("created", [h["action"] for h in self.core.second_brain.history(found[0].id)])

    def test_5_profiles_and_systems_panel(self):
        from ultron.hud import quality
        for name in quality.NAMES:
            self.controller.set_profile(name)
            self.pump(0.15)
            self.assertEqual(self.controller.second.profile.name, name, "o TARDIS segue o perfil do CORE")
            self.assertEqual(len(self.controller.second.scene.particles), quality.get(name).max_particles)
        self.controller.set_profile("balanced")
        self.controller.open_systems("network")
        self.pump(0.5)
        self.assertTrue(self.controller.systems.isVisible())
        self.controller.open_systems("voice")
        self.pump(0.3)
        self.controller.systems.hide()

    def test_6_shutdown_leaves_no_worker_behind(self):
        names = {t.name for t in threading.enumerate()}
        self.assertTrue(any(n.startswith("ultron-") for n in names), "núcleo rodando")


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class ShutdownTest(unittest.TestCase):
    def test_core_and_hubs_stop_their_threads(self):
        from PySide6 import QtCore, QtWidgets

        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.hud.controller import HudController

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        before = {t.ident for t in threading.enumerate()}
        with FakeOllama(["qwen2.5:3b"], responder=lambda payload: "ok") as fake:
            manager = SettingsManager(helpers.temp_dir() / "settings.json")
            manager.load()
            manager.settings.ollama_url = fake.url
            manager.settings.network_discovery = False
            manager.settings.auto_backup = False
            core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
            controller = HudController(core)
            controller.show()
            core.boot()
            controller.open_tardis()
            controller.open_systems()
            end = time.time() + 1.0
            while time.time() < end:
                app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            controller.quit()
            core.shutdown()
            end = time.time() + 3.0
            while time.time() < end:
                app.processEvents(QtCore.QEventLoop.AllEvents, 20)
                left = [t for t in threading.enumerate() if t.ident not in before and t.is_alive()
                        and not t.name.startswith("Thread-") and "serve_forever" not in t.name]
                if not left:
                    break
                time.sleep(0.05)
        self.assertEqual([t.name for t in left], [], "nenhuma thread do JARVIS ficou viva após o encerramento")


if __name__ == "__main__":
    unittest.main()
