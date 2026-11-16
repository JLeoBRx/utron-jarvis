"""DREAM MODE — estado criativo: combina conceitos existentes em ideias novas.

Ativado sob pedido ou após um período ocioso (configurável). Escolhe conceitos distantes
no Neural Graph, combina-os e registra um nó IDEA com arestas CREATED_FROM para as origens.
A interface mostra apenas "EXPLORING CONNECTIONS" e "NEW CONCEPT FOUND" — nunca o
raciocínio.
"""
from __future__ import annotations

import random
import time
from typing import Any, Callable

from ..core.events import EventType
from . import procedural
from .generation import clean_text, generate

ELIGIBLE = ("CONCEPT", "PROJECT", "SKILL", "APPLICATION", "DEVICE", "WORLD", "SCENARIO", "IDEA", "MEMORY")


class DreamMode:
    def __init__(self, *, graph=None, router=None, bus=None, state=None, settings_getter: Callable[[], Any] | None = None):
        self.graph = graph
        self.router = router
        self._bus = bus
        self._state = state
        self._settings = settings_getter
        self.last_dream = 0.0
        self.dreams = 0

    def due(self, idle_seconds: float) -> bool:
        s = self._settings() if self._settings else None
        if s is not None and not getattr(s, "dream_mode", True):
            return False
        threshold = 60.0 * float(getattr(s, "dream_idle_minutes", 15.0) if s else 15.0)
        return idle_seconds >= threshold and time.time() - self.last_dream >= threshold

    def _pick(self, rng: random.Random) -> list:
        snapshot = self.graph.snapshot(max_nodes=400)
        # nós de faceta (ex.: "concept:<id>:clima") ficam de fora: o sonho combina conceitos inteiros
        nodes = [n for n in snapshot["nodes"] if n["type"] in ELIGIBLE and n["id"].count(":") <= 1]
        if len(nodes) < 2:
            return []
        by_type: dict[str, list] = {}
        for node in nodes:
            by_type.setdefault(node["type"], []).append(node)
        types = list(by_type)
        rng.shuffle(types)
        picked = []
        for type_ in types:                      # conceitos de tipos diferentes = conexões mais distantes
            weights = [0.2 + n["strength"] for n in by_type[type_]]
            picked.append(rng.choices(by_type[type_], weights=weights, k=1)[0])
            if len(picked) == 3:
                break
        if len(picked) < 2:
            picked = rng.sample(nodes, 2)
        return picked

    def dream(self, *, cancel=None, seed: int | None = None) -> dict[str, Any] | None:
        if self.graph is None:
            return None
        rng = random.Random(seed if seed is not None else time.time_ns())
        sources = self._pick(rng)
        if not sources:
            return None
        labels = [s["label"] for s in sources]
        if self._state is not None:
            self._state.set_runtime_state("DREAMING", "modo sonho", source="dream")
            self._state.set_cognitive_phase("EXPLORING CONNECTIONS", source="dream")
        if self._bus is not None:
            self._bus.publish(EventType.DREAM_STARTED, {"sources": [s["id"] for s in sources]}, source="dream")
        prompt = ("Combine os seguintes elementos em UM conceito novo e surpreendente, útil ou belo: "
                  + "; ".join(labels) + ". JSON com: name (curto), description (uma ou duas frases).")
        data = generate(self.router, prompt, fallback=lambda: procedural.blend(labels, "|".join(labels)),
                        required=("name", "description"), cancel=cancel, temperature=1.0, num_predict=200)
        name = clean_text(data.get("name"), 60)
        description = clean_text(data.get("description"), 300)
        node_id = None
        try:
            node = self.graph.add_node("IDEA", name, {"description": description, "dream": True,
                                                      "generator": data.get("generator", "")})
            node_id = node.id
            for source in sources:
                self.graph.connect(node.id, source["id"], "CREATED_FROM", delta=0.25)
        except (ValueError, KeyError):
            pass
        self.last_dream = time.time()
        self.dreams += 1
        if self._state is not None:
            self._state.set_cognitive_phase("NEW CONCEPT FOUND", source="dream")
            self._state.merge("imagination_state", {"dream": {"name": name, "sources": labels, "at": time.time()}},
                              _source="dream")
        outcome = {"name": name, "description": description, "sources": labels, "node": node_id,
                   "generator": data.get("generator", "")}
        if self._bus is not None:
            self._bus.publish(EventType.DREAM_FINISHED, outcome, source="dream")
        return outcome
