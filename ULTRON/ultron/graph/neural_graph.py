"""Neural Graph — grafo persistente de conceitos, memórias, skills, projetos e mundos.

É a fonte de verdade do crescimento do cérebro visual: cada nó novo vira estrutura na HUD,
cada aresta vira sinapse, e o peso da aresta cresce com o uso conjunto (reforço hebbiano):
quanto mais uma associação é usada, mais forte ela fica. Associações associativas que
deixam de ser usadas decaem; associações estruturais (aprendizado, derivação) permanecem.
"""
from __future__ import annotations

import itertools
import logging
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from ..core.events import EventType
from ..memory.store import Database, dumps, loads, looks_secret

log = logging.getLogger("ultron.graph")

NODE_TYPES = ("MEMORY", "IDEA", "SKILL", "PROJECT", "WORLD", "SCENARIO", "DEVICE", "APPLICATION", "CONCEPT")
EDGE_TYPES = ("RELATED", "DEPENDS", "DERIVED", "LEARNED", "USED_WITH", "CREATED_FROM", "SIMILAR_TO")
STRUCTURAL_EDGES = {"DEPENDS", "DERIVED", "LEARNED", "CREATED_FROM"}


def normalize(label: str) -> str:
    text = unicodedata.normalize("NFD", str(label or "").casefold())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return " ".join(text.replace("_", " ").split())[:120]


@dataclass
class Node:
    id: str
    type: str
    label: str
    data: dict = field(default_factory=dict)
    strength: float = 0.3
    use_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Edge:
    src: str
    dst: str
    type: str
    weight: float = 0.2
    use_count: int = 1
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NeuralGraph:
    def __init__(self, db: Database, bus=None):
        self.db = db
        self._bus = bus
        self._lock = threading.RLock()
        self._nodes: dict[str, Node] = {}
        self._edges: dict[tuple[str, str, str], Edge] = {}
        self._load()

    def attach_bus(self, bus) -> None:
        self._bus = bus

    # ------------------------------------------------------------ persistência
    def _load(self) -> None:
        for row in self.db.query("SELECT * FROM graph_nodes"):
            self._nodes[row["id"]] = Node(row["id"], row["type"], row["label"], loads(row["data"], {}),
                                          row["strength"], row["use_count"], row["created_at"], row["last_used"])
        for row in self.db.query("SELECT * FROM graph_edges"):
            key = (row["src"], row["dst"], row["type"])
            self._edges[key] = Edge(row["src"], row["dst"], row["type"], row["weight"], row["use_count"],
                                    row["created_at"], row["last_used"])

    def _save_node(self, node: Node) -> None:
        self.db.execute(
            "INSERT INTO graph_nodes(id,type,label,data,strength,use_count,created_at,last_used) "
            "VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET label=excluded.label, data=excluded.data, "
            "strength=excluded.strength, use_count=excluded.use_count, last_used=excluded.last_used",
            (node.id, node.type, node.label, dumps(node.data), node.strength, node.use_count,
             node.created_at, node.last_used))

    def _save_edge(self, edge: Edge) -> None:
        self.db.execute(
            "INSERT INTO graph_edges(src,dst,type,weight,use_count,created_at,last_used) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(src,dst,type) DO UPDATE SET weight=excluded.weight, use_count=excluded.use_count, "
            "last_used=excluded.last_used",
            (edge.src, edge.dst, edge.type, edge.weight, edge.use_count, edge.created_at, edge.last_used))

    def _publish(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="graph")

    # ------------------------------------------------------------ nós
    @staticmethod
    def make_id(type_: str, label: str) -> str:
        return f"{type_.lower()}:{normalize(label)}"

    def add_node(self, type_: str, label: str, data: dict | None = None, *, node_id: str | None = None,
                 strength: float | None = None, parent: str | None = None) -> Node:
        type_ = str(type_).upper()
        if type_ not in NODE_TYPES:
            raise ValueError(f"tipo de nó inválido: {type_}")
        label = " ".join(str(label or "").split())[:120]
        if not label:
            raise ValueError("rótulo vazio")
        if looks_secret(label):
            raise ValueError("rótulo parece conter dado sensível")
        nid = node_id or self.make_id(type_, label)
        now = time.time()
        created = False
        with self._lock:
            node = self._nodes.get(nid)
            if node is None:
                node = Node(nid, type_, label, dict(data or {}), strength if strength is not None else 0.3, 1, now, now)
                if parent and parent in self._nodes:
                    node.data.setdefault("parent", parent)
                self._nodes[nid] = node
                created = True
            else:
                node.use_count += 1
                node.last_used = now
                node.strength = min(1.0, node.strength + 0.04 * (1.0 - node.strength))
                if data:
                    node.data.update(data)
            self._save_node(node)
        if created:
            self._publish(EventType.GRAPH_NODE_ADDED, id=nid, type=type_, label=label,
                          parent=node.data.get("parent"), strength=node.strength)
        return node

    def get(self, node_id: str) -> Node | None:
        with self._lock:
            node = self._nodes.get(node_id)
            return Node(**asdict(node)) if node else None

    def find(self, label: str, type_: str | None = None, limit: int = 10) -> list[Node]:
        wanted = normalize(label)
        with self._lock:
            hits = [n for n in self._nodes.values()
                    if (type_ is None or n.type == type_) and wanted and wanted in normalize(n.label)]
        hits.sort(key=lambda n: (-n.strength, -n.use_count))
        return hits[:limit]

    def remove_node(self, node_id: str) -> bool:
        with self._lock:
            if node_id not in self._nodes:
                return False
            del self._nodes[node_id]
            for key in [k for k in self._edges if node_id in (k[0], k[1])]:
                del self._edges[key]
            self.db.execute("DELETE FROM graph_edges WHERE src=? OR dst=?", (node_id, node_id))
            self.db.execute("DELETE FROM graph_nodes WHERE id=?", (node_id,))
        return True

    # ------------------------------------------------------------ arestas
    def connect(self, src: str, dst: str, type_: str = "RELATED", *, delta: float = 0.15) -> Edge | None:
        type_ = str(type_).upper()
        if type_ not in EDGE_TYPES:
            raise ValueError(f"tipo de aresta inválido: {type_}")
        if src == dst:
            return None
        now = time.time()
        with self._lock:
            if src not in self._nodes or dst not in self._nodes:
                raise KeyError("nó inexistente na conexão")
            key = (src, dst, type_)
            edge = self._edges.get(key)
            created = edge is None
            if created:
                edge = Edge(src, dst, type_, min(1.0, 0.2 + delta), 1, now, now)
                self._edges[key] = edge
            else:
                edge.weight = min(1.0, edge.weight + delta * (1.0 - edge.weight))
                edge.use_count += 1
                edge.last_used = now
            self._save_edge(edge)
            weight = edge.weight
        if created:
            self._publish(EventType.GRAPH_EDGE_ADDED, src=src, dst=dst, type=type_, weight=weight)
        return edge

    def activate(self, node_ids: Iterable[str], *, reason: str = "", reinforce: bool = True) -> list[str]:
        """Registra uso. Nós usados juntos fortalecem a associação entre si (USED_WITH)."""
        now = time.time()
        ids = []
        with self._lock:
            for nid in dict.fromkeys(node_ids):
                node = self._nodes.get(nid)
                if node is None:
                    continue
                node.use_count += 1
                node.last_used = now
                node.strength = min(1.0, node.strength + 0.05 * (1.0 - node.strength))
                self._save_node(node)
                ids.append(nid)
        if reinforce and len(ids) > 1:
            for a, b in itertools.islice(itertools.combinations(ids, 2), 12):
                existing = self._edge_between(a, b)
                self.connect(a, b, existing.type if existing else "USED_WITH", delta=0.08)
        if ids:
            self._publish(EventType.GRAPH_ACTIVATED, ids=ids, reason=reason)
        return ids

    def _edge_between(self, a: str, b: str) -> Edge | None:
        with self._lock:
            for (s, d, _t), edge in self._edges.items():
                if (s, d) in ((a, b), (b, a)):
                    return edge
        return None

    def neighbors(self, node_id: str, *, min_weight: float = 0.0, limit: int = 20) -> list[tuple[Node, Edge]]:
        with self._lock:
            out = []
            for (s, d, _t), edge in self._edges.items():
                if edge.weight < min_weight:
                    continue
                other = d if s == node_id else s if d == node_id else None
                if other and other in self._nodes:
                    out.append((self._nodes[other], edge))
        out.sort(key=lambda item: -item[1].weight)
        return out[:limit]

    # ------------------------------------------------------------ manutenção
    def decay(self, *, factor: float = 0.97, idle_seconds: float = 3600.0, floor: float = 0.05) -> dict[str, int]:
        """Enfraquece associações não usadas; remove as associativas muito fracas."""
        now = time.time()
        weakened = pruned = 0
        with self._lock:
            for key, edge in list(self._edges.items()):
                if now - edge.last_used < idle_seconds:
                    continue
                if edge.type in STRUCTURAL_EDGES:
                    continue
                edge.weight *= factor
                weakened += 1
                if edge.weight < floor:
                    del self._edges[key]
                    self.db.execute("DELETE FROM graph_edges WHERE src=? AND dst=? AND type=?", key)
                    pruned += 1
                else:
                    self._save_edge(edge)
        return {"weakened": weakened, "pruned": pruned}

    def snapshot(self, *, max_nodes: int = 800) -> dict[str, Any]:
        with self._lock:
            nodes = sorted(self._nodes.values(), key=lambda n: (-n.strength, -n.use_count, n.created_at))
            nodes = nodes[:max_nodes]
            ids = {n.id for n in nodes}
            edges = [e.to_dict() for e in self._edges.values() if e.src in ids and e.dst in ids]
            return {"nodes": [n.to_dict() for n in nodes], "edges": edges,
                    "total_nodes": len(self._nodes), "total_edges": len(self._edges)}

    def stats(self) -> dict[str, Any]:
        with self._lock:
            by_type: dict[str, int] = {}
            for node in self._nodes.values():
                by_type[node.type] = by_type.get(node.type, 0) + 1
            return {"nodes": len(self._nodes), "edges": len(self._edges), "by_type": by_type}

    def __len__(self) -> int:
        with self._lock:
            return len(self._nodes)
