"""NEURAL SCENE — o estado visual do JARVIS NEURAL HUB (sem Qt, testável).

A cena só muda por dados reais: eventos do Event Bus, o JARVIS_STATE e a telemetria.
Nada aqui é decorativo ou aleatório sem causa:

* malha neural 3D: densidade proporcional ao tamanho real do Neural Graph; os nós e as
  arestas do grafo aparecem como nós e sinapses fortes, sempre na mesma posição;
* ativação de nós, partículas e pulsos = eventos de grafo, percepção, voz e execução;
* câmera (giro, foco e zoom) e profundidade cognitiva (0–9) = estado de runtime e
  complexidade da tarefa; ao ouvir, falar ou agir, o cérebro vira a região certa para frente;
* anel de subsistemas: status vem do ciclo de vida e da saúde reais; a sinapse até cada
  subsistema só cresce enquanto ele é usado de fato;
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

from . import quality
from .brain_model import REGIONS, STRETCH, BrainMesh, development_for

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
    "SHUTDOWN": ("OVERVIEW", "core"), "PERCEIVING": ("FOCUS", "occipital"), "CONTEXT": ("THINKING", "hippocampus"),
    "DECIDING": ("THINKING", "prefrontal"), "REMINDING": ("FOCUS", "hippocampus"),
}
# câmera → (zoom, deslocamento horizontal da tela para abrir espaço aos módulos)
CAMERA_PRESETS = {
    "OVERVIEW": (1.0, 0.0), "FOCUS": (1.10, 0.0), "THINKING": (1.06, 0.0), "MEMORY_DIVE": (1.75, 0.0),
    "IDEA_FOCUS": (1.45, 0.0), "IMAGINATION": (0.86, -0.16), "SIMULATION": (0.84, -0.18),
    "WORLD_EXPLORATION": (0.80, -0.20), "NETWORK_FOCUS": (0.92, -0.14),
}
RUNTIME_DEPTH = {"IDLE": 0, "LISTENING": 1, "SPEAKING": 1, "REMINDING": 1, "PERCEIVING": 1, "CONTEXT": 2,
                 "DECIDING": 2, "THINKING": 2, "PLANNING": 3, "NETWORK": 3, "EXECUTING": 4,
                 "AWAITING_AUTHORIZATION": 4, "VERIFYING": 5, "RECOVERY": 6, "IMAGINING": 6, "SIMULATING": 7,
                 "DREAMING": 8, "ERROR": 2, "BOOTING": 0, "SHUTDOWN": 0}
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
    "RECORD_CREATED": "hippocampus", "RECORD_UPDATED": "hippocampus", "REMINDER_DUE": "hippocampus",
    "NETWORK_INVENTORY_UPDATED": "parietal",
}
LEFT_REGIONS = {"prefrontal", "frontal", "broca", "motor"}
MODULE_SHIFT = 0.13

# giro livre (rad/s) por estado; estados de foco viram a região para o observador
# giro livre por estado (rad/s). Repouso: lento e discreto — a cadência ociosa (10–24 quadros/s)
# move cada ponto ~1–2 px por quadro, sem degraus visíveis
SPIN = {"IDLE": 0.07, "DREAMING": 0.05, "THINKING": 0.30, "PLANNING": 0.26, "RECOVERY": 0.28,
        "IMAGINING": 0.20, "SIMULATING": 0.16, "BOOTING": 0.45, "ERROR": 0.0, "SHUTDOWN": 0.0,
        "CONTEXT": 0.24, "DECIDING": 0.30}
FACING = {"LISTENING": "auditory", "SPEAKING": "broca", "EXECUTING": "motor", "VERIFYING": "motor",
          "NETWORK": "parietal", "AWAITING_AUTHORIZATION": "prefrontal", "PERCEIVING": "occipital",
          "REMINDING": "hippocampus"}
CAMERA_DWELL = 0.25              # s: um estado precisa durar isso para mover a câmera (sem tremor)

# anel de subsistemas: (nome, ângulo na tela em graus — 0 = direita, horário —, região de origem
# da sinapse, componentes do ciclo de vida que o sustentam). Topo e base ficam livres (título).
SUBSYSTEM_DEFS = (
    ("OLLAMA", -118, "core", ("models",)), ("MEMÓRIA", -139, "hippocampus", ("memory",)),
    ("VISÃO", -159, "occipital", ("perception",)), ("PERCEPÇÃO", 180, "parietal", ("perception",)),
    ("VOZ", 159, "auditory", ("voice", "voice_output")), ("TELEMETRIA", 139, "cerebellum", ("health",)),
    ("REDE", 118, "parietal", ("network",)), ("IMAGINAÇÃO", -62, "prefrontal", ("imagination",)),
    ("OBJETIVOS", -41, "frontal", ("goals",)), ("CÓDIGO", -21, "frontal", ("agent", "skills")),
    ("WEB", 0, "temporal", ("agent", "skills")), ("AUTOMAÇÃO", 21, "motor", ("agent", "skills")),
    ("WINDOWS", 41, "motor", ("agent", "skills")), ("ARQUIVOS", 62, "temporal", ("agent", "skills")),
    ("AGENDA", -90, "hippocampus", ("second_brain", "reminders")),
)
EVENT_SUBSYSTEM = {
    "COGNITIVE_PHASE": ("OLLAMA", 0.35), "MODEL_SELECTED": ("OLLAMA", 0.6), "MODEL_CHANGED": ("OLLAMA", 0.6),
    "MEMORY_RECALLED": ("MEMÓRIA", 0.8), "MEMORY_CREATED": ("MEMÓRIA", 0.8), "MEMORY_CONSOLIDATED": ("MEMÓRIA", 0.6),
    "GRAPH_NODE_ADDED": ("MEMÓRIA", 0.3), "VISION_UPDATED": ("VISÃO", 0.9), "OCR_UPDATED": ("VISÃO", 0.7),
    "SCREEN_CHANGED": ("VISÃO", 0.3), "WINDOW_CHANGED": ("PERCEPÇÃO", 0.35), "APPLICATION_CHANGED": ("PERCEPÇÃO", 0.5),
    "PROCESS_ENDED": ("PERCEPÇÃO", 0.3), "PERCEPTION_FUSED": ("PERCEPÇÃO", 0.8),
    "FILESYSTEM_CHANGED": ("ARQUIVOS", 0.4), "WAKE_WORD": ("VOZ", 1.0), "VOICE_RECEIVED": ("VOZ", 0.9),
    "VOICE_STARTED": ("VOZ", 0.7), "LISTENING_STARTED": ("VOZ", 0.6), "HEALTH_UPDATED": ("TELEMETRIA", 0.25),
    "NETWORK_CHANGED": ("REDE", 0.8), "DEVICE_DETECTED": ("REDE", 0.6), "IMAGINATION_STARTED": ("IMAGINAÇÃO", 0.9),
    "CONCEPT_CREATED": ("IMAGINAÇÃO", 1.0), "SCENARIO_BRANCHED": ("IMAGINAÇÃO", 0.9),
    "WORLD_CREATED": ("IMAGINAÇÃO", 1.0), "WORLD_EXPANDED": ("IMAGINAÇÃO", 0.8), "DREAM_STARTED": ("IMAGINAÇÃO", 0.5),
    "DREAM_FINISHED": ("IMAGINAÇÃO", 0.9), "IMAGE_GENERATED": ("IMAGINAÇÃO", 1.0), "GOAL_CREATED": ("OBJETIVOS", 0.9),
    "PLAN_CREATED": ("OBJETIVOS", 0.9), "PLAN_UPDATED": ("OBJETIVOS", 0.6), "GOAL_COMPLETED": ("OBJETIVOS", 0.8),
    "GOAL_FAILED": ("OBJETIVOS", 0.8), "RECORD_CREATED": ("AGENDA", 0.9), "RECORD_UPDATED": ("AGENDA", 0.6),
    "RECORD_DELETED": ("AGENDA", 0.5), "REMINDER_DUE": ("AGENDA", 1.0), "NETWORK_INVENTORY_UPDATED": ("REDE", 0.7),
}
WAVE_SECONDS = 2.4             # duração de uma onda de percepção (expande e some)
# percepção que analisou algo (troca de janela é rotina: não gera onda nem tira a cena do repouso)
PERCEPTION_EVENTS = ("PERCEPTION_FUSED", "VISION_UPDATED", "OCR_UPDATED", "NETWORK_CHANGED")
GRAPH_REASON_TONE = {"recall": "blue", "consolidation": "blue", "plan": "cyan", "input": "cyan", "focus": "ice"}
GROW_THRESHOLD = 0.12          # atividade mínima para a sinapse de um subsistema crescer até o anel
ROUTINE_TOUCH = 0.08           # sinais de rotina (ex.: verificação de saúde sem mudança): brilho, sem crescer
CATEGORY_SUBSYSTEM = {"development": "CÓDIGO", "browser": "WEB", "automation": "AUTOMAÇÃO", "applications": "WINDOWS",
                      "windows": "WINDOWS", "system": "WINDOWS", "audio": "WINDOWS", "devices": "WINDOWS",
                      "filesystem": "ARQUIVOS", "network": "REDE", "vision": "VISÃO", "memory": "MEMÓRIA",
                      "imagination": "IMAGINAÇÃO", "diagnostics": "TELEMETRIA"}
HEALTH_SUBSYSTEM = {"OLLAMA": "OLLAMA", "VOICE": "VOZ", "VISION": "VISÃO", "NETWORK": "REDE", "MEMORY": "MEMÓRIA",
                    "SECOND_BRAIN": "AGENDA"}
STATUS_FROM_HEALTH = {"OK": "ok", "WARN": "warn", "FAIL": "fail", "UNAVAILABLE": "off", "UNKNOWN": "unknown"}
NODE_TYPE_COLOR = {"MEMORY": "blue", "IDEA": "ice", "CONCEPT": "ice", "SKILL": "cyan", "PROJECT": "cyan",
                   "WORLD": "ice", "SCENARIO": "ice", "DEVICE": "blue", "APPLICATION": "cyan"}


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
    z: float
    strength: float = 0.3
    activation: float = 0.0
    born: float = 0.0
    glow_tone: str = ""                    # tom da ativação real (memória = azul); vazio = tom do tipo


@dataclass
class SceneEdge:
    a: str
    b: str
    type: str
    weight: float
    activation: float = 0.0


@dataclass
class Particle:
    points: tuple                          # (x0, y0, z0, cx, cy, cz, x1, y1, z1): curva quadrática em 3D
    t: float = 0.0
    speed: float = 0.8
    size: float = 1.0
    tone: str = "cyan"

    def position(self) -> tuple[float, float, float]:
        x0, y0, z0, cx, cy, cz, x1, y1, z1 = self.points
        u, t = 1 - self.t, self.t
        return (u * u * x0 + 2 * u * t * cx + t * t * x1, u * u * y0 + 2 * u * t * cy + t * t * y1,
                u * u * z0 + 2 * u * t * cz + t * t * z1)


@dataclass
class Pulse:
    x: float
    y: float
    z: float
    born: float
    duration: float = 1.2
    radius: float = 0.18
    tone: str = "cyan"
    strength: float = 1.0


@dataclass
class Subsystem:
    name: str
    angle: float
    region: str
    components: tuple
    status: str = "unknown"                # unknown | ok | warn | fail | off
    activity: float = 0.0                  # 0..1 (decai)
    grow: float = 0.0                      # 0..1: sinapse do cérebro até o nó
    detail: str = ""
    arrived_at: float = 0.0


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
    x: float = 0.0                          # deslocamento de foco (unidades projetadas do cérebro)
    y: float = 0.0
    zoom: float = 1.0
    shift: float = 0.0
    tx: float = 0.0
    ty: float = 0.0
    tzoom: float = 1.0
    tshift: float = 0.0
    angle: float = 0.6                      # giro em torno do eixo vertical (rad)
    spin: float = 0.16                      # giro livre (rad/s) quando não há região em foco
    target_spin: float = 0.16               # a velocidade muda suavemente (sem trancos entre estados)
    target_angle: float | None = None
    focus: float = 0.0
    tau: float = 0.65                       # constante de tempo da suavização

    def aim(self, state: str, region: str = "core", *, depth: float = 0.0, spin: float = 0.16,
            face: bool = False) -> None:
        zoom, shift = CAMERA_PRESETS.get(state, (1.0, 0.0))
        # FOCUS só gira a região para a frente; mergulhos também a trazem para o centro da tela
        self.focus = 0.9 if state in ("MEMORY_DIVE", "IDEA_FOCUS") else 0.0
        self.state, self.region = state, region
        self.tzoom = zoom * (1.0 + 0.012 * depth)
        self.tshift = shift
        self.target_spin = spin
        self.target_angle = BrainMesh.facing_angle(region) if face else None

    def step(self, dt: float) -> None:
        k = 1.0 - math.exp(-dt / self.tau)
        self.spin += (self.target_spin - self.spin) * (1.0 - math.exp(-dt / 0.6))
        if self.target_angle is None:
            self.angle = (self.angle + self.spin * dt) % (2 * math.pi)
        else:                                             # menor arco até a região em foco
            delta = (self.target_angle - self.angle + math.pi) % (2 * math.pi) - math.pi
            if abs(delta) < 0.0015:                       # encaixa: a câmera para de fato (cache da malha)
                self.angle = self.target_angle % (2 * math.pi)
            else:
                self.angle = (self.angle + delta * (1.0 - math.exp(-dt / 0.8))) % (2 * math.pi)
        for name in ("x", "y", "zoom", "shift"):
            current, target = getattr(self, name), getattr(self, "t" + name)
            value = current + (target - current) * k
            setattr(self, name, target if abs(target - value) < 0.0008 else value)

    def facing_side(self) -> float:
        """Hemisfério voltado para o observador (+1 direito, −1 esquerdo)."""
        return 1.0 if math.cos(self.angle) >= 0 else -1.0

    def moving(self) -> bool:
        """Há movimento além do giro livre? (zoom, enquadramento ou virada para uma região)."""
        if self.target_angle is not None:
            delta = (self.target_angle - self.angle + math.pi) % (2 * math.pi) - math.pi
            if abs(delta) > 0.002:
                return True
        return (abs(self.zoom - self.tzoom) > 0.002 or abs(self.x - self.tx) > 0.002 or abs(self.y - self.ty) > 0.002
                or abs(self.shift - self.tshift) > 0.002 or abs(self.spin - self.target_spin) > 0.01)


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
    MAX_MODULES = 3

    def __init__(self, mesh: BrainMesh | None = None, *, clock: Callable[[], float] = time.monotonic,
                 profile: quality.RenderProfile | None = None):
        self.mesh = mesh or BrainMesh()
        self.clock = clock
        self.profile = profile or quality.get(None)
        # só o que está aceso decai (sem varrer o grafo inteiro); ordem = ativação mais recente por último
        self._hot_nodes: dict[str, None] = {}
        self._hot_edges: dict[tuple[str, str], None] = {}
        self._newborn: deque = deque(maxlen=256)    # (id, nascimento): brilho de nascimento por 1 s
        self.typing_until = 0.0                     # revelação da resposta em andamento (texto)
        self._suspense_target = 0.0
        self._dim_target = 0.0
        self._camera_candidate: tuple | None = None
        self._camera_since = 0.0
        self._camera_choice: tuple | None = None
        self.subsystems: dict[str, Subsystem] = {name: Subsystem(name, angle, region, comps)
                                                 for name, angle, region, comps in SUBSYSTEM_DEFS}
        self.ring_pulses: list[tuple[str, float]] = []
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
        # sinais reais dos estados (identidade visual do JARVIS)
        self.hearing = 0.0                  # nível do microfone suavizado, só enquanto escuta (halo ciano)
        self.voice_level = 0.0              # nível da fala do JARVIS suavizado (anéis sincronizados com a voz)
        self.waves: deque = deque(maxlen=6)  # ondas de percepção: instante de nascimento
        self._last_wave = -1e9
        self._telemetry_at = -1e9

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
            x, y, z = self.mesh.place(node_id, type_)
            node = SceneNode(node_id, type_, label, x, y, z, strength, 0.0, self.clock() if born is None else born)
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
            edge = SceneEdge(key[0], key[1], type_, weight)
            self.edges[key] = edge
            self._adjacency.setdefault(a, set()).add(b)
            self._adjacency.setdefault(b, set()).add(a)
            self.graph_version += 1
        else:
            edge.weight = max(edge.weight, weight)
        return edge

    # ================================================================ estímulos
    def region_point(self, region: str) -> tuple[float, float, float]:
        """Centro da região no hemisfério voltado para o observador."""
        x, y, z = self.mesh.region_center(region, self.camera.facing_side())
        return float(x), float(y), float(z)

    def stimulate(self, region: str, amount: float = 0.6, *, pulse: bool = True, tone: str = "cyan") -> None:
        if region not in REGIONS:
            return
        self.region_activity[region] = _clamp(self.region_activity[region] + amount)
        if pulse and len(self.pulses) < self.profile.max_pulses:
            x, y, z = self.region_point(region)
            radius = REGIONS[region][3]
            self.pulses.append(Pulse(x, y, z, self.clock(), 1.1 + 0.6 * amount, radius * (0.8 + amount), tone, amount))

    def touch_subsystem(self, name: str, amount: float) -> None:
        sub = self.subsystems.get(name)
        if sub is not None:
            sub.activity = _clamp(max(sub.activity, amount))

    def activate_nodes(self, ids: list[str], *, spread: bool = True, tone: str = "cyan") -> None:
        for node_id in ids:
            node = self.nodes.get(node_id)
            if node is None:
                continue
            node.activation = 1.0
            node.glow_tone = tone
            self._heat_node(node_id)
            if not spread:
                continue
            for other in list(self._adjacency.get(node_id, ()))[:6]:
                self._emit_particle(node_id, other, tone=tone)

    def _heat_node(self, node_id: str) -> None:
        self._hot_nodes.pop(node_id, None)
        self._hot_nodes[node_id] = None
        while len(self._hot_nodes) > 3 * self.profile.max_particles:      # o mais antigo já é o mais fraco
            old = self.nodes.get(next(iter(self._hot_nodes)))
            if old is not None:
                old.activation = 0.0
            self._hot_nodes.pop(next(iter(self._hot_nodes)))

    def _heat_edge(self, key: tuple[str, str]) -> None:
        self._hot_edges.pop(key, None)
        self._hot_edges[key] = None
        while len(self._hot_edges) > 4 * self.profile.active_edges:
            old = self.edges.get(next(iter(self._hot_edges)))
            if old is not None:
                old.activation = 0.0
            self._hot_edges.pop(next(iter(self._hot_edges)))

    def _emit_particle(self, a: str, b: str, *, tone: str = "cyan") -> None:
        key = (a, b) if a < b else (b, a)
        edge = self.edges.get(key)
        na, nb = self.nodes.get(a), self.nodes.get(b)
        if edge is None or na is None or nb is None:
            return
        edge.activation = 1.0                       # a sinapse acende mesmo sem partícula (limite do perfil)
        self._heat_edge(key)
        if len(self.particles) >= self.profile.max_particles:
            return
        mx, my, mz = (na.x + nb.x) / 2, (na.y + nb.y) / 2, (na.z + nb.z) / 2
        self.particles.append(Particle((na.x, na.y, na.z, mx * 0.8, my * 0.8, mz * 0.8, nb.x, nb.y, nb.z), 0.0,
                                       0.55 + 0.5 * edge.weight, 1.0 + edge.weight, tone))

    def region_particles(self, src: str, dst: str, count: int = 3, tone: str = "cyan") -> None:
        """Sinal entre regiões (ex.: percepção → córtex), em arco pelo interior do cérebro."""
        if src not in REGIONS or dst not in REGIONS:
            return
        x0, y0, z0 = self.region_point(src)
        x1, y1, z1 = self.region_point(dst)
        for i in range(count):
            if len(self.particles) >= self.profile.max_particles:
                return
            off = (i - (count - 1) / 2) * 0.12
            control = ((x0 + x1) * 0.25, (y0 + y1) * 0.25 + off, (z0 + z1) * 0.25 - off)
            self.particles.append(Particle((x0, y0, z0, *control, x1, y1, z1), -0.15 * i, 0.9, 1.2, tone))

    # ================================================================ eventos
    def on_event(self, kind: str, payload: dict | None = None) -> None:
        p = payload or {}
        now = self.clock()
        region = EVENT_REGION.get(kind)
        target = EVENT_SUBSYSTEM.get(kind)
        if kind in PERCEPTION_EVENTS:
            self._wave(now)
        if kind == "HEALTH_UPDATED" and not p.get("changed"):
            # verificação de rotina sem mudança: só um brilho no anel, abaixo do limiar que faz a
            # sinapse crescer (antes, a cada 15 s, ~4 s de animação no teto de quadros em repouso)
            target = ("TELEMETRIA", ROUTINE_TOUCH)
        if target is not None and not (kind == "DEVICE_DETECTED" and p.get("origin") == "peripheral"):
            self.touch_subsystem(*target)
        if kind in ("ACTION_STARTED", "ACTION_FINISHED"):
            name = CATEGORY_SUBSYSTEM.get(str(p.get("category", "")))
            if name is None:
                skill = str(p.get("skill", ""))
                name = next((sub for prefix, sub in (("dev.", "CÓDIGO"), ("web.", "WEB"), ("fs.", "ARQUIVOS"),
                                                     ("input.", "AUTOMAÇÃO"), ("automation.", "AUTOMAÇÃO"),
                                                     ("app.", "WINDOWS"), ("window.", "WINDOWS"),
                                                     ("network.", "REDE"), ("vision.", "VISÃO"))
                             if skill.startswith(prefix)), None)
            if name:
                self.touch_subsystem(name, 1.0 if kind == "ACTION_STARTED" else 0.6)
        if kind == "SYSTEM_BOOT":
            self.boot.start()
        elif kind in ("COMPONENT_STARTED", "COMPONENT_FAILED", "COMPONENT_STOPPED"):
            component = str(p.get("component", ""))
            if kind != "COMPONENT_STOPPED":
                self.boot.component(component, kind == "COMPONENT_STARTED", str(p.get("error", "")))
            status = {"COMPONENT_STARTED": "ok", "COMPONENT_FAILED": "fail", "COMPONENT_STOPPED": "off"}[kind]
            for sub in self.subsystems.values():
                if component in sub.components and not (status == "ok" and sub.status == "fail"):
                    sub.status = status
                    sub.detail = str(p.get("error", ""))[:60] if status == "fail" else ""
        elif kind == "SYSTEM_READY":
            self.boot.ready()
        elif kind == "GRAPH_NODE_ADDED":
            known = str(p.get("id", "")) in self.nodes
            node = self._add_node(str(p.get("id", "")), str(p.get("type", "CONCEPT")), str(p.get("label", "")),
                                  float(p.get("strength", 0.3)))
            if node is not None:
                node.activation = 1.0
                self._heat_node(node.id)
                if not known:
                    self.total_nodes += 1
                    self._newborn.append((node.id, now))
                if len(self.pulses) < self.profile.max_pulses:
                    self.pulses.append(Pulse(node.x, node.y, node.z, now, 1.4, 0.07, "ice", 0.8))
                parent = p.get("parent")
                if parent:
                    self._add_edge(str(parent), node.id, "DERIVED", 0.3)
                    self._emit_particle(str(parent), node.id, tone="ice")
            self._update_development()
        elif kind == "GRAPH_EDGE_ADDED":
            edge = self._add_edge(str(p.get("src", "")), str(p.get("dst", "")), str(p.get("type", "RELATED")),
                                  float(p.get("weight", 0.2)))
            if edge is not None:
                self.total_edges += 1
                self._emit_particle(edge.a, edge.b)
            self._update_development()
        elif kind == "GRAPH_ACTIVATED":
            # memória consultada acende em azul; o caminho de um plano/entrada em ciano
            self.activate_nodes([str(i) for i in (p.get("ids") or [])][:24],
                                tone=GRAPH_REASON_TONE.get(str(p.get("reason") or ""), "cyan"))
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
            self.activate_nodes([str(i) for i in (p.get("sources") or [])], tone="ice")
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
                self.typing_until = max(self.typing_until, now + len(text) / 70.0 + 0.2)
            if not p.get("partial"):
                self.release = 1.0
                self._waiting_since = 0.0
        elif kind == "USER_INPUT":
            self.transcript.append({"role": "user", "text": str(p.get("text", "")), "at": now, "kind": "input"})
            self._waiting_since = now
        elif kind == "WAKE_WORD":
            self.stimulate("auditory", 0.9, tone="ice")
            self.region_particles("auditory", "prefrontal", 3, "ice")
        elif kind == "VERIFICATION_SUCCESS":
            self.stimulate("motor", 0.7, tone="ice")
        elif kind in ("VERIFICATION_FAILED", "ERROR_DETECTED", "RECOVERY_STARTED"):
            self.stimulate(region or "frontal", 0.8, tone="error" if kind != "RECOVERY_STARTED" else "alert")
        elif kind == "REMINDER_DUE":
            when = str(p.get("when_text") or "")
            lines = [str(p.get("title", ""))[:90]] + ([when] if when else [])
            if p.get("lead"):
                lines.append(f"aviso antecipado · {p.get('lead')}")
            self._module("reminder", "LEMBRETE", "hippocampus", lines, ttl=18.0, priority=5)
            self.stimulate("hippocampus", 0.9, tone="glow")
        elif kind in ("RECORD_CREATED", "RECORD_UPDATED", "RECORD_DELETED"):
            verb = {"RECORD_CREATED": "registrado", "RECORD_UPDATED": "atualizado",
                    "RECORD_DELETED": "excluído" if p.get("permanent") else "enviado à lixeira"}[kind]
            record = p.get("record") or {}
            title = str(record.get("title") or p.get("title") or "")[:70]
            label = {"task": "Tarefa", "event": "Compromisso", "study": "Estudo", "project": "Projeto",
                     "idea": "Ideia", "note": "Nota", "person": "Pessoa", "routine": "Rotina",
                     "deadline": "Prazo"}.get(str(record.get("kind") or p.get("kind") or ""), "Registro")
            if p.get("change") == "completed":
                verb = "concluído"
            if label in ("Tarefa", "Ideia", "Nota", "Pessoa", "Rotina"):     # concordância: "Tarefa registrada"
                verb = verb.replace("registrado", "registrada").replace("atualizado", "atualizada") \
                    .replace("excluído", "excluída").replace("enviado", "enviada").replace("concluído", "concluída")
            self._module("secondbrain", "MEMÓRIA PESSOAL", "hippocampus", [f"{label} {verb}", title],
                         ttl=6.0, priority=45)
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
                self.region_particles("auditory", "frontal", 2, "ice")

    def _wave(self, now: float, *, min_gap: float = 0.6) -> None:
        if now - self._last_wave >= min_gap:
            self.waves.append(now)
            self._last_wave = now

    def plan_progress(self) -> list[str]:
        """Estado de cada etapa do plano atual (só enquanto há plano em andamento): o desenho acende
        as conexões entre etapas à medida que elas terminam — progresso real, não animação solta."""
        if self.runtime_state not in ("PLANNING", "EXECUTING", "VERIFYING", "RECOVERY", "AWAITING_AUTHORIZATION",
                                      "THINKING"):
            return []
        steps = (self.state.get("current_plan") or {}).get("steps") or []
        return [str(step.get("status", "pending")).lower() for step in steps[:12]]

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
        health = state.get("health") or {}
        for check, name in HEALTH_SUBSYSTEM.items():
            entry = (health.get("checks") or {}).get(check)
            if entry:
                sub = self.subsystems[name]
                sub.status = STATUS_FROM_HEALTH.get(str(entry.get("status", "")).upper(), sub.status)
                sub.detail = str(entry.get("detail", ""))[:60] if sub.status in ("warn", "fail", "off") else ""
        if health.get("overall"):
            sub = self.subsystems["TELEMETRIA"]
            sub.status = STATUS_FROM_HEALTH.get(str(health["overall"]).upper(), sub.status)
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
                     f"{net.get('devices_online', 0)} presente(s) · {net.get('devices_known', 0)} conhecido(s)"]
            self._module("network", "NETWORK MESH", "parietal", lines, ttl=12.0, priority=25)

    def on_telemetry(self, telemetry: dict) -> None:
        self.telemetry = telemetry
        self._telemetry_at = self.clock()
        if telemetry.get("listening"):
            self.region_activity["auditory"] = max(self.region_activity["auditory"],
                                                   _clamp(0.25 + float(telemetry.get("mic_level", 0.0))))
            self.touch_subsystem("VOZ", 0.5)
        if telemetry.get("speaking"):
            self.region_activity["broca"] = max(self.region_activity["broca"],
                                                _clamp(0.2 + 2.2 * float(telemetry.get("out_level", 0.0))))
            self.touch_subsystem("VOZ", 0.6)

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

    def _choose_camera(self) -> tuple[str, str, bool]:
        """(estado da câmera, região, virar a região para o observador)."""
        now = self.clock()
        if self._camera_override and now < self._camera_override[2]:
            return self._camera_override[0], self._camera_override[1], True
        self._camera_override = None
        if self.boot.active:
            return "OVERVIEW", "core", False
        if "world" in self.modules and self.modules["world"].expires is None:
            return "WORLD_EXPLORATION", "occipital", True
        if self.runtime_state == "IMAGINING" and "simulation" in self.modules:
            return "SIMULATION", "prefrontal", False
        state, region = RUNTIME_CAMERA.get(self.runtime_state, ("OVERVIEW", "core"))
        return state, region, self.runtime_state in FACING

    def _stable_camera(self) -> tuple[str, str, bool]:
        """Histerese: um estado breve (ex.: VERIFYING de 50 ms entre duas execuções) não sacode a
        câmera. Focos transitórios de eventos reais e a inicialização valem na hora."""
        choice = self._choose_camera()
        now = self.clock()
        immediate = self.boot.active or (self._camera_override is not None and now < self._camera_override[2])
        if immediate or self._camera_choice is None:
            self._camera_choice, self._camera_candidate = choice, None
        elif choice != self._camera_choice:
            if choice != self._camera_candidate:
                self._camera_candidate, self._camera_since = choice, now
            elif now - self._camera_since >= CAMERA_DWELL:
                self._camera_choice, self._camera_candidate = choice, None
        else:
            self._camera_candidate = None
        return self._camera_choice

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
        state, region, face = self._stable_camera()
        spin = SPIN.get("BOOTING" if self.boot.active else self.runtime_state, SPIN["IDLE"])
        self.camera.aim(state, region, depth=self.depth, spin=spin, face=face)
        if CAMERA_PRESETS.get(state, (1.0, 0.0))[1] == 0.0:
            shift, zoom = self._module_shift()
            self.camera.tshift = shift
            self.camera.tzoom *= zoom
        if self.camera.focus > 0 and region != "core":   # a região focada vai para o centro da tela
            X, Y, _Z = self.mesh.rotate(self.mesh.region_center(region, self.camera.facing_side())[None, :],
                                        self.camera.angle)
            self.camera.tx, self.camera.ty = float(X[0]) * STRETCH * self.camera.focus, float(Y[0]) * self.camera.focus
        else:
            self.camera.tx = self.camera.ty = 0.0
        self.camera.step(dt)
        # escuta e fala: níveis REAIS (microfone / saída de áudio), suavizados para não tremer
        tel = (self.telemetry or {}) if now - self._telemetry_at < 1.0 else {}     # leitura velha não conta
        hearing = float(tel.get("mic_level", 0.0) or 0.0) if tel.get("listening") or self.runtime_state == "LISTENING" \
            else 0.0
        voice = float(tel.get("out_level", 0.0) or 0.0) if tel.get("speaking") or self.runtime_state == "SPEAKING" \
            else 0.0
        self.hearing += (_clamp(hearing * 1.6) - self.hearing) * (1 - math.exp(-dt / 0.12))
        self.voice_level += (_clamp(voice * 2.2) - self.voice_level) * (1 - math.exp(-dt / 0.08))
        if self.hearing < 0.003:
            self.hearing = 0.0
        if self.voice_level < 0.003:
            self.voice_level = 0.0
        # percepção: ondas sutis enquanto o estado real é de percepção (além das de cada evento)
        if self.runtime_state in ("PERCEIVING", "NETWORK"):
            self._wave(now, min_gap=1.8)
        while self.waves and now - self.waves[0] > WAVE_SECONDS:
            self.waves.popleft()
        # suspense: esperando resposta há mais de 1,5 s, ou autorização pendente
        waiting = self._waiting_since and now - self._waiting_since > 1.5 and \
            self.runtime_state in ("THINKING", "PLANNING")          # nada visível acontecendo ainda
        target_suspense = 1.0 if self.runtime_state == "AWAITING_AUTHORIZATION" else 0.7 if waiting else 0.0
        self._suspense_target = target_suspense
        self.suspense += (target_suspense - self.suspense) * (1 - math.exp(-dt / 0.8))
        if abs(target_suspense - self.suspense) < 0.005:
            self.suspense = target_suspense
        self.release = max(0.0, self.release - dt / 0.9)
        dim_target = 0.45 if self.runtime_state == "DREAMING" else 0.25 * self.suspense
        self._dim_target = dim_target
        self.dim += (dim_target - self.dim) * (1 - math.exp(-dt / 1.2))
        if abs(dim_target - self.dim) < 0.005:
            self.dim = dim_target
        # respiração (repouso): lenta, só como sinal de "vivo e em repouso"
        rate = 0.12 if self.runtime_state in ("IDLE", "DREAMING") else 0.35
        self.breath = (self.breath + dt * rate) % 1.0
        # decaimentos: só o que está aceso (atualização incremental; o grafo inteiro não é varrido)
        node_decay = math.exp(-dt / 1.6)
        for node_id in list(self._hot_nodes):
            node = self.nodes.get(node_id)
            if node is None:
                self._hot_nodes.pop(node_id, None)
                continue
            node.activation *= node_decay
            if node.activation < 0.02:                  # abaixo do visível: sai do conjunto aceso
                node.activation = 0.0
                self._hot_nodes.pop(node_id, None)
        edge_decay = math.exp(-dt / 1.2)
        for key in list(self._hot_edges):
            edge = self.edges.get(key)
            if edge is None:
                self._hot_edges.pop(key, None)
                continue
            edge.activation *= edge_decay
            if edge.activation < 0.03:
                edge.activation = 0.0
                self._hot_edges.pop(key, None)
        while self._newborn and now - self._newborn[0][1] > 1.0:
            self._newborn.popleft()
        region_decay = math.exp(-dt / 1.4)
        for name in self.region_activity:
            value = self.region_activity[name] * region_decay
            self.region_activity[name] = value if value > 0.001 else 0.0
        # subsistemas: atividade contínua dos estados reais e sinapses que crescem só durante o uso
        continuous = {"THINKING": "OLLAMA", "PLANNING": "OBJETIVOS", "IMAGINING": "IMAGINAÇÃO",
                      "SIMULATING": "IMAGINAÇÃO", "DREAMING": "IMAGINAÇÃO", "NETWORK": "REDE",
                      "PERCEIVING": "PERCEPÇÃO", "CONTEXT": "MEMÓRIA", "DECIDING": "OBJETIVOS",
                      "REMINDING": "AGENDA"}
        if self.runtime_state in continuous:
            self.touch_subsystem(continuous[self.runtime_state], 0.45)
        sub_decay = math.exp(-dt / 2.2)
        for sub in self.subsystems.values():
            sub.activity = sub.activity * sub_decay if sub.activity > 0.002 else 0.0
            target = 1.0 if sub.activity > GROW_THRESHOLD and sub.status not in ("fail", "off") else 0.0
            before = sub.grow
            rate = 1.6 if target > sub.grow else 0.5
            sub.grow += max(-rate * dt, min(rate * dt, target - sub.grow))
            if before < 0.97 <= sub.grow:
                sub.arrived_at = now
                self.ring_pulses.append((sub.name, now))
        self.ring_pulses = [(n, t) for n, t in self.ring_pulses if now - t < 1.0]
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
    def hot_edges(self, limit: int, *, threshold: float = 0.05) -> list[SceneEdge]:
        """Sinapses do grafo percorridas por um sinal agora: as ``limit`` ativadas mais recentemente
        (todas decaem no mesmo ritmo, então são também as mais intensas — sem ordenar a cada quadro)."""
        keys = list(self._hot_edges)[-limit:] if limit > 0 else []
        return [e for e in (self.edges.get(k) for k in keys) if e is not None and e.activation >= threshold]

    def glowing_nodes(self, limit: int = 1000) -> list[tuple[SceneNode, float]]:
        """(nó, idade em s): nós ativados agora (os mais intensos, até ``limit``) ou nascidos há
        menos de 1 s."""
        now = self.clock()
        out: dict[str, tuple[SceneNode, float]] = {}
        for node_id, born in self._newborn:
            node = self.nodes.get(node_id)
            if node is not None:
                out[node_id] = (node, now - born)
        room = max(0, limit - len(out))
        recent = list(self._hot_nodes)[-room:] if room else []
        hot = [n for n in (self.nodes.get(i) for i in recent)
               if n is not None and n.activation >= 0.08 and n.id not in out]
        for node in hot:
            out[node.id] = (node, now - node.born)
        return list(out.values())

    def in_motion(self) -> bool:
        """Há movimento real na tela (algo se deslocando ou surgindo)? Decide o ritmo de quadros:
        no teto do perfil durante o movimento; esmaecimentos lentos (brilho de nós, regiões e
        subsistemas apagando), o giro livre e a respiração ficam na cadência econômica."""
        if self.boot.active or self.particles or self.pulses or self.release > 0.0:
            return True
        if self.waves or self.hearing > 0.02 or self.voice_level > 0.02:
            return True                                   # ondas de percepção, escuta e fala acompanham o sinal
        if self._newborn or self.ring_pulses or self.camera.moving():
            return True
        if abs(self.suspense - self._suspense_target) > 0.01 or abs(self.dim - self._dim_target) > 0.01:
            return True
        if any(0.0 < s.grow < 1.0 or (s.grow > 0.5 and s.activity > GROW_THRESHOLD)
               for s in self.subsystems.values()):
            return True                                   # sinapse crescendo ou sinal percorrendo
        if any(0.02 < m.alpha < 0.98 for m in self.modules.values()):
            return True
        return self.clock() < self.typing_until

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

    def genesis(self) -> float:
        """0..1: quanto da malha já nasceu (inicialização guiada por componentes reais)."""
        if not self.boot.active:
            return 1.0
        return _clamp((self.boot.shown - 2.5) / 7.5)

    def headline(self) -> str:
        if self.boot.active:
            return self.boot.label
        if self.runtime_state == "AWAITING_AUTHORIZATION":
            return "AUTHORIZATION REQUIRED"
        if self.overlay_label:
            return self.overlay_label
        return self.cognitive_phase or ""
