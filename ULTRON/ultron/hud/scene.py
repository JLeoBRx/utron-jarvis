"""NEURAL SCENE — o estado visual do ULTRON NEURAL HUB (sem Qt, testável).

A cena só muda por dados reais: eventos do Event Bus, o ULTRON_STATE e a telemetria.
Nada aqui é decorativo ou aleatório sem causa:

* nós e sinapses = nós e arestas do Neural Graph (mesma posição sempre);
* ativação de nós, partículas e pulsos = eventos de grafo, percepção, voz e execução;
* câmera e profundidade cognitiva (0–9) = estado de runtime e complexidade da tarefa;
* inicialização em 12 fases = eventos COMPONENT_STARTED/FAILED reais;
* módulos neurais nascem de uma região do cérebro só quando há algo real a mostrar
  (plano em execução, autorização pendente, insight, rede, imaginação, simulação...).
"""
from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from .brain_model import REGIONS, BrainGeometry, development_for

CAMERA_STATES = ("OVERVIEW", "FOCUS", "THINKING", "MEMORY_DIVE", "IDEA_FOCUS", "IMAGINATION", "SIMULATION",
                 "WORLD_EXPLORATION", "NETWORK_FOCUS")

# estado de runtime → (câmera, região de foco)
RUNTIME_CAMERA = {
    "BOOTING": ("OVERVIEW", "core"), "IDLE": ("OVERVIEW", "core"), "LISTENING": ("FOCUS", "auditory"),
    "THINKING": ("THINKING", "core"), "PLANNING": ("THINKING", "frontal"), "EXECUTING": ("FOCUS", "motor"),
    "VERIFYING": ("FOCUS", "motor"), "RECOVERY": ("THINKING", "frontal"), "SPEAKING": ("FOCUS", "broca"),
    "IMAGINING": ("IMAGINATION", "prefrontal"), "SIMULATING": ("SIMULATION", "prefrontal"),
    "DREAMING": ("OVERVIEW", "core"), "NETWORK": ("NETWORK_FOCUS", "parietal"),
    "AWAITING_AUTHORIZATION": ("FOCUS", "prefrontal"), "ERROR": ("OVERVIEW", "core"),
    "SHUTDOWN": ("OVERVIEW", "core"),
}
# câmera → (zoom, deslocamento horizontal da tela para abrir espaço aos módulos)
CAMERA_PRESETS = {
    "OVERVIEW": (1.0, 0.0), "FOCUS": (1.22, 0.0), "THINKING": (1.12, 0.0), "MEMORY_DIVE": (1.85, 0.0),
    "IDEA_FOCUS": (1.5, 0.0), "IMAGINATION": (0.86, -0.16), "SIMULATION": (0.84, -0.18),
    "WORLD_EXPLORATION": (0.80, -0.20), "NETWORK_FOCUS": (0.92, -0.14),
}
RUNTIME_DEPTH = {"IDLE": 0, "LISTENING": 1, "SPEAKING": 1, "THINKING": 2, "PLANNING": 3, "NETWORK": 3,
                 "EXECUTING": 4, "AWAITING_AUTHORIZATION": 4, "VERIFYING": 5, "RECOVERY": 6, "IMAGINING": 6,
                 "SIMULATING": 7, "DREAMING": 8, "ERROR": 2, "BOOTING": 0, "SHUTDOWN": 0}
WORLD_DEPTH = {"WORLD": 6, "CONTINENT": 6, "COUNTRY": 7, "CITY": 7, "DISTRICT": 8, "BUILDING": 8, "ROOM": 9,
               "OBJECT": 9}

# (nome da fase, componente cujo início a conclui)
BOOT_PHASES = (
    ("VOID", None), ("SPARK", "privacy"), ("CORE IGNITION", "memory"), ("MEMORY LATTICE", "world_model"),
    ("LANGUAGE CORTEX", "models"), ("GOAL MATRIX", "goals"), ("NETWORK MESH", "network"),
    ("MOTOR CORTEX", "agent"), ("IMAGINATION FIELD", "imagination"), ("VOICE", "voice"),
    ("SENSORY ARRAY", "perception"), ("ONLINE", None),
)
BOOT_MIN_PHASE = 0.22                      # segundos mínimos por fase (para a sequência ser legível)

# evento → região do cérebro que reage (estímulo real)
EVENT_REGION = {
    "WINDOW_CHANGED": "occipital", "APPLICATION_CHANGED": "occipital", "SCREEN_CHANGED": "occipital",
    "VISION_UPDATED": "occipital", "OCR_UPDATED": "occipital", "PROCESS_ENDED": "parietal",
    "FILESYSTEM_CHANGED": "temporal", "NETWORK_CHANGED": "parietal", "DEVICE_DETECTED": "parietal",
    "MEMORY_RECALLED": "hippocampus", "MEMORY_CREATED": "hippocampus", "MEMORY_CONSOLIDATED": "hippocampus",
    "ACTION_STARTED": "motor", "ACTION_FINISHED": "motor", "SKILL_ACTIVATED": "cerebellum",
    "VERIFICATION_STARTED": "motor", "VERIFICATION_SUCCESS": "motor", "VERIFICATION_FAILED": "motor",
    "RECOVERY_STARTED": "frontal", "PLAN_CREATED": "frontal", "PLAN_UPDATED": "frontal", "GOAL_CREATED": "frontal",
    "WAKE_WORD": "auditory", "VOICE_RECEIVED": "auditory", "VOICE_STARTED": "broca", "USER_INPUT": "auditory",
    "CONCEPT_CREATED": "prefrontal", "IMAGINATION_STARTED": "prefrontal", "SCENARIO_BRANCHED": "prefrontal",
    "WORLD_CREATED": "occipital", "WORLD_EXPANDED": "occipital", "INSIGHT": "frontal", "MODEL_SELECTED": "core",
}
LEFT_REGIONS = {"prefrontal", "frontal", "broca", "motor"}
MODULE_SHIFT = 0.13
NODE_TYPE_COLOR = {"MEMORY": "amber", "IDEA": "white", "CONCEPT": "white", "SKILL": "gold", "PROJECT": "gold",
                   "WORLD": "white", "SCENARIO": "white", "DEVICE": "amber", "APPLICATION": "gold"}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


# ---------------------------------------------------------------- elementos
@dataclass
class SceneNode:
    id: str
    type: str
    label: str
    x: float
    y: float
    strength: float = 0.3
    activation: float = 0.0
    born: float = 0.0


@dataclass
class SceneEdge:
    a: str
    b: str
    type: str
    weight: float
    cx: float
    cy: float
    activation: float = 0.0


@dataclass
class Particle:
    points: tuple                          # (x0, y0, cx, cy, x1, y1) curva quadrática no espaço do cérebro
    t: float = 0.0
    speed: float = 0.8
    size: float = 1.0
    tone: str = "gold"

    def position(self) -> tuple[float, float]:
        x0, y0, cx, cy, x1, y1 = self.points
        u = 1 - self.t
        return (u * u * x0 + 2 * u * self.t * cx + self.t * self.t * x1,
                u * u * y0 + 2 * u * self.t * cy + self.t * self.t * y1)


@dataclass
class Pulse:
    x: float
    y: float
    born: float
    duration: float = 1.2
    radius: float = 0.18
    tone: str = "gold"
    strength: float = 1.0


@dataclass
class Module:
    key: str
    title: str
    region: str
    lines: list = field(default_factory=list)
    born: float = 0.0
    expires: float | None = None           # None: vive enquanto a condição real durar
    alpha: float = 0.0
    data: dict = field(default_factory=dict)
    priority: int = 50


@dataclass
class Camera:
    state: str = "OVERVIEW"
    region: str = "core"
    x: float = 0.0
    y: float = 0.0
    zoom: float = 1.0
    shift: float = 0.0
    tx: float = 0.0
    ty: float = 0.0
    tzoom: float = 1.0
    tshift: float = 0.0
    tau: float = 0.65                       # constante de tempo da suavização

    def aim(self, state: str, region: str = "core", *, depth: float = 0.0) -> None:
        zoom, shift = CAMERA_PRESETS.get(state, (1.0, 0.0))
        rx, ry, _r = REGIONS.get(region, REGIONS["core"])
        focus = 0.0 if state in ("OVERVIEW", "IMAGINATION", "SIMULATION", "WORLD_EXPLORATION") else 0.55
        if state in ("MEMORY_DIVE", "IDEA_FOCUS"):
            focus = 0.9
        self.state, self.region = state, region
        self.tx, self.ty = rx * focus, ry * focus
        self.tzoom = zoom * (1.0 + 0.025 * depth)
        self.tshift = shift

    def step(self, dt: float) -> None:
        k = 1.0 - math.exp(-dt / self.tau)
        for name in ("x", "y", "zoom", "shift"):
            current, target = getattr(self, name), getattr(self, "t" + name)
            value = current + (target - current) * k
            setattr(self, name, target if abs(target - value) < 0.0008 else value)


class BootSequence:
    def __init__(self, clock: Callable[[], float]):
        self._clock = clock
        self.active = False
        self.done = False
        self.reached = -1                   # última fase concluída por evento real
        self.shown = -1.0                   # progresso visual (anda até ``reached`` com ritmo mínimo)
        self.failed: dict[int, str] = {}
        self.started_at = 0.0
        self.finished_at = 0.0
        self._index = {name: i for i, (_label, name) in enumerate(BOOT_PHASES) if name}

    def start(self) -> None:
        self.active, self.done = True, False
        self.reached, self.shown = 0, 0.0
        self.started_at = self._clock()

    def component(self, name: str, ok: bool, error: str = "") -> None:
        index = self._index.get(name)
        if name in ("voice_output", "neural_audio"):
            return                          # a fase VOICE fecha com o pipeline de voz
        if index is None:
            return
        if not ok:
            self.failed[index] = error or "falha"
        self.reached = max(self.reached, index)

    def ready(self) -> None:
        self.reached = len(BOOT_PHASES) - 1
        if not self.active:                 # SYSTEM_READY sem SYSTEM_BOOT visto (HUD aberta depois)
            self.start()
            self.reached = len(BOOT_PHASES) - 1

    def step(self, dt: float) -> None:
        if not self.active or self.done:
            return
        target = float(self.reached)
        self.shown = min(target, self.shown + dt / BOOT_MIN_PHASE)
        if self.reached >= len(BOOT_PHASES) - 1 and self.shown >= target:
            if not self.finished_at:
                self.finished_at = self._clock()
            if self._clock() - self.finished_at > 1.3:    # tempo do "despertar" final
                self.done, self.active = True, False

    @property
    def phase(self) -> int:
        return max(0, int(self.shown))

    @property
    def label(self) -> str:
        return BOOT_PHASES[self.phase][0]

    @property
    def progress(self) -> float:
        return _clamp((self.shown + 1) / len(BOOT_PHASES))

    def phase_failed(self, index: int) -> str:
        return self.failed.get(index, "")


# ---------------------------------------------------------------- cena
class NeuralScene:
    MAX_PARTICLES = 260
    MAX_PULSES = 40
    MAX_MODULES = 3

    def __init__(self, geometry: BrainGeometry | None = None, *, clock: Callable[[], float] = time.monotonic):
        self.geometry = geometry or BrainGeometry()
        self.clock = clock
        self.nodes: dict[str, SceneNode] = {}
        self.edges: dict[tuple[str, str], SceneEdge] = {}
        self._adjacency: dict[str, set[str]] = {}
        self.particles: list[Particle] = []
        self.pulses: list[Pulse] = []
        self.region_activity: dict[str, float] = {name: 0.0 for name in REGIONS}
        self.camera = Camera()
        self.boot = BootSequence(clock)
        self.modules: dict[str, Module] = {}
        self.transcript: deque = deque(maxlen=6)
        self.runtime_state = "BOOTING"
        self.cognitive_phase = ""
        self.depth = 0.0
        self.depth_level = 0
        self.suspense = 0.0
        self.release = 0.0                  # clarão de resolução (resposta pronta)
        self.breath = 0.0
        self.dim = 0.0                      # escurecimento global (sonho, suspense)
        self.total_nodes = 0
        self.total_edges = 0
        self.development = 0.0
        self.telemetry: dict[str, Any] = {}
        self.state: dict[str, Any] = {}
        self.overlay_label = ""             # rótulo de destaque: EXPLORING CONNECTIONS / NEW CONCEPT FOUND
        self.overlay_until = 0.0
        self._waiting_since = 0.0
        self._camera_override: tuple[str, str, float] | None = None
        self._time = 0.0
        self.graph_version = 0              # muda quando a geometria de nós/arestas muda (cache da view)

    # ================================================================ grafo
    def load_graph(self, snapshot: dict) -> None:
        nodes = snapshot.get("nodes") or []
        now = self.clock()
        for raw in nodes:
            self._add_node(raw.get("id", ""), raw.get("type", "CONCEPT"), raw.get("label", ""),
                           float(raw.get("strength", 0.3)), born=now - 10.0)
        for raw in snapshot.get("edges") or []:
            self._add_edge(raw.get("src", ""), raw.get("dst", ""), raw.get("type", "RELATED"),
                           float(raw.get("weight", 0.2)))
        self.total_nodes = int(snapshot.get("total_nodes", len(self.nodes)))
        self.total_edges = int(snapshot.get("total_edges", len(self.edges)))
        self.development = development_for(self.total_nodes, self.total_edges)
        self.graph_version += 1

    def _add_node(self, node_id: str, type_: str, label: str, strength: float = 0.3, *, born: float | None = None):
        if not node_id:
            return None
        node = self.nodes.get(node_id)
        if node is None:
            x, y = self.geometry.place(node_id, type_)
            node = SceneNode(node_id, type_, label, x, y, strength, 0.0, self.clock() if born is None else born)
            self.nodes[node_id] = node
            self.graph_version += 1
        else:
            node.strength = max(node.strength, strength)
        return node

    def _add_edge(self, a: str, b: str, type_: str, weight: float) -> SceneEdge | None:
        if a not in self.nodes or b not in self.nodes or a == b:
            return None
        key = (a, b) if a < b else (b, a)
        edge = self.edges.get(key)
        if edge is None:
            na, nb = self.nodes[key[0]], self.nodes[key[1]]
            mx, my = (na.x + nb.x) / 2, (na.y + nb.y) / 2
            dx, dy = nb.x - na.x, nb.y - na.y
            bend = 0.18 * (1 if (hash(key) & 1) else -1)
            edge = SceneEdge(key[0], key[1], type_, weight, mx - dy * bend, my + dx * bend)
            self.edges[key] = edge
            self._adjacency.setdefault(a, set()).add(b)
            self._adjacency.setdefault(b, set()).add(a)
            self.graph_version += 1
        else:
            edge.weight = max(edge.weight, weight)
        return edge

    # ================================================================ estímulos
    def stimulate(self, region: str, amount: float = 0.6, *, pulse: bool = True, tone: str = "gold") -> None:
        if region not in REGIONS:
            return
        self.region_activity[region] = _clamp(self.region_activity[region] + amount)
        if pulse and len(self.pulses) < self.MAX_PULSES:
            x, y, r = REGIONS[region]
            self.pulses.append(Pulse(x, y, self.clock(), 1.1 + 0.6 * amount, r * (0.8 + amount), tone, amount))

    def activate_nodes(self, ids: list[str], *, spread: bool = True, tone: str = "gold") -> None:
        for node_id in ids:
            node = self.nodes.get(node_id)
            if node is None:
                continue
            node.activation = 1.0
            if not spread:
                continue
            for other in list(self._adjacency.get(node_id, ()))[:6]:
                self._emit_particle(node_id, other, tone=tone)

    def _emit_particle(self, a: str, b: str, *, tone: str = "gold") -> None:
        if len(self.particles) >= self.MAX_PARTICLES:
            return
        key = (a, b) if a < b else (b, a)
        edge = self.edges.get(key)
        na, nb = self.nodes.get(a), self.nodes.get(b)
        if edge is None or na is None or nb is None:
            return
        edge.activation = 1.0
        self.particles.append(Particle((na.x, na.y, edge.cx, edge.cy, nb.x, nb.y), 0.0,
                                       0.55 + 0.5 * edge.weight, 1.0 + edge.weight, tone))

    def region_particles(self, src: str, dst: str, count: int = 3, tone: str = "gold") -> None:
        """Sinal entre regiões (ex.: percepção → córtex), em arco pelo interior do cérebro."""
        if src not in REGIONS or dst not in REGIONS:
            return
        x0, y0, _ = REGIONS[src]
        x1, y1, _ = REGIONS[dst]
        for i in range(count):
            if len(self.particles) >= self.MAX_PARTICLES:
                return
            off = (i - (count - 1) / 2) * 0.05
            cx, cy = (x0 + x1) / 2 - (y1 - y0) * (0.2 + off), (y0 + y1) / 2 + (x1 - x0) * (0.2 + off)
            self.particles.append(Particle((x0, y0, cx, cy, x1, y1), -0.15 * i, 0.9, 1.2, tone))

    # ================================================================ eventos
    def on_event(self, kind: str, payload: dict | None = None) -> None:
        p = payload or {}
        now = self.clock()
        region = EVENT_REGION.get(kind)
        if kind == "SYSTEM_BOOT":
            self.boot.start()
        elif kind in ("COMPONENT_STARTED", "COMPONENT_FAILED"):
            self.boot.component(str(p.get("component", "")), kind == "COMPONENT_STARTED", str(p.get("error", "")))
        elif kind == "SYSTEM_READY":
            self.boot.ready()
        elif kind == "GRAPH_NODE_ADDED":
            node = self._add_node(str(p.get("id", "")), str(p.get("type", "CONCEPT")), str(p.get("label", "")),
                                  float(p.get("strength", 0.3)))
            if node is not None:
                node.activation = 1.0
                self.total_nodes += 1
                self.pulses.append(Pulse(node.x, node.y, now, 1.4, 0.07, "white", 0.8))
                parent = p.get("parent")
                if parent:
                    self._add_edge(str(parent), node.id, "DERIVED", 0.3)
                    self._emit_particle(str(parent), node.id, tone="white")
            self._update_development()
        elif kind == "GRAPH_EDGE_ADDED":
            edge = self._add_edge(str(p.get("src", "")), str(p.get("dst", "")), str(p.get("type", "RELATED")),
                                  float(p.get("weight", 0.2)))
            if edge is not None:
                self.total_edges += 1
                self._emit_particle(edge.a, edge.b)
            self._update_development()
        elif kind == "GRAPH_ACTIVATED":
            self.activate_nodes([str(i) for i in (p.get("ids") or [])][:24])
        elif kind == "MEMORY_RECALLED" and int(p.get("count", 0) or 0) > 0:
            self._override_camera("MEMORY_DIVE", "hippocampus", 2.6)
            self._module("memory", "MEMORY RECALL", "hippocampus",
                         [f"{p.get('count')} lembrança(s)", str(p.get("query", ""))[:60]], ttl=5.0, priority=30)
        elif kind == "CONCEPT_CREATED":
            self._override_camera("IDEA_FOCUS", "prefrontal", 3.2)
            node = p.get("node")
            if node:
                self.activate_nodes([str(node)])
        elif kind in ("WORLD_CREATED", "WORLD_EXPANDED"):
            self._override_camera("WORLD_EXPLORATION", "occipital", 6.0)
        elif kind == "DREAM_STARTED":
            self.overlay_label, self.overlay_until = "EXPLORING CONNECTIONS", now + 30.0
            self.activate_nodes([str(i) for i in (p.get("sources") or [])], tone="white")
        elif kind == "DREAM_FINISHED":
            self.overlay_label, self.overlay_until = "NEW CONCEPT FOUND", now + 5.0
            self._module("dream", "NEW CONCEPT FOUND", "prefrontal",
                         [str(p.get("name", ""))[:48], str(p.get("description", ""))[:120]], ttl=9.0, priority=40)
        elif kind == "INSIGHT":
            lines = [str(p.get("text", ""))[:160]]
            if p.get("suggestion"):
                lines.append("Responda: sim / não")
            target = {"network_problem": "parietal", "device_new": "parietal", "network_restored": "parietal",
                      "application_hung": "occipital", "visible_error": "occipital"}.get(str(p.get("kind")), "frontal")
            self._module("insight", "INSIGHT", target, lines, ttl=14.0, priority=20)
        elif kind == "VISION_UPDATED" and not p.get("discarded"):
            summary = str(p.get("summary") or "")[:110]
            if summary:
                self._module("vision", "VISUAL CORTEX", "occipital",
                             [f"{p.get('app') or ''} · {p.get('activity') or ''}".strip(" ·"), summary],
                             ttl=6.0, priority=60)
        elif kind == "RESPONSE_READY":
            text = str(p.get("text", ""))
            if text:
                self.transcript.append({"role": "ultron", "text": text, "at": now, "kind": p.get("kind", "")})
            if not p.get("partial"):
                self.release = 1.0
                self._waiting_since = 0.0
        elif kind == "USER_INPUT":
            self.transcript.append({"role": "user", "text": str(p.get("text", "")), "at": now, "kind": "input"})
            self._waiting_since = now
        elif kind == "WAKE_WORD":
            self.stimulate("auditory", 0.9, tone="white")
            self.region_particles("auditory", "prefrontal", 3, "white")
        elif kind == "VERIFICATION_SUCCESS":
            self.stimulate("motor", 0.7, tone="white")
        elif kind in ("VERIFICATION_FAILED", "ERROR_DETECTED", "RECOVERY_STARTED"):
            self.stimulate(region or "frontal", 0.8, tone="amber")
        elif kind == "HEALTH_UPDATED":
            problems = p.get("problems") or {}
            if p.get("changed") and problems:
                self._module("health", "SYSTEM HEALTH", "core",
                             [f"{k}: {v}"[:80] for k, v in list(problems.items())[:4]], ttl=10.0, priority=70)
        if region and kind not in ("VERIFICATION_FAILED", "ERROR_DETECTED", "RECOVERY_STARTED", "WAKE_WORD",
                                   "VERIFICATION_SUCCESS"):
            self.stimulate(region, 0.35 if kind in ("WINDOW_CHANGED", "APPLICATION_CHANGED", "SCREEN_CHANGED")
                           else 0.55)
            if kind in ("VISION_UPDATED", "OCR_UPDATED"):
                self.region_particles("occipital", "frontal", 2)
            elif kind == "ACTION_STARTED":
                self.region_particles("frontal", "motor", 2)
            elif kind == "VOICE_RECEIVED":
                self.region_particles("auditory", "frontal", 2, "white")

    def _update_development(self) -> None:
        self.development = development_for(self.total_nodes, self.total_edges)

    def _override_camera(self, state: str, region: str, seconds: float) -> None:
        self._camera_override = (state, region, self.clock() + seconds)

    def _module(self, key: str, title: str, region: str, lines: list, *, ttl: float | None,
                priority: int = 50, data: dict | None = None) -> None:
        now = self.clock()
        module = self.modules.get(key)
        if module is None:
            module = Module(key, title, region, born=now, priority=priority)
            self.modules[key] = module
        module.title, module.region, module.lines, module.priority = title, region, list(lines), priority
        module.expires = None if ttl is None else now + ttl
        module.data = dict(data or {})

    def _drop_module(self, key: str) -> None:
        module = self.modules.get(key)
        if module is not None and module.expires is None:
            module.expires = self.clock() + 1.5          # sai devagar (fade), não some de repente

    # ================================================================ estado
    def on_state(self, state: dict) -> None:
        self.state = state
        runtime = str(state.get("runtime_state", "IDLE"))
        if runtime != self.runtime_state:
            self.runtime_state = runtime
            if runtime in ("THINKING", "PLANNING") and not self._waiting_since:
                self._waiting_since = self.clock()
        self.cognitive_phase = str(state.get("cognitive_phase", ""))
        self._plan_module(state)
        self._authorization_module(state)
        self._imagination_modules(state)
        self._network_module(state)

    def _plan_module(self, state: dict) -> None:
        plan = state.get("current_plan") or {}
        steps = plan.get("steps") or []
        busy = self.runtime_state in ("PLANNING", "EXECUTING", "VERIFYING", "RECOVERY", "AWAITING_AUTHORIZATION")
        if steps and (busy or self.runtime_state == "THINKING"):
            glyph = {"done": "●", "running": "▸", "unconfirmed": "◐", "failed": "✕", "skipped": "◌",
                     "cancelled": "✕", "pending": "○"}
            lines = []
            for step in steps[:9]:
                status = str(step.get("status", "pending")).lower()
                lines.append((glyph.get(status, "○"), str(step.get("description", ""))[:46], status))
            if len(steps) > 9:
                lines.append(("…", f"+{len(steps) - 9} etapas", "pending"))
            self._module("plan", f"PLAN · {len(steps)} {'ETAPA' if len(steps) == 1 else 'ETAPAS'}", "frontal",
                         lines, ttl=None, priority=10,
                         data={"strategy": plan.get("strategy", "")})
        elif "plan" in self.modules:
            self._drop_module("plan")

    def _authorization_module(self, state: dict) -> None:
        pending = state.get("pending_authorization")
        if pending and pending.get("status") == "pending":
            risk = {"none": "nenhum", "low": "baixo", "medium": "médio", "high": "alto",
                    "critical": "crítico"}.get(str(pending.get("risk", "")).lower(), str(pending.get("risk", "?")))
            self._module("authorization", "AUTORIZAÇÃO", "prefrontal",
                         [str(pending.get("description", ""))[:120], f"risco {risk}"],
                         ttl=None, priority=0, data={"expires": pending.get("expires", 0),
                                                     "created": pending.get("created", 0)})
        elif "authorization" in self.modules:
            self._drop_module("authorization")

    def _imagination_modules(self, state: dict) -> None:
        imagination = state.get("imagination_state") or {}
        recent = time.time() - float(imagination.get("at", 0) or 0) < 20
        stage = imagination.get("stage")
        if stage and (self.runtime_state == "IMAGINING" or recent):
            chain = ("IDEA", "CONCEPT", "RELATIONSHIPS", "SCENARIO", "WORLD MODEL", "VISUALIZATION", "IMAGE")
            concept = imagination.get("concept") or {}
            lines = [("chain", list(chain), "IMAGE" if stage == "DONE" else stage)]
            if isinstance(concept, dict) and concept.get("name"):
                origin = " (procedural)" if concept.get("generator") == "procedural" else ""
                lines.append(f"{str(concept['name'])[:48]}{origin}")
                facets = concept.get("facets") or ()
                if isinstance(facets, dict):
                    facets = list(facets)
                if facets:
                    lines.append(" · ".join(str(f) for f in list(facets)[:6]))
                if concept.get("image"):
                    lines.append(("image", str(concept["image"])))
            if imagination.get("image_status"):
                lines.append(str(imagination["image_status"])[:110])
            self._module("imagination", "IMAGINATION CORE", "prefrontal", lines, ttl=None, priority=15)
        elif "imagination" in self.modules:
            self._drop_module("imagination")
        world = imagination.get("world")
        if world and (self.runtime_state == "IMAGINING" or recent):
            path = " › ".join(world.get("path") or [world.get("name", "")])
            lines = [str(world.get("level", "")), path[-90:]]
            lines.extend(f"· {c}" for c in (world.get("children") or [])[:5])
            self._module("world", "WORLD BUILDER", "occipital", lines, ttl=None, priority=16,
                         data={"level": world.get("level")})
        elif "world" in self.modules:
            self._drop_module("world")
        simulation = state.get("simulation_state") or {}
        if simulation.get("stage") == "COMPARED" and self.runtime_state in ("SIMULATING", "IMAGINING", "THINKING",
                                                                             "SPEAKING", "IDLE"):
            options = simulation.get("options") or []
            lines = [("option", o, o.get("id") == simulation.get("recommended")) for o in options[:4]]
            self._module("simulation", "SCENARIO BRANCHING", "prefrontal", lines,
                         ttl=None if self.runtime_state == "SIMULATING" else 25.0, priority=12)
        elif simulation.get("stage") == "BRANCHING":
            self._module("simulation", "SCENARIO BRANCHING", "prefrontal", ["gerando ramificações A–D…"], ttl=None,
                         priority=12)

    def _network_module(self, state: dict) -> None:
        net = state.get("network_state") or {}
        if self.runtime_state == "NETWORK" and net:
            lines = [f"{net.get('interface', '')} {net.get('ipv4', '')}".strip(),
                     f"gateway {net.get('gateway') or '—'}",
                     f"{net.get('devices_online', 0)} online · {net.get('devices_known', 0)} conhecidos"]
            self._module("network", "NETWORK MESH", "parietal", lines, ttl=12.0, priority=25)

    def on_telemetry(self, telemetry: dict) -> None:
        self.telemetry = telemetry
        if telemetry.get("listening"):
            self.region_activity["auditory"] = max(self.region_activity["auditory"],
                                                   _clamp(0.25 + float(telemetry.get("mic_level", 0.0))))
        if telemetry.get("speaking"):
            self.region_activity["broca"] = max(self.region_activity["broca"],
                                                _clamp(0.2 + 2.2 * float(telemetry.get("out_level", 0.0))))

    # ================================================================ animação
    def _target_depth(self) -> float:
        depth = RUNTIME_DEPTH.get(self.runtime_state, 0)
        plan = (self.state.get("current_plan") or {}).get("steps") or []
        if self.runtime_state in ("PLANNING", "EXECUTING", "VERIFYING", "RECOVERY"):
            depth += (1 if len(plan) > 4 else 0) + (1 if len(plan) > 8 else 0)
        world = (self.state.get("imagination_state") or {}).get("world") or {}
        if self.camera.state == "WORLD_EXPLORATION" and world.get("level") in WORLD_DEPTH:
            depth = max(depth, WORLD_DEPTH[world["level"]])
        if self.suspense > 0.5:
            depth += 1
        return float(min(9, depth))

    def _choose_camera(self) -> tuple[str, str]:
        now = self.clock()
        if self._camera_override and now < self._camera_override[2]:
            return self._camera_override[0], self._camera_override[1]
        self._camera_override = None
        if self.boot.active:
            return "OVERVIEW", "core"
        if "world" in self.modules and self.modules["world"].expires is None:
            return "WORLD_EXPLORATION", "occipital"
        if self.runtime_state == "IMAGINING" and "simulation" in self.modules:
            return "SIMULATION", "prefrontal"
        return RUNTIME_CAMERA.get(self.runtime_state, ("OVERVIEW", "core"))

    def step(self, dt: float) -> None:
        dt = max(0.0, min(0.1, dt))
        self._time += dt
        now = self.clock()
        self.boot.step(dt)
        # profundidade cognitiva
        target = self._target_depth()
        self.depth += (target - self.depth) * (1 - math.exp(-dt / 0.9))
        if abs(target - self.depth) < 0.01:
            self.depth = target
        self.depth_level = int(round(self.depth))
        # câmera
        state, region = self._choose_camera()
        self.camera.aim(state, region, depth=self.depth)
        if CAMERA_PRESETS.get(state, (1.0, 0.0))[1] == 0.0:
            shift, zoom = self._module_shift()
            self.camera.tshift = shift
            self.camera.tzoom *= zoom
        self.camera.step(dt)
        # suspense: esperando resposta há mais de 1,5 s, ou autorização pendente
        waiting = self._waiting_since and now - self._waiting_since > 1.5 and \
            self.runtime_state in ("THINKING", "PLANNING")          # nada visível acontecendo ainda
        target_suspense = 1.0 if self.runtime_state == "AWAITING_AUTHORIZATION" else 0.7 if waiting else 0.0
        self.suspense += (target_suspense - self.suspense) * (1 - math.exp(-dt / 0.8))
        if abs(target_suspense - self.suspense) < 0.005:
            self.suspense = target_suspense
        self.release = max(0.0, self.release - dt / 0.9)
        dim_target = 0.45 if self.runtime_state == "DREAMING" else 0.25 * self.suspense
        self.dim += (dim_target - self.dim) * (1 - math.exp(-dt / 1.2))
        if abs(dim_target - self.dim) < 0.005:
            self.dim = dim_target
        # respiração (repouso): lenta, só como sinal de "vivo e em repouso"
        rate = 0.12 if self.runtime_state in ("IDLE", "DREAMING") else 0.35
        self.breath = (self.breath + dt * rate) % 1.0
        # decaimentos
        node_decay = math.exp(-dt / 1.6)
        for node in self.nodes.values():
            if node.activation > 0.001:
                node.activation *= node_decay
        edge_decay = math.exp(-dt / 1.2)
        for edge in self.edges.values():
            if edge.activation > 0.001:
                edge.activation *= edge_decay
        region_decay = math.exp(-dt / 1.4)
        for name in self.region_activity:
            self.region_activity[name] *= region_decay
        # partículas: ao chegar, ativam o nó de destino
        alive = []
        for particle in self.particles:
            particle.t += dt * particle.speed
            if particle.t < 1.0:
                alive.append(particle)
        self.particles = alive
        self.pulses = [p for p in self.pulses if now - p.born < p.duration]
        # módulos: entrada/saída suaves e limite de visíveis
        for key in list(self.modules):
            module = self.modules[key]
            expired = module.expires is not None and now > module.expires
            target_alpha = 0.0 if expired else 1.0
            module.alpha += (target_alpha - module.alpha) * (1 - math.exp(-dt / 0.35))
            if expired and module.alpha < 0.02:
                del self.modules[key]
        if self.overlay_label and now > self.overlay_until:
            self.overlay_label = ""

    # ================================================================ leitura para a view
    def visible_modules(self) -> list[Module]:
        if self.boot.active:
            return []                                    # a sequência de inicialização não é interrompida
        ordered = sorted(self.modules.values(), key=lambda m: (m.priority, m.born))
        return ordered[: self.MAX_MODULES]

    def module_side(self, module: Module) -> str:
        """Painéis de regiões frontais ficam à esquerda — a menos que a câmera já tenha aberto
        espaço à direita (imaginação, simulação, mundo, rede)."""
        preset_shift = CAMERA_PRESETS.get(self.camera.state, (1.0, 0.0))[1]
        if preset_shift < 0:
            return "right"
        return "left" if module.region in LEFT_REGIONS else "right"

    def _module_shift(self) -> tuple[float, float]:
        """(deslocamento, fator de zoom) para que os painéis não cubram o cérebro."""
        sides = {self.module_side(m) for m in self.visible_modules() if m.alpha > 0.05 or m.expires is None}
        if sides == {"left"}:
            return MODULE_SHIFT, 0.96
        if sides == {"right"}:
            return -MODULE_SHIFT, 0.96
        if sides == {"left", "right"}:
            return 0.0, 0.84
        return 0.0, 1.0

    def headline(self) -> str:
        if self.boot.active:
            return self.boot.label
        if self.runtime_state == "AWAITING_AUTHORIZATION":
            return "AUTHORIZATION REQUIRED"
        if self.overlay_label:
            return self.overlay_label
        return self.cognitive_phase or ""
