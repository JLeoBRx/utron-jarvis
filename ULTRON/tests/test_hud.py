import math
import time
import unittest

import numpy as np

import helpers

from ultron.hud.brain_model import MIN_VISIBLE, REGIONS, TYPE_REGIONS, BrainMesh, development_for
from ultron.hud.scene import BOOT_PHASES, CAMERA_STATES, NeuralScene

MESH = BrainMesh()


def make_scene():
    clock = helpers.FakeClock()
    return NeuralScene(MESH, clock=clock), clock


def run(scene, clock, seconds, dt=1 / 60):
    for _ in range(int(seconds / dt)):
        clock.advance(dt)
        scene.step(dt)


def region_depth(scene, region):
    """Profundidade (Z rotacionado; > 0 = voltado para o observador) do centro da região."""
    sides = (1.0, -1.0) if REGIONS[region][2] else (1.0,)
    points = np.array([MESH.region_center(region, side) for side in sides])
    _x, _y, z = MESH.rotate(points, scene.camera.angle)
    return float(z.max())


BOOT_ORDER = ["privacy", "memory", "world_model", "models", "goals", "network", "skills", "agent", "imagination",
              "voice_output", "neural_audio", "voice", "perception", "proactive", "plugins", "health"]


class BrainMeshTest(unittest.TestCase):
    def test_nodes_have_stable_positions_inside_their_regions(self):
        for type_, regions in TYPE_REGIONS.items():
            for i in range(6):
                node_id = f"{type_.lower()}:exemplo{i}"
                x, y, z = MESH.place(node_id, type_)
                self.assertEqual((x, y, z), MESH.place(node_id, type_), "posição determinística")
                self.assertTrue(MESH.inside(x, y, z), type_)
                near = [r for r in regions
                        if min(np.linalg.norm(np.array([x, y, z]) - MESH.region_center(r, s)) for s in (1, -1))
                        <= REGIONS[r][3] * 1.5]
                self.assertTrue(near, f"{type_} {node_id} fora das regiões do seu tipo")

    def test_brain_grows_with_the_graph(self):
        self.assertEqual(development_for(0, 0), 0.0)
        self.assertLess(development_for(10, 10), development_for(200, 400))
        self.assertLessEqual(development_for(10 ** 6, 10 ** 6), 1.0)
        young, mature = MESH.visible_indices(0.0), MESH.visible_indices(1.0)
        self.assertEqual(len(young), MIN_VISIBLE)
        self.assertEqual(len(mature), len(MESH.points))
        self.assertTrue(set(young.tolist()) <= set(mature.tolist()), "crescer adensa; nenhum nó muda de lugar")
        self.assertLess(len(MESH.edges(young)), len(MESH.edges(mature)))
        steps = {MESH.visible_count(d / 1000) for d in range(1001)}
        self.assertLessEqual(len(steps), (len(MESH.points) - MIN_VISIBLE) // 20 + 1,
                             "cresce em degraus (as sinapses não são recalculadas a cada nó)")

    def test_young_brain_already_has_the_whole_silhouette(self):
        young = MESH.points[MESH.visible_indices(0.0)]
        full = MESH.points
        for axis in range(3):
            span = young[:, axis].max() - young[:, axis].min()
            self.assertGreater(span, 0.9 * (full[:, axis].max() - full[:, axis].min()), f"eixo {axis}")
        visible = set(MESH.visible_indices(0.0).tolist())
        for name in ("prefrontal", "occipital", "temporal", "cerebellum", "motor"):
            self.assertGreaterEqual(len(visible & set(MESH.membership[name].tolist())), 5, name)

    def test_synapses_are_local_unique_and_cached(self):
        indices = MESH.visible_indices(0.5)
        edges = MESH.edges(indices)
        self.assertIs(edges, MESH.edges(indices), "sinapses em cache")
        self.assertTrue((edges[:, 0] < edges[:, 1]).all())
        self.assertEqual(len(np.unique(edges, axis=0)), len(edges))
        lengths = np.linalg.norm(MESH.points[edges[:, 0]] - MESH.points[edges[:, 1]], axis=1)
        self.assertLess(lengths.max(), 0.5, "só vizinhos próximos se ligam")

    def test_projection_perspective_and_facing(self):
        for region in ("auditory", "broca", "occipital", "prefrontal", "motor"):
            angle = MESH.facing_angle(region)
            sides = (-1.0,) if region == "broca" else (1.0,)
            _x, _y, z = MESH.rotate(MESH.region_center(region, sides[0])[None, :], angle)
            self.assertGreater(float(z[0]), 0.3, f"{region} voltada para o observador")
        sx, sy, z, f = MESH.project(MESH.points, 0.4, 100.0, 100.0, 50.0)
        self.assertTrue(np.all(np.isfinite(sx)) and np.all(np.isfinite(sy)))
        self.assertTrue(((f > 1) == (z > 0)).all(), "o que está mais perto parece maior")


class SceneTest(unittest.TestCase):
    def test_boot_never_runs_ahead_of_real_events(self):
        scene, clock = make_scene()
        scene.on_event("SYSTEM_BOOT", {})
        self.assertEqual(scene.genesis(), 0.0, "antes dos componentes, nenhum nó nasceu")
        scene.on_event("COMPONENT_STARTED", {"component": "privacy"})
        run(scene, clock, 5)
        self.assertEqual(scene.boot.phase, 1, "sem novos componentes, a sequência espera")
        self.assertTrue(scene.boot.active)
        self.assertEqual(scene.genesis(), 0.0)
        for name in BOOT_ORDER[1:6]:
            scene.on_event("COMPONENT_STARTED", {"component": name})
        run(scene, clock, 3)
        self.assertTrue(0.0 < scene.genesis() < 1.0, "a malha nasce conforme os componentes sobem")
        for name in BOOT_ORDER[6:]:
            scene.on_event("COMPONENT_STARTED", {"component": name})
        scene.on_event("COMPONENT_FAILED", {"component": "voice", "error": "sem microfone"})
        scene.on_event("SYSTEM_READY", {})
        run(scene, clock, 6)
        self.assertTrue(scene.boot.done)
        self.assertEqual(scene.genesis(), 1.0)
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

    def test_brain_turns_the_working_region_to_the_viewer(self):
        scene, clock = make_scene()
        scene.on_state({"runtime_state": "IDLE"})
        start = scene.camera.angle
        run(scene, clock, 2)
        self.assertNotAlmostEqual(scene.camera.angle, start, msg="em repouso o cérebro gira devagar")
        for runtime, region in (("LISTENING", "auditory"), ("SPEAKING", "broca"), ("EXECUTING", "motor")):
            scene.on_state({"runtime_state": runtime})
            run(scene, clock, 4)
            self.assertGreater(region_depth(scene, region), 0.3, f"{runtime}: {region} à frente")
        scene.on_state({"runtime_state": "ERROR"})
        run(scene, clock, 0.5)
        angle = scene.camera.angle
        run(scene, clock, 1)
        self.assertAlmostEqual(scene.camera.angle, angle, places=6, msg="em erro, o giro para")

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

    def test_subsystem_ring_reflects_real_status_and_use(self):
        scene, clock = make_scene()
        self.assertTrue(all(sub.status == "unknown" for sub in scene.subsystems.values()), "nada é presumido")
        scene.on_event("COMPONENT_STARTED", {"component": "models"})
        scene.on_event("COMPONENT_STARTED", {"component": "memory"})
        scene.on_event("COMPONENT_FAILED", {"component": "voice", "error": "sem microfone"})
        scene.on_state({"runtime_state": "IDLE", "health": {"checks": {"VISION": {"status": "UNAVAILABLE",
                                                                                  "detail": "sem modelo"}}}})
        subs = scene.subsystems
        self.assertEqual((subs["OLLAMA"].status, subs["MEMÓRIA"].status), ("ok", "ok"))
        self.assertEqual(subs["VOZ"].status, "fail")
        self.assertEqual(subs["VISÃO"].status, "off")
        run(scene, clock, 1)
        self.assertEqual(subs["MEMÓRIA"].grow, 0.0, "sem uso, nenhuma sinapse até o subsistema")
        scene.on_event("MEMORY_RECALLED", {"count": 0})
        scene.on_event("WAKE_WORD", {})
        run(scene, clock, 0.4)
        self.assertGreater(subs["MEMÓRIA"].grow, 0.3, "a sinapse cresce enquanto a memória é usada")
        self.assertTrue(any(name == "MEMÓRIA" for name, _t in scene.ring_pulses) or subs["MEMÓRIA"].grow < 0.97)
        self.assertEqual(subs["VOZ"].grow, 0.0, "subsistema em falha não recebe sinapse")
        run(scene, clock, 8)
        self.assertEqual(subs["MEMÓRIA"].grow, 0.0, "o uso acabou: a sinapse se recolhe")

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
        development = scene.development
        scene.on_event("GRAPH_NODE_ADDED", {"id": "idea:b", "type": "IDEA", "label": "b", "parent": "memory:a"})
        self.assertIn("idea:b", scene.nodes)
        self.assertTrue(MESH.inside(scene.nodes["idea:b"].x, scene.nodes["idea:b"].y, scene.nodes["idea:b"].z))
        self.assertEqual(len(scene.edges), 1)
        self.assertGreater(scene.development, development, "o cérebro cresce com o grafo")
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
        self.assertTrue(all(sub.grow == 0.0 for sub in scene.subsystems.values()))


@unittest.skipIf(helpers.QUICK, "teste lento (--quick)")
@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class RenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def _view(self, scene, size=(1320, 820)):
        from ultron.hud.brain_view import BrainView
        view = BrainView(scene)
        view.resize(*size)
        return view

    def _render(self, view):
        from PySide6 import QtGui
        image = QtGui.QImage(view.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
        view.render(image)
        return image

    def test_render_reflects_real_data_and_is_fast(self):
        scene, clock = make_scene()
        scene.load_graph({"nodes": [{"id": f"concept:{i}", "type": "CONCEPT", "label": str(i), "strength": 0.5}
                                    for i in range(40)], "edges": [], "total_nodes": 40, "total_edges": 0})
        for name in BOOT_ORDER:
            scene.on_event("COMPONENT_STARTED", {"component": name})
        scene.on_state({"runtime_state": "IDLE", "privacy": {"local_mode": True}})
        run(scene, clock, 3)
        view = self._view(scene)
        image = self._render(view)
        stats = view.stats
        hidden_inner = int(np.isin(MESH.visible_indices(scene.development), np.nonzero(MESH.inner_mask)[0]).sum())
        self.assertEqual(stats["points"], MESH.visible_count(scene.development) - hidden_inner,
                         "a malha desenhada é a do tamanho real do grafo")
        self.assertGreater(stats["edges"], stats["points"])
        self.assertEqual(stats["graph_nodes"], 40)
        self.assertEqual(stats["ring"], len(scene.subsystems))
        self.assertEqual(stats["synapses"], 0, "em repouso, nenhum subsistema recebe sinal")
        frame = view.frame()
        lit = 0
        for dx in range(-60, 61, 6):
            for dy in range(-40, 41, 6):
                c = image.pixelColor(int(frame.cx + dx), int(frame.cy + dy))
                lit += c.red() + c.green() > 120
        self.assertGreater(lit, 3, "nós e sinapses aparecem no centro")
        renders = view.base_renders
        started = time.perf_counter()
        for _ in range(20):
            run(scene, clock, 1 / 60)
            self._render(view)
        per_frame = (time.perf_counter() - started) / 20
        self.assertLessEqual(view.base_renders - renders, 3, "fundo, órbitas e auréola vêm do cache")
        self.assertLess(per_frame, 0.05)

    def test_boot_genesis_starts_from_void(self):
        scene, clock = make_scene()
        scene.on_event("SYSTEM_BOOT", {})
        run(scene, clock, 0.05)
        view = self._view(scene)
        self._render(view)
        self.assertEqual((view.stats["points"], view.stats["ring"]), (0, 0), "VOID: nada nasceu ainda")
        for name in BOOT_ORDER[:6]:
            scene.on_event("COMPONENT_STARTED", {"component": name})
        run(scene, clock, 2.5)
        self._render(view)
        self.assertGreater(view.stats["points"], 0)
        self.assertLess(view.stats["points"], MESH.visible_count(scene.development))
        self.assertGreater(view.stats["ring"], 0, "subsistemas surgem com os componentes reais")
        self.assertLess(view.stats["ring"], len(scene.subsystems))

    def test_orb_draws_the_rotating_mini_brain(self):
        from PySide6 import QtCore, QtGui
        from ultron.hud.orb import OrbWindow
        scene, clock = make_scene()
        scene.on_state({"runtime_state": "IDLE"})
        run(scene, clock, 1)
        orb = OrbWindow(scene)
        image = QtGui.QImage(orb.size(), QtGui.QImage.Format_ARGB32_Premultiplied)
        image.fill(QtGui.QColor(0, 0, 0))
        painter = QtGui.QPainter(image)
        orb.render(painter, QtCore.QPoint(0, 0))
        painter.end()
        lit = sum(image.pixelColor(x, y).green() > 90 for x in range(30, 74, 2) for y in range(30, 74, 2))
        self.assertGreater(lit, 5, "o cérebro em miniatura aparece no orbe")
        self.assertTrue(math.isfinite(scene.camera.angle))


if __name__ == "__main__":
    unittest.main()
