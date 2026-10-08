import time
import unittest

import helpers

from ultron.hud.brain_model import REGIONS, TYPE_REGIONS, BrainGeometry, development_for
from ultron.hud.scene import BOOT_PHASES, CAMERA_STATES, NeuralScene

GEOMETRY = BrainGeometry()


def make_scene():
    clock = helpers.FakeClock()
    return NeuralScene(GEOMETRY, clock=clock), clock


def run(scene, clock, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        clock.advance(dt)
        scene.step(dt)


BOOT_ORDER = ["privacy", "memory", "world_model", "models", "goals", "network", "skills", "agent", "imagination",
              "voice_output", "neural_audio", "voice", "perception", "proactive", "plugins", "health"]


class BrainModelTest(unittest.TestCase):
    def test_nodes_have_stable_positions_inside_their_regions(self):
        for type_, regions in TYPE_REGIONS.items():
            x, y = GEOMETRY.place(f"{type_.lower()}:exemplo", type_)
            self.assertEqual((x, y), GEOMETRY.place(f"{type_.lower()}:exemplo", type_), "posição determinística")
            self.assertTrue(GEOMETRY.inside(x, y), type_)
            nearest = min(REGIONS, key=lambda r: (REGIONS[r][0] - x) ** 2 + (REGIONS[r][1] - y) ** 2)
            self.assertTrue(any(abs(REGIONS[r][0] - x) < 0.45 and abs(REGIONS[r][1] - y) < 0.45 for r in regions),
                            f"{type_} longe de suas regiões (mais perto de {nearest})")

    def test_brain_grows_with_the_graph(self):
        self.assertEqual(development_for(0, 0), 0.0)
        self.assertLess(development_for(10, 10), development_for(200, 400))
        self.assertLessEqual(development_for(10 ** 6, 10 ** 6), 1.0)
        self.assertLess(len(GEOMETRY.visible_folds(0.1)), len(GEOMETRY.visible_folds(0.9)))

    def test_cortex_texture_depth_follows_development(self):
        import numpy as np
        from ultron.hud.cortex import CortexRenderer
        renderer = CortexRenderer(GEOMETRY, width=160)
        young, mature = renderer.texture(0.05), renderer.texture(1.0)
        self.assertEqual(young.shape[2], 4)
        inside = young[..., 3] > 0
        self.assertTrue(inside.any() and (~inside).any(), "alfa recorta a silhueta")
        def folding(t):
            """Variação local da luminância (relevo das dobras), longe da borda."""
            lum = t[..., :3].astype(float).mean(axis=2)
            gy, gx = np.gradient(lum)
            mask = t[..., 3] > 0
            interior = mask[2:-2, 2:-2] & mask[:-4, 2:-2] & mask[4:, 2:-2] & mask[2:-2, :-4] & mask[2:-2, 4:]
            return float(np.hypot(gx, gy)[2:-2, 2:-2][interior].mean())
        self.assertGreater(folding(mature), 1.5 * folding(young), "cérebro maduro é mais dobrado")


class SceneTest(unittest.TestCase):
    def test_boot_never_runs_ahead_of_real_events(self):
        scene, clock = make_scene()
        scene.on_event("SYSTEM_BOOT", {})
        scene.on_event("COMPONENT_STARTED", {"component": "privacy"})
        run(scene, clock, 5)
        self.assertEqual(scene.boot.phase, 1, "sem novos componentes, a sequência espera")
        self.assertTrue(scene.boot.active)
        for name in BOOT_ORDER[1:]:
            scene.on_event("COMPONENT_STARTED", {"component": name})
        scene.on_event("COMPONENT_FAILED", {"component": "voice", "error": "sem microfone"})
        scene.on_event("SYSTEM_READY", {})
        run(scene, clock, 6)
        self.assertTrue(scene.boot.done)
        voice_phase = [name for _label, name in BOOT_PHASES].index("voice")
        self.assertEqual(scene.boot.phase_failed(voice_phase), "sem microfone")
        self.assertEqual(len(BOOT_PHASES), 12)

    def test_camera_and_depth_follow_runtime_state(self):
        scene, clock = make_scene()
        expectations = {"IDLE": "OVERVIEW", "LISTENING": "FOCUS", "THINKING": "THINKING",
                        "IMAGINING": "IMAGINATION", "SIMULATING": "SIMULATION", "NETWORK": "NETWORK_FOCUS"}
        for runtime, camera in expectations.items():
            scene.on_state({"runtime_state": runtime})
            run(scene, clock, 0.5)
            self.assertEqual(scene.camera.state, camera, runtime)
            self.assertIn(scene.camera.state, CAMERA_STATES)
        scene.on_state({"runtime_state": "IDLE"})
        run(scene, clock, 6)
        self.assertEqual(scene.depth_level, 0)
        steps = [{"id": str(i), "description": f"etapa {i}", "status": "PENDING"} for i in range(10)]
        scene.on_state({"runtime_state": "EXECUTING", "current_plan": {"steps": steps}})
        run(scene, clock, 6)
        self.assertGreaterEqual(scene.depth_level, 6, "tarefa longa = mergulho cognitivo mais profundo")
        self.assertLessEqual(scene.depth_level, 9)

    def test_memory_and_concept_events_move_the_camera(self):
        scene, clock = make_scene()
        scene.on_state({"runtime_state": "THINKING"})
        scene.on_event("MEMORY_RECALLED", {"count": 3, "query": "projeto Atlas"})
        run(scene, clock, 0.2)
        self.assertEqual(scene.camera.state, "MEMORY_DIVE")
        scene.on_event("CONCEPT_CREATED", {"name": "Halcyra"})
        run(scene, clock, 0.2)
        self.assertEqual(scene.camera.state, "IDEA_FOCUS")
        run(scene, clock, 5)
        self.assertEqual(scene.camera.state, "THINKING", "foco transitório volta ao estado real")

    def test_modules_exist_only_while_real_data_exists(self):
        scene, clock = make_scene()
        steps = [{"id": "a", "description": "localizar", "status": "DONE"},
                 {"id": "b", "description": "executar", "status": "RUNNING"}]
        scene.on_state({"runtime_state": "AWAITING_AUTHORIZATION", "current_plan": {"steps": steps},
                        "pending_authorization": {"status": "pending", "description": "mover arquivo",
                                                  "risk": "high", "created": time.time(), "expires": time.time() + 30}})
        run(scene, clock, 1)
        keys = [m.key for m in scene.visible_modules()]
        self.assertEqual(keys[:2], ["authorization", "plan"], "autorização tem prioridade")
        self.assertEqual(scene.headline(), "AUTHORIZATION REQUIRED")
        self.assertGreater(scene.suspense, 0.5)
        scene.on_state({"runtime_state": "IDLE", "current_plan": {"steps": steps}})
        run(scene, clock, 4)
        self.assertEqual(scene.visible_modules(), [], "sem tarefa ativa, os módulos se recolhem")

    def test_graph_events_create_nodes_synapses_and_signals(self):
        scene, clock = make_scene()
        scene.load_graph({"nodes": [{"id": "memory:a", "type": "MEMORY", "label": "a"}], "edges": [],
                          "total_nodes": 1, "total_edges": 0})
        scene.on_event("GRAPH_NODE_ADDED", {"id": "idea:b", "type": "IDEA", "label": "b", "parent": "memory:a"})
        self.assertIn("idea:b", scene.nodes)
        self.assertEqual(len(scene.edges), 1)
        self.assertTrue(scene.particles, "o sinal percorre a nova sinapse")
        scene.on_event("GRAPH_ACTIVATED", {"ids": ["memory:a"]})
        self.assertGreater(scene.nodes["memory:a"].activation, 0.9)
        run(scene, clock, 5)
        self.assertLess(scene.nodes["memory:a"].activation, 0.1, "ativação decai: nada fica aceso sem causa")
        self.assertEqual(scene.particles, [])

    def test_idle_scene_is_calm(self):
        scene, clock = make_scene()
        scene.on_state({"runtime_state": "IDLE"})
        run(scene, clock, 3)
        self.assertEqual(scene.particles, [])
        self.assertEqual(scene.pulses, [])
        self.assertEqual(scene.suspense, 0.0)


@unittest.skipIf(helpers.QUICK, "teste lento (--quick)")
@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class RenderTest(unittest.TestCase):
    def test_offscreen_render_and_cached_layers(self):
        from PySide6 import QtGui, QtWidgets
        from ultron.hud.brain_view import BrainView
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        scene, clock = make_scene()
        scene.load_graph({"nodes": [{"id": f"concept:{i}", "type": "CONCEPT", "label": str(i), "strength": 0.5}
                                    for i in range(40)], "edges": [], "total_nodes": 40, "total_edges": 0})
        view = BrainView(scene, cache_dir=helpers.temp_dir())
        view.resize(960, 600)
        deadline = time.time() + 30
        while view._texture is None and time.time() < deadline:
            app.processEvents()
            time.sleep(0.02)
        self.assertIsNotNone(view._texture, "textura do córtex calculada fora da thread da interface")
        scene.on_state({"runtime_state": "IDLE"})
        run(scene, clock, 3)
        image = QtGui.QImage(view.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
        view.render(image)
        renders = view.base_renders
        started = time.perf_counter()
        for _ in range(20):
            run(scene, clock, 1 / 60)
            view.render(image)
        per_frame = (time.perf_counter() - started) / 20
        self.assertLessEqual(view.base_renders - renders, 2, "em repouso a camada base vem do cache "
                                                            "(só a respiração lenta a renova)")
        self.assertLess(per_frame, 0.05)
        center = image.pixelColor(480, 280)
        self.assertGreater(center.red() + center.green(), 20, "o cérebro aparece no centro")


if __name__ == "__main__":
    unittest.main()
