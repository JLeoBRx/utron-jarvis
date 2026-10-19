"""Perfis de qualidade dos HUBs: ``economy`` (Econômico) · ``balanced`` (Equilibrado) ·
``high`` (Alto) · ``cinematic`` (Cinematográfico).

Um perfil muda apenas o CUSTO VISUAL e a cadência de leituras da interface. Memória,
execução, verificação, autorização, lembretes e segurança funcionam igual em todos.

Por que isso importa: o desenho do QPainter no PySide6 não libera o GIL. Cada milissegundo
gasto pintando é um milissegundo em que as threads do núcleo (IA, percepção, memória,
áudio) não executam Python. O ritmo de quadros é adaptativo: a cena só é redesenhada no
teto do perfil enquanto há movimento real (sinais, câmera, módulos, inicialização); em
repouso — apenas o giro lento — cai para ``idle_fps``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

NAMES = ("economy", "balanced", "high", "cinematic")
LABELS = {"economy": "Econômico", "balanced": "Equilibrado", "high": "Alto", "cinematic": "Cinematográfico"}
LEGACY = {"performance": "economy"}           # nome usado pelo ULTRON
DEFAULT = "balanced"


@dataclass(frozen=True)
class RenderProfile:
    name: str
    max_fps: int                 # teto com atividade visível (limitado também por ``hud_fps``)
    geometry_fps: int            # cadência máxima de redesenho da malha girando (sinais seguem no teto)
    idle_fps: int                # repouso: só o giro lento e a respiração
    hidden_interval_ms: int      # relógio da cena com o HUB oculto (sem desenho)
    max_particles: int
    max_pulses: int
    active_edges: int            # sinapses ativadas do grafo desenhadas por quadro (as mais intensas)
    curve_steps: int             # segmentos por sinapse ativada
    front_glow: bool             # cintilação dos nós mais próximos
    strong_glow: int             # nós fortes do grafo com brilho permanente (0 = desligado)
    mesh_points: int             # teto de pontos da malha desenhados (o grafo real não muda)
    region_lines: bool           # a região ativa acende suas sinapses
    depth_levels: int            # camadas de profundidade desenhadas (5 = todas; a mais funda é quase invisível)
    telemetry_ms: int            # leitura de níveis de áudio e filas
    state_ms: int                # leitura do estado central (só quando mudou)

    def to_dict(self) -> dict:
        return asdict(self)


PROFILES: dict[str, RenderProfile] = {
    "economy": RenderProfile("economy", max_fps=30, geometry_fps=15, idle_fps=12, hidden_interval_ms=500,
                             max_particles=70, max_pulses=14, active_edges=30, curve_steps=3,
                             front_glow=False, strong_glow=0, mesh_points=420, region_lines=False,
                             depth_levels=3, telemetry_ms=120, state_ms=200),
    "balanced": RenderProfile("balanced", max_fps=60, geometry_fps=30, idle_fps=24, hidden_interval_ms=300,
                              max_particles=120, max_pulses=28, active_edges=60, curve_steps=4,
                              front_glow=True, strong_glow=32, mesh_points=640, region_lines=True,
                              depth_levels=4, telemetry_ms=80, state_ms=110),
    "high": RenderProfile("high", max_fps=90, geometry_fps=60, idle_fps=30, hidden_interval_ms=280,
                          max_particles=190, max_pulses=34, active_edges=110, curve_steps=5,
                          front_glow=True, strong_glow=40, mesh_points=640, region_lines=True,
                          depth_levels=5, telemetry_ms=70, state_ms=100),
    "cinematic": RenderProfile("cinematic", max_fps=144, geometry_fps=144, idle_fps=60, hidden_interval_ms=250,
                               max_particles=260, max_pulses=40, active_edges=160, curve_steps=6,
                               front_glow=True, strong_glow=48, mesh_points=640, region_lines=True,
                               depth_levels=5, telemetry_ms=60, state_ms=90),
}


def get(name: str | None) -> RenderProfile:
    key = str(name or DEFAULT)
    return PROFILES.get(LEGACY.get(key, key), PROFILES[DEFAULT])


def effective_fps(profile: RenderProfile, hud_fps: int, *, active: bool) -> int:
    """Quadros por segundo efetivos: o perfil nunca passa do limite configurado pelo usuário."""
    cap = max(10, int(hud_fps or 60))
    return max(5, min(cap, profile.max_fps if active else profile.idle_fps))
