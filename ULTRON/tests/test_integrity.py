"""Integridade do pacote: todo módulo importa, a sintaxe compila e as falhas de rede são relatadas.

Não substitui os testes de comportamento: pega módulos que nenhum outro teste importa (por
exemplo, skills e sensores do Windows) e quebrariam só em produção.
"""
import compileall
import importlib
import pkgutil
import unittest
from pathlib import Path

import helpers


class ImportTest(unittest.TestCase):
    def test_every_module_imports(self):
        import ultron
        failed = []
        names = [m.name for m in pkgutil.walk_packages(ultron.__path__, "ultron.")
                 if not m.name.endswith("__main__")]          # __main__ inicia o programa de verdade
        for name in names:
            try:
                importlib.import_module(name)
            except Exception as exc:                      # registra todos antes de falhar
                failed.append(f"{name}: {type(exc).__name__}: {exc}")
        self.assertGreater(len(names), 100)
        self.assertEqual(failed, [])

    def test_sources_compile(self):
        root = Path(helpers.ROOT)
        for folder in ("ultron", "tests", "tools", "plugins"):
            if (root / folder).exists():
                self.assertTrue(compileall.compile_dir(str(root / folder), quiet=1, force=False), folder)

    def test_every_builtin_skill_is_registered_and_described(self):
        from ultron.skills.registry import SkillRegistry, load_builtin
        registry = load_builtin(SkillRegistry())
        names = [s.name for s in registry.all()] if hasattr(registry, "all") else list(registry.names())
        self.assertGreater(len(names), 40)
        for required in ("secondbrain.capture", "secondbrain.conflicts", "secondbrain.export", "memory.backup",
                         "autonomy.revoke", "autonomy.list", "voice.diagnose", "network.devices"):
            self.assertIn(required, names)


class NetworkFailureTest(unittest.TestCase):
    def test_scan_failure_is_reported_not_hidden(self):
        from ultron.memory.store import Database
        from ultron.network import discovery
        from ultron.network.world_integration import NetworkIntelligence

        db = Database(helpers.temp_dir("netfail-") / "net.sqlite3")
        settings = helpers.make_settings(network_discovery=True)
        net = NetworkIntelligence(db=db, settings_getter=lambda: settings)
        net.snapshot = {"primary": {"ipv4": "192.168.0.12", "subnet": "192.168.0.0/24", "name": "Wi-Fi"},
                        "gateway": {"ip": "192.168.0.1"}}

        def broken(*args, **kwargs):
            raise OSError("adaptador desconectado")

        original = discovery.discover
        discovery.discover = broken
        try:
            result = net.scan(force=True)
        finally:
            discovery.discover = original
        self.assertIn("adaptador desconectado", str(result.get("error", "")))
        self.assertTrue(net.last_scan.get("limitations"), "a limitação aparece no painel de rede")
        self.assertEqual(net.inventory.devices(), [], "falha não inventa dispositivos")
        self.assertFalse(net._scan_lock.locked(), "a trava da varredura é liberada")
        db.close()


class ProcessControlTest(unittest.TestCase):
    """--stop pede a saída normal: um processo de teste que segue o protocolo encerra sozinho."""

    def test_stop_request_is_honoured_and_pid_cleared(self):
        import os
        import subprocess
        import sys
        import time

        from ultron.platform import control

        folder = helpers.temp_dir("control-")
        script = folder / "main.py"                       # o nome conta: só processos do JARVIS são considerados
        script.write_text(
            "import os, sys, time\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "os.environ['JARVIS_DATA_DIR'] = sys.argv[2]\n"
            "from ultron.platform import control\n"
            "control.register()\n"
            "end = time.time() + 20\n"
            "while time.time() < end and not control.stop_requested():\n"
            "    time.sleep(0.05)\n"
            "control.clear_stop_request()\n"
            "control.unregister()\n", encoding="utf-8")
        data = os.environ.get("JARVIS_DATA_DIR") or os.environ["ULTRON_DATA_DIR"]
        process = subprocess.Popen([sys.executable, str(script), str(helpers.ROOT), data])
        try:
            deadline = time.time() + 10
            while control.running_pid() is None and time.time() < deadline:
                time.sleep(0.05)
            self.assertEqual(control.running_pid(), process.pid, "a instância registrou o PID")
            ok, message = control.stop(timeout=10)
            self.assertTrue(ok, message)
            self.assertEqual(process.wait(timeout=10), 0, "saiu normalmente, sem ser morto")
            self.assertIsNone(control.running_pid())
            self.assertFalse(control.stop_requested(), "pedido de parada consumido")
        finally:
            if process.poll() is None:
                process.kill()

    def test_nothing_running(self):
        from ultron.platform import control
        control.unregister()
        ok, message = control.stop(timeout=1)
        self.assertTrue(ok)
        self.assertIn("não está em execução", message)


if __name__ == "__main__":
    unittest.main()


class ReleasePackageValidationTest(unittest.TestCase):
    def test_windows_style_zip_paths_are_rejected(self):
        import zipfile

        from tools import build_release

        archive = helpers.temp_dir("release-") / "unsafe.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr(r"JARVIS/subfolder\payload.txt", "unsafe")
            bundle.writestr(r"JARVIS/..\outside.txt", "unsafe")
        problems = build_release.check(archive)
        unsafe = [problem for problem in problems if "caminho inseguro" in problem]
        self.assertEqual(len(unsafe), 2, problems)
