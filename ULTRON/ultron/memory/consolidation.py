"""Consolidação de memória.

Executada periodicamente no worker de memória:

1. itens salientes da memória de trabalho viram episódios;
2. memória de trabalho expirada é descartada;
3. associações não usadas no grafo decaem (as estruturais permanecem);
4. conceitos citados em episódios recentes reforçam suas conexões.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ..graph.concepts import extract

log = logging.getLogger("ultron.consolidation")


@dataclass
class ConsolidationReport:
    episodes_created: int = 0
    working_purged: int = 0
    edges_weakened: int = 0
    edges_pruned: int = 0
    concepts_linked: int = 0
    seconds: float = 0.0
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return dict(self.__dict__)


class Consolidator:
    def __init__(self, working, episodic, graph=None):
        self.working = working
        self.episodic = episodic
        self.graph = graph
        self.last_report: ConsolidationReport | None = None

    def run(self) -> ConsolidationReport:
        started = time.perf_counter()
        report = ConsolidationReport()
        salient = self.working.salient(0.7)
        for item in salient:
            if self.episodic.record(f"observation:{item.kind}", item.content, importance=item.salience,
                                    context={"source": "working_memory"}, started_at=item.timestamp):
                report.episodes_created += 1
                if self.graph is not None:
                    report.concepts_linked += self._link_concepts(item.content)
        self.working.mark_consolidated(salient)
        report.working_purged = self.working.purge()
        if self.graph is not None:
            decay = self.graph.decay()
            report.edges_weakened = decay["weakened"]
            report.edges_pruned = decay["pruned"]
        report.seconds = time.perf_counter() - started
        self.last_report = report
        return report

    def _link_concepts(self, text: str) -> int:
        mentions = extract(text, max_items=6)
        ids = []
        for mention in mentions:
            try:
                ids.append(self.graph.add_node(mention.type, mention.label).id)
            except ValueError:
                continue
        if len(ids) > 1:
            self.graph.activate(ids, reason="consolidation")
        return len(ids)
