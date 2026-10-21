"""Geometria da cabeça holográfica — NumPy puro (testável sem Qt).

A cabeça é uma superfície em coordenadas cilíndricas: para cada ângulo θ (0 = frente) e altura y,
``radius(θ, y)`` esculpe crânio, têmporas, órbitas, maçãs, nariz, lábios e queixo. Dela saem:

* a malha: contornos horizontais (linhas de varredura) e meridianos;
* placas e costuras (testa, laterais, mandíbula) e linhas de relevo (nariz, sulcos, queixo);
* orelhas (anéis), pescoço e colar com o reator — o DNA do avatar original;
* as normais em repouso (calculadas uma vez; por quadro só giram com a cabeça e, quando a boca
  abre, só a parte de baixo é recalculada).

``jaw_transform`` gira a mandíbula em torno da articulação: a malha inferior acompanha a boca.
A densidade da malha vem do perfil de qualidade (mais linhas no Alto/Cinematográfico).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Y_EYE, Y_BROW, Y_NOSE, Y_MOUTH, Y_CHIN = -0.02, 0.15, -0.36, -0.60, -1.04
EYE_THETA = 0.36                         # ângulo do centro de cada olho
HINGE_Y, HINGE_Z = -0.22, -0.05          # articulação da mandíbula
LIGHT = np.array([-0.40, 0.50, 0.77]) / np.linalg.norm([-0.40, 0.50, 0.77])


def _g(x, mu, s):
    return np.exp(-((x - mu) / s) ** 2)


def radius(theta, y):
    """Raio da cabeça no ângulo ``theta`` (rad, 0 = frente) e altura ``y`` (−1,04 queixo … 1 topo)."""
    c, s = np.cos(theta), np.sin(theta)
    u = np.clip((y + 0.05) / 1.05, 0, 1)
    cranium = (1 - u ** 2.6) ** (1 / 2.6)
    d = np.clip((-0.05 - y) / 1.0, 0, 1)
    jaw = 1 - 0.40 * d ** 1.4 - 0.25 * np.clip((d - 0.75) / 0.25, 0, 1) ** 2
    profile = np.where(y >= -0.05, cranium, jaw)
    n = 2.6
    section = 1.0 / (np.abs(c / 0.94) ** n + np.abs(s / 0.78) ** n) ** (1 / n)
    r = 0.80 * profile * section
    front = np.clip(c, 0, 1)
    f3 = front ** 3
    r = r * (1 - 0.07 * f3 * _g(y, -0.2, 0.6))
    r += 0.055 * f3 * _g(y, Y_BROW, 0.05) * _g(theta, 0, 0.55)                 # arco das sobrancelhas
    for side in (-1, 1):
        r -= 0.085 * _g(theta, side * EYE_THETA, 0.14) * _g(y, Y_EYE, 0.075)    # órbitas
        r += 0.045 * _g(theta, side * 0.63, 0.15) * _g(y, -0.20, 0.11)          # maçãs
        r -= 0.035 * _g(theta, side * 0.52, 0.12) * _g(y, -0.48, 0.12)          # bochechas
    k = np.clip((Y_BROW - 0.03 - y) / (Y_BROW - 0.03 - Y_NOSE), 0, 1)
    nose = 0.17 * k ** 1.1 * (y > Y_NOSE - 0.05) * _g(y, Y_NOSE + 0.02, 0.6)
    nose = np.where(y < Y_NOSE, 0.17 * _g(y, Y_NOSE, 0.05), nose)
    r += nose * _g(theta, 0, 0.065 + 0.05 * k)
    r += 0.030 * _g(theta, 0, 0.32) * _g(y, Y_MOUTH, 0.07)                       # lábios
    r += 0.045 * _g(theta, 0, 0.26) * _g(y, -0.90, 0.10)                         # queixo
    return r


def surface(theta, y):
    theta = np.asarray(theta, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    r = radius(theta, y)
    return np.stack([r * np.sin(theta), y * np.ones_like(theta), r * np.cos(theta)], axis=-1)


def theta_samples(n_front: int = 44, n_back: int = 26) -> np.ndarray:
    """Ângulos mais densos na frente (relevo do rosto) e esparsos atrás."""
    front = np.linspace(-1.25, 1.25, n_front)
    back = np.linspace(1.25, 2 * math.pi - 1.25, n_back + 2)[1:-1]
    back = np.where(back > math.pi, back - 2 * math.pi, back)
    return np.sort(np.concatenate([front, back]))


def rotation(yaw: float, pitch: float, roll: float) -> np.ndarray:
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    rz = np.array([[cr, -sr, 0], [sr, cr, 0], [0, 0, 1]])
    return rz @ rx @ ry


def jaw_transform(points: np.ndarray, opening: float) -> np.ndarray:
    """A mandíbula gira em torno da articulação; só a parte abaixo da boca acompanha (com falloff)."""
    if opening <= 1e-4:
        return points
    weight = np.clip((Y_MOUTH + 0.01 - points[..., 1]) / 0.10, 0, 1)
    side = np.clip(1 - (np.abs(points[..., 0]) - 0.45) / 0.25, 0, 1)
    angle = 0.20 * opening * weight * side
    y0 = points[..., 1] - HINGE_Y
    z0 = points[..., 2] - HINGE_Z
    ca, sa = np.cos(angle), np.sin(angle)
    out = points.copy()
    out[..., 1] = HINGE_Y + y0 * ca - z0 * sa
    out[..., 2] = HINGE_Z + y0 * sa + z0 * ca
    return out


def normals(grid: np.ndarray) -> np.ndarray:
    """Normais por ponto de uma grade (linhas × colunas × 3), apontando para fora."""
    dth = np.gradient(grid, axis=1)                  # ao longo de θ (para a direita na frente)
    dy = np.gradient(grid, axis=0)                   # para cima
    n = np.cross(dth, dy)                            # θ × y aponta para fora da cabeça
    return n / (np.linalg.norm(n, axis=-1, keepdims=True) + 1e-9)


def pad_rows(lines: list[np.ndarray]) -> np.ndarray:
    """Várias polilinhas de tamanhos diferentes → uma matriz (linhas × pontos × 3) com NaN no fim."""
    size = max(len(line) for line in lines)
    out = np.full((len(lines), size, 3), np.nan)
    for i, line in enumerate(lines):
        out[i, :len(line)] = line
    return out


class RadiusTable:
    """r(θ, y) tabelado: olhos, lábios e sobrancelhas seguem a superfície sem recalcular a escultura."""

    def __init__(self, nt: int = 1440, ny: int = 440):
        self.t0, self.t1 = -math.pi, math.pi
        self.y0, self.y1 = -1.15, 1.06
        theta = np.linspace(self.t0, self.t1, nt)
        ys = np.linspace(self.y0, self.y1, ny)
        T, Y = np.meshgrid(theta, ys)
        self.r = radius(T, Y).astype(np.float32)
        self.nt, self.ny = nt, ny

    def surface(self, theta, y) -> np.ndarray:
        theta = np.asarray(theta, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64) * np.ones_like(theta)
        fx = (theta - self.t0) / (self.t1 - self.t0) * (self.nt - 1)
        fy = (y - self.y0) / (self.y1 - self.y0) * (self.ny - 1)
        ix = np.clip(fx.astype(int), 0, self.nt - 2)
        iy = np.clip(fy.astype(int), 0, self.ny - 2)
        ax, ay = fx - ix, fy - iy
        r = (self.r[iy, ix] * (1 - ax) * (1 - ay) + self.r[iy, ix + 1] * ax * (1 - ay)
             + self.r[iy + 1, ix] * (1 - ax) * ay + self.r[iy + 1, ix + 1] * ax * ay)
        return np.stack([r * np.sin(theta), y, r * np.cos(theta)], axis=-1)


def accent_lines() -> list[np.ndarray]:
    """Linhas de relevo (θ, y): dorso e asas do nariz, filtro, maçãs, sulcos e queixo."""
    specs = []
    for side in (-1, 1):
        t = np.linspace(0, 1, 12)
        specs.append((side * (0.10 - 0.02 * t), Y_BROW - 0.05 - t * (Y_BROW - 0.05 - Y_NOSE - 0.02), 0.012))
        a = np.linspace(0, math.pi * 0.9, 10)
        specs.append((side * (0.065 + 0.05 * np.sin(a)), Y_NOSE - 0.02 + 0.04 * np.cos(a) - 0.02, 0.01))
        t = np.linspace(0, 1, 6)
        specs.append((side * (0.035 + 0.008 * t), Y_NOSE - 0.075 - t * 0.12, 0.006))
        t = np.linspace(0, 1, 14)
        specs.append((side * (0.50 + 0.14 * t - 0.10 * t ** 2), -0.10 - t * 0.38, 0.004))
        t = np.linspace(0, 1, 10)
        specs.append((side * (0.20 + 0.06 * t), Y_MOUTH - 0.02 - t * 0.10, 0.004))
    t = np.linspace(-1, 1, 14)
    specs.append((t * 0.12, -0.84 - 0.02 * (1 - t ** 2), 0.006))
    out = []
    for theta, y, lift in specs:
        theta = np.asarray(theta, dtype=float) * np.ones_like(np.asarray(y, dtype=float))
        points = surface(theta, np.asarray(y, dtype=float) * np.ones_like(theta))
        points[..., 2] += lift
        out.append(points)
    return out


@dataclass(frozen=True)
class Density:
    rows: int
    front: int
    back: int
    meridian_step: int


DENSITY = {"economy": Density(26, 32, 18, 4), "balanced": Density(40, 44, 26, 3),
           "high": Density(48, 52, 30, 3), "cinematic": Density(56, 60, 34, 2)}


class FaceGeometry:
    """Tudo o que é fixo na cabeça (em repouso), calculado uma vez por densidade."""

    def __init__(self, density: Density = DENSITY["balanced"]):
        self.density = density
        self.theta = theta_samples(density.front, density.back)
        self.levels = np.linspace(Y_CHIN + 0.02, 1.0, density.rows)
        T, Y = np.meshgrid(self.theta, self.levels)
        self.grid = surface(T, Y)                                   # (linhas, colunas, 3)
        self.rest_normals = normals(self.grid)
        self.lower_rows = np.where(self.levels < Y_MOUTH + 0.12)[0]  # o que a mandíbula move
        self.meridians = [i for i in range(len(self.theta)) if i % density.meridian_step == 0]
        self.eye_angles = np.linspace(0, 2 * math.pi, 36)
        # placas e costuras
        tt = np.linspace(-0.95, 0.95, 30)
        top = surface(tt, 0.46 + 0.05 * np.cos(tt * 1.6))
        side_y = np.linspace(0.46, -0.66, 18)
        inset = 0.95 - 0.10 * np.clip((0.0 - side_y) / 0.66, 0, 1)
        right = surface(inset, side_y)
        left = surface(-inset, side_y)
        jt = np.linspace(0.85, -0.85, 28)
        jaw_line = surface(jt, -0.66 - 0.36 * (1 - (jt / 0.85) ** 2) ** 1.2)
        yy = np.linspace(0.46, 0.98, 12)
        forehead = surface(np.zeros_like(yy), yy)
        self.lines = pad_rows([top, right, left, jaw_line, forehead, *accent_lines()])
        # orelhas: três anéis por lado
        ears = []
        for side in (-1, 1):
            for ring in (0.17, 0.12, 0.07):
                a = np.linspace(0, 2 * math.pi, 28)
                x = np.full_like(a, side * (0.78 * 0.98 + 0.03))
                ears.append(np.stack([x, -0.02 + ring * np.sin(a), -0.05 + ring * np.cos(a)], -1))
        self.ears = pad_rows(ears)
        # pescoço e colar
        lower = []
        for y in np.linspace(-0.95, -1.55, 6):
            a = np.linspace(-math.pi, math.pi, 40)
            r = 0.30 + 0.06 * np.clip((-1.25 - y) / 0.3, 0, 1)
            lower.append(np.stack([r * np.sin(a), np.full_like(a, y), -0.12 + r * 0.85 * np.cos(a)], -1))
        a = np.linspace(-math.pi, math.pi, 64)
        for rc, yc in ((0.62, -1.58), (0.78, -1.66), (0.95, -1.74)):
            lower.append(np.stack([rc * np.sin(a), np.full_like(a, yc), -0.12 + rc * 0.62 * np.cos(a)], -1))
        self.lower = pad_rows(lower)
        self.reactor = np.array([[0.0, -1.50, 0.40]])

    def posed_grid(self, jaw: float) -> tuple[np.ndarray, np.ndarray]:
        """Malha e normais com a mandíbula aberta (só as linhas de baixo são recalculadas)."""
        if jaw <= 1e-4:
            return self.grid, self.rest_normals
        grid = jaw_transform(self.grid, jaw)
        normal = self.rest_normals.copy()
        rows = self.lower_rows
        if len(rows):
            lo = max(0, rows[0] - 1)
            hi = min(len(self.levels), rows[-1] + 2)
            normal[lo:hi] = normals(grid[lo:hi])
        return grid, normal
