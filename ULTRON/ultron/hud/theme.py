"""Sistema de tema do SAFRA — vermelho, bordô, preto e grafite. FONTE ÚNICA de cores e estilos do Qt.

Os valores vêm de ``palette.py`` (que espelha ``design/tokens.json``). Semântica: o VERMELHO SAFRA é
atividade, escuta e dados em movimento; o BORDÔ é repouso e profundidade; o vermelho-framboesa marca
pensamento, planejamento e execução; texto em branco e cinza. Atenção usa âmbar e falha usa laranja —
fora da família do vermelho, para nunca se confundirem com a identidade —, sem piscar nem alarmar.

Nenhum outro módulo define cores próprias: plataforma, ORBE, painéis e a TARDIS leem daqui (tokens, tons
de partícula, cores por estado e folhas de estilo geradas da paleta).
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
PRIMARY_DIM = QtGui.QColor(HEX["muted"])      # contornos, estados apagados
PRIMARY = QtGui.QColor(HEX["primary"])          # atividade, percepção, dados
GLOW = QtGui.QColor(HEX["glow"])             # brilho, destaque luminoso
ELECTRIC = QtGui.QColor(HEX["energy"])     # execução, planejamento, memória
TEXT = QtGui.QColor(HEX["text"])
TEXT_BRIGHT = QtGui.QColor(255, 255, 255)
TEXT_DIM = QtGui.QColor(HEX["dim_text"])
ALERT = QtGui.QColor(HEX["alert"])           # aviso / autorização pendente
ERROR = QtGui.QColor(HEX["error"])           # falha real
CYAN = PRIMARY

# Aliases das identidades anteriores (mantidos para código externo/plugins): já apontam para o vermelho.
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
    """Centro do brilho: quase branco; aviso e erro mantêm o próprio matiz."""
    if tone in ("alert", "amber"):
        return QtGui.QColor(255, 236, 180)
    if tone == "error":
        return QtGui.QColor(255, 214, 176)
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


# --------------------------------------------------------------- folhas de estilo (geradas da paleta)
def _style_values() -> dict:
    h, r = palette.HEX, palette.rgb
    return {"bg": h["space"], "layer": h["abyss"], "surface": h["deep"], "raised": h["graphite"],
            "text": h["text"], "bright": "#FFFFFF", "dim": h["dim_text"], "accent": h["primary"], "glow": h["glow"],
            "muted": h["muted"], "a": r("primary"), "g": r("glow"), "m": r("muted"), "l": r("abyss"), "w": r("wine")}


STYLESHEET = """
QWidget#HudInput {{ background: transparent; }}
QLineEdit#HudLine {{
    background: rgba({l}, 225); color: {text}; border: 1px solid rgba({a}, 70);
    border-radius: 2px; padding: 8px 12px; selection-background-color: rgba({a}, 110);
    font-size: 11pt;
}}
QLineEdit#HudLine:focus {{ border: 1px solid rgba({a}, 190); }}
QPushButton#HudButton {{
    background: rgba({l}, 225); color: {glow}; border: 1px solid rgba({a}, 80);
    border-radius: 2px; padding: 7px 12px; font-size: 9pt; letter-spacing: 2px;
}}
QPushButton#HudButton:hover {{ border: 1px solid rgba({a}, 200); color: {bright}; }}
QPushButton#HudButton:checked {{ background: rgba({a}, 40); }}
QPushButton#HudButton:disabled {{ color: {dim}; border-color: rgba({m}, 120); }}
QPushButton#HudPrimary {{
    background: rgba({a}, 60); color: {bright}; border: 1px solid rgba({a}, 210);
    border-radius: 2px; padding: 7px 16px; font-size: 9pt; letter-spacing: 2px;
}}
QPushButton#HudPrimary:hover {{ background: rgba({a}, 100); }}
QPushButton#HudPrimary:disabled {{ color: {dim}; background: rgba({m}, 50); border-color: rgba({m}, 120); }}
QLabel#HudLabel {{ color: {text}; font-size: 10pt; }}
QMenu {{ background: {layer}; color: {text}; border: 1px solid rgba({a}, 90); }}
QMenu::item:selected {{ background: rgba({a}, 60); }}
QToolTip {{ background: {surface}; color: {text}; border: 1px solid rgba({a}, 120); }}
""".format(**_style_values())

# Painéis (diagnóstico de voz, rede, memória da TARDIS, diálogos): mesma paleta.
PANEL_STYLESHEET = """
QDialog, QWidget#Panel, QWidget#Hub2 {{ background: {layer}; color: {text}; }}
QWidget#Panel QLabel, QDialog QLabel, QWidget#Hub2 QLabel {{ color: {text}; }}
QLabel#PanelTitle, QLabel#H2Title {{ color: {glow}; font-size: 10pt; letter-spacing: 3px; }}
QLabel#PanelDim, QLabel#H2Dim {{ color: {dim}; font-size: 9pt; }}
QLabel#PanelPrompt, QLabel#H2Answer {{ color: {bright}; background: rgba({a}, 20);
    border-left: 2px solid {accent}; padding: 8px; }}
QLabel#H2Big {{ color: {bright}; font-size: 13pt; }}
QListWidget#H2Nav {{ background: {bg}; border: none; border-right: 1px solid rgba({a}, 40);
    color: {dim}; font-size: 9pt; outline: none; }}
QListWidget#H2Nav::item {{ padding: 11px 14px; letter-spacing: 2px; }}
QListWidget#H2Nav::item:selected {{ background: rgba({a}, 32); color: {bright}; border-left: 2px solid {accent}; }}
QFrame#H2Card {{ background: {surface}; border: 1px solid rgba({a}, 38); border-radius: 2px; }}
QListWidget, QTreeWidget, QTableView, QPlainTextEdit, QTextBrowser {{
    background: {bg}; color: {text}; border: 1px solid rgba({a}, 30);
    selection-background-color: rgba({a}, 80); selection-color: {bright};
    alternate-background-color: {layer}; }}
QHeaderView::section {{ background: {surface}; color: {glow}; border: none;
    border-bottom: 1px solid rgba({a}, 60); padding: 5px 6px; font-size: 8pt; letter-spacing: 1px; }}
QTableView {{ gridline-color: rgba({a}, 16); }}
QLineEdit, QComboBox, QSpinBox, QDateTimeEdit {{ background: {bg}; color: {text};
    border: 1px solid rgba({a}, 60); border-radius: 2px; padding: 5px 8px; }}
QComboBox QAbstractItemView {{ background: {layer}; color: {text}; selection-background-color: rgba({a}, 80); }}
QCheckBox {{ color: {text}; }}
QScrollBar:vertical {{ background: {bg}; width: 10px; }}
QScrollBar::handle:vertical {{ background: rgba({a}, 70); border-radius: 1px; min-height: 24px; }}
QScrollBar:horizontal {{ background: {bg}; height: 10px; }}
QScrollBar::handle:horizontal {{ background: rgba({a}, 70); border-radius: 1px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QSplitter::handle {{ background: rgba({a}, 22); }}
QTabWidget::pane {{ border: 1px solid rgba({a}, 40); border-radius: 2px; top: -1px; }}
QTabBar::tab {{ background: {bg}; color: {dim}; padding: 8px 18px; letter-spacing: 2px; font-size: 9pt;
    border: 1px solid rgba({a}, 30); border-bottom: none; margin-right: 2px; }}
QTabBar::tab:selected {{ background: {surface}; color: {bright}; border-color: rgba({a}, 130);
    border-top: 2px solid {accent}; }}
QFrame#Panel {{ background: {layer}; border-left: 1px solid rgba({a}, 60); }}
""".format(**_style_values())

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


def _swaps() -> tuple:
    """Cores do SAFRA → cores do Protocolo ULTRON (violeta e cromo), nas duas grafias usadas nos estilos."""
    pairs = (("primary", "ultron"), ("glow", "ultron_glow"), ("energy", "ultron_glow"), ("wine", "ultron_deep"),
             ("muted", "ultron_deep"))
    hexes = {**palette.HEX, **palette.ULTRON_HEX}
    out = []
    for safra, ultron in pairs:
        out.append((hexes[safra], hexes[ultron]))
        out.append((palette.rgb(safra), palette.rgb(ultron)))
    return tuple(out)


ULTRON_SWAPS = _swaps()


def ultron_stylesheet(base: str) -> str:
    """O mesmo estilo com as cores do Protocolo ULTRON: só troca cores (a restauração usa o original salvo)."""
    for old, new in ULTRON_SWAPS:
        base = base.replace(old, new).replace(old.lower(), new)
    return base
