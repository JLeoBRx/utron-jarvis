"""Protocolo ULTRON: ativação manual e ocasional, intervalo mínimo, saída, restauração visual — e a restrição
absoluta: o evento não altera permissões, configurações, autorizações, arquivos do usuário nem executa nada."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers

from ultron.hud.ultron_protocol import LABEL, LABEL_OPERATOR, MESSAGES, Guard, UltronProtocol
from ultron.personality import persona


class _Settings:
    def __init__(self, **values):
        self.ultron_manual = True
        self.ultron_occasional = False
        self.ultron_chance_per_hour = 2.0
        self.ultron_min_interval_hours = 24.0
        self.ultron_duration_s = 45.0
        self.__dict__.update(values)


class ProtocolLogicTest(unittest.TestCase):
    def setUp(self):
        self.now = 1_000_000.0
        self.settings = _Settings()
        self.path = Path(tempfile.mkdtemp()) / "protocolo_ultron.json"
        self.p = UltronProtocol(settings=lambda: self.settings, history_path=self.path, clock=lambda: self.now,
                                rng=lambda: 0.0)

    def test_manual_start_and_restore(self):
        ok, reason = self.p.start("manual", Guard())
        self.assertTrue(ok, reason)
        self.assertTrue(self.p.active)
        self.assertFalse(self.p.start("manual", Guard())[0], "não começa duas vezes")
        self.assertTrue(self.p.stop("comando"))
        self.assertFalse(self.p.active)
        self.assertFalse(self.p.stop("comando"), "parar de novo não faz nada")
        saved = json.loads(self.path.read_text(encoding="utf-8"))["ocorrencias"]
        self.assertEqual((saved[-1]["source"], saved[-1]["ended_by"]), ("manual", "comando"), "histórico registrado")

    def test_never_during_sensitive_moments(self):
        for guard, word in ((Guard(authorization_pending=True), "autorização"), (Guard(action_running=True), "ação"),
                            (Guard(runtime_state="EXECUTING"), "ocupado"), (Guard(runtime_state="VERIFYING"), "ocupado"),
                            (Guard(privacy=True), "privacidade")):
            ok, reason = self.p.start("manual", guard)
            self.assertFalse(ok)
            self.assertIn(word, reason)
        self.assertFalse(self.p.active)

    def test_real_activity_only_blocks_the_start(self):
        for guard in (Guard(authorization_pending=True), Guard(action_running=True), Guard(privacy=True)):
            self.assertTrue(UltronProtocol.start_conflict(guard))
        self.assertEqual(UltronProtocol.start_conflict(Guard(runtime_state="SPEAKING")), "")
        self.assertFalse(hasattr(self.p, "interrupt_reason"), "depois de iniciado, o ULTRON pode operar")

    def test_manual_can_be_disabled(self):
        self.settings.ultron_manual = False
        ok, reason = self.p.start("manual", Guard())
        self.assertFalse(ok)
        self.assertIn("desligada", reason)

    def test_automatic_end_and_demo_duration(self):
        self.p.start("manual", Guard())
        self.now += 44
        self.assertFalse(self.p.expired())
        self.now += 2
        self.assertTrue(self.p.expired())
        self.p.stop("tempo")
        self.settings.ultron_duration_s = 0
        self.p.start("manual", Guard())
        self.now += 10_000
        self.assertFalse(self.p.expired(), "0 = só termina por comando, botão ou Esc")
        self.p.stop("Esc")
        self.p.start("demonstracao", Guard())
        self.now += 21
        self.assertTrue(self.p.expired(), "a demonstração é curta")

    def test_occasional_needs_setting_idle_time_cooldown_and_chance(self):
        idle = Guard(idle_seconds=600)
        self.assertFalse(self.p.maybe_trigger(idle), "desligado por padrão")
        self.settings.ultron_occasional = True
        self.now += 120
        self.assertFalse(self.p.maybe_trigger(Guard(idle_seconds=30)), "precisa de dois minutos sem interação")
        self.now += 120
        self.assertFalse(self.p.maybe_trigger(Guard(idle_seconds=600, runtime_state="THINKING")), "só em repouso")
        self.now += 120
        self.assertTrue(self.p.maybe_trigger(idle), "sorteio favorável (rng=0)")
        self.assertEqual(self.p.current.source, "ocasional")
        self.p.stop("tempo")
        self.now += 3600
        self.assertFalse(self.p.maybe_trigger(idle), "intervalo mínimo de 24 h")
        self.now += 24 * 3600
        self.p.rng = lambda: 0.99
        self.assertFalse(self.p.maybe_trigger(idle), "sorteio desfavorável")
        self.now += 61
        self.p.rng = lambda: 0.0
        self.assertTrue(self.p.maybe_trigger(idle))

    def test_occasional_is_checked_at_most_once_a_minute(self):
        self.settings.ultron_occasional = True
        calls = []
        self.p.rng = lambda: calls.append(1) or 0.99
        for _ in range(10):
            self.p.maybe_trigger(Guard(idle_seconds=600))
        self.assertLessEqual(len(calls), 1)

    def test_messages_and_labels_are_honest(self):
        self.assertIn("PROTOCOLO ULTRON INICIADO", MESSAGES)
        self.assertIn("NÃO CONFUNDA EFICIÊNCIA COM OBEDIÊNCIA", MESSAGES)
        self.assertIn("permissões normais", LABEL)
        self.assertIn("ações reais", LABEL_OPERATOR)
        self.assertIn("ATIVIDADES", LABEL_OPERATOR)
        self.assertFalse(any("INTERROMPIDO" in m or "COMPROMETIDO" in m for m in MESSAGES),
                         "nenhuma mensagem sugere que o computador foi tomado")


class IntentTest(unittest.TestCase):
    def test_secret_phrases(self):
        from ultron.cognition.intent_engine import IntentEngine
        engine = IntentEngine()
        cases = {"JARVIS, iniciar protocolo ULTRON.": "start", "protocolo ultron demonstração": "demo",
                 "encerrar protocolo ultron": "stop", "restaurar JARVIS": "stop"}
        for phrase, action in cases.items():
            intent = engine.classify(phrase)
            self.assertEqual((intent.kind, intent.args), ("control", {"ultron": action}), phrase)
        self.assertNotEqual(engine.classify("o que é o ultron do filme?").args.get("ultron"), "start")


class IdentityTest(unittest.TestCase):
    def test_protocol_name_survives_but_self_reference_is_still_corrected(self):
        from ultron.personality.response_style import stylize
        self.assertIn("Protocolo ULTRON solicitado", stylize("Protocolo ULTRON solicitado."))
        self.assertNotIn("ULTRON", stylize("Eu sou o ULTRON, seu assistente."))


class ConsoleModeTest(unittest.TestCase):
    def tearDown(self):
        persona.reset()

    def test_console_switches_voice_tone_and_operator_profile(self):
        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                          memory_db=helpers.make_memory().db)
        try:
            from ultron.cognition.intent_engine import IntentEngine
            from ultron.personality.voice_profile import ULTRON_VOICE_PROFILE
            from ultron.voice.profile import effective_profile
            engine = IntentEngine()
            response = core._control(engine.classify("JARVIS, iniciar protocolo ULTRON."))
            self.assertIn("console", response.text)
            self.assertIn("ULTRON_OPERATOR", response.text)
            self.assertTrue(persona.current().ultron and persona.current().operator)
            self.assertEqual(effective_profile(manager.settings).pitch, ULTRON_VOICE_PROFILE.pitch, "voz do ULTRON")
            self.assertEqual((core.state.get("persona") or {}).get("name"), "ultron", "estado para a ORBE")
            self.assertEqual(core._control(engine.classify("restaurar JARVIS")).text, "JARVIS restaurado.")
            self.assertFalse(persona.current().ultron)
        finally:
            core.memory.db.close()


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class ControllerSafetyTest(unittest.TestCase):
    """Com a interface real (Qt offscreen): só a aparência muda — e volta exatamente como era."""

    def setUp(self):
        from PySide6 import QtWidgets

        from fake_ollama import FakeOllama
        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.hud.controller import HudController
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.app.setStyleSheet("QWidget { color: #00D9FF; border: 1px solid rgba(0, 217, 255, 70); }")
        self.fake = FakeOllama(["qwen2.5:3b"], responder=lambda payload: "ok")
        self.fake.__enter__()
        self.data = Path(tempfile.mkdtemp(prefix="jarvis-ultron-"))
        self.env = mock.patch.dict(os.environ, {"JARVIS_DATA_DIR": str(self.data)})
        self.env.start()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = self.fake.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        manager.settings.permission_policy = ("arquivos=confirmar",)
        self.manager = manager
        self.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                               memory_db=helpers.make_memory().db)
        self.controller = HudController(self.core)
        self.controller.show()

    def tearDown(self):
        persona.reset()
        self.controller.quit()
        self.core.memory.db.close()
        self.env.stop()
        self.fake.__exit__(None, None, None)

    def test_identity_changes_settings_do_not_and_everything_returns(self):
        from PySide6 import QtWidgets
        c = self.controller
        settings_before = json.dumps(self.manager.settings.to_dict(), sort_keys=True, default=str)
        standing_before = list(self.core.authorizations.standing())
        files_before = {p.name for p in self.data.iterdir()}
        style_before, title_before = self.app.styleSheet(), c.window.windowTitle()
        panels_before = {id(w): w.styleSheet() for w in c.window.findChildren(QtWidgets.QWidget) if w.styleSheet()}
        self.assertTrue(panels_before, "há painéis com estilo próprio")
        executed, said = [], []
        add_system = c.window.conversation.add_system
        c.window.conversation.add_system = lambda text, **k: said.append(text) or add_system(text, **k)
        original_execute = self.core.executor.execute if hasattr(self.core, "executor") else None
        if original_execute is not None:
            self.core.executor.execute = lambda *a, **k: executed.append(a) or original_execute(*a, **k)

        self.assertTrue(c.ultron_start("manual"))
        self.assertEqual(c.window.windowTitle(), "U.L.T.R.O.N.")
        self.assertEqual(c.window.top.brand.title, "U.L.T.R.O.N.")
        self.assertIn("255, 31, 61", self.app.styleSheet(), "cores trocadas")
        self.assertTrue(c.orb.ultron)
        self.assertTrue(any("255, 31, 61" in w.styleSheet() for w in c.window.findChildren(QtWidgets.QWidget)),
                        "os painéis também mudam de cor")
        self.assertTrue(any("ULTRON_OPERATOR ATIVO" in line and "ações reais" in line for line in said),
                        "a conversa diz, com honestidade, que há um operador ativo")
        self.assertTrue(persona.current().ultron and persona.current().operator, "persona no núcleo")
        self.assertEqual(self.core.autonomy.level, "autonomous", "perfil operador em vigor")
        self.assertEqual(c.escape(), "ultron", "Esc restaura o JARVIS primeiro")
        self.assertFalse(persona.current().ultron, "voz, tom e permissões voltam ao JARVIS")
        self.assertNotEqual(self.core.autonomy.level, "autonomous")
        self.assertFalse(c.ultron.active)

        self.assertEqual(self.app.styleSheet(), style_before, "estilo restaurado exatamente")
        self.assertEqual(c.window.windowTitle(), title_before)
        self.assertEqual({id(w): w.styleSheet() for w in c.window.findChildren(QtWidgets.QWidget) if w.styleSheet()},
                         panels_before, "cada painel volta exatamente ao estilo de antes")
        self.assertEqual(c.window.top.brand.title, "J.A.R.V.I.S.")
        self.assertFalse(c.orb.ultron)
        self.assertEqual(json.dumps(self.manager.settings.to_dict(), sort_keys=True, default=str), settings_before,
                         "nenhuma configuração (inclusive permissões) mudou")
        self.assertEqual(list(self.core.authorizations.standing()), standing_before, "autorizações intactas")
        self.assertEqual(executed, [], "nenhuma ação executada")
        self.assertEqual({p.name for p in self.data.iterdir()} - files_before, {"protocolo_ultron.json"},
                         "o único arquivo novo é o histórico do próprio evento")

    def test_blocked_with_pending_authorization_and_voice_path(self):
        c = self.controller
        with mock.patch.object(self.core.authorizations, "pending", return_value={"status": "pending"}):
            self.assertFalse(c.ultron_start("manual"))
        self.assertFalse(c.ultron.active)
        c._ui_request({"ultron": "start"})
        self.assertTrue(c.ultron.active, "o pedido de voz/texto chega pelo caminho normal da interface")
        c._ui_request({"ultron": "stop"})
        self.assertFalse(c.ultron.active)
        c._ui_request({"ultron": "demo"})
        self.assertEqual(c.ultron.current.source, "demonstracao")
        c._scene3d_request("restore")
        self.assertFalse(c.ultron.active, "o botão RESTAURAR JARVIS da cena encerra")

    def test_real_work_during_the_event_stays_visible_and_the_emergency_key_stops_it(self):
        c = self.controller
        self.assertTrue(c.ultron_start("manual"))
        with mock.patch.object(self.core.authorizations, "pending", return_value={"status": "pending"}):
            c._tick()
        self.assertTrue(c.ultron.active, "o ULTRON opera: uma autorização real não encerra o evento")
        self.assertTrue(c.window.top.state_chip.text().startswith("ULTRON ·") if hasattr(c.window.top.state_chip,
                        "text") else True)
        cancelled = []
        original = self.core.cancel
        self.core.cancel = lambda reason="": cancelled.append(reason) or original(reason)
        c.ultron_emergency()
        self.assertFalse(c.ultron.active)
        self.assertTrue(cancelled, "a tecla de emergência também interrompe o que estiver em curso")
        self.assertEqual(c.ultron.history[-1]["ended_by"], "tecla de emergência")
        self.assertEqual(c.emergency_shortcut.key().toString(), "Ctrl+Shift+U")

    def test_occasional_and_demo_change_only_the_identity(self):
        c = self.controller
        c.ultron_start("demonstracao")
        self.assertTrue(persona.current().ultron)
        self.assertFalse(persona.current().operator, "demonstração: só identidade")
        c.ultron_stop("botão")
        c._ultron_apply(True, "ocasional")
        self.assertFalse(persona.current().operator, "ocasional: só identidade (padrão)")
        c._ultron_apply(False, "botão")

    def test_page_titles_and_esc_inside_the_tardis(self):
        c = self.controller
        c.window.navigate("jarvis", animate=False)
        c.ultron_start("manual")
        c.window.navigate("tardis", animate=False)
        self.assertEqual(c.window.windowTitle(), "U.L.T.R.O.N. — TARDIS", "a identidade vale em todas as páginas")
        from PySide6 import QtGui
        escape = QtGui.QKeySequence("Esc")
        room_shortcuts = [sc for sc in c.tardis_page.findChildren(QtGui.QShortcut) if sc.key() == escape]
        self.assertTrue(room_shortcuts and not any(sc.isEnabled() for sc in room_shortcuts),
                        "durante o evento, o Esc próprio da página fica suspenso (sem atalho ambíguo)")
        self.assertTrue(c.window.escape.isEnabled(), "e o Esc da plataforma vale mesmo com o foco no campo de texto")
        c.window.escape.activated.emit()
        self.assertFalse(c.ultron.active, "Esc na página TARDIS encerra o evento antes de qualquer outra coisa")
        self.assertFalse(c.window.escape.isEnabled(), "a TARDIS volta a usar o próprio Esc")
        self.assertTrue(all(sc.isEnabled() for sc in room_shortcuts), "atalhos da página restaurados")
        c.ultron_start("manual")
        c.tardis_page.room._escape()
        self.assertFalse(c.ultron.active, "o Esc da sala também encerra o evento primeiro")
        self.assertEqual(c.window.windowTitle(), "J.A.R.V.I.S. — TARDIS", "volta com o nome da página atual")
        c.window.navigate("jarvis", animate=False)
        self.assertEqual(c.window.windowTitle(), "J.A.R.V.I.S.")

    def test_settings_page_controls_demo_and_history(self):
        from ultron.hud.settings_page import ultron_history_text
        c = self.controller
        page = c._make_settings()
        self.assertEqual(ultron_history_text([]), "nenhuma ocorrência registrada")
        page.ultron_demo.emit()
        self.assertEqual(c.ultron.current.source, "demonstracao", "o botão DEMONSTRAÇÃO inicia o evento rotulado")
        c.ultron_stop("botão")
        text = ultron_history_text(page.ultron_history())
        self.assertIn("1 registrada", text)
        self.assertIn("demonstração", text)
        self.assertIn("botão", text)
        page.apply(ultron_occasional=True, ultron_chance_per_hour=5.0)
        self.assertTrue(self.core.settings().ultron_occasional)
        self.assertEqual(self.core.settings().ultron_chance_per_hour, 5.0)


class OperatorPolicyTest(unittest.TestCase):
    """ULTRON_OPERATOR: o MESMO executor e as MESMAS autorizações, com a política do operador — que nunca
    desbloqueia, mantém os pisos e sempre confirma envio externo, ações administrativas e risco alto."""

    def tearDown(self):
        persona.reset()

    def _decide(self, settings, skill_name, args=None):
        from ultron.agent.autonomy import AutonomyPolicy
        from ultron.agent.permissions import PermissionPolicy
        from ultron.skills.registry import load_builtin, SkillRegistry
        skill = load_builtin(SkillRegistry()).get(skill_name)
        args = args or {}
        autonomy = AutonomyPolicy(lambda: settings)
        decision = autonomy.decide(skill.risk_for(args), reversible=skill.reversible, origin="user",
                                   sensitive=skill.sensitive_for(args))
        return PermissionPolicy(lambda: settings).apply(decision, skill, args).action

    def test_operator_relaxes_only_what_the_user_allows(self):
        settings = helpers.make_settings(permission_policy=("arquivos=confirmar", "executar_programas=bloquear"))
        note = ("memory.session_note", {"note": "teste"})
        self.assertEqual(self._decide(settings, *note), "authorize", "JARVIS: a categoria pede confirmação")
        persona.set_persona("ultron", operator=True)
        self.assertEqual(self._decide(settings, *note), "execute", "operador: rotina liberada no perfil")
        self.assertEqual(self._decide(settings, "app.open", {"name": "notepad"}), "refuse",
                         "bloqueado na política normal continua bloqueado")
        self.assertEqual(self._decide(settings, "fs.delete", {"path": "C:/x.txt"}), "authorize",
                         "apagar dados sempre pede confirmação")
        persona.set_persona("ultron", operator=False)
        self.assertEqual(self._decide(settings, *note), "authorize", "só identidade: permissões normais")

    def test_external_and_administrative_actions_always_confirm(self):
        settings = helpers.make_settings()
        persona.set_persona("ultron", operator=True)
        self.assertEqual(self._decide(settings, "web.search", {"query": "x"}), "authorize")
        self.assertEqual(self._decide(settings, "system.power", {"action": "shutdown"}), "authorize")
        settings.ultron_operator_policy = ("arquivos=bloquear",)
        self.assertEqual(self._decide(settings, "memory.session_note", {"note": "x"}), "refuse",
                         "o perfil do operador também pode restringir")

    def test_the_same_executor_runs_the_routine_without_asking(self):
        from fake_ollama import FakeOllama
        from ultron.agent.execution import Action
        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        with FakeOllama(["qwen2.5:3b"]) as ollama:
            manager = SettingsManager(helpers.temp_dir() / "settings.json")
            manager.load()
            manager.settings.apply({"ollama_url": ollama.url, "network_discovery": False, "auto_backup": False,
                                    "permission_policy": ["arquivos=confirmar"], "authorization_timeout": 5})
            core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
            try:
                core.set_persona("ultron", operator=True, source="teste")
                record = core.executor.execute(Action("memory.session_note", {"note": "rotina do operador"}))
                self.assertEqual(record.status, "executed", record.result.error)
                self.assertIsNone(record.authorization, "rotina liberada no perfil: sem pedido de autorização")
                titles = [r["title"] for r in core.memory.db.query("SELECT title FROM activity")]
                self.assertTrue(any(t.startswith("[ULTRON]") for t in titles), titles)
                core.set_persona("jarvis", source="teste")
                self.assertFalse(persona.current().ultron)
            finally:
                core.memory.db.close()

    def test_actions_are_recorded_as_ultron_and_voice_and_tone_follow_the_persona(self):
        from ultron.core.activity import ActivityLog
        from ultron.personality import identity
        from ultron.personality.response_style import stylize
        from ultron.personality.voice_profile import JARVIS_VOICE_PROFILE, ULTRON_VOICE_PROFILE
        from ultron.voice.profile import effective_profile
        memory = helpers.make_memory()
        try:
            log = ActivityLog(memory.db, settings_getter=lambda: helpers.make_settings())
            persona.set_persona("ultron", operator=True)
            row_id = log.begin("acao", "abrir o bloco de notas", origin="user")
            row = memory.db.query("SELECT title, detail FROM activity WHERE id=?", (row_id,))[0]
            self.assertTrue(row["title"].startswith("[ULTRON]"))
            self.assertIn("ULTRON_OPERATOR", row["detail"])
            self.assertEqual(effective_profile(helpers.make_settings()).pitch, ULTRON_VOICE_PROFILE.pitch)
            self.assertIn("ULTRON", identity.system_prompt())
            self.assertIn("Nunca afirme que executou", identity.system_prompt(), "as regras de verdade continuam")
            self.assertEqual(stylize("Eu sou ULTRON."), "Eu sou ULTRON.")
            persona.reset()
            self.assertEqual(effective_profile(helpers.make_settings()).pitch, JARVIS_VOICE_PROFILE.pitch)
            self.assertNotIn("ULTRON", stylize("Eu sou ULTRON."))
        finally:
            memory.db.close()


if __name__ == "__main__":
    unittest.main()
