"""Central 3D (Three.js no QtWebEngine): disponibilidade, arquivos da página, segurança e reserva 2D.

* ``AvailabilityTest`` e ``WebFilesTest`` não precisam de tela nem de QtWebEngine;
* ``ControllerSceneTest`` usa uma vista 3D FALSA (mesma interface) para provar a lógica do controlador —
  troca JARVIS ⇄ TARDIS, pedidos da página e a volta para 2D quando a cena cai; não é um teste de WebGL;
* ``NativeSceneTest`` abre a cena DE VERDADE num processo próprio (``scene3d_probe.py``): roda no Windows
  nativo e, no Linux, só com JARVIS_TEST_SCENE3D=1 (o CI usa Xvfb). Em máquina sem WebGL 2, o teste aceita a
  falha tratada — e diz qual dos dois aconteceu.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401  (pastas temporárias e ambiente de teste)

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "ultron" / "hud" / "scene3d" / "web"


class AvailabilityTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jarvis-cena3d-")
        self.env = mock.patch.dict(os.environ, {"JARVIS_DATA_DIR": self.tmp})
        self.env.start()
        from ultron.hud import scene3d
        self.s3 = scene3d
        scene3d.set_persist(True)
        self.webengine = mock.patch.object(scene3d, "webengine_import_error", return_value="")
        self.webengine.start()

    def tearDown(self):
        self.webengine.stop()
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def settings(self, value="auto"):
        return type("S", (), {"scene3d": value})()

    def test_available_by_default_with_a_window_platform(self):
        self.assertEqual(self.s3.availability(self.settings(), platform_name="windows"), (True, ""))

    def test_turned_off_in_settings(self):
        ok, reason = self.s3.availability(self.settings("desligado"), platform_name="windows")
        self.assertFalse(ok)
        self.assertIn("CONFIGURAÇÕES", reason)

    def test_no_window_platform_never_opens_webengine(self):
        for name in ("offscreen", "minimal"):
            ok, reason = self.s3.availability(self.settings(), platform_name=name)
            self.assertFalse(ok)
            self.assertIn(name, reason)

    def test_missing_webengine_says_how_to_install(self):
        with mock.patch.object(self.s3, "webengine_import_error", return_value="ImportError: QtWebEngineWidgets"):
            ok, reason = self.s3.availability(self.settings(), platform_name="windows")
        self.assertFalse(ok)
        self.assertIn("PySide6-Addons", reason)

    def test_failure_is_remembered_until_the_user_retries(self):
        self.s3.mark_failed("sem WebGL 2")
        ok, reason = self.s3.availability(self.settings(), platform_name="windows")
        self.assertFalse(ok)
        self.assertIn("sem WebGL 2", reason)
        self.assertIn("Automática".lower(), reason.lower())
        self.s3.clear_marker()                                   # o que a escolha "Automática" faz
        self.assertTrue(self.s3.availability(self.settings(), platform_name="windows")[0])

    def test_crash_during_startup_disables_the_next_attempt(self):
        self.s3.mark_starting()                                  # processo morreu antes de "pronta"
        ok, reason = self.s3.availability(self.settings(), platform_name="windows")
        self.assertFalse(ok)
        self.assertIn("não terminou de abrir", reason)

    def test_gui_check_does_not_touch_the_marker(self):
        self.s3.set_persist(False)
        try:
            self.s3.mark_failed("verificação")
            self.assertEqual(self.s3.read_marker(), "")
        finally:
            self.s3.set_persist(True)

    def test_page_may_only_read_its_own_folder(self):
        inside = self.s3.inside_web
        self.assertTrue(inside(str(WEB / "index.html")))
        self.assertTrue(inside(str(WEB / "js" / "main.js")))
        self.assertFalse(inside(str(WEB / ".." / "view.py")))
        self.assertFalse(inside(str(WEB.parent.parent / "controller.py")))
        self.assertFalse(inside(str(ROOT / "main.py")))


class WebFilesTest(unittest.TestCase):
    def test_every_module_and_import_resolves_locally(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        importmap = json.loads(re.search(r'<script type="importmap">(.*?)</script>', html, re.S).group(1))["imports"]
        self.assertTrue((WEB / importmap["three"]).is_file())
        for path in sorted((WEB / "js").glob("*.js")):
            for spec in re.findall(r"from '([^']+)'", path.read_text(encoding="utf-8")):
                if spec == "three":
                    continue
                if spec.startswith("three/addons/"):
                    target = WEB / importmap["three/addons/"] / spec[len("three/addons/"):]
                else:
                    target = (path.parent / spec).resolve()
                self.assertTrue(target.is_file(), f"{path.name}: import {spec} não existe")
        for addon in (WEB / "vendor" / "three" / "addons").rglob("*.js"):
            for spec in re.findall(r"from '(\.[^']+)'", addon.read_text(encoding="utf-8")):
                self.assertTrue((addon.parent / spec).resolve().is_file(), f"{addon.name}: {spec}")

    def test_no_remote_resources_in_the_page(self):
        own = [WEB / "index.html", *sorted((WEB / "js").glob("*.js")), *sorted((WEB / "css").glob("*.css"))]
        for path in own:
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"https?://", f"{path.name} referencia endereço remoto")
        html = (WEB / "index.html").read_text(encoding="utf-8")
        for src in re.findall(r'src="([^"]+)"', html):
            self.assertTrue(src.startswith(("qrc:///", "js/")), src)

    def test_vendored_three_is_licensed_and_pinned(self):
        license_text = (WEB / "vendor" / "three" / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT", license_text)
        head = (WEB / "vendor" / "three" / "three.module.min.js").read_text(encoding="utf-8")[:400]
        self.assertIn("170", head)

    def test_demo_mode_is_labeled_and_only_without_the_bridge(self):
        main = (WEB / "js" / "main.js").read_text(encoding="utf-8")
        self.assertIn("const DEMO = !send.connected", main)
        self.assertIn("DEMONSTRAÇÃO fora do JARVIS", main)
        self.assertIn("não são dados reais", main)

    def test_page_requests_are_whitelisted_in_python(self):
        view = (ROOT / "ultron" / "hud" / "scene3d" / "view.py").read_text(encoding="utf-8")
        self.assertIn('REQUESTS = frozenset({"tardis", "jarvis", "mic"})', view)
        self.assertNotIn("subprocess", view)
        self.assertNotIn("os.system", view)

    @unittest.skipUnless(shutil.which("node"), "node não instalado: sintaxe dos módulos não verificada")
    def test_modules_parse(self):
        for path in sorted((WEB / "js").glob("*.js")):
            done = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True,
                                  stdin=subprocess.DEVNULL)
            self.assertEqual(done.returncode, 0, f"{path.name}: {done.stderr[-400:]}")


class _FakeScene:
    """Mesma interface pública da Scene3DView, sem QtWebEngine (lógica do controlador apenas)."""

    @staticmethod
    def make(parent=None):
        from collections import deque

        from PySide6 import QtCore, QtWidgets

        from ultron.hud.avatar.view import _AvatarCore

        class FakeScene(QtWidgets.QWidget, _AvatarCore):
            face_clicked = QtCore.Signal()
            became_ready = QtCore.Signal(dict)
            unavailable = QtCore.Signal(str)
            panel_selected = QtCore.Signal(str)
            action_requested = QtCore.Signal(str)
            backend = "3d"

            def __init__(self):
                super().__init__(parent)
                self._init_avatar()
                self.frame_times = deque(maxlen=10)
                self.is_ready, self.failed, self.stats, self.info = True, "", {}, {}
                self.mode, self.selected, self.rooms, self.disposed = "jarvis", "", [], False
                self.modes = []

            def set_mode(self, mode, *, animate=True):
                self.mode = mode
                self.modes.append(mode)

            def select_panel(self, key):
                self.selected = key

            def push_room(self, snapshot):
                self.rooms.append(snapshot)

            def step(self, dt):
                self.update_state()
                self.paint_count += 1

            def dispose(self):
                self.disposed = True

        return FakeScene()


class ControllerSceneTest(unittest.TestCase):
    """O controlador com uma cena 3D (falsa) no lugar do rosto: uma cena, emprestada à TARDIS, e a reserva 2D."""

    def setUp(self):
        from PySide6 import QtWidgets

        from fake_ollama import FakeOllama
        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.hud.controller import HudController
        self.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        self.fake_ollama = FakeOllama(["qwen2.5:3b"], responder=lambda payload: "ok")
        self.fake_ollama.__enter__()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = self.fake_ollama.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        self.manager = manager
        self.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                               memory_db=helpers.make_memory().db)
        self.created = []

        def fake_make(controller_self):
            if getattr(controller_self.core.settings(), "scene3d", "auto") == "desligado":
                controller_self.scene3d, controller_self.scene3d_reason = None, "desligada em CONFIGURAÇÕES"
                return None
            scene = _FakeScene.make()
            scene.unavailable.connect(controller_self._scene3d_failed)
            scene.action_requested.connect(controller_self._scene3d_request)
            controller_self.scene3d, controller_self.scene3d_reason = scene, ""
            controller_self.avatar_reason = "cena 3D (abrindo)"          # como a vista real
            self.created.append(scene)
            return scene

        self.patch = mock.patch.object(HudController, "_make_scene3d", fake_make)
        self.patch.start()
        self.controller = HudController(self.core)
        self.controller.show()

    def tearDown(self):
        self.patch.stop()
        self.controller.quit()
        self.core.memory.db.close()
        self.fake_ollama.__exit__(None, None, None)

    def pump(self, condition=None, seconds=3.0):
        from PySide6 import QtCore
        end = time.time() + seconds
        while time.time() < end and not (condition and condition()):
            self.app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            time.sleep(0.01)

    def test_one_scene_is_lent_to_the_tardis_and_returned(self):
        c = self.controller
        scene = c.scene3d
        self.assertIs(c.central(), scene, "a cena 3D é a vista do JARVIS")
        c.open_tardis("telemetria")
        self.pump(lambda: scene.mode == "tardis")
        room = c.tardis_page.room
        self.assertIs(room.scene3d, scene, "a sala usa a MESMA cena (sem segundo motor)")
        self.assertIs(c.central(), c._placeholder)
        self.assertFalse(room.view.isVisible(), "o desenho 2D da sala fica parado")
        self.assertEqual(scene.selected, "telemetria")
        self.pump(lambda: scene.rooms)
        snap = scene.rooms[-1]
        self.assertTrue(snap["available"])
        self.assertIn("panels", snap)
        self.assertEqual(set(snap["panels"]), {"analise", "planejamento", "arquivo", "rotinas", "telemetria",
                                               "diagnostico"})
        scene.panel_selected.emit("rotinas")                 # clique no console 3D = clique na aba
        self.pump(lambda: room.current_panel == "rotinas")
        self.assertEqual(room.current_panel, "rotinas")
        scene.action_requested.emit("jarvis")                # botão VOLTAR AO JARVIS da página
        self.pump(lambda: c.window.current_key == "jarvis")
        self.assertIs(c.central(), scene)
        self.assertIsNone(room.scene3d)
        self.assertTrue(room.view.isVisibleTo(room))
        self.assertEqual(scene.modes[-2:], ["tardis", "jarvis"])

    def test_page_request_opens_the_tardis_through_the_normal_path(self):
        c = self.controller
        c.scene3d.action_requested.emit("tardis")
        self.pump(lambda: c.window.current_key == "tardis")
        self.assertEqual(c.window.current_key, "tardis")

    def test_scene_failure_falls_back_to_2d_without_losing_the_page(self):
        from ultron.hud.avatar.view import AvatarView
        c = self.controller
        scene = c.scene3d
        c.open_tardis()
        self.pump(lambda: c.tardis_page is not None and c.tardis_page.room.scene3d is scene)
        scene.unavailable.emit("contexto WebGL perdido (teste)")
        self.pump(lambda: c.scene3d is None)
        self.assertIsNone(c.scene3d)
        self.assertEqual(c.scene3d_reason, "contexto WebGL perdido (teste)")
        self.assertTrue(scene.disposed)
        self.assertIsInstance(c.avatar, AvatarView)
        self.assertEqual(c.avatar_reason, "CPU", "o texto da vista acompanha a troca (achado no CI do Windows)")
        self.assertIsNone(c.tardis_page.room.scene3d)
        self.assertTrue(c.tardis_page.room.view.isVisibleTo(c.tardis_page.room), "a sala 2D volta a desenhar")
        c.open_page("jarvis")
        self.pump(lambda: c.central() is c.avatar)
        self.assertIs(c.central(), c.avatar, "a página JARVIS mostra o rosto 2D")
        c.frame_rate = c.frame_rate or 30.0                  # health() só detalha depois da primeira medição
        self.assertIn("cena 3D não usada: contexto WebGL perdido", c.health()["detail"])

    def test_tardis_state_reaches_the_cabin_lamp_outside_the_room(self):
        c = self.controller
        from ultron.core.events import EventType
        c.core.bus.publish(EventType.TARDIS_STATE, {"mode": "processando", "fault": False}, source="teste")
        self.pump(lambda: c.scene3d.rooms)
        self.assertEqual(c.scene3d.rooms[-1]["mode"], "processando")

    def test_turning_the_scene_off_in_settings_switches_to_2d(self):
        from ultron.hud.avatar.view import AvatarView
        c = self.controller
        scene = c.scene3d
        self.manager.update(scene3d="desligado")
        self.pump(lambda: isinstance(c.avatar, AvatarView))
        self.assertIsInstance(c.avatar, AvatarView)
        self.assertTrue(scene.disposed)


class NativeSceneTest(unittest.TestCase):
    """A cena DE VERDADE (QtWebEngine + WebGL desta máquina), num processo próprio."""

    @unittest.skipUnless(sys.platform == "win32" or os.environ.get("JARVIS_TEST_SCENE3D") == "1",
                         "cena 3D real: Windows nativo ou JARVIS_TEST_SCENE3D=1 (Linux com Xvfb)")
    def test_real_scene_opens_or_falls_back_cleanly(self):
        from ultron.hud import scene3d
        if scene3d.webengine_import_error():
            self.skipTest("QtWebEngine (PySide6-Addons) não instalado")
        env = {k: v for k, v in os.environ.items() if k != "QT_QPA_PLATFORM"}
        env["PYTHONIOENCODING"] = "utf-8"
        done = subprocess.run([sys.executable, str(Path(__file__).with_name("scene3d_probe.py"))], capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=240, env=env,
                              stdin=subprocess.DEVNULL)
        line = next((ln for ln in done.stdout.splitlines() if ln.startswith("SONDA ")), "")
        self.assertTrue(line, f"sonda sem resultado (código {done.returncode}): {done.stdout[-800:]} {done.stderr[-1500:]}")
        result = json.loads(line[len("SONDA "):])
        print(f"\n  cena 3D real: {json.dumps(result, ensure_ascii=False)[:600]}", file=sys.stderr)
        self.assertTrue(result["available"], result.get("reason"))
        if not result["ready"]:                                   # sem WebGL 2: a falha precisa ter motivo
            self.assertTrue(result["failed"], "nem pronta nem falha: a interface ficaria em branco")
            return
        self.assertEqual(result["js_errors"], 0)
        self.assertFalse(result["failed_after"])
        self.assertEqual(result["jarvis"]["mode"], "jarvis")
        self.assertTrue(result["jarvis"]["deck"])
        self.assertTrue(result["jarvis"]["connected"], "a página recebe os sinais do JARVIS")
        self.assertEqual(result["tardis"]["mode"], "tardis")
        self.assertTrue(result["tardis"]["room"])
        self.assertFalse(result["tardis"]["deck"])
        self.assertEqual(result["tardis"]["selected"], "telemetria")
        self.assertEqual(result["requests"], ["jarvis"], "o botão da página vira pedido ao Python")


if __name__ == "__main__":
    unittest.main()
