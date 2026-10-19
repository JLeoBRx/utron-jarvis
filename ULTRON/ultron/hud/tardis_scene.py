"""TARDIS — modelo da cena da memória espacial (sem Qt, testável).

Um espaço interior maior que o exterior: no centro, a CÂMARA DE ENERGIA (hoje); em volta,
PORTAIS para as regiões da memória pessoal — projetos, compromissos, tarefas, ideias e
memórias —, mais dois satélites (lembretes e revisão). Cada portal mostra números e pontos
que são registros REAIS do banco; nada é decorativo inventado.

* câmera: visão geral ↔ foco numa região, com transição suave (amortecimento exponencial);
* partículas ciano circulam pelo espaço (quantidade limitada pelo perfil de qualidade);
* pulsos de dados percorrem os corredores quando um evento REAL acontece (registro criado,
  editado, concluído, lembrete disparado…);
* a câmara central reflete o estado de atividade do núcleo (o mesmo contrato do HUB principal).
"""
from __future__ import annotations

import math
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

from . import palette

# Região → (rótulo, posição no mundo (x, y), profundidade 0 = perto .. 1 = longe, página, tom)
REGIONS = {
    "agenda": ("COMPROMISSOS", (0.0, -330.0), 0.55, "timeline", "glow"),
    "projects": ("PROJETOS", (-530.0, -150.0), 0.3, "projects", "cyan"),
    "tasks": ("TAREFAS E PRAZOS", (530.0, -150.0), 0.3, "tasks", "cyan"),
    "ideas": ("IDEIAS", (-430.0, 235.0), 0.0, "ideas", "ice"),
    "memories": ("MEMÓRIAS", (430.0, 235.0), 0.0, "search", "blue"),
    "reminders": ("LEMBRETES", (-170.0, 395.0), 0.0, "notifications", "glow"),
    "review": ("REVISÃO", (170.0, 395.0), 0.0, "review", "alert"),
}
CORE_KEY = "core"                 # câmara central: hoje
CORE_PAGE = "today"
SATELLITES = ("reminders", "review")
# tipo de registro → região (para pulsos de eventos reais)
KIND_REGION = {"project": "projects", "event": "agenda", "task": "tasks", "study": "tasks", "deadline": "tasks",
               "routine": "tasks", "idea": "ideas", "note": "memories", "person": "memories"}
WORLD_W, WORLD_H = 1500.0, 1000.0


@dataclass
class Camera:
    x: float = 0.0
    y: float = 0.0
    zoom: float = 1.0
    target_x: float = 0.0
    target_y: float = 0.0
    target_zoom: float = 1.0
    orbit: float = 0.0               # giro lento dos anéis (rad)
    tau: float = 0.38                # constante de tempo da transição (s)

    def step(self, dt: float) -> None:
        k = 1.0 - math.exp(-dt / self.tau) if dt > 0 else 0.0
        self.x += (self.target_x - self.x) * k
        self.y += (self.target_y - self.y) * k
        self.zoom += (self.target_zoom - self.zoom) * k
        if abs(self.target_x - self.x) < 0.05:
            self.x = self.target_x
        if abs(self.target_y - self.y) < 0.05:
            self.y = self.target_y
        if abs(self.target_zoom - self.zoom) < 1e-4:
            self.zoom = self.target_zoom

    def moving(self) -> bool:
        return (self.x, self.y, self.zoom) != (self.target_x, self.target_y, self.target_zoom)


@dataclass
class Region:
    key: str
    label: str
    pos: tuple[float, float]
    depth: float
    page: str
    tone: str
    count: int = 0
    detail: str = ""
    alert: bool = False
    items: list = field(default_factory=list)       # [{"id", "title", "status", "priority", "overdue"}]
    energy: float = 0.0                             # brilho recente por evento real (decai)

    @property
    def scale(self) -> float:
        base = 0.62 if self.key in SATELLITES else 1.0
        return base * (1.0 - 0.28 * self.depth)


@dataclass
class Pulse:
    region: str
    born: float
    inbound: bool                    # True: região → câmara; False: câmara → região
    tone: str = "cyan"
    duration: float = 1.1


@dataclass
class Particle:
    angle: float
    radius: float
    height: float
    speed: float
    drift: float
    size: float


class TardisScene:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic, max_particles: int = 120,
                 seed: int = 11):
        self.clock = clock
        self.camera = Camera()
        self.regions = {key: Region(key, label, pos, depth, page, tone)
                        for key, (label, pos, depth, page, tone) in REGIONS.items()}
        self.focus: str | None = None
        self.activity = "IDLE"
        self.core_energy = 0.0           # resposta a eventos reais (decai)
        self.today: dict = {}
        self.pulses: deque[Pulse] = deque(maxlen=48)
        self._rng = random.Random(seed)
        self.particles: list[Particle] = []
        self.set_particle_budget(max_particles)
        self.panel_fraction = 0.0        # fração da largura ocupada pelo painel lateral (0 = fechado)
        self.events = 0

    # ------------------------------------------------------------ dados reais
    def set_particle_budget(self, count: int) -> None:
        count = max(0, int(count))
        rng = self._rng
        while len(self.particles) < count:
            self.particles.append(Particle(rng.uniform(0, math.tau), rng.uniform(60, 720), rng.uniform(-0.5, 0.5),
                                           rng.uniform(0.04, 0.16) * rng.choice((-1, 1)), rng.uniform(-12, 12),
                                           rng.uniform(0.8, 2.2)))
        del self.particles[count:]

    def apply_data(self, data: dict) -> None:
        """Contagens e itens por região (lidos do banco numa thread de trabalho)."""
        for key, info in (data.get("regions") or {}).items():
            region = self.regions.get(key)
            if region is None:
                continue
            region.count = int(info.get("count", 0))
            region.detail = str(info.get("detail", ""))
            region.alert = bool(info.get("alert"))
            region.items = list(info.get("items") or [])[:14]
        self.today = dict(data.get("today") or {})

    def on_event(self, kind: str, payload: dict) -> None:
        """Só eventos reais geram movimento: o pulso vai do núcleo à região do registro (ou volta)."""
        now = self.clock()
        region = None
        inbound = False
        tone = "cyan"
        if kind in ("RECORD_CREATED", "RECORD_UPDATED", "RECORD_DELETED", "RECORD_RESTORED"):
            record = payload.get("record") or {}
            region = KIND_REGION.get(str(record.get("kind") or payload.get("kind") or ""), "memories")
            if not record.get("confirmed", True):
                region = "review" if kind == "RECORD_CREATED" else region
            tone = "error" if kind == "RECORD_DELETED" else ("ice" if kind == "RECORD_UPDATED" else "cyan")
        elif kind == "REMINDER_DUE":
            region, inbound, tone = KIND_REGION.get(str(payload.get("record_kind") or ""), "agenda"), True, "glow"
            self._pulse("reminders", now, inbound=True, tone="glow")
        elif kind in ("REMINDER_SNOOZED", "NOTIFICATION"):
            region, inbound, tone = "reminders", True, "glow"
        if region is None or region not in self.regions:
            return
        self.events += 1
        self._pulse(region, now, inbound=inbound, tone=tone)
        self.regions[region].energy = 1.0
        self.core_energy = min(1.0, self.core_energy + 0.5)

    def _pulse(self, region: str, now: float, *, inbound: bool, tone: str) -> None:
        self.pulses.append(Pulse(region, now, inbound, tone))
        if region in self.regions:
            self.regions[region].energy = 1.0

    def set_activity(self, activity: str) -> None:
        self.activity = str(activity or "IDLE")

    # ------------------------------------------------------------ câmera
    def focus_region(self, key: str | None) -> None:
        """None = visão geral; ``CORE_KEY`` = câmara central; senão, a região."""
        self.focus = key
        if key is None:
            self.camera.target_x, self.camera.target_y, self.camera.target_zoom = 0.0, 0.0, 1.0
            return
        if key == CORE_KEY:
            x, y, zoom = 0.0, 0.0, 1.55
        else:
            region = self.regions[key]
            (x, y), zoom = region.pos, 1.9 if key not in SATELLITES else 2.3
        self.camera.target_x, self.camera.target_y, self.camera.target_zoom = x, y, zoom

    # ------------------------------------------------------------ tempo
    def step(self, dt: float) -> None:
        dt = max(0.0, min(0.1, dt))
        self.camera.step(dt)
        self.camera.orbit = (self.camera.orbit + dt * (0.05 + 0.10 * self.activity_level())) % math.tau
        for particle in self.particles:
            particle.angle = (particle.angle + particle.speed * dt) % math.tau
            particle.radius -= 6.0 * dt * (1 + self.activity_level())
            if particle.radius < 40:                         # chegou à câmara: renasce na borda
                particle.radius = self._rng.uniform(560, 740)
        decay = math.exp(-dt / 1.6)
        self.core_energy *= decay
        for region in self.regions.values():
            region.energy *= decay
        now = self.clock()
        while self.pulses and now - self.pulses[0].born > self.pulses[0].duration:
            self.pulses.popleft()

    def activity_level(self) -> float:
        return palette.state_glow(self.activity)

    def in_motion(self) -> bool:
        """Movimento que pede o teto de quadros (o giro lento e as partículas cabem na cadência econômica)."""
        return (self.camera.moving() or bool(self.pulses) or self.core_energy > 0.05
                or any(r.energy > 0.05 for r in self.regions.values()))

    # ------------------------------------------------------------ geometria e toque
    def world_to_screen(self, x: float, y: float, w: float, h: float, *, parallax: float = 1.0) -> tuple[float, float]:
        cam = self.camera
        scale = self.fit(w, h) * (1 + (cam.zoom - 1) * parallax)
        cx = (w * (1 - self.panel_fraction)) / 2
        return cx + (x - cam.x * parallax) * scale, h / 2 + (y - cam.y * parallax) * scale

    def fit(self, w: float, h: float) -> float:
        usable = w * (1 - self.panel_fraction * 0.6)
        return max(0.2, min(usable / WORLD_W, h / WORLD_H))

    def screen_scale(self, w: float, h: float, parallax: float = 1.0) -> float:
        return self.fit(w, h) * (1 + (self.camera.zoom - 1) * parallax)

    def hit(self, sx: float, sy: float, w: float, h: float) -> str | None:
        """Região sob o ponto da tela (câmara central incluída)."""
        scale = self.screen_scale(w, h)
        best, best_d = None, 1e9
        for region in self.regions.values():
            px, py = self.world_to_screen(*region.pos, w, h)
            radius = 92 * region.scale * scale
            d = math.hypot((sx - px) / 1.0, (sy - py) / 0.62)
            if d <= radius and d < best_d:
                best, best_d = region.key, d
        if best is None:
            cx, cy = self.world_to_screen(0.0, 0.0, w, h)
            if math.hypot(sx - cx, (sy - cy) / 0.8) <= 150 * scale:
                return CORE_KEY
        return best

    def item_at(self, sx: float, sy: float, w: float, h: float) -> dict | None:
        """Registro (ponto de um portal) sob o cursor — para a dica com o título real."""
        scale = self.screen_scale(w, h)
        for region in self.regions.values():
            for i, item in enumerate(region.items):
                ix, iy = self.item_position(region, i, w, h)
                if math.hypot(sx - ix, sy - iy) <= max(5.0, 6.0 * scale):
                    return {**item, "region": region.key}
        return None

    def item_position(self, region: Region, index: int, w: float, h: float) -> tuple[float, float]:
        """Itens orbitam o portal em elipse (posição estável por índice, giro lento)."""
        count = max(1, len(region.items))
        angle = self.camera.orbit * 0.6 + index * math.tau / count
        rx, ry = 118 * region.scale, 70 * region.scale
        x = region.pos[0] + rx * math.cos(angle)
        y = region.pos[1] + ry * math.sin(angle)
        return self.world_to_screen(x, y, w, h)
