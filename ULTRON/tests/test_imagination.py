import json
import unittest

import helpers

from fake_ollama import FakeOllama
from ultron.core.events import EventType
from ultron.imagination.dream_mode import DreamMode
from ultron.imagination.image_pipeline import ImagePipeline, ImageUnavailable
from ultron.imagination.imagination_core import ImaginationCore
from ultron.imagination.world_builder import LEVELS
from ultron.models.ollama_client import OllamaClient
from ultron.models.router import ModelRouter


class _NoProvider:
    name = "nenhum"

    def available(self):
        return False, "gerador de imagem não instalado"


class ImaginationTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.memory = helpers.make_memory(self.bus, self.state)
        self.images = ImagePipeline(db=self.memory.db, graph=self.memory.graph, providers=[_NoProvider()])
        self.events = []
        self.bus.subscribe(None, lambda e: self.events.append(e.type))

    def tearDown(self):
        self.memory.stop()

    def core(self, router=None):
        return ImaginationCore(router=router, memory=self.memory, bus=self.bus, state=self.state, images=self.images)

    def test_concept_pipeline_without_model_is_procedural_and_labeled(self):
        imagination = self.core()
        concept = imagination.imagine("uma cidade flutuante movida a energia solar", with_image=True)
        self.assertEqual(concept.generator, "procedural")
        self.assertTrue(concept.name)
        self.assertGreaterEqual(len(concept.facets), 3)
        self.assertIn(EventType.CONCEPT_CREATED, self.events)
        self.assertNotIn(EventType.IMAGE_GENERATED, self.events, "sem gerador, nenhuma imagem é fingida")
        stage = self.state.get("imagination_state")
        self.assertEqual(stage["stage"], "DONE")
        self.assertTrue(self.memory.graph.find(concept.name), "o conceito vira nó do Neural Graph")

    def test_concept_from_local_model(self):
        payload = {"name": "Halcyra", "summary": "Arquipélago suspenso.",
                   "facets": {"ARCHITECTURE": "torres de vidro", "CLIMATE": "ventos constantes",
                              "CULTURE": "navegadores do céu"},
                   "relationships": [["CLIMATE", "molda", "ARCHITECTURE"]], "visual_description": "ilhas no céu",
                   "image_prompt": "floating islands"}
        with FakeOllama(["qwen2.5:3b"], responder=lambda p: json.dumps(payload)) as fake:
            settings = helpers.make_settings(ollama_url=fake.url)
            router = ModelRouter(OllamaClient(fake.url), settings_getter=lambda: settings)
            concept = self.core(router).imagine("ilhas flutuantes", with_image=False, with_scenario=False)
        self.assertEqual(concept.name, "Halcyra")
        self.assertTrue(concept.generator.startswith("llm:"))

    def test_scenario_branching_compares_four_options(self):
        result = self.core().scenarios.branch("lançar um app de estudos")
        options = result["options"]
        self.assertEqual([o["id"] for o in options], ["A", "B", "C", "D"])
        for option in options:
            for key in ("cost", "time", "quality", "complexity", "risk", "expected_result"):
                self.assertIn(key, option)
        self.assertIn(result["recommended"], "ABCD")
        self.assertIn(EventType.SCENARIO_BRANCHED, self.events)

    def test_world_builder_descends_the_hierarchy(self):
        worlds = self.core().worlds
        node = worlds.create("um mundo oceânico")
        self.assertEqual(node.level, "WORLD")
        for expected in LEVELS[1:4]:
            node = worlds.expand(node.id)
            self.assertEqual(node.level, expected)
        path = [n.level for n in worlds.path(node.id)]
        self.assertEqual(path, list(LEVELS[:4]))
        self.assertIn(EventType.WORLD_CREATED, self.events)
        self.assertIn(EventType.WORLD_EXPANDED, self.events)

    def test_dream_mode_creates_new_connections(self):
        graph = self.memory.graph
        graph.add_node("CONCEPT", "energia solar")
        graph.add_node("PROJECT", "Atlas")
        graph.add_node("IDEA", "cidade flutuante")
        dream = DreamMode(graph=graph, bus=self.bus, state=self.state)
        before = graph.stats()["nodes"]
        outcome = dream.dream(seed=3)
        self.assertIsNotNone(outcome)
        self.assertTrue(outcome["name"])
        self.assertGreater(graph.stats()["nodes"], before)
        self.assertIn(EventType.DREAM_FINISHED, self.events)
        empty = DreamMode(graph=helpers.make_memory().graph)
        self.assertIsNone(empty.dream(seed=1), "sem conceitos suficientes, não há sonho")

    def test_image_generation_reports_unavailability(self):
        status = self.images.status(refresh=True)
        self.assertFalse(status["available"])
        self.assertIn("gerador de imagem não instalado", status["reason"])
        with self.assertRaises(ImageUnavailable):
            self.images.generate("floating city")


if __name__ == "__main__":
    unittest.main()
