"""Plataforma JARVIS ULTIMATE com o núcleo real (Qt offscreen, Ollama simulado, banco temporário).

Cobre: navegação entre os seis módulos sem perder estado, transição holográfica, indicadores lidos do
estado real, conversa com horários e botões do original, Esc/PARAR, histórico de atividades na tela,
configurações (validação, consentimento da OpenAI, permissões com pisos, restaurar padrões),
diagnósticos (console de eventos, log), Observador/privacidade, cobertura da tela, orbe e encerramento.
Não é teste de GPU, de microfone real nem de janela real do Windows.
"""
import logging
import threading
import time
import unittest

import helpers

from fake_ollama import FakeOllama


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class PlatformTest(unittest.TestCase):
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
        manager.settings.mic_name = "Microfone do usuário"
        cls.manager = manager
        cls.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
        cls.controller = HudController(cls.core)
        cls.controller.show()
        cls.window = cls.controller.window
        threading.Thread(target=cls.core.boot, daemon=True).start()
        cls.pump_until(lambda: cls.core.booted, 30)
        cls.pump(0.4)

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

    def setUp(self):
        self.controller.open_page("jarvis")
        self.pump(0.05)

    # ------------------------------------------------------------ navegação
    def test_01_navigation_creates_pages_once_and_preserves_state(self):
        from ultron.hud.platform import NAV_KEYS
        created = {}
        for key in NAV_KEYS:
            page = self.controller.open_page(key)
            self.pump(0.05)
            self.assertEqual(self.window.current_key, key)
            self.assertTrue(page.isVisible(), key)
            created[key] = page
        tardis = self.controller.open_page("tardis")
        tardis.open_region("tasks")                      # abre o ARQUIVO (memória espacial) na região
        self.pump(0.3)
        self.assertEqual(tardis.mode, "arquivo")
        self.controller.open_page("atividades")
        self.pump(0.1)
        self.assertFalse(tardis.isVisible())
        self.assertFalse(tardis.archive._clock.isActive(), "TARDIS fora da tela: nenhum quadro")
        self.assertFalse(tardis.room._clock.isActive(), "sala de controle fora da tela: nenhum quadro")
        again = self.controller.open_page("tardis")
        self.assertIs(again, created["tardis"], "a página não é recriada")
        self.assertEqual(again.mode, "arquivo", "volta como estava")
        self.assertEqual(again.archive._region, "tasks", "a região aberta continua como estava")
        for key in NAV_KEYS:
            self.assertIs(self.window.page(key), created[key])

    def test_02_shortcuts_and_window_title(self):
        from PySide6 import QtGui
        expected = {"F1": "jarvis", "F2": "tardis", "F4": "noctario", "F5": "atividades", "F6": "configuracoes",
                    "F3": "diagnosticos", "F7": "diagnosticos"}
        shortcuts = {s.key().toString(): s for s in self.window.findChildren(QtGui.QShortcut)
                     if s.parent() is self.window}
        for key, page in expected.items():
            shortcuts[key].activated.emit()
            self.pump(0.02)
            self.assertEqual(self.window.current_key, page, key)
        self.assertIn("DIAGNÓSTICOS", self.window.windowTitle())
        shortcuts["F1"].activated.emit()
        self.assertEqual(self.window.windowTitle(), "J.A.R.V.I.S.")
        self.assertTrue(self.window.escape.isEnabled(), "fora do TARDIS, Esc é da plataforma")
        shortcuts["F2"].activated.emit()
        self.assertFalse(self.window.escape.isEnabled(), "no TARDIS, Esc fecha a região aberta (sem conflito)")
        shortcuts["F1"].activated.emit()

    def test_03_holographic_transition_follows_the_effects_setting(self):
        self.manager.update(heavy_effects=True)
        runs = self.window.overlay.runs
        self.controller.open_page("atividades")
        self.assertEqual(self.window.overlay.runs, runs + 1)
        self.assertTrue(self.window.overlay.running)
        self.assertTrue(self.pump_until(lambda: not self.window.overlay.running, 2))
        self.assertFalse(self.window.overlay.isVisible(), "a projeção some ao terminar")
        self.manager.update(heavy_effects=False)
        try:
            self.controller.open_page("jarvis")
            self.assertEqual(self.window.overlay.runs, runs + 1, "sem efeitos pesados: troca imediata")
        finally:
            self.manager.update(heavy_effects=True)

    # ------------------------------------------------------------ indicadores
    def test_04_chips_come_from_real_state(self):
        from ultron.hud.platform import compute_chips

        def chips(state, **kw):
            return {c.key: c for c in compute_chips(self.core, state, **kw)}

        base = chips({})
        self.assertEqual(base["mic"].value, "—", "voz desligada nesta execução: sem número inventado")
        self.assertEqual(base["noct"].value, "SEM CONEXÃO")
        self.assertNotIn("bat", base, "sem bateria lida: o indicador não aparece")
        self.assertEqual(base["net"].value, "—")
        offline = chips({"models": {"ollama_alive": False, "error": "recusado"}})
        self.assertEqual((offline["ai"].value, offline["ai"].level), ("OFFLINE", "error"))
        online = chips({"models": {"ollama_alive": True}, "active_model": "qwen2.5:3b",
                        "network_state": {"online": True, "wifi": {"ssid": "Casa", "signal": 70}, "ipv4": "10.0.0.2"},
                        "telemetry": {"battery": {"percent": 12, "plugged": False}, "net_rx_bps": 2048}})
        self.assertEqual(online["ai"].value, "qwen2.5:3b")
        self.assertEqual(online["net"].label, "Wi-Fi")
        self.assertEqual(online["net"].value, "Casa 70%")
        self.assertEqual((online["bat"].value, online["bat"].level), ("12%", "error"))
        self.assertIn("2.0 KB/s", online["net"].tip)
        self.assertEqual(chips({"observer": {"mode": "observer"}}, covering=True)["obs"].value, "SUSPENSO")
        self.assertEqual(chips({"observer": {"mode": "observer", "paused": True}})["obs"].value, "PAUSADO")
        self.assertTrue(chips({})["session"].value.endswith("LOCAL"))
        self.window.refresh_chips()
        self.assertEqual(self.window.chips.value("noct"), "SEM CONEXÃO")

    def test_05_covering_the_screen_suspends_observation(self):
        from PySide6 import QtCore
        from ultron.hud.platform import covers_screen
        area = QtCore.QRect(0, 0, 1920, 1040)
        self.assertTrue(covers_screen(QtCore.QRect(0, 0, 1700, 1000), area))
        self.assertFalse(covers_screen(QtCore.QRect(100, 100, 900, 600), area), "janela pequena: observa")
        self.assertFalse(covers_screen(QtCore.QRect(3000, 0, 1900, 1000), area), "em outro monitor: não cobre")
        self.window.showFullScreen()
        self.pump(0.1)
        self.window.refresh_chips()
        self.assertTrue(self.core.hud_probe(), "tela cheia: a interface cobre a tela")
        self.window.showNormal()
        self.window.hide()
        self.window.refresh_chips()
        self.assertFalse(self.core.hud_probe(), "oculta: não cobre nada")
        self.controller.expand()
        self.pump(0.1)

    # ------------------------------------------------------------ conversa, Esc e PARAR
    def test_06_conversation_has_times_buttons_and_copy(self):
        from PySide6 import QtGui
        conversation = self.window.conversation
        conversation.clear()
        self.core.submit("que horas são?", source="text")
        self.assertTrue(self.pump_until(lambda: "J.A.R.V.I.S." in conversation.text(), 10))
        text = conversation.text()
        self.assertRegex(text, r"\[\d\d:\d\d\] VOCÊ \(texto\) ▸ que horas são\?")
        self.assertRegex(text, r"\[\d\d:\d\d\] J.A.R.V.I.S. ▸ São ")
        self.assertTrue(conversation.copy_last())
        self.assertTrue(QtGui.QGuiApplication.clipboard().text().startswith("São "))
        conversation.clear()
        conversation.time_button.click()
        self.assertTrue(self.pump_until(lambda: "J.A.R.V.I.S." in conversation.text(), 10), "HORAS → núcleo")
        shortcut = next(s for s in self.window.findChildren(QtGui.QShortcut) if s.key().toString() == "Ctrl+L")
        shortcut.activated.emit()
        self.assertEqual(conversation.text(), "", "Ctrl+L limpa a conversa")

    def test_07_escape_and_stop_follow_the_original(self):
        req = self.core.authorizations.request("teste", skill="test.x", risk="high")
        self.assertEqual(self.controller.escape(), "cancel", "Esc cancela o que está pendente")
        self.assertEqual(req.status, "cancelled")
        self.window.showFullScreen()
        self.pump(0.1)
        self.assertEqual(self.controller.escape(), "fullscreen")
        self.pump(0.1)
        self.assertFalse(self.window.isFullScreen())
        self.assertEqual(self.controller.escape(), "", "nunca minimiza")
        self.assertTrue(self.window.isVisible())
        self.window.conversation.clear()
        self.controller.stop()
        self.assertIn("não havia nada em andamento", self.window.conversation.text())

    def test_08_input_history_keeps_draft_and_skips_repeats(self):
        from PySide6 import QtCore, QtGui
        bar = self.window.input
        submitted = []
        bar.submitted.connect(submitted.append)
        try:
            for text in ("primeiro pedido", "primeiro pedido"):
                bar.line.setText(text)
                bar.send.click()
            self.assertEqual(submitted, ["primeiro pedido", "primeiro pedido"])
            self.assertEqual(bar._history.count("primeiro pedido"), 1, "a última não se repete no histórico")
            bar.line.setText("rascunho")
            up = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Up, QtCore.Qt.NoModifier)
            down = QtGui.QKeyEvent(QtCore.QEvent.KeyPress, QtCore.Qt.Key_Down, QtCore.Qt.NoModifier)
            bar.eventFilter(bar.line, up)
            self.assertEqual(bar.line.text(), "primeiro pedido")
            bar.eventFilter(bar.line, down)
            self.assertEqual(bar.line.text(), "rascunho", "o rascunho volta")
        finally:
            bar.submitted.disconnect(submitted.append)
            bar.line.clear()
            self.pump(1.0)

    # ------------------------------------------------------------ atividades
    def test_09_activity_page_shows_requests_live(self):
        page = self.controller.open_page("atividades")
        self.assertTrue(self.pump_until(lambda: page.loaded_once, 5))
        self.core.submit("que horas são?", source="text")
        self.assertTrue(self.pump_until(lambda: any(r["kind"] == "pedido" and r["input"] == "que horas são?"
                                                    and r["final"] for r in page.model.rows), 10),
                        "o pedido aparece e termina na tela sem recarregar")
        page.kind.setCurrentIndex(page.kind.findData("erro"))
        self.assertTrue(self.pump_until(lambda: all(r["kind"] == "erro" for r in page.model.rows), 5))
        page.kind.setCurrentIndex(0)
        self.assertTrue(self.pump_until(lambda: any(r["kind"] == "pedido" for r in page.model.rows), 5))
        self.assertIn("Pedido", page.visible_text())

    def test_10_clearing_history_needs_confirmation(self):
        page = self.controller.open_page("atividades")
        self.assertTrue(self.pump_until(lambda: page.loaded_once, 5))
        before = self.core.activity.count()
        self.assertGreater(before, 0)
        page.request_clear()
        self.assertTrue(self.pump_until(lambda: self.core.authorizations.pending() is not None, 5))
        pending = self.core.authorizations.pending()
        self.assertEqual(pending.permission, "apagar_dados")
        self.assertTrue(self.pump_until(lambda: self.window.authorization.isVisibleTo(self.window), 3),
                        "barra de decisão da plataforma")
        self.core.authorizations.resolve(False, by="teste")
        self.assertTrue(self.pump_until(lambda: "mantido" in page.status.text(), 5))
        self.assertGreaterEqual(self.core.activity.count(), before, "negado: nada apagado")
        page.request_clear()
        self.assertTrue(self.pump_until(lambda: self.core.authorizations.pending() is not None, 5))
        self.core.authorizations.resolve(True, by="teste")
        self.assertTrue(self.pump_until(lambda: "apagado" in page.status.text(), 5))
        self.assertLessEqual(self.core.activity.count(), 2)

    # ------------------------------------------------------------ configurações
    def test_11_settings_bind_validate_and_restore(self):
        from PySide6 import QtWidgets
        page = self.controller.open_page("configuracoes")
        page._ask = lambda title, text: True
        captions = next(b for b in page.findChildren(QtWidgets.QCheckBox) if b.text().startswith("Legendas"))
        captions.click()
        self.assertEqual(self.manager.settings.captions, captions.isChecked())
        address = next(w for w in page.findChildren(QtWidgets.QLineEdit)
                       if w.placeholderText() == "AA:BB:CC:DD:EE:FF")
        address.setText("isto não é um endereço")
        address.editingFinished.emit()
        self.assertEqual(self.manager.settings.noctario_address, "")
        self.assertIn("recusado", page.status.text())
        self.assertEqual(address.text(), "", "o controle volta ao valor efetivo")
        page.permission_boxes["arquivos"].setCurrentIndex(page.permission_boxes["arquivos"].findData("bloquear"))
        page._choose_permission("arquivos")
        self.assertIn("arquivos=bloquear", self.manager.settings.permission_policy)
        delete_box = page.permission_boxes["apagar_dados"]
        self.assertFalse(delete_box.model().item(delete_box.findData("permitir")).isEnabled(), "piso: confirmar")
        self.manager.update(permission_policy=[])
        page.reset_defaults()
        self.assertEqual(self.manager.settings.mic_name, "Microfone do usuário", "microfone mantido ao restaurar")
        self.assertEqual(self.manager.settings.captions, True)
        self.assertTrue(list(self.manager.path.parent.glob("settings.backup-*.json")), "cópia guardada antes")

    def test_12_openai_needs_explicit_consent(self):
        page = self.controller.open_page("configuracoes")
        page._ask = lambda title, text: False
        page._choose_provider("openai")
        self.assertEqual(self.manager.settings.ai_provider, "ollama", "sem consentimento: nada muda")
        self.assertEqual(self.manager.settings.privacy_mode, "local")
        page._ask = lambda title, text: "OpenAI" in text
        page._choose_provider("openai")
        try:
            self.assertEqual((self.manager.settings.ai_provider, self.manager.settings.privacy_mode,
                              self.manager.settings.allow_external_models), ("openai", "standard", True))
            self.assertIn("bloqueada", page.provider_state.text(), "sem chave: o Ollama local continua respondendo")
        finally:
            self.manager.update(ai_provider="ollama", privacy_mode="local", allow_external_models=False)

    # ------------------------------------------------------------ diagnósticos
    def test_13_diagnostics_console_filter_copy_clear(self):
        from PySide6 import QtGui
        self.controller.open_systems("eventos")
        console = self.controller.systems.console
        self.assertTrue(any("SYSTEM_READY" in line for line in console.entries),
                        "eventos anteriores à abertura da página também aparecem")
        self.core.bus.publish(__import__("ultron.core.events", fromlist=["EventType"]).EventType.NOTIFICATION,
                              {"title": "Teste do console"}, source="teste")
        self.assertTrue(self.pump_until(lambda: any("Teste do console" in line for line in console.entries), 5))
        console.filter.setText("teste do CONSOLE")
        self.assertEqual(len(console.visible_lines()), 1)
        console.copy_visible()
        self.assertIn("Teste do console", QtGui.QGuiApplication.clipboard().text())
        console.filter.clear()
        console.clear()
        self.assertEqual(console.entries.__len__(), 0)
        self.controller.open_systems("log")
        viewer = self.controller.systems.log_viewer
        self.assertTrue(self.pump_until(lambda: viewer.status.text() and "Lendo" not in viewer.status.text(), 5))
        self.controller.open_systems("network")
        self.assertTrue(self.controller.systems.isVisible())

    def test_14_observer_and_privacy_from_the_interface(self):
        self.controller._observer("observer")
        self.assertEqual(self.manager.settings.observer_mode, "observer")
        self.controller._observer("pause")
        self.pump_until(lambda: (self.controller.state_cache.get("observer") or {}).get("paused"), 3)
        self.controller._observer("off")
        self.assertEqual(self.manager.settings.observer_mode, "off")
        self.controller._privacy(True)
        self.assertTrue(self.core.privacy_shield)
        self.window.refresh_chips()
        self.assertEqual(self.window.chips.value("obs"), "SUSPENSO")
        self.controller._privacy(False)
        self.assertFalse(self.core.privacy_shield)

    # ------------------------------------------------------------ orbe, bandeja e encerramento
    def test_15_orb_remembers_where_it_was_left(self):
        from PySide6 import QtCore
        self.controller._orb_moved(QtCore.QPoint(100, 120))
        self.assertEqual(tuple(self.manager.settings.orb_position), ("100", "120"))
        self.controller.orb.move(0, 0)
        self.controller.collapse()
        self.pump(0.1)
        self.assertEqual(self.controller.orb.pos(), QtCore.QPoint(100, 120))
        self.controller.expand()
        self.pump(0.1)
        self.assertFalse(self.controller.orb.isVisible())
        self.assertTrue(self.window.isVisible())

    def test_16_tray_menu_reads_real_state(self):
        menu = self.controller._menu()
        labels = [a.text() for a in menu.actions()]
        for expected in ("Reiniciar voz", "Iniciar com o Windows", "Observador", "Diagnósticos", "Sair"):
            self.assertIn(expected, labels)
        startup = next(a for a in menu.actions() if a.text() == "Iniciar com o Windows")
        from ultron.platform import autostart
        self.assertEqual(startup.isEnabled(), autostart.supported())

    def test_17_shutdown_request_closes_the_interface(self):
        from ultron.core.events import EventType
        calls = []
        original = self.controller.quit
        self.controller.quit = lambda: calls.append(time.time())
        try:
            self.core.bus.publish(EventType.SHUTDOWN_REQUESTED, {"reason": "teste"}, source="teste")
            self.assertTrue(self.pump_until(lambda: calls, 5), "a interface fecha depois da fala de despedida")
        finally:
            self.controller.quit = original


class VoiceNavigationTest(unittest.TestCase):
    def test_pages_open_by_voice_and_old_commands_keep_their_meaning(self):
        from ultron.cognition.intent_engine import IntentEngine
        engine = IntentEngine()
        cases = {"abra as configurações do jarvis": ("control", {"open_view": "configuracoes"}),
                 "mostre o histórico de atividades": ("control", {"open_view": "atividades"}),
                 "abra o console de eventos": ("control", {"open_view": "diagnosticos", "section": "eventos"}),
                 "abra o log do jarvis": ("control", {"open_view": "diagnosticos", "section": "log"}),
                 "abra o noctário": ("control", {"open_view": "noctario"}),
                 "volte para o jarvis": ("control", {"open_view": "jarvis"})}
        for phrase, (kind, args) in cases.items():
            intent = engine.classify(phrase)
            self.assertEqual((intent.kind, intent.args), (kind, args), phrase)
        self.assertEqual(engine.classify("abra as configurações").skill, "app.open",
                         "sem o nome do JARVIS continua abrindo as configurações do Windows (original)")
        self.assertEqual(engine.classify("diagnóstico do jarvis").skill, "diagnostics.health")
        self.assertEqual(engine.classify("o que você fez hoje?").skill, "activity.recent")


class AudioOutputSelectionTest(unittest.TestCase):
    def test_chosen_output_by_name_then_index_then_default(self):
        from ultron.voice.audio import AudioOutput
        devices = [{"index": 3, "name": "Alto-falantes (Realtek)"}, {"index": 7, "name": "Fone USB"}]
        out = AudioOutput(device_name="fone")
        self.assertEqual(out._choose(devices, 3)["index"], 7)
        out = AudioOutput(device_index=3)
        self.assertEqual(out._choose(devices, 7)["index"], 3)
        out = AudioOutput()
        self.assertIsNone(out._choose(devices, None), "sem escolha nem padrão: a biblioteca decide")
        self.assertEqual(AudioOutput(device_name="inexistente")._choose(devices, 3)["index"], 3)

    def test_listing_never_raises(self):
        from ultron.voice.audio import list_output_devices
        result = list_output_devices()
        self.assertIn("devices", result)
        self.assertIn("errors", result)


class ExceptionHooksTest(unittest.TestCase):
    def test_unhandled_thread_exception_goes_to_the_log(self):
        import sys
        from ultron import app
        old = sys.excepthook, threading.excepthook
        try:
            app.install_exception_hooks()
            with self.assertLogs("ultron", level=logging.CRITICAL) as logs:
                worker = threading.Thread(target=lambda: 1 / 0, name="falha-proposital")
                worker.start()
                worker.join()
            self.assertTrue(any("falha-proposital" in line and "ZeroDivisionError" in line for line in logs.output))
        finally:
            sys.excepthook, threading.excepthook = old


if __name__ == "__main__":
    unittest.main()
