"""IMAGINATION CORE — constrói conceitos, não apenas imagens.

    IDEIA → CONCEITO → RELAÇÕES → CENÁRIO → WORLD MODEL → VISUALIZAÇÃO → IMAGEM

Exemplo: "Imagine uma cidade que nunca existiu" → conceito com ARQUITETURA, CLIMA,
ILUMINAÇÃO, TRANSPORTE, CULTURA, HISTÓRIA, TECNOLOGIA, POPULAÇÃO, GEOGRAFIA; relações
entre essas facetas; um cenário; e, se houver modelo de imagem local, a imagem.

Cada estágio atualiza ``imagination_state`` — a HUD mostra o conceito se formando.
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..core.events import EventType
from ..memory.store import dumps
from . import procedural
from .dream_mode import DreamMode
from .generation import clean_map, clean_text, generate
from .image_pipeline import ImagePipeline, ImageUnavailable
from .scenario_engine import ScenarioEngine
from .world_builder import LEVEL_PT, WorldBuilder

log = logging.getLogger("ultron.imagination")

FACETS = ("ARCHITECTURE", "CLIMATE", "LIGHTING", "TRANSPORT", "CULTURE", "HISTORY", "TECHNOLOGY", "POPULATION",
          "GEOGRAPHY")
FACET_PT = {"ARCHITECTURE": "arquitetura", "CLIMATE": "clima", "LIGHTING": "iluminação", "TRANSPORT": "transporte",
            "CULTURE": "cultura", "HISTORY": "história", "TECHNOLOGY": "tecnologia", "POPULATION": "população",
            "GEOGRAPHY": "geografia"}
STAGES = ("IDEA", "CONCEPT", "RELATIONSHIPS", "SCENARIO", "WORLD MODEL", "VISUALIZATION", "IMAGE")


@dataclass
class Concept:
    id: str
    idea: str
    name: str
    summary: str
    facets: dict = field(default_factory=dict)
    relationships: list = field(default_factory=list)
    visual_description: str = ""
    image_prompt: str = ""
    generator: str = ""
    scenario_id: str | None = None
    image_path: str | None = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def describe(self) -> str:
        details = "; ".join(f"{FACET_PT.get(k, k.lower())}: {v}" for k, v in list(self.facets.items())[:5])
        return f"{self.name}. {self.summary} {details}."


class ImaginationCore:
    name = "imagination"

    def __init__(self, *, router=None, memory=None, bus=None, state=None, privacy=None,
                 settings_getter: Callable[[], Any] | None = None, images: ImagePipeline | None = None):
        self.router = router
        self.memory = memory
        self._bus = bus
        self._state = state
        db = memory.db if memory is not None else None
        graph = memory.graph if memory is not None else None
        self.graph = graph
        self.db = db
        self.images = images or ImagePipeline(db=db, graph=graph, bus=bus, privacy=privacy, settings_getter=settings_getter)
        self.scenarios = ScenarioEngine(router=router, db=db, graph=graph, bus=bus, state=state)
        self.worlds = WorldBuilder(router=router, db=db, graph=graph, bus=bus, state=state)
        self.dream = DreamMode(graph=graph, router=router, bus=bus, state=state, settings_getter=settings_getter)
        self.last_concept: Concept | None = None
        self.current_world_node: str | None = None

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def health(self) -> dict:
        status = self.images.status()
        return {"status": "OK", "detail": "imagem: " + (status["provider"] or "indisponível")}

    def _stage(self, stage: str, **extra: Any) -> None:
        if self._state is not None:
            self._state.merge("imagination_state", {"stage": stage, "at": time.time(), **extra}, _source="imagination")

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="imagination")

    # ------------------------------------------------------------ pipeline principal
    def imagine(self, idea: str, *, cancel=None, with_image: bool = True, with_scenario: bool = True) -> Concept:
        idea = clean_text(idea, 400)
        self._emit(EventType.IMAGINATION_STARTED, idea=idea)
        self._stage("IDEA", idea=idea, concept=None)
        self._stage("CONCEPT")
        prompt = (f"Ideia: \"{idea}\". Crie um conceito original. JSON com: name, summary, facets (objeto com as chaves "
                  f"{', '.join(FACETS)}; cada valor uma descrição específica e concreta), relationships (lista de "
                  "[faceta, relação, faceta]), visual_description (uma frase visual rica), image_prompt (prompt em "
                  "inglês para um modelo de imagem, estilo concept art).")
        data = generate(self.router, prompt, fallback=lambda: procedural.concept(idea), required=("name", "facets"),
                        cancel=cancel)
        concept = Concept(uuid.uuid4().hex[:12], idea, clean_text(data.get("name"), 80), clean_text(data.get("summary"), 500),
                          clean_map(data.get("facets"), FACETS), [r for r in (data.get("relationships") or [])
                                                                  if isinstance(r, list) and len(r) == 3][:12],
                          clean_text(data.get("visual_description"), 500), clean_text(data.get("image_prompt"), 600),
                          data.get("generator", ""))
        self._stage("RELATIONSHIPS", concept={"id": concept.id, "name": concept.name,
                                              "facets": list(concept.facets.keys()), "generator": concept.generator})
        concept_node = self._graph_concept(concept)
        self._emit(EventType.CONCEPT_CREATED, id=concept.id, name=concept.name, facets=list(concept.facets),
                   generator=concept.generator, node=concept_node)
        if with_scenario and not (cancel is not None and getattr(cancel, "cancelled", False)):
            self._stage("SCENARIO")
            scenario = self.scenarios.create(f"{concept.name}: {concept.summary}", cancel=cancel)
            concept.scenario_id = scenario.id
            if self.graph is not None and concept_node:
                try:
                    self.graph.connect(concept_node, f"scenario:{scenario.id}", "DERIVED", delta=0.25)
                except KeyError:
                    pass
        self._stage("WORLD MODEL")
        self._store(concept)
        self._stage("VISUALIZATION", visual=concept.visual_description)
        if with_image:
            self.render(concept, cancel=cancel)
        self.last_concept = concept
        self._stage("DONE", concept={"id": concept.id, "name": concept.name, "generator": concept.generator,
                                     "image": concept.image_path})
        return concept

    def render(self, concept: Concept, *, cancel=None) -> str | None:
        self._stage("IMAGE")
        prompt = concept.image_prompt or concept.visual_description or concept.name
        try:
            record = self.images.generate(prompt, concept_id=f"concept:{concept.id}", label=concept.name, cancel=cancel)
        except ImageUnavailable as exc:
            self._stage("IMAGE", image_status=str(exc))
            return None
        except Exception as exc:
            log.warning("falha ao gerar imagem: %s", exc)
            self._stage("IMAGE", image_status=f"falha ao gerar imagem: {exc}")
            return None
        concept.image_path = record.path
        self._store(concept)
        self._emit(EventType.IMAGE_GENERATED, concept=concept.id, path=record.path, provider=record.provider)
        return record.path

    def _graph_concept(self, concept: Concept) -> str | None:
        if self.graph is None:
            return None
        try:
            idea = self.graph.add_node("IDEA", concept.idea[:80])
            node = self.graph.add_node("CONCEPT", concept.name, {"concept": concept.id, "generator": concept.generator},
                                       node_id=f"concept:{concept.id}")
            self.graph.connect(idea.id, node.id, "CREATED_FROM", delta=0.3)
            facet_ids = {}
            for facet, text in concept.facets.items():
                child = self.graph.add_node("CONCEPT", f"{concept.name} · {FACET_PT.get(facet, facet.lower())}",
                                            {"facet": facet, "text": text[:200]},
                                            node_id=f"concept:{concept.id}:{facet.lower()}")
                self.graph.connect(node.id, child.id, "DERIVED", delta=0.2)
                facet_ids[facet] = child.id
            for a, _relation, b in concept.relationships:
                if str(a).upper() in facet_ids and str(b).upper() in facet_ids:
                    self.graph.connect(facet_ids[str(a).upper()], facet_ids[str(b).upper()], "RELATED", delta=0.15)
            return node.id
        except (ValueError, KeyError):
            return None

    def _store(self, concept: Concept) -> None:
        if self.db is not None:
            now = time.time()
            self.db.execute("INSERT INTO creations(id,kind,name,parent_id,data,created_at,updated_at) VALUES(?,?,?,?,?,?,?) "
                            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                            (concept.id, "concept", concept.name, None, dumps(concept.to_dict()), concept.created_at, now))

    # ------------------------------------------------------------ interface com o orquestrador
    def handle(self, intent, cancel=None) -> dict[str, Any]:
        """Executa uma intenção criativa e devolve {'text', 'data'} para a resposta."""
        kind = intent.kind
        text = intent.text
        if kind == "imagination":
            concept = self.imagine(text, cancel=cancel)
            image_note = self._image_note(concept)
            origin = " (gerador procedural: o modelo de linguagem não estava disponível)" if concept.generator == "procedural" else ""
            return {"text": f"Conceito construído: {concept.describe()}{image_note}{origin}", "data": concept.to_dict()}
        if kind == "world":
            node = self.worlds.create(text, cancel=cancel)
            self.current_world_node = node.id
            origin = " (gerador procedural)" if node.generator == "procedural" else ""
            return {"text": f"Mundo criado. {node.describe()}{origin} Diga 'explore' e o nome de um lugar para aprofundar.",
                    "data": node.to_dict()}
        if kind == "explore":
            if not self.current_world_node:
                worlds = self.worlds.worlds(1)
                if not worlds:
                    return {"text": "Não há mundo criado para explorar. Peça para eu criar um mundo.", "data": {}}
                self.current_world_node = worlds[0]["id"]
            current = self.worlds.get(self.current_world_node)
            target = self.worlds.find_child(current, text) if current else None
            if current is not None and target is None and re.search(r"\b(volt\w*|subi\w*|acima)\b", text, re.I) and current.parent_id:
                parent = self.worlds.get(current.parent_id)
                self.current_world_node = parent.id
                self.worlds._publish_state(parent)
                return {"text": f"De volta a {LEVEL_PT[parent.level]} {parent.name}. {parent.describe()}", "data": parent.to_dict()}
            node = self.worlds.expand(self.current_world_node, target, cancel=cancel)
            self.current_world_node = node.id
            return {"text": f"{node.describe()}", "data": node.to_dict()}
        if kind == "scenario":
            result = self.scenarios.branch(text, cancel=cancel)
            best = next(o for o in result["options"] if o["id"] == result["recommended"])
            lines = "; ".join(f"{o['id']}: {o['title']} (qualidade {o['quality']}, risco {o['risk']})" for o in result["options"])
            origin = " Alternativas genéricas: o modelo de linguagem não estava disponível." if result["generator"] == "procedural" else ""
            return {"text": f"Ramificações: {lines}. Recomendação: {best['id']} — {best['title']}.{origin}", "data": result}
        if kind == "image":
            subject = (intent.entities or {}).get("subject") or text
            concept = self.last_concept if self.last_concept and subject.lower() in self.last_concept.idea.lower() else None
            if concept is None:
                concept = self.imagine(subject, cancel=cancel, with_image=False, with_scenario=False)
            path = self.render(concept, cancel=cancel)
            if path:
                return {"text": f"Imagem gerada para {concept.name}: {path}", "data": {"path": path, **concept.to_dict()}}
            return {"text": f"Conceito {concept.name} construído, mas {self.images.status()['reason'].lower()}",
                    "data": concept.to_dict()}
        if kind == "dream":
            outcome = self.dream.dream(cancel=cancel)
            if not outcome:
                return {"text": "Não há conceitos suficientes no grafo para sonhar.", "data": {}}
            return {"text": f"Nova conexão: {outcome['name']}. {outcome['description']}", "data": outcome}
        return {"text": "Pedido criativo não reconhecido.", "data": {}}

    def _image_note(self, concept: Concept) -> str:
        if concept.image_path:
            return f" Imagem: {concept.image_path}."
        status = self.images.status()
        return "" if status["available"] else " " + status["reason"] + "."
