"""WORLD BUILDER — mundos com camadas e aprofundamento hierárquico.

    WORLD → CONTINENT → COUNTRY → CITY → DISTRICT → BUILDING → ROOM → OBJECT

Cada nível é gerado sob demanda (preguiçosamente) a partir do contexto do pai. Tudo é
persistido e ligado ao Neural Graph (o usuário pode voltar a explorar depois).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.events import EventType
from ..memory.store import dumps, loads
from . import procedural
from .generation import clean_map, clean_text, generate

LEVELS = ("WORLD", "CONTINENT", "COUNTRY", "CITY", "DISTRICT", "BUILDING", "ROOM", "OBJECT")
LEVEL_PT = {"WORLD": "mundo", "CONTINENT": "continente", "COUNTRY": "país", "CITY": "cidade", "DISTRICT": "distrito",
            "BUILDING": "edifício", "ROOM": "sala", "OBJECT": "objeto"}
LAYERS = ("MAP", "TERRAIN", "CLIMATE", "ARCHITECTURE", "POPULATION", "CULTURE", "ECONOMY", "HISTORY", "LANGUAGE",
          "TECHNOLOGY", "BIOLOGY", "EVENTS", "RELATIONSHIPS")


@dataclass
class WorldNode:
    id: str
    level: str
    name: str
    summary: str
    world_id: str
    parent_id: str | None = None
    layers: dict = field(default_factory=dict)
    children: list = field(default_factory=list)           # nomes ainda não explorados
    explored: dict = field(default_factory=dict)            # nome -> id do nó gerado
    generator: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def child_level(self) -> str | None:
        index = LEVELS.index(self.level)
        return LEVELS[index + 1] if index + 1 < len(LEVELS) else None

    def describe(self) -> str:
        layer_text = "; ".join(f"{k.lower()}: {v}" for k, v in list(self.layers.items())[:4])
        nxt = self.child_level
        children = f" {LEVEL_PT.get(nxt, '').capitalize()}s: {', '.join(self.children[:5])}." if nxt and self.children else ""
        return f"{LEVEL_PT[self.level].capitalize()} {self.name}. {self.summary} {layer_text}.{children}"


class WorldBuilder:
    def __init__(self, *, router=None, db=None, graph=None, bus=None, state=None):
        self.router = router
        self.db = db
        self.graph = graph
        self._bus = bus
        self._state = state
        self._cache: dict[str, WorldNode] = {}

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="world_builder")

    def _save(self, node: WorldNode) -> None:
        self._cache[node.id] = node
        if self.db is not None:
            now = time.time()
            self.db.execute("INSERT INTO creations(id,kind,name,parent_id,data,created_at,updated_at) VALUES(?,?,?,?,?,?,?) "
                            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                            (node.id, "world_node", node.name[:120], node.parent_id, dumps(node.to_dict()), node.created_at, now))

    def _link(self, node: WorldNode) -> None:
        if self.graph is None:
            return
        try:
            self.graph.add_node("WORLD", f"{node.name} ({LEVEL_PT[node.level]})",
                                {"world_node": node.id, "level": node.level, "world_id": node.world_id},
                                node_id=f"world:{node.id}")
            if node.parent_id:
                self.graph.connect(f"world:{node.parent_id}", f"world:{node.id}", "DERIVED", delta=0.25)
        except (ValueError, KeyError):
            pass

    def _publish_state(self, node: WorldNode) -> None:
        if self._state is not None:
            self._state.merge("imagination_state", {"world": {"id": node.id, "world_id": node.world_id,
                                                              "level": node.level, "name": node.name,
                                                              "path": [p.name for p in self.path(node.id)],
                                                              "children": node.children[:8]}}, _source="world_builder")

    # ------------------------------------------------------------ criação
    def create(self, idea: str, *, cancel=None) -> WorldNode:
        prompt = (f"Construa um mundo original a partir da ideia: \"{idea}\". JSON com: name, summary, layers (objeto "
                  f"com as chaves {', '.join(LAYERS)}; cada valor uma frase específica), children (lista de 3 a 5 "
                  "nomes de continentes).")
        data = generate(self.router, prompt, fallback=lambda: procedural.world(idea), required=("name", "layers"),
                        cancel=cancel)
        ident = uuid.uuid4().hex[:12]
        node = WorldNode(ident, "WORLD", clean_text(data.get("name"), 80), clean_text(data.get("summary"), 500), ident,
                         None, clean_map(data.get("layers"), LAYERS), [clean_text(c, 60) for c in (data.get("children") or [])][:6],
                         {}, data.get("generator", ""))
        self._save(node)
        self._link(node)
        if self.graph is not None:
            try:
                idea_node = self.graph.add_node("IDEA", idea[:80])
                self.graph.connect(idea_node.id, f"world:{node.id}", "CREATED_FROM", delta=0.3)
            except (ValueError, KeyError):
                pass
        self._publish_state(node)
        self._emit(EventType.WORLD_CREATED, id=node.id, name=node.name, level=node.level, generator=node.generator,
                   children=node.children[:6])
        return node

    def expand(self, node_id: str, child_name: str | None = None, *, cancel=None) -> WorldNode:
        parent = self.get(node_id)
        if parent is None:
            raise KeyError(f"nó de mundo inexistente: {node_id}")
        level = parent.child_level
        if level is None:
            raise ValueError("objetos são o nível mais profundo")
        if child_name and child_name in parent.explored:
            existing = self.get(parent.explored[child_name])
            if existing is not None:
                self._publish_state(existing)
                return existing
        target = child_name or (parent.children[0] if parent.children else None)
        lineage = " > ".join(f"{LEVEL_PT[p.level]} {p.name}" for p in self.path(parent.id))
        next_level = LEVELS[LEVELS.index(level) + 1] if LEVELS.index(level) + 1 < len(LEVELS) else None
        child_hint = (f", children (lista de 2 a 5 nomes de {LEVEL_PT[next_level]}s)" if next_level else "")
        prompt = (f"Contexto: {lineage}. Resumo do {LEVEL_PT[parent.level]}: {parent.summary}. Crie o "
                  f"{LEVEL_PT[level]} chamado \"{target or 'à sua escolha'}\" coerente com esse contexto. JSON com: name, "
                  f"summary, layers (objeto com 3 a 6 destas chaves: {', '.join(LAYERS)}){child_hint}.")
        data = generate(self.router, prompt, fallback=lambda: procedural.child(parent.name, level, target),
                        required=("name", "summary"), cancel=cancel)
        node = WorldNode(uuid.uuid4().hex[:12], level, clean_text(data.get("name") or target, 80),
                         clean_text(data.get("summary"), 500), parent.world_id, parent.id,
                         clean_map(data.get("layers"), LAYERS),
                         [clean_text(c, 60) for c in (data.get("children") or [])][:6] if next_level else [],
                         {}, data.get("generator", ""))
        parent.explored[target or node.name] = node.id
        if node.name not in parent.children and target is None:
            parent.children.append(node.name)
        self._save(parent)
        self._save(node)
        self._link(node)
        self._publish_state(node)
        self._emit(EventType.WORLD_EXPANDED, id=node.id, name=node.name, level=node.level, parent=parent.id,
                   world_id=node.world_id, generator=node.generator)
        return node

    # ------------------------------------------------------------ leitura
    def get(self, node_id: str) -> WorldNode | None:
        if node_id in self._cache:
            return self._cache[node_id]
        if self.db is None:
            return None
        row = self.db.one("SELECT data FROM creations WHERE id=? AND kind='world_node'", (node_id,))
        if not row:
            return None
        node = WorldNode(**loads(row["data"], {}))
        self._cache[node.id] = node
        return node

    def path(self, node_id: str) -> list[WorldNode]:
        chain, current, guard = [], self.get(node_id), 0
        while current is not None and guard < len(LEVELS) + 1:
            chain.append(current)
            current = self.get(current.parent_id) if current.parent_id else None
            guard += 1
        return list(reversed(chain))

    def children(self, node_id: str) -> list[WorldNode]:
        if self.db is None:
            return [n for n in self._cache.values() if n.parent_id == node_id]
        rows = self.db.query("SELECT data FROM creations WHERE parent_id=? AND kind='world_node' ORDER BY created_at",
                             (node_id,))
        return [WorldNode(**loads(r["data"], {})) for r in rows]

    def worlds(self, limit: int = 20) -> list[dict]:
        if self.db is None:
            return [n.to_dict() for n in self._cache.values() if n.level == "WORLD"][:limit]
        rows = self.db.query("SELECT id,name,created_at FROM creations WHERE kind='world_node' AND parent_id IS NULL "
                             "ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def find_child(self, node: WorldNode, text: str) -> str | None:
        """Encontra, no texto do usuário, o nome de um filho (explorado ou não)."""
        low = text.casefold()
        for name in list(node.children) + list(node.explored):
            if name and name.casefold() in low:
                return name
        return None
