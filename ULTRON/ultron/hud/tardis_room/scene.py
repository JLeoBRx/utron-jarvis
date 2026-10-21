"""Estado da sala de controle — sem Qt (testável).

A cena só ANIMA o que o motor da TARDIS informa:

* o modo do rotor vem do ``TARDIS_STATE`` (repouso, processando, operação, consulta do JARVIS, falha);
* cada painel do console acende enquanto uma tarefa REAL daquele tipo roda, pulsa quando ela termina
  (âmbar se concluiu, vermelho se falhou) e apaga devagar;
* o feixe JARVIS ⇄ TARDIS só existe enquanto uma tarefa pedida pelo JARVIS está em execução;
* o anel de falha no piso acende quando uma tarefa falha e apaga sozinho.

Sem evento, a sala fica em repouso: nada aqui inventa atividade.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ...tardis.protocol import KINDS, PANEL_LABELS, PANELS

AMBER = (255.0, 179.0, 71.0)
AMBER_DIM = (214.0, 140.0, 52.0)
CYAN = (0.0, 217.0, 255.0)
TEAL = (77.0, 232.0, 194.0)
RED = (255.0, 93.0, 115.0)
ICE = (220.0, 238.0, 255.0)


@dataclass(frozen=True)
class ModeStyle:
    key: str
    label: str
    speed: float          # ciclos do rotor por segundo (subir e descer)
    amplitude: float      # curso do rotor (0..1)
    brightness: float     # brilho do vidro e do console
    color: tuple          # cor do núcleo do rotor
    spin: float           # giro dos anéis internos (voltas por segundo)


MODES: dict[str, ModeStyle] = {m.key: m for m in (
    ModeStyle("repouso", "REPOUSO", 0.12, 0.30, 0.42, AMBER_DIM, 0.05),
    ModeStyle("processando", "PROCESSANDO", 0.55, 1.00, 0.92, AMBER, 0.35),
    ModeStyle("operacao", "OPERAÇÃO", 0.35, 0.60, 0.78, TEAL, 0.22),
    ModeStyle("jarvis", "CONSULTA DO JARVIS", 0.65, 1.00, 1.00, CYAN, 0.45),
    ModeStyle("falha", "FALHA", 0.03, 0.12, 0.55, RED, 0.02),
)}
PANEL_ANGLES = {key: math.radians(90 - 60 * i) for i, key in enumerate(PANELS)}   # ANÁLISE de frente
FOCUS_RATE = 3.2            # aproximação da câmera ao painel escolhido (1/s); sem painel, a câmera fica parada


def _approach(value: float, target: float, rate: float, dt: float) -> float:
    return target + (value - target) * math.exp(-rate * dt)


def _approach_rgb(value: tuple, target: tuple, rate: float, dt: float) -> tuple:
    return tuple(_approach(v, t, rate, dt) for v, t in zip(value, target))


def _angle_delta(a: float, b: float) -> float:
    """Menor diferença b − a, em (−π, π]."""
    return (b - a + math.pi) % (2 * math.pi) - math.pi


@dataclass
class Mote:
    x: float
    y: float
    z: float
    speed: float
    phase: float


@dataclass
class PanelState:
    key: str
    label: str
    level: float = 0.0         # atividade 0..1 (acende com tarefa em execução)
    flash: float = 0.0         # pulso ao terminar
    fault: float = 0.0         # pulso vermelho ao falhar
    running: int = 0           # tarefas deste painel em execução agora
    last: str = ""             # resumo da última tarefa deste painel


@dataclass
class RoomScene:
    mode: str = "repouso"
    fault: bool = False
    fault_text: str = ""
    queued: int = 0
    running: dict | None = None
    operations: list = field(default_factory=list)
    phase: float = 0.0
    spin: float = 0.0
    speed: float = MODES["repouso"].speed
    amplitude: float = MODES["repouso"].amplitude
    brightness: float = MODES["repouso"].brightness
    color: tuple = MODES["repouso"].color
    beam: float = 0.0
    fault_glow: float = 0.0
    azimuth: float = PANEL_ANGLES["analise"]
    focus: str = ""
    selected: str = ""
    hover: str = ""
    time: float = 0.0
    panels: dict = field(default_factory=lambda: {k: PanelState(k, PANEL_LABELS[k]) for k in PANELS})
    motes: list = field(default_factory=list)
    screens: dict = field(default_factory=dict)
    model_label: str = ""
    events: int = 0

    # ------------------------------------------------------------ dados do motor
    def set_engine_state(self, state: dict) -> None:
        """``TARDIS_STATE`` ou ``engine.state()``: modo, fila, tarefa em execução, operações e falha."""
        mode = str(state.get("mode") or "repouso")
        self.mode = mode if mode in MODES else "repouso"
        self.fault = bool(state.get("fault"))
        self.fault_text = str(state.get("fault_text") or "")
        self.queued = int(state.get("queued") or 0)
        self.running = state.get("running") or None
        self.operations = list(state.get("operations") or [])
        self.events += 1

    def task_event(self, kind: str, payload: dict) -> None:
        """TARDIS_TASK_STARTED/FINISHED/FAILED/CANCELLED → painel do tipo de análise."""
        spec = KINDS.get(str(payload.get("kind") or ""))
        if spec is None:
            return
        panel = self.panels[spec.panel]
        if kind == "TARDIS_TASK_STARTED":
            panel.running += 1
        elif kind in ("TARDIS_TASK_FINISHED", "TARDIS_TASK_FAILED", "TARDIS_TASK_CANCELLED"):
            panel.running = max(0, panel.running - 1)
            if kind == "TARDIS_TASK_FINISHED":
                panel.flash = 1.0
                panel.last = str(payload.get("summary") or "")[:160]
                model = str(payload.get("model") or "")
                if "(o mesmo do JARVIS)" in model:          # só o nome do modelo de linguagem usado
                    self.model_label = model.replace("(o mesmo do JARVIS)", "").strip()
            elif kind == "TARDIS_TASK_FAILED":
                panel.fault = 1.0
                panel.last = "falhou: " + str((payload.get("error") or {}).get("message") or "")[:150]
        self.events += 1

    # ------------------------------------------------------------ interação
    def select(self, key: str) -> None:
        """Escolher um painel gira a câmera até ele ("" solta o painel; a câmera fica onde está)."""
        self.selected = key if key in self.panels else ""
        self.focus = self.selected

    def set_motes(self, count: int, seed: int = 7) -> None:
        rng = random.Random(seed)
        self.motes = [Mote(rng.uniform(-4.2, 4.2), rng.uniform(0.0, 3.4), rng.uniform(-4.2, 4.2),
                           rng.uniform(0.04, 0.16), rng.uniform(0, math.tau)) for _ in range(max(0, count))]

    # ------------------------------------------------------------ relógio
    @property
    def style(self) -> ModeStyle:
        return MODES[self.mode]

    def step(self, dt: float) -> None:
        dt = max(0.0, min(0.25, float(dt)))
        self.time += dt
        style = self.style
        self.speed = _approach(self.speed, style.speed, 2.0, dt)
        self.amplitude = _approach(self.amplitude, style.amplitude, 2.0, dt)
        self.brightness = _approach(self.brightness, style.brightness, 2.5, dt)
        self.color = _approach_rgb(self.color, style.color, 2.5, dt)
        self.phase = (self.phase + dt * self.speed * math.tau) % math.tau
        self.spin = (self.spin + dt * style.spin * math.tau) % math.tau
        self.beam = _approach(self.beam, 1.0 if self.mode == "jarvis" else 0.0, 3.0, dt)
        self.fault_glow = _approach(self.fault_glow, 1.0 if self.fault else 0.0, 3.0, dt)
        for panel in self.panels.values():
            panel.level = _approach(panel.level, 1.0 if panel.running else 0.0, 3.0 if panel.running else 0.8, dt)
            panel.flash = _approach(panel.flash, 0.0, 1.6, dt)
            panel.fault = _approach(panel.fault, 0.0, 0.7, dt)
        if self.focus:
            target = PANEL_ANGLES[self.focus]
            delta = _angle_delta(self.azimuth, target)
            self.azimuth = target if abs(delta) < 0.002 else self.azimuth + delta * (1.0 - math.exp(-FOCUS_RATE * dt))
        for mote in self.motes:
            mote.y += mote.speed * dt
            if mote.y > 3.4:
                mote.y -= 3.4

    def camera_moving(self) -> bool:
        """A câmera ainda gira até o painel escolhido (o desenho usa menos detalhe nesses quadros)."""
        return bool(self.focus) and abs(_angle_delta(self.azimuth, PANEL_ANGLES[self.focus])) > 0.002

    def rotor_offset(self) -> float:
        """Curso do rotor: 0 (encolhido) .. 1 (estendido) — sobe e desce como o original."""
        return 0.5 + 0.5 * math.sin(self.phase) * self.amplitude

    def in_motion(self) -> bool:
        if self.mode != "repouso" or self.fault_glow > 0.02 or self.beam > 0.02:
            return True
        if self.focus and abs(_angle_delta(self.azimuth, PANEL_ANGLES[self.focus])) > 0.004:
            return True
        return any(p.level > 0.02 or p.flash > 0.02 or p.fault > 0.02 for p in self.panels.values())
