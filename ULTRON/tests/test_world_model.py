import unittest

import helpers

from ultron.core.events import EventType
from ultron.world.world_model import SECTIONS, WorldModel


class WorldModelTest(unittest.TestCase):
    def setUp(self):
        self.path = helpers.temp_dir() / "world_model.json"
        self.bus, self.state = helpers.make_bus_state()
        self.world = WorldModel(self.path, bus=self.bus, state=self.state, save_delay=0)

    def test_required_sections(self):
        for section in ("computer", "applications", "windows", "processes", "files", "projects", "network",
                        "peripherals", "user_context", "current_goals"):
            self.assertIn(section, SECTIONS)

    def test_update_records_source_confidence_and_publishes(self):
        seen = []
        self.bus.subscribe(EventType.WORLD_MODEL_UPDATED, lambda e: seen.append(e.get("section")))
        changed = self.world.update("computer", {"os": "Windows 11", "ram_total_gb": 16}, source="system",
                                    confidence=0.97)
        self.assertTrue(changed)
        section = self.world.section("computer")
        self.assertEqual(section["source"], "system")
        self.assertAlmostEqual(section["confidence"], 0.97)
        self.assertEqual(seen, ["computer"])
        self.assertFalse(self.world.update("computer", {"os": "Windows 11", "ram_total_gb": 16}, source="system"),
                         "dados iguais não geram revisão")
        self.assertEqual(self.state.get("world_model")["os"], "Windows 11")

    def test_merge_and_upsert_items(self):
        self.world.update("user_context", {"application": "VS Code"}, source="windows")
        self.world.update("user_context", {"window": "main.py"}, source="windows", merge=True)
        self.assertEqual(self.world.get("user_context"), {"application": "VS Code", "window": "main.py"})
        self.world.upsert_item("projects", "atlas", {"name": "Atlas", "path": "C:/Projects/Atlas"}, source="fs")
        self.world.upsert_item("projects", "atlas", {"language": "python"}, source="fs")
        atlas = self.world.get("projects")["atlas"]
        self.assertEqual(atlas["language"], "python")
        self.assertEqual(atlas["name"], "Atlas")
        self.assertIn("first_seen", atlas)

    def test_persistence_survives_restart(self):
        self.world.update("network", {"gateway": "192.168.0.1", "devices": {"a": {}}}, source="network")
        self.world.flush()
        again = WorldModel(self.path, save_delay=0)
        again.load()
        self.assertEqual(again.get("network")["gateway"], "192.168.0.1")
        self.assertIn("192.168.0.1", again.describe())

    def test_unknown_section_rejected(self):
        with self.assertRaises(KeyError):
            self.world.update("inventado", {}, source="teste")


if __name__ == "__main__":
    unittest.main()
