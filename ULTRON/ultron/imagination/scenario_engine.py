"""SCENARIO ENGINE — cenários hipotéticos e ramificação de ideias.

Cenário: name, premise, rules, environment, entities, relationships, history, physics,
technology, visual_description.

Ramificação: IDEIA → opções A, B, C, D comparadas por custo, tempo, qualidade,
complexidade, risco e resultado esperado (notas de 1 a 5).
"""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from ..core.events import EventType
from ..memory.store import dumps, loads
from . import procedural
from .generation import clean_text, generate

CRITERIA = ("cost", "time", "quality", "complexity", "risk")


@dataclass
class Scenario:
    id: str
    name: str
    premise: str
    rules: list = field(default_factory=list)
    environment: str = ""
    entities: list = field(default_factory=list)
    relationships: list = field(default_factory=list)
    history: str = ""
    physics: str = ""
    technology: str = ""
    visual_description: str = ""
    generator: str = ""
    parent_id: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def describe(self) -> str:
        parts = [f"{self.name}. {self.premise}"]
        if self.environment:
            parts.append(f"Ambiente: {self.environment}.")
        if self.rules:
            parts.append("Regras: " + "; ".join(self.rules[:3]) + ".")
        if self.technology:
            parts.append(f"Tecnologia: {self.technology}.")
        return " ".join(parts)


def score(option: dict) -> float:
    """Maior é melhor: qualidade conta a favor; custo, tempo, complexidade e risco contra."""
    return round(option.get("quality", 3) * 1.6 - option.get("cost", 3) * 0.6 - option.get("time", 3) * 0.5
                 - option.get("complexity", 3) * 0.5 - option.get("risk", 3) * 0.8, 2)


class ScenarioEngine:
    def __init__(self, *, router=None, db=None, graph=None, bus=None, state=None):
        self.router = router
        self.db = db
        self.graph = graph
        self._bus = bus
        self._state = state

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="scenario")

    def _store(self, kind: str, ident: str, name: str, data: dict, parent: str | None = None) -> None:
        if self.db is not None:
            now = time.time()
            self.db.execute("INSERT INTO creations(id,kind,name,parent_id,data,created_at,updated_at) VALUES(?,?,?,?,?,?,?) "
                            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                            (ident, kind, name[:120], parent, dumps(data), now, now))

    def create(self, idea: str, *, cancel=None, parent_id: str | None = None) -> Scenario:
        prompt = (f"Crie um cenário hipotético a partir de: \"{idea}\". JSON com as chaves: name, premise, "
                  "rules (lista), environment, entities (lista), relationships (lista de [a, relação, b]), history, "
                  "physics, technology, visual_description.")
        data = generate(self.router, prompt, fallback=lambda: procedural.scenario(idea),
                        required=("name", "premise"), cancel=cancel)
        scenario = Scenario(
            uuid.uuid4().hex[:12], clean_text(data.get("name"), 120), clean_text(data.get("premise"), 600),
            [clean_text(r, 200) for r in (data.get("rules") or [])][:8], clean_text(data.get("environment"), 400),
            [clean_text(e, 120) for e in (data.get("entities") or [])][:10],
            [r for r in (data.get("relationships") or []) if isinstance(r, list) and len(r) == 3][:10],
            clean_text(data.get("history"), 600), clean_text(data.get("physics"), 300),
            clean_text(data.get("technology"), 400), clean_text(data.get("visual_description"), 500),
            data.get("generator", ""), parent_id)
        self._store("scenario", scenario.id, scenario.name, scenario.to_dict(), parent_id)
        if self.graph is not None:
            try:
                node = self.graph.add_node("SCENARIO", scenario.name, {"id": scenario.id, "generator": scenario.generator},
                                           node_id=f"scenario:{scenario.id}")
                idea_node = self.graph.add_node("IDEA", idea[:80])
                self.graph.connect(idea_node.id, node.id, "DERIVED", delta=0.3)
            except (ValueError, KeyError):
                pass
        self._emit(EventType.SCENARIO_CREATED, id=scenario.id, name=scenario.name, generator=scenario.generator)
        return scenario

    def branch(self, idea: str, *, cancel=None) -> dict[str, Any]:
        if self._state is not None:
            self._state.update(_source="scenario", simulation_state={"stage": "BRANCHING", "idea": idea[:200]})
        prompt = (f"Gere 4 alternativas distintas (A, B, C, D) para: \"{idea}\". JSON: {{\"options\": [{{\"id\": \"A\", "
                  "\"title\": \"...\", \"description\": \"...\", \"cost\": 1-5, \"time\": 1-5, \"quality\": 1-5, "
                  "\"complexity\": 1-5, \"risk\": 1-5, \"expected_result\": \"...\"}}]}}. Notas inteiras de 1 a 5.")
        data = generate(self.router, prompt, fallback=lambda: procedural.branches(idea), required=("options",),
                        cancel=cancel, temperature=0.7)
        options = []
        for index, raw in enumerate((data.get("options") or [])[:4]):
            if not isinstance(raw, dict):
                continue
            option = {"id": "ABCD"[index], "title": clean_text(raw.get("title"), 120),
                      "description": clean_text(raw.get("description"), 400),
                      "expected_result": clean_text(raw.get("expected_result"), 300)}
            for criterion in CRITERIA:
                try:
                    option[criterion] = max(1, min(5, int(raw.get(criterion, 3))))
                except (TypeError, ValueError):
                    option[criterion] = 3
            option["score"] = score(option)
            options.append(option)
        if not options:
            raise RuntimeError("não foi possível gerar alternativas")
        best = max(options, key=lambda o: o["score"])
        result = {"id": uuid.uuid4().hex[:12], "idea": idea[:300], "options": options, "recommended": best["id"],
                  "generator": data.get("generator", ""), "criteria": list(CRITERIA)}
        self._store("branching", result["id"], idea[:120], result)
        if self.graph is not None:
            try:
                root = self.graph.add_node("IDEA", idea[:80])
                for option in options:
                    node = self.graph.add_node("IDEA", f"{option['id']}: {option['title']}"[:100],
                                               {"branch_of": result["id"], "score": option["score"]})
                    self.graph.connect(root.id, node.id, "DERIVED", delta=0.2)
            except (ValueError, KeyError):
                pass
        if self._state is not None:
            self._state.update(_source="scenario", simulation_state={"stage": "COMPARED", "idea": idea[:200],
                                                                     "options": options, "recommended": best["id"]})
        self._emit(EventType.SCENARIO_BRANCHED, id=result["id"], idea=idea[:200], options=len(options),
                   recommended=best["id"], generator=result["generator"])
        return result

    def get(self, scenario_id: str) -> dict | None:
        if self.db is None:
            return None
        row = self.db.one("SELECT data FROM creations WHERE id=?", (scenario_id,))
        return loads(row["data"], None) if row else None

    def list(self, kind: str = "scenario", limit: int = 20) -> list[dict]:
        if self.db is None:
            return []
        rows = self.db.query("SELECT id,name,created_at FROM creations WHERE kind=? ORDER BY created_at DESC LIMIT ?",
                             (kind, limit))
        return [dict(r) for r in rows]
