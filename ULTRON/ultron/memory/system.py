"""MEMORY — fachada do subsistema de memória (componente do Neural Core)."""
from __future__ import annotations

import logging
from typing import Any

from ..config import paths
from ..core.events import EventType
from ..core.lifecycle import HealthStatus
from ..graph.concepts import extract
from ..graph.neural_graph import NeuralGraph
from .consolidation import Consolidator
from .episodic_memory import EpisodicMemory
from .legacy_import import import_jarvis
from .preference_memory import PreferenceMemory
from .procedural_memory import ProceduralMemory
from .retrieval import Recall, Retriever
from .semantic_memory import SemanticMemory
from .store import Database
from .working_memory import WorkingMemory

log = logging.getLogger("ultron.memory")


class MemorySystem:
    name = "memory"
    critical = True

    def __init__(self, db: Database | None = None, *, bus=None, state=None, import_legacy: bool = True):
        self.db = db or Database(paths.database_path())
        self.bus = bus
        self.state = state
        self.working = WorkingMemory()
        self.episodic = EpisodicMemory(self.db)
        self.semantic = SemanticMemory(self.db)
        self.procedural = ProceduralMemory(self.db)
        self.preferences = PreferenceMemory(self.db)
        self.graph = NeuralGraph(self.db, bus)
        self.retriever = Retriever(self.semantic, self.episodic, self.procedural, self.graph)
        self.consolidator = Consolidator(self.working, self.episodic, self.graph)
        self._import_legacy = import_legacy
        self.legacy_report: dict[str, int] = {}

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        if self._import_legacy:
            try:
                self.legacy_report = import_jarvis(self.db, paths.legacy_jarvis_database())
            except Exception as exc:          # dados legados nunca impedem o boot
                log.warning("importação do JARVIS falhou: %s", exc)
        self.publish_state()

    def stop(self) -> None:
        self.db.close()

    def health(self) -> HealthStatus:
        ok = self.db.integrity_ok()
        return HealthStatus("OK" if ok else "FAIL", "integridade verificada" if ok else "falha de integridade",
                            self.stats())

    # ------------------------------------------------------------ operações
    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self.bus is not None:
            self.bus.publish(event_type, payload, source="memory")

    def remember_fact(self, subject: str, fact: str, *, source: str = "user") -> str:
        stored = self.semantic.remember(subject, fact, source=source)
        node = self.graph.add_node("MEMORY", stored.subject, {"fact": stored.fact[:200]})
        for mention in extract(f"{stored.subject} {stored.fact}", max_items=5):
            try:
                concept = self.graph.add_node(mention.type, mention.label)
                self.graph.connect(node.id, concept.id, "RELATED")
            except ValueError:
                continue
        self._emit(EventType.MEMORY_CREATED, kind="fact", subject=stored.subject, node=node.id)
        self.publish_state()
        return stored.subject

    def forget_fact(self, subject: str) -> bool:
        removed = self.semantic.forget(subject)
        if removed:
            self.graph.remove_node(NeuralGraph.make_id("MEMORY", subject))
            self.publish_state()
        return removed

    def recall(self, query: str, *, limit: int = 6) -> list[Recall]:
        results = self.retriever.search(query, limit=limit)
        if results:
            concept_ids = [r.ref for r in results if r.kind == "concept"]
            if concept_ids:
                self.graph.activate(concept_ids, reason="recall", reinforce=False)
            self._emit(EventType.MEMORY_RECALLED, query=query[:120], count=len(results),
                       kinds=sorted({r.kind for r in results}))
        return results

    def record_episode(self, kind: str, summary: str, **kwargs: Any) -> int | None:
        episode_id = self.episodic.record(kind, summary, **kwargs)
        if episode_id:
            self._emit(EventType.MEMORY_CREATED, kind="episode", id=episode_id, summary=summary[:120])
        return episode_id

    def consolidate(self) -> dict:
        report = self.consolidator.run().to_dict()
        self._emit(EventType.MEMORY_CONSOLIDATED, **report)
        self.publish_state()
        return report

    def stats(self) -> dict[str, Any]:
        graph = self.graph.stats()
        return {"facts": self.semantic.count(), "episodes": self.episodic.count(),
                "procedures": self.procedural.count(), "working": len(self.working),
                "graph_nodes": graph["nodes"], "graph_edges": graph["edges"],
                "db_bytes": self.db.size_bytes()}

    def publish_state(self) -> None:
        if self.state is not None:
            self.state.update(_source="memory", memory_state=self.stats())
