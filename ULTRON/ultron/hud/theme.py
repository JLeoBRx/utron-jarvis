"""Identidade visual do ULTRON NEURAL HUB: preto, grafite escuro, ouro metálico, âmbar e
branco quente. Fontes com alternativas (Bahnschrift/Segoe UI no Windows)."""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6 import QtCore, QtGui

BLACK = QtGui.QColor(4, 4, 5)
GRAPHITE = QtGui.QColor(18, 17, 16)
GRAPHITE_LIGHT = QtGui.QColor(38, 35, 31)
GOLD = QtGui.QColor(214, 162, 66)
GOLD_DIM = QtGui.QColor(150, 112, 46)
AMBER = QtGui.QColor(236, 132, 38)
WARM_WHITE = QtGui.QColor(255, 240, 214)
TEXT = QtGui.QColor(232, 222, 204)
TEXT_DIM = QtGui.QColor(150, 140, 124)

TONES = {"gold": GOLD, "amber": AMBER, "white": WARM_WHITE, "dim": GOLD_DIM}

DISPLAY_FAMILIES = ["Bahnschrift", "Segoe UI", "DejaVu Sans", "Sans Serif"]
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Monospace"]


def color(tone: str, alpha: float = 1.0) -> QtGui.QColor:
    c = QtGui.QColor(TONES.get(tone, GOLD))
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def with_alpha(c: QtGui.QColor, alpha: float) -> QtGui.QColor:
    out = QtGui.QColor(c)
    out.setAlphaF(max(0.0, min(1.0, alpha)))
    return out


@lru_cache(maxsize=32)
def font(size: float, *, weight: int = 400, spacing: float = 0.0, mono: bool = False) -> QtGui.QFont:
    f = QtGui.QFont()
    f.setFamilies(MONO_FAMILIES if mono else DISPLAY_FAMILIES)
    f.setPointSizeF(size)
    f.setWeight(QtGui.QFont.Weight(weight))
    if spacing:
        f.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, spacing)
    f.setHintingPreference(QtGui.QFont.PreferNoHinting)
    return f


@lru_cache(maxsize=64)
def glow_sprite(tone: str, size: int = 64, hardness: float = 0.18) -> QtGui.QPixmap:
    """Brilho radial pré-renderizado (desenhado com composição aditiva)."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    grad = QtGui.QRadialGradient(size / 2, size / 2, size / 2)
    base = TONES.get(tone, GOLD)
    core = QtGui.QColor(WARM_WHITE) if tone != "amber" else QtGui.QColor(255, 200, 140)
    grad.setColorAt(0.0, with_alpha(core, 1.0))
    grad.setColorAt(hardness, with_alpha(base, 0.85))
    grad.setColorAt(0.45, with_alpha(base, 0.25))
    grad.setColorAt(1.0, with_alpha(base, 0.0))
    p.setBrush(grad)
    p.setPen(QtCore.Qt.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.end()
    return pix


@lru_cache(maxsize=8)
def soft_sprite(tone: str, size: int = 128) -> QtGui.QPixmap:
    """Halo largo e suave (regiões ativas, auréola do cérebro)."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    grad = QtGui.QRadialGradient(size / 2, size / 2, size / 2)
    base = TONES.get(tone, GOLD)
    grad.setColorAt(0.0, with_alpha(base, 0.55))
    grad.setColorAt(0.35, with_alpha(base, 0.22))
    grad.setColorAt(1.0, with_alpha(base, 0.0))
    p.setBrush(grad)
    p.setPen(QtCore.Qt.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.end()
    return pix


STYLESHEET = """
QWidget#HudInput { background: transparent; }
QLineEdit#HudLine {
    background: rgba(14, 13, 12, 210); color: #f0e6d2; border: 1px solid rgba(214, 162, 66, 70);
    border-radius: 3px; padding: 8px 12px; selection-background-color: rgba(214, 162, 66, 120);
    font-size: 11pt;
}
QLineEdit#HudLine:focus { border: 1px solid rgba(214, 162, 66, 160); }
QPushButton#HudButton {
    background: rgba(14, 13, 12, 210); color: #d6a242; border: 1px solid rgba(214, 162, 66, 80);
    border-radius: 3px; padding: 7px 12px; font-size: 9pt; letter-spacing: 2px;
}
QPushButton#HudButton:hover { border: 1px solid rgba(214, 162, 66, 190); color: #ffe6b8; }
QPushButton#HudButton:checked { background: rgba(214, 162, 66, 40); }
QPushButton#HudPrimary {
    background: rgba(214, 162, 66, 50); color: #fff0d6; border: 1px solid rgba(214, 162, 66, 200);
    border-radius: 3px; padding: 7px 16px; font-size: 9pt; letter-spacing: 2px;
}
QPushButton#HudPrimary:hover { background: rgba(214, 162, 66, 90); }
QLabel#HudLabel { color: #e8decc; font-size: 10pt; }
QMenu { background: #121110; color: #e8decc; border: 1px solid rgba(214,162,66,90); }
QMenu::item:selected { background: rgba(214,162,66,60); }
"""


@lru_cache(maxsize=640)
def sprite_px(kind: str, tone: str, radius: int, dpr: float = 1.0) -> QtGui.QPixmap:
    """Sprite já no tamanho final em pixels (desenho sem escala = caminho rápido do QPainter)."""
    radius = max(1, int(radius))
    size = max(2, int(round(2 * radius * dpr)))
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    grad = QtGui.QRadialGradient(size / 2, size / 2, size / 2)
    base = TONES.get(tone, GOLD)
    if kind == "glow":
        core = QtGui.QColor(WARM_WHITE) if tone != "amber" else QtGui.QColor(255, 200, 140)
        grad.setColorAt(0.0, with_alpha(core, 1.0))
        grad.setColorAt(0.18, with_alpha(base, 0.85))
        grad.setColorAt(0.45, with_alpha(base, 0.25))
        grad.setColorAt(1.0, with_alpha(base, 0.0))
    else:                                                    # "soft": halo largo
        grad.setColorAt(0.0, with_alpha(base, 0.55))
        grad.setColorAt(0.35, with_alpha(base, 0.22))
        grad.setColorAt(1.0, with_alpha(base, 0.0))
    p.setBrush(grad)
    p.setPen(QtCore.Qt.NoPen)
    p.drawEllipse(0, 0, size, size)
    p.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def quantize_radius(radius_px: float) -> int:
    """Raios pequenos em passos de 1 px; grandes em passos maiores (menos sprites em cache)."""
    if radius_px <= 24:
        return max(1, int(round(radius_px)))
    if radius_px <= 96:
        return int(round(radius_px / 4.0) * 4)
    return int(round(radius_px / 24.0) * 24)


@lru_cache(maxsize=1024)
def dot_px(rgb: tuple[int, int, int], radius: float, qx: int, qy: int, dpr: float = 1.0) -> QtGui.QPixmap:
    """Nó da malha pré-renderizado, com o centro deslocado em quartos de pixel (``qx``, ``qy``):
    desenhado em coordenadas inteiras, o movimento continua suave (subpixel) e barato."""
    size = dot_size(radius)
    pix = QtGui.QPixmap(max(1, int(round(size * dpr))), max(1, int(round(size * dpr))))
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    cx, cy = (size / 2 + qx / 4.0) * dpr, (size / 2 + qy / 4.0) * dpr
    outer = (radius + 0.9) * dpr
    grad = QtGui.QRadialGradient(cx, cy, outer)
    c = QtGui.QColor(*rgb)
    grad.setColorAt(0.0, with_alpha(c, 1.0))
    grad.setColorAt(radius / (radius + 0.9), with_alpha(c, 0.92))
    grad.setColorAt(1.0, with_alpha(c, 0.0))
    p.setBrush(grad)
    p.setPen(QtCore.Qt.NoPen)
    p.drawEllipse(QtCore.QPointF(cx, cy), outer, outer)
    p.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def dot_size(radius: float) -> int:
    """Lado (px lógicos, par) do sprite de um nó de raio ``radius``."""
    return 2 * int(math.ceil(radius + 1.4))
