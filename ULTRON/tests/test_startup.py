"""Inicialização — os dois jeitos de usar o JARVIS, de verdade, como processos separados.

* **Janela** com a bandeja do sistema disponível (como num Windows de mesa): abre, responde a uma segunda
  abertura trazendo a janela para a frente, encerra com ``--stop`` e abre de novo sem conflito de instância.
  Foi assim que a interface caía no Windows (``'HudController' object has no attribute 'state_cache'``) e os
  testes não viam: no ambiente de teste não há bandeja, e o menu dela nunca era montado.
* **Falha da interface**: o erro completo vai para o registro, o motivo aparece, o modo console é oferecido
  (no terminal, com o MESMO núcleo) e a instância única é liberada.
* **Modo console**: o mesmo núcleo, banco, memória, TARDIS e autorizações; ``sair``, ``--stop``, segunda
  abertura recusada com aviso e reabertura.
* **Diagnóstico**: etapa que não responde é marcada e as seguintes continuam; nenhum caractere derruba a saída.

A bandeja "disponível" é declarada por um ``main.py`` de teste (o Qt offscreen não tem bandeja); o Ollama é o
servidor local de teste; os dados ficam numa pasta temporária. Não é teste de tela, bandeja ou microfone reais.
"""
import contextlib
import io
import os
import subprocess
import sys
import textwrap
import time
import unittest
from unittest import mock

import helpers

from fake_ollama import FakeOllama

HARNESS = textwrap.dedent('''
    """main.py de teste: a bandeja do sistema existe (como no Windows de mesa) e a interface pode falhar de propósito."""
    import os, sys
    sys.path.insert(0, {root!r})
    from PySide6 import QtWidgets
    QtWidgets.QSystemTrayIcon.isSystemTrayAvailable = staticmethod(lambda: True)
    reason = os.environ.get("JARVIS_TEST_GUI_FAIL")
    if reason:
        from ultron.hud import controller
        def broken(self, core, **_kw):
            raise RuntimeError(reason)
        controller.HudController.__init__ = broken
    from ultron import app
    raise SystemExit(app.main())
''')


def responder(payload):
    last = str((payload.get("messages") or [{}])[-1].get("content", ""))
    return "Boa noite, senhor. Como posso ajudar?" if "olá" in last.lower() else "Resposta do modelo local."


class _Processes(unittest.TestCase):
    """Uma pasta de dados só desta classe, um Ollama de teste e um ``main.py`` de teste com bandeja."""

    @classmethod
    def setUpClass(cls):
        cls.data = helpers.temp_dir("inicio-")
        cls.fake = FakeOllama(["qwen2.5:3b"], responder=responder)
        cls.fake.__enter__()
        cls.harness = helpers.temp_dir("harness-") / "main.py"     # "main.py": o --status reconhece o processo
        cls.harness.write_text(HARNESS.format(root=str(helpers.ROOT)), encoding="utf-8")
        cls.env = {**os.environ, "JARVIS_DATA_DIR": str(cls.data), "QT_QPA_PLATFORM": "offscreen",
                   "JARVIS_OLLAMA_URL": cls.fake.url, "JARVIS_OLLAMA_AUTOSTART": "0",
                   "JARVIS_NETWORK_DISCOVERY": "0", "JARVIS_AUTO_BACKUP": "0", "PYTHONIOENCODING": "utf-8"}
        cls.env.pop("JARVIS_TEST_GUI_FAIL", None)

    @classmethod
    def tearDownClass(cls):
        cls.fake.__exit__(None, None, None)

    def jarvis(self, *args, script=None, env=None, timeout=180, stdin=""):
        done = subprocess.run([sys.executable, str(script or helpers.ROOT / "main.py"), *args], cwd=helpers.ROOT,
                              env=env or self.env, input=stdin, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
        return done.returncode, done.stdout + done.stderr

    def start(self, *args, script=None, env=None):
        output = open(helpers.temp_dir("saida-") / "saida.txt", "w+", encoding="utf-8")   # pipe sem leitor trava
        proc = subprocess.Popen([sys.executable, str(script or helpers.ROOT / "main.py"), *args], cwd=helpers.ROOT,
                                env=env or self.env, stdin=subprocess.PIPE, stdout=output, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        proc.output_file = output
        return proc

    @staticmethod
    def output_of(proc) -> str:
        proc.output_file.flush()
        with open(proc.output_file.name, encoding="utf-8", errors="replace") as handle:
            return handle.read()

    def wait_running(self, seconds=60) -> str:
        end = time.time() + seconds
        while time.time() < end:
            _code, out = self.jarvis("--status")
            if "processo" in out:
                return out
            time.sleep(0.5)
        self.fail("o JARVIS não ficou em execução")

    def log_text(self) -> str:
        path = self.data / "logs" / "ultron.log"
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""

    def stop(self, proc) -> tuple[int, str]:
        code, out = self.jarvis("--stop")
        try:
            proc.wait(30)
        except subprocess.TimeoutExpired:
            proc.kill()
            self.fail(f"--stop não encerrou o processo: {out}\n{self.output_of(proc)[-2000:]}\n{self.log_text()[-3000:]}")
        finally:
            proc.stdin.close()
        return code, out


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class WindowStartupTest(_Processes):
    def test_1_window_opens_with_a_system_tray_answers_a_second_launch_and_stops(self):
        args = ("--no-voice", "--no-perception", "--no-plugins")
        for attempt in (1, 2):                                     # a segunda vez: reabrir sem conflito
            opened = self.log_text().count("interface aberta")
            proc = self.start(*args, script=self.harness)
            try:
                self.wait_running()
                end = time.time() + 30
                while time.time() < end and self.log_text().count("interface aberta") == opened:
                    time.sleep(0.3)
                log = self.log_text()
                self.assertIn("bandeja do sistema disponível", log, "o caminho do Windows com bandeja foi exercido")
                self.assertIn("interface aberta", log, log[-3000:])
                self.assertNotIn("state_cache", log)
                if attempt == 1:
                    started = time.time()
                    code, out = self.jarvis(*args)                 # START_JARVIS.bat de novo
                    self.assertEqual(code, 0, out)
                    self.assertIn("a janela foi trazida para a frente", out)
                    self.assertLess(time.time() - started, 30)
            finally:
                code, out = self.stop(proc)
            self.assertEqual(code, 0, out)
            self.assertIn("JARVIS encerrado", out)
            self.assertEqual(proc.returncode, 0)
            self.assertIn("não está em execução", self.jarvis("--status")[1])
        self.assertNotIn("CRITICAL", self.log_text())

    def test_2_interface_failure_is_logged_explained_and_releases_the_instance(self):
        env = {**self.env, "JARVIS_TEST_GUI_FAIL": "falha simulada da interface"}
        code, out = self.jarvis("--no-voice", "--no-perception", "--no-plugins", script=self.harness, env=env)
        self.assertEqual(code, 4, out[-2000:])
        self.assertIn("A interface gráfica do JARVIS não abriu", out)
        self.assertIn("Motivo: RuntimeError: falha simulada da interface", out)
        self.assertIn("START_JARVIS.bat --console", out)
        self.assertIn("não foram alterados", out)
        log = self.log_text()
        self.assertIn("a interface gráfica não abriu", log)
        self.assertIn("Traceback", log, "o erro completo fica no registro")
        self.assertIn("não está em execução", self.jarvis("--status")[1], "a instância foi liberada")
        code, out = self.jarvis("--headless", "--no-voice", "--no-perception", "--no-plugins", stdin="sair\n")
        self.assertEqual(code, 0, out)
        self.assertIn("Até logo.", out)

    def test_4_a_stop_sent_while_the_window_is_still_opening_is_not_lost(self):
        proc = self.start("--no-voice", "--no-perception", "--no-plugins", script=self.harness)
        try:
            self.wait_running()                                    # registrado, mas a janela ainda pode estar montando
        finally:
            code, out = self.stop(proc)
        self.assertEqual((code, proc.returncode), (0, 0), out)

    def test_3_gui_check_mounts_the_window_without_showing_it(self):
        code, out = self.jarvis("--gui-check", "--no-voice", "--no-perception", "--no-plugins", script=self.harness)
        self.assertEqual(code, 0, out[-2000:])
        self.assertRegex(out, r"INTERFACE OK: Qt [\d.]+, plataforma \w+, bandeja do sistema disponível")
        env = {**self.env, "JARVIS_TEST_GUI_FAIL": "biblioteca gráfica quebrada"}
        code, out = self.jarvis("--gui-check", script=self.harness, env=env)
        self.assertEqual(code, 1)
        self.assertIn("INTERFACE FALHOU: RuntimeError: biblioteca gráfica quebrada", out)


class InterfaceFallbackInTerminalTest(unittest.TestCase):
    def test_a_terminal_user_continues_in_console_with_the_same_core(self):
        from ultron import app
        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.platform import notice
        fake = FakeOllama(["qwen2.5:3b"], responder=responder)
        fake.__enter__()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = fake.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        core = NeuralCore(manager, voice=False, perception=False, plugins=False, memory_db=helpers.make_memory().db)
        answers = iter(["s", "que horas são?", "sair"])
        args = app.parse_args(["--no-voice", "--no-perception", "--no-plugins"])
        output = io.StringIO()
        try:
            with mock.patch.object(notice, "has_console", lambda: True), \
                    mock.patch("builtins.input", lambda prompt="": next(answers)), contextlib.redirect_stdout(output):
                code = app._interface_failed(args, core, RuntimeError("Qt sem plataforma"),
                                             __import__("logging").getLogger("ultron.teste"))
        finally:
            core.shutdown()
            fake.__exit__(None, None, None)
        text = output.getvalue()
        self.assertEqual(code, 0, text)
        self.assertIn("Motivo: RuntimeError: Qt sem plataforma", text)
        self.assertIn("CONSOLE INTERFACE", text)
        self.assertRegex(text, r"JARVIS > São \d{2}:\d{2}")
        self.assertIn("Até logo.", text)
        self.assertIsNotNone(core.started_at, "o console iniciou o MESMO núcleo que a janela ia usar")


class ConsoleModeTest(_Processes):
    def setUp(self):
        from ultron.config import paths
        from ultron.memory.preference_memory import PreferenceMemory
        from ultron.memory.store import Database
        with mock.patch.dict(os.environ, {"JARVIS_DATA_DIR": str(self.data)}):
            db = Database(paths.database_path())
            PreferenceMemory(db).set("profile_name", "Leo")        # o nome que o usuário configurou
            db.close()

    def test_1_conversation_memory_tardis_authorization_and_exit(self):
        lines = ["Olá, Jarvis.", "que horas são?", "anote uma ideia: horta vertical na varanda",
                 "o que anotei sobre horta?", "consulte a TARDIS sobre a horta vertical", "encerre o jarvis", "não",
                 "sair"]
        code, out = self.jarvis("--headless", "--no-voice", "--no-perception", "--no-plugins",
                                stdin="\n".join(lines) + "\n")
        self.assertEqual(code, 0, out[-3000:])
        for expected in ("J.A.R.V.I.S. 2.0", "CONSOLE INTERFACE", "Sistema: ONLINE", "Modelo: qwen2.5:3b",
                         "Memória: CONECTADA", "TARDIS: DISPONÍVEL", "Voz: DESATIVADA nesta execução (--no-voice)",
                         "JARVIS aguardando instruções."):
            self.assertIn(expected, out)
        self.assertIn("LEO > ", out, "o prompt usa o nome configurado, não um nome fixo")
        self.assertIn("JARVIS > Boa noite, senhor. Como posso ajudar?", out, "conversa pelo modelo")
        self.assertRegex(out, r"JARVIS > São \d{2}:\d{2}")
        self.assertIn("Ideia registrada: Horta vertical na varanda", out)
        self.assertIn("Encontrei 1 registro(s) sobre \"horta\"", out, "memória pessoal consultada")
        self.assertIn("(o mesmo do JARVIS)", out, "TARDIS com o mesmo modelo")
        self.assertIn("[CONFIRMAÇÃO]", out)
        self.assertIn("Não autorizado: encerre o jarvis", out, "autorização negada: nada executado")
        self.assertIn("Até logo.", out)
        self.assertNotIn("Traceback", out)
        code, out = self.jarvis("--headless", "--no-voice", "--no-perception", "--no-plugins",
                                stdin="o que anotei sobre horta?\nsair\n")
        self.assertIn("Horta vertical na varanda", out, "a memória gravada continua lá na próxima abertura")

    def test_2_stop_second_instance_and_reopen(self):
        proc = self.start("--headless", "--no-voice", "--no-perception", "--no-plugins")
        try:
            self.wait_running()
            code, out = self.jarvis("--headless", "--no-voice", stdin="sair\n")
            self.assertEqual(code, 0)
            self.assertIn("já está aberto em modo console", out, "nunca duas instâncias")
            code, out = self.jarvis("--no-voice")                   # abrir a janela com o console aberto
            self.assertIn("já está aberto em modo console", out)
        finally:
            code, out = self.stop(proc)
        self.assertEqual((code, proc.returncode), (0, 0), out)
        rest = self.output_of(proc)
        self.assertIn("Encerrando a pedido (--stop)", rest)
        self.assertIn("Até logo.", rest)
        code, out = self.jarvis("--headless", "--no-voice", "--no-perception", "--no-plugins",
                                stdin="que horas são?\nsair\n")
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"São \d{2}:\d{2}")


class ChildProcessInputTest(unittest.TestCase):
    def test_no_child_process_inherits_the_user_input(self):
        """Todo processo filho do JARVIS diz de onde vem a entrada. O PowerShell (nome da GPU, no boot) lia a entrada
        padrão até o fim quando ela era redirecionada: no CI do Windows, as linhas digitadas para o console sumiam
        antes do primeiro prompt."""
        import ast
        missing = []
        for path in sorted((helpers.ROOT / "ultron").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                func = getattr(node, "func", None)
                if (isinstance(node, ast.Call) and isinstance(func, ast.Attribute)
                        and isinstance(func.value, ast.Name) and func.value.id == "subprocess"
                        and func.attr in ("run", "Popen", "call", "check_call", "check_output")):
                    if not {"stdin", "input"} & {k.arg for k in node.keywords}:
                        missing.append(f"{path.relative_to(helpers.ROOT)}:{node.lineno}")
        self.assertEqual(missing, [], "subprocesso sem stdin definido (use subprocess.DEVNULL)")


class DiagnoseTest(unittest.TestCase):
    def test_a_step_that_does_not_answer_is_named_and_the_next_ones_run(self):
        from ultron import diagnose
        lines = []
        report = diagnose.Report(lines.append)
        report.step("Voz", 0.3, lambda: time.sleep(5) or ("OK", ""), wait_text="testando")
        report.step("Plugins", 5, lambda: ("OK", "nenhum plugin instalado"))
        report.step("Banco", 5, lambda: 1 / 0)
        self.assertEqual(report.summary(), 1)
        text = "\n".join(lines)
        self.assertIn("[....]  Voz: testando (até 0 s)…", text)
        self.assertIn("[TEMPO] Voz: sem resposta em 0 s", text)
        self.assertIn("[OK]    Plugins: nenhum plugin instalado", text, "a etapa seguinte rodou")
        self.assertIn("[FALHA] Banco: ZeroDivisionError", text)
        self.assertIn("Com problema: Voz, Banco", text)

    def test_output_survives_characters_the_code_page_does_not_have(self):
        code = ("import sys; sys.path.insert(0, %r); from ultron import app; app._safe_output(); "
                "print('voz → ok ✓')" % str(helpers.ROOT))
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}          # como uma saída redirecionada no Windows
        done = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, timeout=60)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout.strip(), b"voz ? ok ?")
        broken = subprocess.run([sys.executable, "-c", "print('voz → ok')"], env=env, capture_output=True, timeout=60)
        self.assertNotEqual(broken.returncode, 0, "sem a proteção, o mesmo texto derruba o processo")
        self.assertIn(b"UnicodeEncodeError", broken.stderr)


if __name__ == "__main__":
    unittest.main()
