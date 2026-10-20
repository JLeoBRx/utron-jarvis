"""Desempenho dos hubs: cadência adaptativa, causas de movimento e caches (sem medir tempo real)."""
import unittest

import helpers

from ultron.hud import quality
from ultron.hud.brain_model import BrainMesh
from ultron.hud.scene import NeuralScene
from ultron.hud.tardis_scene import TardisScene

MESH = BrainMesh()


def run(scene, clock, seconds, dt=1 / 30):
    for _ in range(int(seconds / dt)):
        clock.advance(dt)
        scene.step(dt)


class CadenceTest(unittest.TestCase):
    def test_profiles_are_ordered_and_capped_by_the_user_limit(self):
        names = list(quality.NAMES)
        self.assertEqual(names, ["economy", "balanced", "high", "cinematic"])
        for key in ("max_fps", "idle_fps", "background_fps", "max_particles"):
            values = [getattr(quality.get(n), key) for n in names]
            self.assertEqual(values, sorted(values), f"{key} cresce do econômico ao cinematográfico")
        for name in names:
            profile = quality.get(name)
            self.assertLess(profile.background_fps, profile.idle_fps)
            self.assertLess(profile.idle_fps, profile.max_fps)
            self.assertLessEqual(quality.effective_fps(profile, 30, active=True), 30, "hud_fps é o teto")
        self.assertEqual(quality.get("performance").name, "economy", "nome antigo do ULTRON continua valendo")

    def test_background_hub_drops_to_background_cadence_even_in_motion(self):
        profile = quality.get("balanced")
        self.assertEqual(quality.effective_fps(profile, 60, active=True), 60)
        self.assertEqual(quality.effective_fps(profile, 60, active=False), profile.idle_fps)
        self.assertEqual(quality.effective_fps(profile, 60, active=True, background=True), profile.background_fps)


class IdleMotionTest(unittest.TestCase):
    def _scene(self):
        clock = helpers.FakeClock()
        scene = NeuralScene(MESH, clock=clock)
        for component in ("health", "memory", "models"):
            scene.on_event("COMPONENT_STARTED", {"component": component})
        scene.on_state({"runtime_state": "IDLE"})
        run(scene, clock, 4)
        return scene, clock

    def test_routine_health_check_does_not_animate_the_brain(self):
        scene, clock = self._scene()
        self.assertFalse(scene.in_motion())
        scene.on_event("HEALTH_UPDATED", {"overall": "OK", "changed": False, "problems": {}})
        run(scene, clock, 0.5)
        self.assertEqual(scene.subsystems["TELEMETRIA"].grow, 0.0, "rotina: só brilho, nenhuma sinapse cresce")
        self.assertFalse(scene.in_motion(), "a verificação de rotina não tira a cena do repouso")

    def test_real_health_change_is_shown(self):
        scene, clock = self._scene()
        scene.on_event("HEALTH_UPDATED", {"overall": "WARN", "changed": True, "problems": {"DISK": "disco cheio"}})
        run(scene, clock, 0.3)
        self.assertGreater(scene.subsystems["TELEMETRIA"].grow, 0.0)
        self.assertTrue(scene.in_motion())
        self.assertIn("health", scene.modules)

    def test_idle_rotation_is_slow_and_calm(self):
        scene, clock = self._scene()
        before = scene.camera.angle
        run(scene, clock, 1.0)
        turned = (scene.camera.angle - before) % 6.283185307179586
        self.assertLess(turned, 0.1, "repouso: giro lento (rad/s)")
        self.assertGreater(turned, 0.0, "repouso não é parado: a cena continua viva")


class HealthSignatureTest(unittest.TestCase):
    def test_changed_only_when_the_picture_changes(self):
        from types import SimpleNamespace
        from unittest import mock

        from ultron.health import monitor as monitor_module

        seen = []
        bus = SimpleNamespace(publish=lambda kind, payload, source="": seen.append(payload))
        status = {"MEMORY": "OK"}
        ok = lambda *a, **k: {"status": "OK", "detail": ""}                     # noqa: E731
        monitor = monitor_module.HealthMonitor(bus=bus, probes={
            "MEMORY": lambda: {"status": status["MEMORY"], "detail": "x"}})
        with mock.patch.multiple(monitor_module, check_cpu=ok, check_ram=ok, check_disk=ok, check_gpu=ok):
            monitor.check_all()
            monitor.check_all()
            status["MEMORY"] = "WARN"
            monitor.check_all()
            monitor.check_all()
        self.assertEqual([p["changed"] for p in seen], [True, False, True, False])
        self.assertEqual(seen[-1]["problems"], {"MEMORY": "x"})


class TardisSceneMotionTest(unittest.TestCase):
    def test_idle_flow_is_slower_than_active_flow(self):
        def travel(activity):
            clock = helpers.FakeClock()
            scene = TardisScene(clock=clock, max_particles=40, seed=3)
            scene.set_activity(activity)
            start = [p.angle for p in scene.particles]
            run(scene, clock, 1.0)
            return sum(abs(p.angle - a) for p, a in zip(scene.particles, start))

        self.assertLess(travel("IDLE"), travel("EXECUTING") * 0.7)

    def test_only_real_events_put_the_tardis_in_motion(self):
        clock = helpers.FakeClock()
        scene = TardisScene(clock=clock, max_particles=20)
        run(scene, clock, 0.5)
        self.assertFalse(scene.in_motion(), "repouso: partículas lentas não pedem o teto de quadros")
        scene.on_event("RECORD_CREATED", {"record": {"kind": "task", "confirmed": True}})
        self.assertTrue(scene.in_motion())
        run(scene, clock, 6)
        self.assertFalse(scene.in_motion(), "o pulso termina e a energia decai")


class AdaptivePerceptionTest(unittest.TestCase):
    def test_sensors_relax_while_the_user_is_away_and_restore_on_return(self):
        from types import SimpleNamespace

        from ultron.perception import engine as engine_module

        intervals = {}
        scheduler = SimpleNamespace(set_interval=lambda name, value: intervals.__setitem__(name, value),
                                    every=lambda *a, **k: None, set_enabled=lambda *a, **k: None)
        sensors = [SimpleNamespace(name="windows", interval=1.0), SimpleNamespace(name="vision", interval=20.0),
                   SimpleNamespace(name="microphone", interval=1.0)]

        class Engine(engine_module.PerceptionEngine):                  # sensores simulados, sem hardware
            sensors = property(lambda self: sensors)

        engine = Engine.__new__(Engine)
        engine.runtime = SimpleNamespace(scheduler=scheduler)
        engine.away = False
        engine._base_intervals = {s.name: s.interval for s in sensors}
        self.assertFalse(engine.adapt_to_presence(30.0), "usuário presente: nada muda")
        self.assertTrue(engine.adapt_to_presence(engine_module.AWAY_AFTER + 1))
        self.assertEqual(sensors[0].interval, 3.0)
        self.assertEqual(sensors[1].interval, 80.0)
        self.assertEqual(sensors[2].interval, 1.0, "microfone nunca é relaxado")
        self.assertEqual(intervals["sense:windows"], 3.0)
        self.assertFalse(engine.adapt_to_presence(engine_module.AWAY_AFTER + 60), "já relaxado")
        self.assertTrue(engine.adapt_to_presence(2.0))
        self.assertEqual((sensors[0].interval, sensors[1].interval), (1.0, 20.0), "volta ao configurado")
        self.assertFalse(engine.adapt_to_presence(None), "sem medição de ociosidade: nada muda")


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class TardisStructureCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_structure_is_redrawn_only_when_it_changes(self):
        from PySide6 import QtGui

        from ultron.hud.tardis import TardisView

        clock = helpers.FakeClock()
        scene = TardisScene(clock=clock, max_particles=30)
        view = TardisView(scene)
        view.resize(900, 600)
        image = QtGui.QImage(view.size(), QtGui.QImage.Format_ARGB32_Premultiplied)

        def frames(n):
            for _ in range(n):
                clock.advance(1 / 15)
                scene.step(1 / 15)
                view.render(image)

        frames(3)
        self.assertEqual(view.structure_renders, 1, "câmera parada: a estrutura vem do cache")
        scene.apply_data({"regions": {"tasks": {"count": 3, "items": [{"id": "a", "title": "a", "status": "open",
                                                                     "priority": 2}]}}, "today": {}})
        frames(2)
        self.assertEqual(view.structure_renders, 2, "dados novos do banco: refeita uma vez")
        scene.on_event("RECORD_CREATED", {"record": {"kind": "task", "confirmed": True}})
        frames(4)
        self.assertEqual(view.structure_renders, 2, "evento real acende a camada de movimento, não a estrutura")
        scene.focus_region("tasks")
        frames(3)
        self.assertGreater(view.structure_renders, 2, "a câmera viajando refaz a estrutura")
        for _ in range(120):
            clock.advance(1 / 15)
            scene.step(1 / 15)
        frames(1)
        settled = view.structure_renders
        frames(5)
        self.assertEqual(view.structure_renders, settled, "câmera parada de novo: cache")


if __name__ == "__main__":
    unittest.main()
