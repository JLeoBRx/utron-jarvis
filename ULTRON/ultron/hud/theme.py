"""Sistema de tema do JARVIS — azul profundo e ciano. FONTE ÚNICA de cores e estilos.

Paleta (especificação):

    preto espacial #030712 · azul quase preto #071426 · azul profundo #0B1F3A
    azul tecnológico #075985 · ciano #00D9FF · ciano luminoso #67F3FF
    azul elétrico #168BFF · branco azulado #DCEEFF

Semântica: o CIANO é atividade, percepção e circulação de dados; o AZUL PROFUNDO é repouso,
memória e profundidade; o azul elétrico marca execução e conexões de planejamento. Aviso usa
um âmbar suave e erro um coral — identificáveis, sem piscar nem alarmar.

Nenhum outro módulo define cores próprias: HUB principal, orbe, painéis e o TARDIS leem
daqui (tokens, tons de partícula, cores por estado e folhas de estilo).
"""
from __future__ import annotations

import math
from functools import lru_cache

from PySide6 import QtCore, QtGui

from . import palette

NAME, HEX, STATE, TONE_HEX = palette.NAME, palette.HEX, palette.STATE, palette.TONE_HEX
state_glow, state_label = palette.state_glow, palette.state_label

BG = QtGui.QColor(HEX["space"])              # fundo
BG2 = QtGui.QColor(HEX["abyss"])             # camadas e painéis
PANEL = QtGui.QColor(HEX["deep"])            # superfícies, trilhos, repouso
PRIMARY_DIM = QtGui.QColor(HEX["tech"])      # contornos, estados apagados
PRIMARY = QtGui.QColor(HEX["cyan"])          # atividade, percepção, dados
GLOW = QtGui.QColor(HEX["glow"])             # brilho, destaque luminoso
ELECTRIC = QtGui.QColor(HEX["electric"])     # execução, planejamento, memória
TEXT = QtGui.QColor(HEX["ice"])
TEXT_BRIGHT = QtGui.QColor(240, 250, 255)
TEXT_DIM = QtGui.QColor(HEX["dim_text"])
ALERT = QtGui.QColor(HEX["alert"])           # aviso / autorização pendente
ERROR = QtGui.QColor(HEX["error"])           # falha real
CYAN = PRIMARY

# Aliases da identidade anterior (mantidos para código externo/plugins): já apontam para o azul.
BLACK, GRAPHITE, GRAPHITE_LIGHT = BG, BG2, PANEL
GOLD, GOLD_DIM, AMBER, WARM_WHITE = PRIMARY, PRIMARY_DIM, ALERT, TEXT_BRIGHT

# Tons das partículas, pulsos e nós ("gold"/"amber"/"white" = nomes antigos, mesmas cores novas).
TONES = {tone: QtGui.QColor(value) for tone, value in TONE_HEX.items()}

# Estado de atividade (contrato do núcleo) → (cor principal, intensidade do halo 0..1, descrição do efeito)
STATE_STYLE = {state: (QtGui.QColor(hex_), glow, effect) for state, (hex_, glow, effect) in STATE.items()}


def state_color(activity: str) -> QtGui.QColor:
    return QtGui.QColor(STATE_STYLE.get(str(activity or "IDLE"), STATE_STYLE["IDLE"])[0])


DISPLAY_FAMILIES = ["Bahnschrift", "Segoe UI", "DejaVu Sans", "Sans Serif"]
MONO_FAMILIES = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Monospace"]


def color(tone: str, alpha: float = 1.0) -> QtGui.QColor:
    c = QtGui.QColor(TONES.get(tone, PRIMARY))
    c.setAlphaF(max(0.0, min(1.0, alpha)))
    return c


def with_alpha(c: QtGui.QColor, alpha: float) -> QtGui.QColor:
    out = QtGui.QColor(c)
    out.setAlphaF(max(0.0, min(1.0, alpha)))
    return out


def mix(a: QtGui.QColor, b: QtGui.QColor, t: float) -> QtGui.QColor:
    """Transição suave entre dois tons (0 = a, 1 = b)."""
    t = max(0.0, min(1.0, t))
    return QtGui.QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                        int(a.blue() + (b.blue() - a.blue()) * t))


def _core_of(tone: str) -> QtGui.QColor:
    """Centro do brilho: quase branco-azulado; aviso e erro mantêm o próprio matiz."""
    if tone in ("alert", "amber"):
        return QtGui.QColor(255, 226, 170)
    if tone == "error":
        return QtGui.QColor(255, 196, 204)
    return QtGui.QColor(TEXT_BRIGHT)


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
    base = TONES.get(tone, PRIMARY)
    core = _core_of(tone)
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
    base = TONES.get(tone, PRIMARY)
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
    background: rgba(7, 20, 38, 215); color: #DCEEFF; border: 1px solid rgba(0, 217, 255, 70);
    border-radius: 4px; padding: 8px 12px; selection-background-color: rgba(0, 217, 255, 110);
    font-size: 11pt;
}
QLineEdit#HudLine:focus { border: 1px solid rgba(0, 217, 255, 170); }
QPushButton#HudButton {
    background: rgba(7, 20, 38, 215); color: #67F3FF; border: 1px solid rgba(0, 217, 255, 80);
    border-radius: 4px; padding: 7px 12px; font-size: 9pt; letter-spacing: 2px;
}
QPushButton#HudButton:hover { border: 1px solid rgba(0, 217, 255, 190); color: #E6FBFF; }
QPushButton#HudButton:checked { background: rgba(0, 217, 255, 38); }
QPushButton#HudButton:disabled { color: #3D5873; border-color: rgba(7, 89, 133, 90); }
QPushButton#HudPrimary {
    background: rgba(0, 217, 255, 46); color: #F0FAFF; border: 1px solid rgba(0, 217, 255, 200);
    border-radius: 4px; padding: 7px 16px; font-size: 9pt; letter-spacing: 2px;
}
QPushButton#HudPrimary:hover { background: rgba(0, 217, 255, 82); }
QPushButton#HudPrimary:disabled { color: #5B7B97; background: rgba(7, 89, 133, 40); border-color: rgba(7, 89, 133, 90); }
QLabel#HudLabel { color: #DCEEFF; font-size: 10pt; }
QMenu { background: #071426; color: #DCEEFF; border: 1px solid rgba(0, 217, 255, 90); }
QMenu::item:selected { background: rgba(0, 217, 255, 55); }
QToolTip { background: #0B1F3A; color: #DCEEFF; border: 1px solid rgba(0, 217, 255, 120); }
"""

# Painéis (diagnóstico de voz, rede, painel de memória do TARDIS, diálogos): mesma paleta.
PANEL_STYLESHEET = """
QDialog, QWidget#Panel, QWidget#Hub2 { background: #071426; color: #DCEEFF; }
QWidget#Panel QLabel, QDialog QLabel, QWidget#Hub2 QLabel { color: #DCEEFF; }
QLabel#PanelTitle, QLabel#H2Title { color: #00D9FF; font-size: 10pt; letter-spacing: 3px; }
QLabel#PanelDim, QLabel#H2Dim { color: #7F9BB7; font-size: 9pt; }
QLabel#PanelPrompt, QLabel#H2Answer { color: #E6FBFF; background: rgba(0, 217, 255, 18);
    border-left: 2px solid #00D9FF; padding: 8px; }
QLabel#H2Big { color: #F0FAFF; font-size: 13pt; }
QListWidget#H2Nav { background: #030712; border: none; border-right: 1px solid rgba(0, 217, 255, 40);
    color: #9FB9D3; font-size: 9pt; outline: none; }
QListWidget#H2Nav::item { padding: 11px 14px; letter-spacing: 2px; }
QListWidget#H2Nav::item:selected { background: rgba(0, 217, 255, 30); color: #E6FBFF; border-left: 2px solid #00D9FF; }
QFrame#H2Card { background: #0B1F3A; border: 1px solid rgba(0, 217, 255, 38); border-radius: 6px; }
QListWidget, QTreeWidget, QTableView, QPlainTextEdit, QTextBrowser {
    background: #050E1C; color: #DCEEFF; border: 1px solid rgba(0, 217, 255, 30);
    selection-background-color: rgba(0, 217, 255, 70); selection-color: #F0FAFF;
    alternate-background-color: #08162A; }
QHeaderView::section { background: #0B1F3A; color: #67F3FF; border: none;
    border-bottom: 1px solid rgba(0, 217, 255, 60); padding: 5px 6px; font-size: 8pt; letter-spacing: 1px; }
QTableView { gridline-color: rgba(0, 217, 255, 14); }
QLineEdit, QComboBox, QSpinBox, QDateTimeEdit { background: #050E1C; color: #DCEEFF;
    border: 1px solid rgba(0, 217, 255, 60); border-radius: 4px; padding: 5px 8px; }
QComboBox QAbstractItemView { background: #071426; color: #DCEEFF; selection-background-color: rgba(0, 217, 255, 70); }
QCheckBox { color: #DCEEFF; }
QScrollBar:vertical { background: #050E1C; width: 10px; }
QScrollBar::handle:vertical { background: rgba(0, 217, 255, 60); border-radius: 4px; min-height: 24px; }
QScrollBar:horizontal { background: #050E1C; height: 10px; }
QScrollBar::handle:horizontal { background: rgba(0, 217, 255, 60); border-radius: 4px; min-width: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QSplitter::handle { background: rgba(0, 217, 255, 20); }
QTabWidget::pane { border: 1px solid rgba(0, 217, 255, 40); border-radius: 4px; top: -1px; }
QTabBar::tab { background: #050E1C; color: #9FB9D3; padding: 8px 18px; letter-spacing: 2px; font-size: 9pt;
    border: 1px solid rgba(0, 217, 255, 30); border-bottom: none; margin-right: 2px; }
QTabBar::tab:selected { background: #0B1F3A; color: #E6FBFF; border-color: rgba(0, 217, 255, 120); }
QFrame#Panel { background: #071426; border-left: 1px solid rgba(0, 217, 255, 60); }
"""

STYLESHEET = STYLESHEET + PANEL_STYLESHEET



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
    base = TONES.get(tone, PRIMARY)
    if kind == "glow":
        core = _core_of(tone)
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
