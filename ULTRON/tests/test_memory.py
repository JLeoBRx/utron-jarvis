import sqlite3
import time
import unittest

import helpers

from ultron.core.events import EventType
from ultron.memory.legacy_import import import_jarvis
from ultron.memory.store import Database, looks_secret


class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.path = helpers.temp_dir() / "ultron.sqlite3"
        self.memory = helpers.make_memory(self.bus, self.state, path=self.path)

    def tearDown(self):
        self.memory.stop()

    def test_semantic_memory_and_recall(self):
        self.memory.remember_fact("projeto Atlas", "usa Python e Flask")
        self.memory.remember_fact("cliente", "prefere relatórios em PDF")
        results = self.memory.recall("qual a stack do projeto Atlas?")
        self.assertTrue(results)
        self.assertIn("Flask", results[0].text)

    def test_secrets_are_never_stored(self):
        self.assertTrue(looks_secret("minha senha é hunter2"))
        with self.assertRaises(ValueError):
            self.memory.remember_fact("banco", "senha: 1234")
        self.assertEqual(self.memory.semantic.count(), 0)

    def test_episodes_procedures_preferences_automations(self):
        self.memory.record_episode("goal", "Projeto Atlas preparado", goal_id="g1")
        self.assertEqual(self.memory.episodic.count(), 1)
        steps = [{"skill": "dev.locate_project", "args": {"name": "Atlas"}}]
        self.memory.procedural.learn("prepare meu projeto Atlas", steps, success=True)
        self.assertIsNotNone(self.memory.procedural.match("prepare meu projeto Atlas"))
        self.memory.preferences.set("city", "Recife")
        self.assertEqual(self.memory.preferences.get("city"), "Recife")
        self.memory.procedural.save_automation("modo foco", "modo foco", "app.open", {"name": "spotify"})
        self.assertEqual(self.memory.procedural.automation_for("Modo foco")["skill"], "app.open")

    def test_working_memory_consolidation(self):
        self.memory.working.add("input", "lembre que o servidor fica no IP 10.0.0.5", salience=0.9)
        report = self.memory.consolidate()
        self.assertIsInstance(report, dict)

    def test_neural_graph_persists_and_reinforces(self):
        graph = self.memory.graph
        a = graph.add_node("PROJECT", "Atlas")
        b = graph.add_node("SKILL", "dev.run_project")
        edge = graph.connect(a.id, b.id, "USED_WITH")
        first = edge.weight
        graph.activate([a.id, b.id], reason="teste")
        self.assertGreaterEqual(graph.connect(a.id, b.id, "USED_WITH").weight, first)
        self.memory.stop()
        reopened = helpers.make_memory(path=self.path)
        self.assertIsNotNone(reopened.graph.get(a.id))
        snapshot = reopened.graph.snapshot()
        self.assertEqual(snapshot["total_nodes"], 2)
        self.assertEqual(len(snapshot["edges"]), 1)
        reopened.stop()
        self.memory = helpers.make_memory(path=self.path)

    def test_graph_events_feed_the_hud(self):
        seen = []
        self.bus.subscribe([EventType.GRAPH_NODE_ADDED, EventType.GRAPH_EDGE_ADDED], lambda e: seen.append(e.type))
        a = self.memory.graph.add_node("IDEA", "cidade flutuante")
        b = self.memory.graph.add_node("CONCEPT", "energia solar")
        self.memory.graph.connect(a.id, b.id, "RELATED")
        self.assertEqual(seen.count(EventType.GRAPH_NODE_ADDED), 2)
        self.assertEqual(seen.count(EventType.GRAPH_EDGE_ADDED), 1)

    def test_decay_only_weakens_associations(self):
        graph = self.memory.graph
        a, b = graph.add_node("IDEA", "x"), graph.add_node("IDEA", "y")
        edge = graph.connect(a.id, b.id, "RELATED")
        edge.last_used = time.time() - 10 * 86400
        before = edge.weight
        graph.decay(factor=0.5, idle_seconds=1)
        current = graph.connect(a.id, b.id, "RELATED", delta=0.0)
        self.assertLessEqual(current.weight if current else 0.0, before)


class LegacyImportTest(unittest.TestCase):
    def test_jarvis_import_is_read_only_idempotent_and_filters_secrets(self):
        folder = helpers.temp_dir()
        legacy = folder / "assistant.sqlite3"
        con = sqlite3.connect(legacy)
        con.executescript("""
            CREATE TABLE memories(subject TEXT, fact TEXT);
            CREATE TABLE preferences(name TEXT, value TEXT);
            CREATE TABLE automations(name TEXT, trigger_text TEXT, tool_name TEXT, arguments TEXT, enabled INTEGER);
            INSERT INTO memories VALUES ('servidor', 'IP 192.168.0.10'), ('banco', 'senha: 1234');
            INSERT INTO preferences VALUES ('city', 'Recife');
            INSERT INTO automations VALUES ('foco', 'modo foco', 'app.open', '{"name": "spotify"}', 1);
        """)
        con.commit()
        con.close()
        db = Database(folder / "ultron.sqlite3")
        report = import_jarvis(db, legacy)
        self.assertEqual(report["facts"], 1)
        self.assertEqual(report["skipped"], 1)
        self.assertEqual(report["automations"], 1)
        again = import_jarvis(db, legacy)
        self.assertEqual(again["facts"], 0, "importação acontece uma única vez")
        db.close()


if __name__ == "__main__":
    unittest.main()
