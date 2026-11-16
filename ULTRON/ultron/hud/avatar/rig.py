"""Parâmetros de expressão do avatar (o "esqueleto") e suavização.

O animador escreve aqui a cada quadro; o renderizador só lê. Nada aqui inventa estado: os valores
vêm do estado resolvido (sinais reais), da trilha labial (áudio real) e dos níveis de áudio reais.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Rig:
    # cabeça
    yaw: float = 0.0
    pitch: float = -0.12
    roll: float = 0.0
    offset_x: float = 0.0              # deslocamento horizontal ("falha" de projeção no erro)
    # boca (trilha labial)
    jaw: float = 0.0                   # abertura 0..1
    wide: float = 0.0                  # largura −1..1
    round: float = 0.0                 # arredondamento 0..1
    press: float = 0.15                # pressão dos lábios 0..1
    teeth: float = 0.0
    energy: float = 0.0                # energia real da fala agora
    # olhos e sobrancelhas
    blink: float = 1.0                 # 1 = fechados (o boot começa de olhos fechados)
    eye_open: float = 1.0
    brow: float = 0.0
    gaze_x: float = 0.0
    gaze_y: float = 0.0
    # luz e cor
    glow: float = 0.7
    rgb: tuple = (0.0, 217.0, 255.0)
    iris: tuple = (103.0, 243.0, 255.0)
    alert: float = 0.0                 # tinta âmbar de alerta (0..1)
    visor: float = 0.0                 # viseira de privacidade (0..1)
    glitch: float = 0.0
    # ambiente
    assemble: float = 0.0              # montagem do rosto no boot (1 = completo)
    pulse: float = 0.0                 # pulso de conexão de um componente
    dim: float = 0.0                   # perda de conexão (escurece um instante)
    scan_speed: float = 0.6
    ring_speed: float = 0.35
    particles: float = 0.5
    mic_level: float = 0.0             # halo de escuta (nível real do microfone)
    out_level: float = 0.0             # anéis de fala (nível real da saída)
    extra: dict = field(default_factory=dict)


def approach(current: float, target: float, rate: float, dt: float) -> float:
    """Aproximação exponencial (independente da taxa de quadros)."""
    if dt <= 0:
        return current
    return current + (target - current) * (1.0 - math.exp(-rate * dt))


def approach_rgb(current: tuple, target: tuple, rate: float, dt: float) -> tuple:
    return tuple(approach(c, t, rate, dt) for c, t in zip(current, target))


def mix(a: tuple, b: tuple, t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    return tuple(x + (y - x) * t for x, y in zip(a, b))
