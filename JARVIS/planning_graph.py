"""J.A.R.V.I.S. // DYNAMIC PLANNING GRAPH
Representa uma missão como estados, ações e transições alternativas.
O grafo orienta planejamento; não executa ferramentas e não concede permissões.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from threading import RLock
import uuid

_LOCK = RLock()
_CURRENT = None

@dataclass
class GraphNode:
    id: str
    kind: str
    label: str
    status: str = "PENDING"
    evidence: str = ""

@dataclass
class GraphEdge:
    source: str
    target: str
    action: str
    cost: float = 1.0
    risk: str = "low"
    enabled: bool = True

class PlanningGraph:
    def __init__(self, goal: str):
        self.id = uuid.uuid4().hex[:8]
        self.goal = str(goal)
        self.nodes: list[GraphNode] = []
        self.edges: list[GraphEdge] = []
        self.revision = 0
        self._build()

    def _node(self, kind, label):
        n = GraphNode(uuid.uuid4().hex[:6], kind, label)
        self.nodes.append(n); return n

    def _edge(self, source, target, action, cost=1.0, risk="low"):
        self.edges.append(GraphEdge(source, target, action, cost, risk))

    def _build(self):
        start = self._node("state", "objetivo recebido")
        inspect = self._node("state", "evidências disponíveis")
        action = self._node("state", "ação executada")
        verified = self._node("state", "resultado verificado")
        recovery = self._node("state", "recuperação necessária")
        done = self._node("state", "objetivo alcançado")
        self._edge(start.id, inspect.id, "observar e coletar evidências", 1.0, "low")
        self._edge(inspect.id, action.id, "selecionar ferramenta e executar", 2.0, "medium")
        self._edge(action.id, verified.id, "observar novamente e verificar", 1.0, "low")
        self._edge(verified.id, done.id, "confirmar estado esperado", 1.0, "low")
        self._edge(action.id, recovery.id, "entrar em recovery", 2.0, "medium")
        self._edge(verified.id, recovery.id, "replanejar por estado não confirmado", 1.5, "low")
        self._edge(recovery.id, inspect.id, "coletar novas evidências", 1.0, "low")

    def available_transitions(self, node_id=None):
        if node_id is None:
            node_id = self.nodes[0].id if self.nodes else ""
        return [asdict(e) for e in self.edges if e.source == node_id and e.enabled]

    def mark(self, label_or_id, status, evidence=""):
        for n in self.nodes:
            if n.id == label_or_id or n.label == label_or_id:
                n.status = str(status); n.evidence = str(evidence)[:500]
                return asdict(n)
        return None

    def replan(self, reason=""):
        self.revision += 1
        # Desabilita apenas transições de alto custo já marcadas como problemáticas;
        # o restante permanece disponível como rota alternativa.
        if reason:
            for e in self.edges:
                if e.action == "selecionar ferramenta e executar" and self.revision > 1:
                    e.cost += 0.5
        return self.snapshot()

    def next_actions(self):
        pending = [n for n in self.nodes if n.status == "PENDING"]
        if not pending: return []
        current = next((n for n in self.nodes if n.status == "RUNNING"), self.nodes[0] if self.nodes else None)
        return self.available_transitions(current.id if current else None)

    def snapshot(self):
        return {"id": self.id, "goal": self.goal, "revision": self.revision,
                "nodes": [asdict(n) for n in self.nodes],
                "edges": [asdict(e) for e in self.edges]}


def create(goal: str):
    global _CURRENT
    with _LOCK:
        _CURRENT = PlanningGraph(goal)
        return _CURRENT.snapshot()

def current():
    with _LOCK:
        return _CURRENT.snapshot() if _CURRENT else None

def mark(label_or_id, status, evidence=""):
    with _LOCK:
        return _CURRENT.mark(label_or_id, status, evidence) if _CURRENT else None

def replan(reason=""):
    with _LOCK:
        return _CURRENT.replan(reason) if _CURRENT else None

def next_actions():
    with _LOCK:
        return _CURRENT.next_actions() if _CURRENT else []
