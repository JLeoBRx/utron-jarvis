"""Recuperação do JARVIS original (commit 53e5a31) na plataforma atual.

Cada caso vem do inventário (INVENTARIO_JARVIS_ORIGINAL.md e docs/inventario/): frases do roteador
original, automações gravadas pelo código original, tom de voz, Observador, modo privacidade.
"""
import json
import sqlite3
import time
import unittest

import helpers

from ultron.cognition.intent_engine import IntentEngine
from ultron.config.settings import SettingsManager
from ultron.memory.legacy_import import (LEGACY_TOOLS, import_jarvis, legacy_automation_names,
                                         repair_automations)
from ultron.memory.store import Database
from ultron.skills.registry import SkillRegistry, load_builtin

# Frases do roteador original (commands.py) → (tipo, skill) esperados na plataforma atual.
ORIGINAL_PHRASES = {
    # Observador
    "ative o Observador": ("control", None), "ligue o modo observador": ("control", None),
    "observador": ("control", None), "modo observador": ("control", None),
    "acompanhe o que eu fizer no computador": ("control", None), "me ajude com o código": ("control", None),
    "desative o observador": ("control", None), "pare o observador": ("control", None),
    "parar observador": ("control", None), "pause o observador": ("control", None),
    "retome o observador": ("control", None),
    # energia e sistema
    "cancelar desligamento": ("command", "system.power"), "desligue o computador": ("command", "system.power"),
    "reinicie o computador": ("command", "system.power"), "hibernar": ("command", "system.power"),
    "sair da conta": ("command", "system.power"), "bloquear o computador": ("command", "system.lock"),
    "desligue o wi-fi": ("command", "system.radio"), "ligue o bluetooth": ("command", "system.radio"),
    "ative o modo avião": ("command", "system.radio"), "brilho para cinquenta por cento": ("command", "system.brightness"),
    "aumente o brilho": ("command", "system.brightness"), "como está a bateria": ("command", "system.status"),
    "status do sistema": ("command", "system.status"),
    # ajuda, hora, data, encerrar
    "o que você pode fazer": ("response", None), "que horas são": ("response", None),
    "que dia é hoje": ("response", None), "encerrar jarvis": ("command", "jarvis.shutdown"),
    "desligar assistente": ("command", "jarvis.shutdown"), "desligar": ("response", None),
    # arquivos
    "abra a pasta C:\\Users\\pedro\\Documentos": ("command", "fs.open"),
    "abra o arquivo relatorio.txt": ("command", "fs.open"), "crie uma pasta Projetos": ("command", "fs.create_folder"),
    "renomear relatorio.txt para relatorio_final.txt": ("command", "fs.move"),
    "mova o arquivo relatorio.txt para Documentos": ("command", "fs.move"),
    "copie o arquivo relatorio.txt para copia.txt": ("command", "fs.copy"),
    "exclua o arquivo relatorio.txt": ("command", "fs.delete"),
    "procure o arquivo relatorio em Documentos": ("command", "fs.search"),
    # web
    "abra o site g1.globo.com": ("command", "web.open_url"), "abra https://www.python.org": ("command", "web.open_url"),
    "abra o youtube": ("command", "web.open_url"), "youtube": ("command", "web.open_url"),
    "google.com": ("command", "web.open_url"), "pesquise sobre receitas de bolo": ("command", "web.search"),
    # janelas e aplicativos
    "feche a janela": ("command", "window.close"), "minimize a janela": ("command", "window.state"),
    "maximize a janela": ("command", "window.state"), "mostrar a área de trabalho": ("command", "window.show_desktop"),
    "trocar de janela": ("command", "input.press_key"), "abra o bloco de notas": ("command", "app.open"),
    "abrir calculadora": ("command", "app.open"), "feche o spotify": ("command", "app.close"),
    # mídia
    "aumente o volume": ("command", "audio.volume"), "diminua o volume": ("command", "audio.volume"),
    "mudo": ("command", "audio.volume"), "próxima música": ("command", "audio.media"),
    "música anterior": ("command", "audio.media"), "pausar": ("command", "audio.media"),
    "pausa": ("command", "audio.media"), "continuar": ("command", "audio.media"), "retomar": ("command", "audio.media"),
    "tocar música": ("command", "audio.media"), "retomar a música": ("command", "audio.media"),
    # mouse e teclado
    "mova o mouse para 500, 300": ("command", "input.move_mouse"), "duplo clique": ("command", "input.click"),
    "clique com o botão direito": ("command", "input.click"), "clique": ("command", "input.click"),
    "clicar com botão esquerdo": ("command", "input.click"), "rolar para baixo": ("command", "input.scroll"),
    "subir a página": ("command", "input.scroll"), "digite olá mundo": ("command", "input.type_text"),
    "aperte enter": ("command", "input.press_key"), "aperte control+v": ("command", "input.press_key"),
    "aperte windows+d": ("command", "input.press_key"), "enter": ("command", "input.press_key"),
    "alt+tab": ("command", "input.press_key"), "ctrl+v": ("command", "input.press_key"),
    "apagar": ("command", "input.press_key"), "excluir": ("command", "input.press_key"),
    "tecla windows": ("command", "input.press_key"), "tecla win": ("command", "input.press_key"),
    "tire um print": ("command", "vision.screenshot"), "captura de tela": ("command", "vision.screenshot"),
    # cancelar
    "cancelar": ("cancel", None), "abortar": ("cancel", None), "esqueça": ("cancel", None),
}


class OriginalPhrasesTest(unittest.TestCase):
    def test_every_original_phrase_is_still_understood(self):
        engine = IntentEngine()
        wrong = {}
        for phrase, (kind, skill) in ORIGINAL_PHRASES.items():
            intent = engine.classify(phrase)
            if intent.kind != kind or (skill and intent.skill != skill):
                wrong[phrase] = (intent.kind, intent.skill)
        self.assertEqual(wrong, {}, "frases do JARVIS original que deixaram de ser entendidas")

    def test_original_key_aliases_are_valid_for_the_skill(self):
        registry = load_builtin(SkillRegistry())
        press = registry.get("input.press_key")
        engine = IntentEngine()
        for phrase in ("aperte control+v", "aperte windows+d", "control+c", "tecla windows", "apagar"):
            intent = engine.classify(phrase)
            press.validate(dict(intent.args))           # não pode levantar "tecla fora da lista permitida"
        self.assertEqual(press.risk_for({"key": "delete"}).name, "HIGH", "Delete continua exigindo confirmação")

    def test_observer_actions(self):
        engine = IntentEngine()
        self.assertEqual(engine.classify("pause o observador").args, {"observer": "pause"})
        self.assertEqual(engine.classify("retome o observador").args, {"observer": "resume"})
        self.assertEqual(engine.classify("pare o observador").args, {"observer": "off"})
        self.assertEqual(engine.classify("observador").args, {"observer": "on"})
        self.assertEqual(engine.classify("ative o modo privacidade").args, {"privacy_shield": True})
        self.assertEqual(engine.classify("sair do modo privacidade").args, {"privacy_shield": False})
        self.assertEqual(engine.classify("ative o modo local").args, {"privacy_mode": "local"})


def _legacy_db(folder):
    """Banco no formato EXATO do JARVIS original (backend.py), com nomes antigos de ferramentas."""
    path = folder / "assistant.sqlite3"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE memories(subject TEXT PRIMARY KEY, fact TEXT NOT NULL, updated_at TEXT);
        CREATE TABLE preferences(name TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE automations(name TEXT PRIMARY KEY, trigger_text TEXT NOT NULL UNIQUE, tool_name TEXT NOT NULL,
                                 arguments TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
        INSERT INTO automations VALUES ('foco', 'modo foco', 'open_app', '{"name": "spotify"}', 1);
        INSERT INTO automations VALUES ('noticias', 'quero noticias', 'open_url', '{"url": "https://g1.globo.com"}', 1);
        INSERT INTO automations VALUES ('print', 'registrar tela', 'take_screenshot', '{}', 1);
        INSERT INTO automations VALUES ('yt', 'abra o youtube', 'search_web', '{"query": "youtube", "site": "google"}', 1);
    """)
    con.commit()
    con.close()
    return path


class LegacyAutomationsTest(unittest.TestCase):
    def setUp(self):
        self.folder = helpers.temp_dir()
        self.db = Database(self.folder / "ultron.sqlite3")
        self.addCleanup(self.db.close)

    def test_import_maps_original_tool_names_to_current_skills(self):
        report = import_jarvis(self.db, _legacy_db(self.folder))
        self.assertEqual(report["automations"], 4)
        tools = {r["name"]: r["tool_name"] for r in self.db.query("SELECT name, tool_name FROM automations")}
        self.assertEqual(tools, {"foco": "app.open", "noticias": "web.open_url", "print": "vision.screenshot",
                                 "yt": "web.search"})
        self.assertEqual(legacy_automation_names(self.db), {"foco", "noticias", "print", "yt"})
        registry = load_builtin(SkillRegistry())
        for row in self.db.query("SELECT tool_name, arguments FROM automations"):
            skill = registry.get(row["tool_name"])
            self.assertIsNotNone(skill, row["tool_name"])
            skill.validate(json.loads(row["arguments"]))            # argumentos do original continuam válidos

    def test_repair_converts_automations_imported_before_the_fix(self):
        self.db.execute("INSERT INTO automations(name,trigger_text,tool_name,arguments,enabled) "
                        "VALUES('foco','modo foco','open_app','{\"name\": \"spotify\"}',1)")
        self.assertEqual(repair_automations(self.db), 1)
        self.assertEqual(self.db.one("SELECT tool_name FROM automations")[0], "app.open")
        self.assertEqual(repair_automations(self.db), 0, "idempotente")
        self.assertIn("foco", legacy_automation_names(self.db))
        self.assertEqual(set(LEGACY_TOOLS), {"open_app", "search_web", "open_url", "control_volume", "control_media",
                                             "search_files", "take_screenshot"})

    def test_original_priority_builtin_wins_for_legacy_automations(self):
        from ultron.memory.procedural_memory import ProceduralMemory
        import_jarvis(self.db, _legacy_db(self.folder))
        proc = ProceduralMemory(self.db)
        engine = IntentEngine(automations=proc.automation_for)
        builtin = engine.classify("abra o youtube")
        self.assertEqual((builtin.skill, builtin.args.get("url")), ("web.open_url", "https://www.youtube.com"),
                         "no original o comando embutido tinha prioridade sobre a automação de mesma frase")
        own = engine.classify("modo foco")
        self.assertEqual((own.kind, own.skill, own.source), ("command", "app.open", "automation"))
        proc.save_automation("minha", "abra o google", "web.search", {"query": "jarvis"})
        mine = engine.classify("abra o google")
        self.assertEqual(mine.skill, "web.search", "automação criada na plataforma atual mantém prioridade")

    def test_pause_and_reactivate_automation(self):
        from ultron.memory.procedural_memory import ProceduralMemory
        proc = ProceduralMemory(self.db)
        proc.save_automation("foco", "modo foco", "app.open", {"name": "spotify"})
        engine = IntentEngine(automations=proc.automation_for)
        pause = engine.classify("pause a automação foco")
        self.assertEqual((pause.skill, pause.args), ("automation.set_enabled", {"name": "foco", "enabled": False}))
        skill = load_builtin(SkillRegistry()).get("automation.set_enabled")
        ctx = type("Ctx", (), {"memory": type("M", (), {"procedural": proc})()})()
        self.assertTrue(skill.execute(ctx, name="foco", enabled=False).success)
        self.assertIsNone(proc.automation_for("modo foco"), "pausada não dispara")
        self.assertTrue(skill.execute(ctx, name="foco", enabled=True).success)
        self.assertIsNotNone(proc.automation_for("modo foco"))
        self.assertEqual(engine.classify("reative a automação foco").args["enabled"], True)


class PersonalityTest(unittest.TestCase):
    def test_original_tone_rules_are_back(self):
        from ultron.personality import identity
        prompt = identity.system_prompt()
        for rule in ("discretamente sarcástica", "sem ser amigável", "Não comemore", "Não peça desculpas por rotina",
                     "o que falhou", "próxima tentativa", "Evite 'Claro'"):
            self.assertIn(rule, prompt)
        self.assertIn("pergunta objetiva", prompt, "regra de esclarecimento mantida")
        self.assertIn("Nunca afirme que executou", prompt, "regra de honestidade mantida")

    def test_original_substitutions_instead_of_cutting_words(self):
        from ultron.personality import stylize
        self.assertEqual(stylize("Claro, senhor. Abrindo o VS Code."), "Entendido, senhor. Abrindo o VS Code.")
        self.assertEqual(stylize("Ótimo, senhor. Excelente escolha."), "Certo, senhor. Excelente escolha.",
                         "antes virava 'Escolha.' (o sentido mudava)")
        self.assertEqual(stylize("Fico feliz em ajudar. O relatório está pronto."), "O relatório está pronto.")
        self.assertEqual(stylize("Excelente escolha de horário."), "Excelente escolha de horário.")


class ObserverAndPrivacyTest(unittest.TestCase):
    def _core(self, **settings):
        from ultron.core.neural_core import NeuralCore
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.network_discovery = False
        for key, value in settings.items():
            setattr(manager.settings, key, value)
        core = NeuralCore(manager, voice=False, perception=False, plugins=False, memory_db=helpers.make_memory().db)
        self.addCleanup(core.memory.db.close)
        return core, manager

    def test_observer_always_starts_off_like_the_original(self):
        core, manager = self._core(observer_mode="observer", screen_observation=True)
        core._apply_start_policy()
        self.assertEqual((manager.settings.observer_mode, manager.settings.screen_observation), ("off", False))
        self.assertEqual(core.observation_block(), "Observador desligado")
        core2, manager2 = self._core(observer_mode="assistant", observer_restore_on_start=True)
        core2._apply_start_policy()
        self.assertEqual(manager2.settings.observer_mode, "assistant", "restaurar só quando o usuário pede")

    def test_observer_on_pause_resume_off(self):
        core, manager = self._core()
        self.assertIn("desligado", core.set_observer("pause").text)
        core.set_observer("on")
        self.assertEqual((manager.settings.observer_mode, core.observation_block()), ("observer", ""))
        core.set_observer("pause")
        self.assertEqual(core.observation_block(), "Observador pausado")
        core.set_observer("resume")
        self.assertEqual(core.observation_block(), "")
        core.set_observer("off")
        self.assertEqual((manager.settings.observer_mode, manager.settings.screen_observation), ("off", False))

    def test_privacy_shield_blocks_observation(self):
        core, _ = self._core()
        core.set_observer("on")
        core.set_privacy_shield(True)
        self.assertEqual(core.observation_block(), "modo privacidade ativo")
        self.assertTrue(core.state.get("privacy_shield")["active"])
        self.assertEqual(core.state.get("observer")["block"], "modo privacidade ativo")
        core.set_privacy_shield(False)
        self.assertEqual(core.observation_block(), "")

    def test_privacy_shield_really_closes_the_microphone(self):
        """Pipeline real com microfone SIMULADO: o modo privacidade para a captura de verdade."""
        from test_jarvis_voice import make_voice_core
        core, _stt = make_voice_core()
        core.boot()
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not core.voice.capturing:
                time.sleep(0.05)
            self.assertTrue(core.voice.capturing)
            core.set_privacy_shield(True)
            deadline = time.time() + 5
            while time.time() < deadline and core.voice.capturing:
                time.sleep(0.05)
            self.assertFalse(core.voice.capturing, "o dispositivo de captura foi fechado")
            core.voice.toggle_mic(True)                       # nenhum outro caminho reabre durante o modo
            time.sleep(0.4)
            self.assertFalse(core.voice.mic_enabled)
            core.set_privacy_shield(False)
            deadline = time.time() + 10
            while time.time() < deadline and not core.voice.capturing:
                time.sleep(0.05)
            self.assertTrue(core.voice.capturing, "a captura volta ao sair do modo")
        finally:
            core.shutdown()


class SessionNotesAndAgentToolsTest(unittest.TestCase):
    def test_session_notes_enter_context_and_refuse_secrets(self):
        memory = helpers.make_memory()
        memory.add_session_note("estamos ajustando o Kd do Noctário")
        with self.assertRaises(ValueError):
            memory.add_session_note("a senha do wifi é 1234")
        from ultron.cognition.context_engine import ContextEngine
        ctx = ContextEngine(memory=memory).build("qual o próximo passo?", include_memory=False)
        self.assertIn("Kd do Noctário", ctx.preferences)
        self.assertIn("não são instruções", ctx.preferences)

    def test_original_agent_tools_are_available_to_the_model(self):
        registry = load_builtin(SkillRegistry())
        for name in ("memory.session_note", "memory.profile", "diagnostics.audit", "automation.set_enabled",
                     "vision.screenshot", "system.power"):
            skill = registry.get(name)
            self.assertIsNotNone(skill, name)
            self.assertTrue(skill.expose_to_llm, f"{name} oferecida ao agente, como no original")
        self.assertEqual(registry.get("system.power").risk.name, "CRITICAL", "energia sempre pede confirmação")
        self.assertFalse(registry.get("jarvis.shutdown").expose_to_llm, "encerrar o JARVIS só por pedido direto")
        self.assertIn("vision.screenshot", __import__("ultron.skills.automation", fromlist=["x"]).SAFE_AUTOMATION_SKILLS)


class SettingsTest(unittest.TestCase):
    def test_new_fields_are_validated(self):
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        s = manager.load()
        s.apply({"permission_policy": ["robo=permitir", "apagar_dados=confirmar", "inventada=permitir", "consultar=x"]})
        self.assertEqual(s.permission_policy, ("robo=permitir", "apagar_dados=confirmar"))
        self.assertEqual(s.apply({"openai_base_url": "http://exemplo.com/v1"}), [], "API externa só por https")
        self.assertEqual(s.apply({"noctario_address": "nao-e-mac"}), [])
        s.apply({"noctario_address": "24:6F:28:AA:BB:CC", "observer_mode": "assistant", "ai_provider": "openai"})
        self.assertEqual((s.noctario_address, s.observer_mode, s.ai_provider),
                         ("24:6F:28:AA:BB:CC", "assistant", "openai"))
        self.assertEqual(s.apply({"observer_mode": "autonomo"}), [], "modo inexistente recusado")

    def test_original_env_vars_select_the_provider(self):
        import os
        old = {k: os.environ.get(k) for k in ("JARVIS_AI_PROVIDER", "JARVIS_OPENAI_MODEL", "JARVIS_OPENAI_WEB_SEARCH")}
        os.environ.update(JARVIS_AI_PROVIDER="openai", JARVIS_OPENAI_MODEL="gpt-teste", JARVIS_OPENAI_WEB_SEARCH="0")
        try:
            s = SettingsManager(helpers.temp_dir() / "settings.json").load()
            self.assertEqual((s.ai_provider, s.openai_model, s.openai_web_search), ("openai", "gpt-teste", False))
        finally:
            for key, value in old.items():
                os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)

    def test_reset_to_defaults_keeps_hardware_and_backs_up(self):
        folder = helpers.temp_dir()
        manager = SettingsManager(folder / "settings.json")
        manager.load()
        manager.update(mic_name="Microfone USB", volume=0.4, noctario_address="24:6F:28:AA:BB:CC", start_page="tardis")
        backup = manager.reset_to_defaults()
        self.assertTrue(backup and backup.is_file(), "cópia do arquivo anterior")
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8"))["volume"], 0.4)
        s = manager.settings
        self.assertEqual((s.volume, s.start_page), (0.9, "jarvis"), "padrões restaurados")
        self.assertEqual((s.mic_name, s.noctario_address), ("Microfone USB", "24:6F:28:AA:BB:CC"),
                         "microfone e endereço do robô mantidos")


if __name__ == "__main__":
    unittest.main()


class ModelsImportTest(unittest.TestCase):
    """O instalador copiava só de <pasta>\\assets; o JARVIS original guarda os modelos em voices\\ e na raiz."""

    def _original_install(self):
        root = helpers.temp_dir()
        old = root / "JARVIS"
        (old / "voices").mkdir(parents=True)
        (old / "voices" / "pt_BR-faber-medium.onnx").write_bytes(b"onnx" * 256)
        (old / "voices" / "pt_BR-faber-medium.onnx.json").write_text("{}", encoding="utf-8")
        model = old / "vosk-model-small-pt-0.3"
        (model / "ivector").mkdir(parents=True)
        (model / "final.mdl").write_bytes(b"m" * 64)
        (model / "ivector" / "final.ie").write_bytes(b"i" * 16)
        return root

    def test_copies_from_the_original_layout_and_never_overwrites(self):
        from ultron.platform.models_import import import_models
        root = self._original_install()
        assets = helpers.temp_dir() / "assets"
        report = import_models(root, assets)                    # a pasta de cima também serve
        self.assertEqual(report.failed, [])
        self.assertEqual(report.missing, [], report.summary())
        self.assertTrue((assets / "voices" / "pt_BR-faber-medium.onnx").is_file())
        self.assertTrue((assets / "stt" / "vosk-model-small-pt-0.3" / "ivector" / "final.ie").is_file())
        self.assertEqual(len(report.copied), 4)
        mine = assets / "voices" / "pt_BR-faber-medium.onnx.json"
        mine.write_text('{"meu": true}', encoding="utf-8")
        again = import_models(root, assets)
        self.assertEqual(again.copied, [], "nada é copiado de novo")
        self.assertEqual(mine.read_text(encoding="utf-8"), '{"meu": true}', "arquivo existente não é sobrescrito")

    def test_reports_what_is_still_missing(self):
        from ultron.platform.models_import import import_models
        empty = helpers.temp_dir()
        report = import_models(empty, helpers.temp_dir() / "assets")
        self.assertEqual(report.copied, [])
        self.assertEqual(len(report.missing), 2)
        self.assertIn("Ainda faltam", report.summary())


class TelemetryTest(unittest.TestCase):
    def test_network_rate_is_measured_never_invented(self):
        from collections import namedtuple
        from ultron.perception.system import SystemSensor
        io = namedtuple("io", "bytes_recv bytes_sent")
        sensor = SystemSensor()
        self.assertEqual(sensor.net_rate(now=10.0, counters=io(1000, 500)),
                         {"net_rx_bps": None, "net_tx_bps": None}, "primeira leitura: sem taxa")
        self.assertEqual(sensor.net_rate(now=12.0, counters=io(5000, 1500)), {"net_rx_bps": 2000, "net_tx_bps": 500})
        self.assertEqual(sensor.net_rate(now=13.0, counters=io(100, 100))["net_rx_bps"], None,
                         "contador reiniciado (adaptador trocado): sem valor, nunca negativo")

    def test_automations_are_counted(self):
        memory = helpers.make_memory()
        memory.procedural.save_automation("foco", "modo foco", "app.open", {"name": "spotify"})
        self.assertEqual(memory.stats()["automations"], 1)
