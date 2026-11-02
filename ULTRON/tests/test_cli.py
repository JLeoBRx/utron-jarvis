"""Linha de comando — os comandos documentados (``START_JARVIS.bat ...`` = ``python main.py ...``) executados
de verdade, como processos separados, numa pasta de dados temporária (nunca a do usuário).

O Ollama aponta para uma porta sem servidor e não é iniciado; sem voz, sem percepção e sem plugins. Não é
teste do Windows, da bandeja ou do microfone: é o caminho de linha de comando do próprio programa.
"""
import json
import os
import re
import socket
import subprocess
import sys
import unittest

import helpers


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CommandLineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = helpers.temp_dir("cli-")
        cls.env = {**os.environ, "ULTRON_DATA_DIR": str(cls.data), "QT_QPA_PLATFORM": "offscreen",
                   "JARVIS_OLLAMA_URL": f"http://127.0.0.1:{free_port()}", "JARVIS_OLLAMA_AUTOSTART": "0",
                   "JARVIS_NETWORK_DISCOVERY": "0", "JARVIS_AUTO_BACKUP": "0",
                   "PYTHONIOENCODING": "utf-8"}           # num pipe, o Windows usaria cp1252 (num console, não)
        cls.env.pop("JARVIS_DATA_DIR", None)

    def run_jarvis(self, *args, timeout=180):
        done = subprocess.run([sys.executable, str(helpers.ROOT / "main.py"), *args], cwd=helpers.ROOT,
                              env=self.env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
        output = done.stdout + done.stderr
        self.assertNotIn("Traceback", output, output[-3000:])
        return done.returncode, output

    def test_1_version_and_status(self):
        code, out = self.run_jarvis("--version")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"JARVIS \d+\.\d+")
        code, out = self.run_jarvis("--status")
        self.assertEqual((code, out.strip()), (0, "O JARVIS não está em execução."))

    def test_2_a_request_from_the_command_line(self):
        code, out = self.run_jarvis("--say", "que horas são?", "--no-voice", "--no-perception", "--no-plugins")
        self.assertEqual(code, 0, out[-2000:])
        self.assertRegex(out, r"São \d{2}:\d{2}")

    def test_3_backup_list_restore_and_export(self):
        code, out = self.run_jarvis("--backup")
        self.assertEqual(code, 0, out)
        self.assertIn("Backup criado:", out)
        created = out.split("Backup criado:", 1)[1].strip().splitlines()[0].strip()
        self.assertTrue(os.path.isfile(created), created)
        code, out = self.run_jarvis("--list-backups")
        self.assertEqual(code, 0)
        self.assertIn(os.path.basename(created), out)
        code, out = self.run_jarvis("--restore-backup", created)
        self.assertEqual(code, 0, out)
        self.assertIn("Banco restaurado de", out)
        self.assertIn("O banco anterior foi guardado em", out, "nada é apagado na restauração")
        target = helpers.temp_dir("export-") / "memoria.json"
        code, out = self.run_jarvis("--export", str(target))
        self.assertEqual(code, 0, out)
        self.assertIn("exportado", out)
        self.assertIsInstance(json.loads(target.read_text(encoding="utf-8")), (dict, list))
        code, out = self.run_jarvis("--export", str(target))
        self.assertEqual(code, 1, "exportar nunca sobrescreve um arquivo existente")
        self.assertIn("Exportação recusada", out)

    def test_4_diagnose_reports_what_is_missing_without_a_model(self):
        code, out = self.run_jarvis("--diagnose", "--no-voice", "--no-perception", "--no-plugins")
        self.assertIn(code, (0, 1))
        self.assertIn("— diagnóstico", out)
        self.assertIn("Ollama: indisponível", out, "sem servidor, o relatório diz isso em vez de inventar")
        self.assertIn("Voz: desativada nesta execução (--no-voice).", out)
        self.assertRegex(out, r"Skills: \d+/\d+ disponíveis")


class WindowsScriptsTest(unittest.TestCase):
    """Os ``.bat`` só rodam no Windows (o CI executa o instalador e os scripts a partir do ZIP extraído); aqui
    fica o que dá para conferir no texto deles."""

    def test_scripts_use_crlf_line_endings(self):
        scripts = sorted(helpers.ROOT.glob("*.bat"))
        self.assertGreaterEqual(len(scripts), 7)
        for script in scripts:
            data = script.read_bytes()
            self.assertNotIn(b"\n", data.replace(b"\r\n", b""),
                             f"{script.name}: com LF sozinho o cmd.exe pode não achar os rótulos do goto")

    def test_commands_that_answer_with_text_run_in_a_console(self):
        """``START_JARVIS.bat`` abre a janela pelo pythonw, que não tem console: um comando que responde com
        texto (backup, restauração, status…) rodaria sem mostrar nada. Todo comando "… e sai" do programa precisa
        estar na lista que o script roda pelo Python de console."""
        from ultron.app import build_parser
        text = (helpers.ROOT / "START_JARVIS.bat").read_text(encoding="ascii")
        listed = set(re.search(r"for %%A in \(([^)]*)\) do", text).group(1).split())
        options = {}
        for action in build_parser()._actions:
            for option in action.option_strings:
                options[option] = action.help or ""
        answering = {option for option, text_ in options.items() if text_.endswith("e sai")}
        answering |= {"--voice-test", "--headless", "--version", "--help"}
        self.assertGreaterEqual(len(answering), 18)
        self.assertEqual(answering - listed, set(), "comandos que responderiam com texto pelo pythonw (sem console)")
        self.assertEqual(listed - set(options), set(), "itens da lista que o programa não conhece")
        self.assertNotIn("--boot", listed, "o início com o Windows abre a janela, sem console")


if __name__ == "__main__":
    unittest.main()
