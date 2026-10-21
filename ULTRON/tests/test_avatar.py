"""Avatar holográfico: os 12 estados a partir de sinais reais, o animador (boca, boot, olhos, viseira),
a renderização em todos os perfis, o widget com eventos reais e a boca ligada à fala de ponta a ponta.

Renderização em Qt offscreen (CPU). A opção por GPU é testada só quanto à volta para a CPU quando o
OpenGL não abre — não é teste de placa de vídeo.
"""
import time
import unittest

import numpy as np

import helpers

from ultron.hud.avatar.animator import Animator
from ultron.hud.avatar.geometry import FaceGeometry
from ultron.hud.avatar.states import ORDER, STYLES, AvatarSignals, active_states, resolve


def signals(**values):
    base = dict(now=1000.0, booted=True, runtime_state="IDLE")
    base.update(values)
    return AvatarSignals(**base)


class StatesTest(unittest.TestCase):
    def test_each_of_the_12_states_comes_from_its_real_signal(self):
        cases = {
            "privacidade": signals(privacy_shield=True),
            "erro": signals(runtime_state="ERROR"),
            "confirmacao": signals(authorization=True),
            "falando": signals(audible=True),
            "alerta": signals(alert_until=1003.0, alert_text="Lembrete: dentista"),
            "reconhecendo": signals(listening=True, recognizing=True),
            "escutando": signals(listening=True),
            "tardis": signals(tardis=True),
            "executando": signals(runtime_state="EXECUTING"),
            "pensando": signals(runtime_state="PLANNING"),
            "inicializando": signals(booted=False, runtime_state="BOOTING", boot_progress=0.4),
            "aguardando": signals(),
        }
        self.assertEqual(set(cases), set(STYLES), "os 12 estados")
        for key, sig in cases.items():
            self.assertEqual(resolve(sig).key, key, key)
        self.assertEqual(len(ORDER), 12)
        self.assertEqual(resolve(cases["inicializando"]).detail, "40% dos componentes")

    def test_priorities_follow_the_architecture(self):
        everything = signals(privacy_shield=True, runtime_state="ERROR", authorization=True, audible=True,
                             listening=True, recognizing=True, tardis=True, alert_until=1005.0)
        self.assertEqual(active_states(everything)[:4], ["privacidade", "erro", "confirmacao", "falando"])
        self.assertEqual(resolve(signals(audible=True, alert_until=1005.0)).key, "falando")
        self.assertEqual(resolve(signals(authorization=True, audible=True)).key, "confirmacao")
        tinted = resolve(signals(listening=True, alert_until=1005.0, alert_text="Lembrete"))
        self.assertEqual(tinted.key, "alerta")
        speaking_alert = resolve(signals(audible=True, alert_until=1005.0))
        self.assertFalse(speaking_alert.alert_tint, "falar tem prioridade maior que o alerta")
        expired = resolve(signals(alert_until=999.0, error_until=999.0))
        self.assertEqual(expired.key, "aguardando", "janelas de alerta/erro vencidas não contam")


class AnimatorTest(unittest.TestCase):
    def run_frames(self, animator, sig, seconds, *, mouth=None, boot=1.0, **levels):
        for _ in range(int(seconds * 30)):
            rig = animator.step(1 / 30, resolve(sig), mouth=mouth, boot_progress=boot, **levels)
        return rig

    def test_mouth_follows_the_track_and_closes_when_speech_stops(self):
        animator = Animator()
        open_mouth = {"open": 0.8, "wide": 0.3, "round": 0.0, "press": 0.0, "teeth": 0.5, "energy": 0.9}
        rig = self.run_frames(animator, signals(audible=True), 0.3, mouth=open_mouth)
        self.assertGreater(rig.jaw, 0.7)
        rig = self.run_frames(animator, signals(), 0.2, mouth=open_mouth)
        self.assertLess(rig.jaw, 0.05, "sem fala audível a boca volta ao repouso (mesmo com trilha)")

    def test_boot_assembly_never_runs_ahead_of_real_progress(self):
        animator = Animator()
        sig = signals(booted=False, runtime_state="BOOTING", boot_progress=0.3)
        rig = self.run_frames(animator, sig, 3.0, boot=0.3)
        self.assertLessEqual(rig.assemble, 0.3 + 1e-6)
        self.assertLess(rig.eye_open, 0.05, "olhos fechados até o rosto estar montado")
        rig = self.run_frames(animator, signals(), 3.0)
        self.assertGreater(rig.assemble, 0.99)
        self.assertGreater(rig.eye_open, 0.9)

    def test_privacy_visor_and_natural_blinks(self):
        animator = Animator(seed=3)
        blinks = 0
        previous = 0.0
        for _ in range(30 * 12):
            rig = animator.step(1 / 30, resolve(signals()))
            if rig.blink > 0.9 and previous <= 0.9:
                blinks += 1
            previous = rig.blink
        self.assertGreaterEqual(blinks, 2, "piscadas naturais em repouso")
        rig = self.run_frames(animator, signals(privacy_shield=True), 2.0)
        self.assertGreater(rig.visor, 0.95)
        self.assertLess(rig.eye_open, 0.05)
        self.assertLess(rig.glow, 0.5, "brilho reduzido no modo privacidade")

    def test_states_change_expression(self):
        thinking = self.run_frames(Animator(), signals(runtime_state="PLANNING"), 2.0)
        confirm = self.run_frames(Animator(), signals(authorization=True), 2.0)
        error = self.run_frames(Animator(), signals(runtime_state="ERROR"), 2.0)
        self.assertLess(thinking.brow, -0.2, "pensando: sobrancelhas franzidas")
        self.assertGreater(confirm.brow, 0.5, "confirmação: sobrancelhas erguidas")
        self.assertGreater(error.glitch, 0.9)
        self.assertGreater(error.rgb[0], 200, "erro: tom coral")
        self.assertGreater(confirm.rgb[0], 200, "confirmação: âmbar")


class GeometryTest(unittest.TestCase):
    def test_normals_point_outward_and_jaw_moves_only_the_lower_face(self):
        geo = FaceGeometry()
        row = int(np.argmin(np.abs(geo.levels - 0.3)))
        front = int(np.argmin(np.abs(geo.theta)))
        self.assertGreater(geo.rest_normals[row, front, 2], 0.9)
        grid, _ = geo.posed_grid(0.9)
        moved = np.abs(grid - geo.grid).max(axis=(1, 2))
        self.assertLess(moved[geo.levels > -0.3].max(), 1e-9, "acima da boca nada se move")
        self.assertGreater(moved.max(), 0.02)


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_every_state_renders_in_every_profile_within_budget(self):
        from PySide6 import QtGui

        from ultron.hud.avatar.renderer import QUALITY, AvatarRenderer
        renderer = AvatarRenderer()
        image = QtGui.QImage(960, 600, QtGui.QImage.Format_ARGB32_Premultiplied)
        timings = {}
        for profile, quality in QUALITY.items():
            for key in ORDER:
                animator = Animator()
                sig = {"privacidade": signals(privacy_shield=True), "falando": signals(audible=True),
                       "inicializando": signals(booted=False, runtime_state="BOOTING")}.get(key, signals())
                rig = animator.step(0.2, resolve(sig), mouth={"open": 0.6, "wide": 0, "round": 0, "press": 0,
                                                             "teeth": 0.5, "energy": 0.7})
                painter = QtGui.QPainter(image)
                started = time.perf_counter()
                stats = renderer.render(painter, 960, 600, rig, 1.0, quality)
                timings.setdefault(profile, []).append(time.perf_counter() - started)
                painter.end()
                self.assertGreater(stats["draw_calls"], 10)
        for profile, values in timings.items():
            self.assertLess(float(np.median(values)), 0.15, f"{profile}: quadro absurdamente lento")


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class ViewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_real_events_drive_the_view(self):
        from ultron.hud.avatar.view import AvatarView
        captions = []

        def caption():
            captions.append(True)
            return {"text": "Entendido, senhor.", "progress": 0.5, "active": True}

        view = AvatarView(caption=caption)
        view.resize(800, 500)
        view.on_state({"runtime_state": "BOOTING", "boot": {"done": 3, "total": 10}})
        view.step(0.05)
        self.assertEqual(view.resolved.key, "inicializando")
        self.assertIn("30%", view.resolved.detail)
        view.on_event("SYSTEM_READY", {})
        view.on_state({"runtime_state": "IDLE", "boot": {"done": 10, "total": 10}})
        view.step(0.05)
        self.assertEqual(view.resolved.key, "aguardando")
        view.on_event("COMPONENT_FAILED", {"component": "voice", "error": "sem microfone"})
        view.step(0.05)
        self.assertEqual(view.resolved.key, "erro")
        self.assertIn("voice", view.resolved.detail)
        view.signals.error_until = 0.0
        view.on_event("REMINDER_DUE", {"notice": "Lembrete: dentista", "silent": False})
        view.step(0.05)
        self.assertEqual((view.resolved.key, view.resolved.detail), ("alerta", "Lembrete: dentista"))
        view.on_state({"runtime_state": "IDLE", "privacy_shield": {"active": True}})
        view.step(0.05)
        self.assertEqual(view.resolved.key, "privacidade")
        view.grab()                                           # pinta um quadro (widget fora da tela)
        self.assertTrue(captions, "a legenda é lida a cada quadro")
        self.assertGreater(view.paint_count, 0)

    def test_tardis_and_noctario_events_map_to_states(self):
        from ultron.hud.avatar.view import AvatarView
        view = AvatarView()
        view.on_state({"runtime_state": "IDLE", "boot": {"done": 1, "total": 1}})
        view.on_event("SYSTEM_READY", {})
        view.on_event("TARDIS_TASK_STARTED", {"id": "t1", "origin": "jarvis", "kind_label": "análise"})
        view.step(0.05)
        self.assertEqual(view.resolved.key, "tardis")
        view.on_event("TARDIS_TASK_FINISHED", {"id": "t1"})
        view.step(0.05)
        self.assertEqual(view.resolved.key, "aguardando")
        view.on_event("NOCTARIO_LINK", {"link": "perdido", "requested": True})
        view.step(0.05)
        self.assertEqual(view.resolved.key, "aguardando", "desconexão pedida pelo usuário não é erro")
        view.on_event("NOCTARIO_LINK", {"link": "perdido", "requested": False})
        view.step(0.05)
        self.assertEqual(view.resolved.key, "erro")


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class ControllerAvatarTest(unittest.TestCase):
    def test_face_is_default_and_settings_switch_view_and_backend(self):
        from PySide6 import QtWidgets

        from fake_ollama import FakeOllama
        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.hud.avatar.view import AvatarView
        from ultron.hud.brain_view import BrainView
        from ultron.hud.controller import HudController
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        with FakeOllama(["qwen2.5:3b"], responder=lambda payload: "ok") as fake:
            manager = SettingsManager(helpers.temp_dir() / "settings.json")
            manager.load()
            manager.settings.ollama_url = fake.url
            manager.settings.network_discovery = False
            manager.settings.auto_backup = False
            core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
            controller = HudController(core)
            try:
                controller.show()
                self.assertIsInstance(controller.central(), AvatarView, "o rosto holográfico é a vista padrão")
                manager.update(avatar_mode="neural")
                self._pump(app, lambda: isinstance(controller.central(), BrainView))
                self.assertIsInstance(controller.central(), BrainView)
                manager.update(avatar_mode="face")
                self._pump(app, lambda: controller.central() is controller.avatar)
                manager.update(render_backend="gpu")
                self._pump(app, lambda: controller.avatar_reason != "CPU")
                self.assertTrue(controller.avatar_reason.startswith(("GPU", "CPU — OpenGL")), controller.avatar_reason)
                self.assertIs(controller.central(), controller.avatar)
                manager.update(render_backend="cpu")
                self._pump(app, lambda: controller.avatar_reason == "CPU")
                self.assertEqual(controller.avatar.backend, "cpu")
            finally:
                controller.quit()
                core.memory.db.close()

    @staticmethod
    def _pump(app, condition, seconds=3.0):
        from PySide6 import QtCore
        end = time.time() + seconds
        while time.time() < end and not condition():
            app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            time.sleep(0.01)


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class SpeechToMouthTest(unittest.TestCase):
    def test_spoken_audio_opens_the_mouth_and_silence_returns_to_rest(self):
        from PySide6 import QtWidgets

        from test_lipsync import FakeTimedOutput, SegmentSynth
        from ultron.hud.avatar.view import AvatarView
        from ultron.voice.tts import Speaker
        QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        settings = helpers.make_settings()
        speaker = Speaker(FakeTimedOutput(), settings_getter=lambda: settings,
                          synth_loader=lambda: (SegmentSynth(), ""))
        speaker.start()
        self.addCleanup(speaker.stop)
        self.assertTrue(speaker.wait_ready(5))
        view = AvatarView(mouth=speaker.mouth, caption=speaker.caption, audible=speaker.audible)
        view.on_state({"runtime_state": "IDLE", "boot": {"done": 1, "total": 1}})
        view.on_event("SYSTEM_READY", {})
        speaker.say("Pá, má.")
        states, jaws = [], []
        deadline = time.time() + 5
        started = False
        while time.time() < deadline:
            view.step(1 / 60)
            states.append(view.resolved.key)
            jaws.append(view.animator.rig.jaw)
            started = started or speaker.speaking
            if started and not speaker.speaking and view.animator.rig.jaw < 0.01:
                break
            time.sleep(1 / 60)
        self.assertIn("falando", states)
        self.assertGreater(max(jaws), 0.3, "a boca abriu com o áudio")
        self.assertEqual(states[-1], "aguardando")
        self.assertLess(jaws[-1], 0.01, "terminada a fala, a boca volta ao repouso")


if __name__ == "__main__":
    unittest.main()
