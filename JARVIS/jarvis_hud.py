"""
J.A.R.V.I.S. // MARK VII — HUD em PySide6
Somente interface. Voz, Ollama e TTS continuam em backend.py.
Todos os dados exibidos são REAIS (telemetria.py e backend.py). O que não estiver
disponível aparece como N/D; nada é simulado.
"""
import os
import sys
import ctypes
import math
import time
import random
import queue
import html
import threading
from collections import deque

from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPointF, QRect, QRectF, Signal, QPropertyAnimation, QEasingCurve,
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QRadialGradient, QConicalGradient,
    QLinearGradient, QPainterPath, QPolygonF, QPixmap, QShortcut, QKeySequence, QRegion, QCursor,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QLineEdit, QPushButton, QSizePolicy, QMenu,
    QMessageBox, QSystemTrayIcon, QStyle, QLabel, QComboBox, QDialog, QListWidget, QButtonGroup,
    QToolTip,
)

import backend
import copilot
import telemetria
from neural_core import NeuralCore, SIM, FlowLayer

APP_TITLE = "J.A.R.V.I.S. // MARK VII"
# (removido) IDLE_TIMEOUT = 7: a HUD NÃO minimiza mais sozinha. Só o botão de minimizar
# (ou o botão flutuante) recolhe a HUD.
COMPACT_SIZE = 340
TRANSITION_MS = 1000

# ============================================================ CORES
BG = "#010610"
ERR = "#FF2A3D"            # erro/falha (fixo)
WHITE = "#F5F6F7"
TEXT = "#B5B3B6"
MUTED = "#656164"
GREEN = "#29F29A"
AMBER = "#7FE3FF"

# Flags da janela flutuante. As cores precisam existir antes de MODE_COLORS.
FLOAT_FLAGS = (Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
               | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint)
MODE_COLORS = {
    copilot.MODE_OFF: MUTED,
    copilot.MODE_ASSISTANT: GREEN,
    copilot.MODE_AUTONOMOUS: AMBER,
}

# Tema que muda sozinho: vermelho -> amarelo -> azul escuro -> roxo -> (volta)
# (principal, claro, escuro, muito escuro)
THEMES = [
    ("#1E8CFF", "#00F0FF", "#0A3C8C", "#041428"),   # azul neon / ciano / azul profundo
]
THEME_HOLD, THEME_BLEND = 14.0, 5.0                 # segundos parado / em transição
# RED* seguem o tema atual (o nome foi mantido para não mexer no resto do código).
RED, RED2, RED_DARK, RED_DEEP = THEMES[0]
THEME_NAMES = ("NEURAL BLUE",)
THEME_LOCK = [None]            # None = troca automática; 0..3 = tema fixo (clique no logotipo)


def mix_hex(a, b, k):
    ca, cb = QColor(a), QColor(b)
    return "#%02x%02x%02x" % (int(ca.red() + (cb.red() - ca.red()) * k),
                              int(ca.green() + (cb.green() - ca.green()) * k),
                              int(ca.blue() + (cb.blue() - ca.blue()) * k))


def dk(k):
    """Preto levemente tingido com a cor do tema."""
    return mix_hex("#000000", RED, k)


def update_theme(t):
    global RED, RED2, RED_DARK, RED_DEEP
    lock = THEME_LOCK[0]
    if lock is not None:
        RED, RED2, RED_DARK, RED_DEEP = THEMES[lock]
        return
    seg = THEME_HOLD + THEME_BLEND
    i = int(t // seg) % len(THEMES)
    u = t % seg
    k = 0.0 if u < THEME_HOLD else (u - THEME_HOLD) / THEME_BLEND
    k = k * k * (3 - 2 * k)
    a, b = THEMES[i], THEMES[(i + 1) % len(THEMES)]
    RED, RED2, RED_DARK, RED_DEEP = (mix_hex(x, y, k) for x, y in zip(a, b))


def state_color(s):
    if s in ("IDLE", "RETURNING_IDLE"):
        return RED
    if s == "WAKE":
        return mix_hex(RED2, "#FFFFFF", .20)
    if s == "LISTENING":
        return RED2
    if s in ("THINKING", "TOOL_EXECUTION"):
        return mix_hex(RED2, "#FFFFFF", .55)
    if s == "SPEAKING":
        return mix_hex(RED2, "#FFFFFF", .30)
    return ERR


STATE_SUB = {
    "IDLE": "AGUARDANDO COMANDO", "WAKE": "ATIVANDO INTERFACE",
    "LISTENING": "OUVINDO SUA VOZ", "THINKING": "PROCESSANDO SOLICITAÇÃO",
    "TOOL_EXECUTION": "EXECUTANDO AÇÃO", "SPEAKING": "RESPONDENDO POR VOZ",
    "ERROR": "ATENÇÃO NECESSÁRIA", "RETURNING_IDLE": "RETORNANDO AO OCIOSO",
}
ENERGY = {"IDLE": .24, "WAKE": 1.0, "LISTENING": .75, "THINKING": 1.0,
          "TOOL_EXECUTION": 1.0, "SPEAKING": .9, "ERROR": .6, "RETURNING_IDLE": .24}
VOICE = {"IDLE": .12, "WAKE": .8, "LISTENING": 1.0, "THINKING": .2,
         "TOOL_EXECUTION": .35, "SPEAKING": 1.0, "ERROR": .1, "RETURNING_IDLE": .12}

DIAS = ["SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM"]
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

QSS = """
QPlainTextEdit { background: transparent; border: none; color: #B5B3B6;
  font-family: Consolas; font-size: 9pt; selection-background-color: #55555C; }
QLineEdit { background: rgba(20,20,24,200); border: 1px solid #3A3A40; border-radius: 6px;
  padding: 6px 10px; color: #F5F6F7; font-family: Consolas; font-size: 10pt;
  selection-background-color: #77777F; }
QLineEdit:focus { border: 1px solid #9A9AA2; }
QPushButton#cbtn, QPushButton#modeOff, QPushButton#modeAssist, QPushButton#modeAuto {
  background: rgba(20,20,24,200); border: 1px solid #3A3A40; border-radius: 5px; padding: 4px 10px;
  color: #B5B3B6; font-family: Consolas; font-size: 8pt; font-weight: bold; }
QPushButton#cbtn:hover, QPushButton#modeOff:hover, QPushButton#modeAssist:hover, QPushButton#modeAuto:hover {
  border: 1px solid #9A9AA2; color: #F5F6F7; }
QPushButton#modeOff:checked { border: 1px solid #8A8A92; color: #F5F6F7; background: rgba(120,120,130,60); }
QPushButton#modeAssist:checked { border: 1px solid #29F29A; color: #29F29A; background: rgba(41,242,154,40); }
QPushButton#modeAuto:checked { border: 1px solid #FFB84D; color: #FFB84D; background: rgba(255,184,77,45); }
QPushButton#cbtn:checked { border: 1px solid #FFB84D; color: #FFB84D; background: rgba(255,184,77,45); }
QPushButton#cbtnStop { background: rgba(60,10,16,200); border: 1px solid #FF2A3D; border-radius: 5px;
  padding: 4px 10px; color: #FF6B78; font-family: Consolas; font-size: 8pt; font-weight: bold; }
QPushButton#cbtnStop:hover { background: rgba(120,16,28,220); color: #FFFFFF; }
QPushButton#cbtn:disabled, QPushButton#cbtnStop:disabled { color: #4A4A4F; border: 1px solid #26262A; }
QComboBox#cbo { background: rgba(20,20,24,200); border: 1px solid #3A3A40; border-radius: 5px;
  padding: 3px 8px; color: #F5F6F7; font-family: Consolas; font-size: 8pt; }
QComboBox#cbo QAbstractItemView { background: #0B0C0E; color: #F5F6F7; selection-background-color: #55555C; }
QLabel#clabel { background: transparent; color: #B5B3B6; font-family: Consolas; font-size: 8pt; font-weight: bold; }
QLabel#csug { background: transparent; color: #FFB84D; font-family: Consolas; font-size: 9pt; }
QListWidget { background: #0B0C0E; color: #F5F6F7; border: 1px solid #3A3A40; font-family: Consolas; }
QDialog { background: #0B0C0E; }
QToolTip { background: #0B0C0E; color: #F5F6F7; border: 1px solid #3A3A40; padding: 4px 6px;
  font-family: Consolas; font-size: 8pt; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 0; }
QScrollBar::handle:vertical { background: #3A3A40; border-radius: 3px; min-height: 20px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


# ============================================================ HELPERS
def clamp(v, a=0.0, b=1.0):
    return max(a, min(b, v))


def acol(c, a=255):
    q = QColor(c)
    q.setAlpha(int(clamp(a, 0, 255)))
    return q


def F(size=8, bold=False, fam="Consolas", sp=0):
    f = QFont(fam)
    f.setPointSizeF(size)
    f.setBold(bold)
    if sp:
        f.setLetterSpacing(QFont.AbsoluteSpacing, sp)
    return f


def ln(p, x1, y1, x2, y2):
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def noise(x):
    return 0.5 + 0.5 * math.sin(x * 1.7) * math.sin(x * 0.63 + 1.3)


def aa(p):
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.TextAntialiasing)


class Anim:
    """Relógio e estado visual compartilhado (transições suaves)."""

    def __init__(self):
        self.t = 0.0
        self.spin = 0.0
        self.state = "IDLE"
        self.summon_t = -100.0   # instante da última expansão (reinicia a entrada dos painéis)
        self.color = QColor(state_color("IDLE"))
        self.energy = ENERGY["IDLE"]
        self.voice = VOICE["IDLE"]
        self.think = 0.0
        self.mic = 0.0           # nível REAL do microfone (suavizado)

    def update(self, dt):
        self.t += dt
        update_theme(self.t)
        s = self.state
        k = min(1.0, dt * 4.0)
        tg, c = QColor(state_color(s)), self.color
        self.color = QColor(int(c.red() + (tg.red() - c.red()) * k),
                            int(c.green() + (tg.green() - c.green()) * k),
                            int(c.blue() + (tg.blue() - c.blue()) * k))
        self.energy += (ENERGY[s] - self.energy) * min(1.0, dt * 2.5)
        self.voice += (VOICE[s] - self.voice) * min(1.0, dt * 6.0)
        self.think += ((1.0 if s in ("THINKING", "TOOL_EXECUTION") else 0.0) - self.think) * min(1.0, dt * 4.0)
        self.spin += dt * (0.5 + 1.6 * self.energy)
        self.mic += (getattr(backend, "audio_level", 0.0) - self.mic) * min(1.0, dt * 10.0)

    @property
    def since(self):
        return self.t - self.summon_t


anim = Anim()
stats = {"events": 0}
live = {"s": telemetria.snapshot()}              # telemetria real (renovada ~4x por segundo)
audio_hist = deque([0.0] * 120, maxlen=120)      # nível REAL do microfone (10 amostras/s)
ACTIVITY_BUCKET_S = 5.0
activity = deque([0] * 44, maxlen=44)            # eventos REAIS por janela de 5 s


def fmt_rate(bps):
    if bps is None:
        return "N/D"
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 ** 2:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps / 1024 ** 2:.1f} MB/s"


def fmt_uptime(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def short(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 1] + "…"


def ia_state():
    """Estado real da IA local: o ping ao Ollama manda; se ainda não houve, usa o backend."""
    ok = live["s"]["ollama_ok"]
    return ok if ok is not None else backend.status["ollama"]


# ============================================================ PAINEL BASE
class HudPanel(QWidget):
    def __init__(self, title, demo=False, delay=0.0, slide=0):
        super().__init__()
        self.title, self.demo, self.delay, self.slide = title, demo, delay, slide
        self.phase = random.random()
        self.setMinimumSize(120, 80)

    def reveal(self):
        x = clamp((anim.since - self.delay) / 0.9)
        return 1 - (1 - x) ** 3

    def body(self):
        return QRectF(16, 44, self.width() - 32, self.height() - 60)

    def paint_body(self, p, r):
        pass

    def paintEvent(self, ev):
        p = QPainter(self)
        aa(p)
        k = self.reveal()
        p.setOpacity(k)
        p.translate(self.slide * (1 - k) * 28, 0)
        w, h, c = self.width(), self.height(), 12
        poly = QPolygonF([QPointF(c, 1), QPointF(w - 1, 1), QPointF(w - 1, h - c),
                          QPointF(w - c, h - 1), QPointF(1, h - 1), QPointF(1, c)])
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0, acol(dk(.08), 225))
        g.setColorAt(1, acol("#07080A", 225))
        p.setBrush(g)
        p.setPen(QPen(acol(RED_DARK, 200), 1))
        p.drawPolygon(poly)

        p.setPen(QPen(acol(RED, 230), 2))
        L = 16
        for a in [(c, 1, c + L, 1), (1, c, 1, c + L), (w - 1 - L, 1, w - 1, 1),
                  (w - 1, 1, w - 1, 1 + L), (1, h - 1 - L, 1, h - 1), (1, h - 1, 1 + L, h - 1),
                  (w - 1, h - c - L, w - 1, h - c), (w - c - L, h - 1, w - c, h - 1)]:
            ln(p, *a)

        p.setBrush(acol(anim.color, 255))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(16, 17, 5, 5))
        p.setFont(F(8.5, True, sp=1.5))
        p.setPen(acol(RED2))
        p.drawText(QRectF(28, 8, w - 100, 22), Qt.AlignVCenter | Qt.AlignLeft, self.title)

        lg = QLinearGradient(16, 0, w - 16, 0)
        lg.setColorAt(0, acol(RED, 200))
        lg.setColorAt(1, acol(RED_DEEP, 40))
        p.setPen(QPen(lg, 1))
        ln(p, 16, 36, w - 16, 36)
        sx = 16 + ((anim.t * 0.18 + self.phase) % 1) * (w - 32)
        p.setPen(QPen(acol(WHITE, 200), 1.5))
        ln(p, sx, 36, min(sx + 34, w - 16), 36)

        if self.demo:
            p.setFont(F(6.5, True))
            p.setPen(QPen(acol(AMBER, 200), 1))
            p.setBrush(Qt.NoBrush)
            rr = QRectF(w - 52, 11, 38, 15)
            p.drawRect(rr)
            p.drawText(rr, Qt.AlignCenter, "DEMO")

        p.save()
        self.paint_body(p, self.body())
        p.restore()


# ============================================================ PAINÉIS ESQUERDOS
class StatusPanel(HudPanel):
    """CPU, RAM, GPU, microfone e rede: todos lidos de telemetria.py / backend.py.

    Barras mudam de cor por faixa (normal / atenção >= 75% / crítico >= 90%) e cada linha
    mostra um tooltip ao passar o mouse.
    """
    HELP = {"CPU": "Uso do processador", "RAM": "Memória em uso / total", "GPU": "Uso da placa de vídeo",
            "ÁUDIO": "Nível real do microfone", "REDE": "Tráfego de entrada e saída"}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setMouseTracking(True)
        self._hover = -1

    @staticmethod
    def bar_color(name, v):
        if v is not None and name in ("CPU", "RAM", "GPU"):
            if v >= .90:
                return QColor(ERR)
            if v >= .75:
                return QColor(AMBER)
        return anim.color

    def _row_at(self, pos):
        r = self.body()
        rows = self.rows()
        if not rows or not (r.left() - 6 <= pos.x() <= r.right() + 6 and r.top() <= pos.y() < r.bottom()):
            return -1, rows
        return int((pos.y() - r.top()) / (r.height() / len(rows))), rows

    def mouseMoveEvent(self, e):
        idx, rows = self._row_at(e.position())
        if idx != self._hover:
            self._hover = idx
            self.update()
        if idx >= 0:
            name, v, text = rows[idx]
            QToolTip.showText(e.globalPosition().toPoint(),
                              f"{name}: {text or 'N/D'}\n{self.HELP.get(name, '')}", self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def rows(self):
        s = live["s"]
        rows = []
        cpu = s["cpu"]
        rows.append(("CPU", cpu, None if cpu is None else f"{int(cpu * 100)}%"))
        ram = s["ram"]
        if ram is None:
            rows.append(("RAM", None, None))
        else:
            rows.append(("RAM", ram, f"{int(ram * 100)}%  {s['ram_used_gb']:.1f}/{s['ram_total_gb']:.0f} GB"))
        gpu = s["gpu"]
        rows.append(("GPU", gpu, None if gpu is None else f"{int(gpu * 100)}%"))
        if backend.status["mic"] is True:
            rows.append(("ÁUDIO", anim.mic, f"MIC {int(anim.mic * 100)}%"))
        else:
            rows.append(("ÁUDIO", None, "MIC INATIVO"))
        if s["net_down"] is None:
            rows.append(("REDE", None, None))
        else:
            peak = max([50 * 1024.0] + s["down_hist"] + s["up_hist"])
            rows.append(("REDE", clamp((s["net_down"] + s["net_up"]) / peak),
                         f"↓{fmt_rate(s['net_down'])} ↑{fmt_rate(s['net_up'])}"))
        return rows

    def paint_body(self, p, r):
        rows = self.rows()
        rh = r.height() / len(rows)
        segs = 28
        for i, (name, v, text) in enumerate(rows):
            y = r.top() + i * rh
            if i == self._hover:
                p.setPen(Qt.NoPen)
                p.setBrush(acol(RED, 26))
                p.drawRect(QRectF(r.left() - 6, y, r.width() + 12, rh))
            bar_col = self.bar_color(name, v)
            p.setFont(F(8))
            p.setPen(acol(TEXT))
            p.drawText(QRectF(r.left(), y, 56, rh * .5), Qt.AlignVCenter | Qt.AlignLeft, name)
            p.setPen(acol(WHITE if v is not None else MUTED))
            p.drawText(QRectF(r.left() + 56, y, r.width() - 56, rh * .5),
                       Qt.AlignVCenter | Qt.AlignRight, text or "N/D")
            sw = r.width() / segs
            by = y + rh * .56
            for j in range(segs):
                lit = v is not None and j < v * segs
                p.setPen(Qt.NoPen)
                p.setBrush(acol(bar_col, 230) if lit else acol(RED_DEEP, 255))
                p.drawRect(QRectF(r.left() + j * sw, by, sw - 2, 6))


def module_view(st, txt):
    """(cor, texto) de um estado de módulo, igual ao usado na lista de módulos."""
    if st is True:
        return GREEN, txt or "ATIVO"
    if st is False:
        return ERR, txt or "FALHA"
    if st == "off":
        return MUTED, txt
    return AMBER, "AGUARDANDO"


class ModulesPanel(HudPanel):
    """Estado real de cada módulo (backend.status + telemetria + banco local).

    Interativo: passar o mouse destaca a linha, clique esquerdo mostra os detalhes na conversa
    e clique direito abre as ações do módulo.
    """
    moduleClicked = Signal(str)
    moduleMenu = Signal(str, QPoint)

    MODULE_HELP = {
        "NÚCLEO VISUAL": "Interface gráfica do J.A.R.V.I.S.",
        "RECONHECIMENTO DE VOZ": "Escuta offline. Clique direito: ativar/pausar escuta ou reiniciar a voz.",
        "SÍNTESE DE VOZ": "Fala do J.A.R.V.I.S. Clique direito: reiniciar a voz.",
        "IA LOCAL (OLLAMA)": "Modelo de linguagem local, processado neste computador.",
        "VISÃO LOCAL": "Modelo de visão local usado pelo Observador.",
        "TELEMETRIA": "Leitura de CPU, RAM, rede e bateria.",
        "MEMÓRIA": "Fatos guardados no banco local.",
        "AUTOMAÇÃO": "Modo de automação. Clique direito: pausar/retomar ou parar tarefa.",
    }

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setMouseTracking(True)
        self._hover = -1

    @staticmethod
    def describe(name):
        for n, st, txt in ModulesPanel.modules():
            if n == name:
                _c, t = module_view(st, txt)
                return f"{n}: {t}. {ModulesPanel.MODULE_HELP.get(n, '')}".strip()
        return name

    def _row_at(self, pos):
        r = self.body()
        mods = self.modules()
        if not (r.left() - 6 <= pos.x() <= r.right() + 6 and r.top() <= pos.y() < r.bottom()):
            return -1, mods
        return int((pos.y() - r.top()) / (r.height() / len(mods))), mods

    def mouseMoveEvent(self, e):
        idx, mods = self._row_at(e.position())
        if idx != self._hover:
            self._hover = idx
            self.setCursor(Qt.PointingHandCursor if idx >= 0 else Qt.ArrowCursor)
            self.update()
        if idx >= 0:
            QToolTip.showText(e.globalPosition().toPoint(), self.describe(mods[idx][0]), self)
        else:
            QToolTip.hideText()

    def mousePressEvent(self, e):
        idx, mods = self._row_at(e.position())
        if idx < 0:
            return
        if e.button() == Qt.LeftButton:
            self.moduleClicked.emit(mods[idx][0])
        elif e.button() == Qt.RightButton:
            self.moduleMenu.emit(mods[idx][0], e.globalPosition().toPoint())

    def leaveEvent(self, e):
        self._hover = -1
        self.setCursor(Qt.ArrowCursor)
        self.update()

    @staticmethod
    def modules():
        s, st = live["s"], backend.status
        ia = ia_state()
        ia_txt = None
        if ia is True and s["ollama_models"] and backend.OLLAMA_MODEL not in s["ollama_models"]:
            ia, ia_txt = False, "MODELO AUSENTE"
        if s["ollama_ok"] is True:
            vision = backend.OLLAMA_VISION_MODEL in s["ollama_models"]
            vis_txt = "PRONTA" if vision else "MODELO AUSENTE"
        else:
            vision, vis_txt = None, None
        if not s["psutil_ok"]:
            tel, tel_txt = False, "INSTALE PSUTIL"
        else:
            tel, tel_txt = True, "ATIVA"
        if s["memories"] is None:
            mem, mem_txt = "off", "SEM DADOS"
        else:
            mem, mem_txt = True, f"{s['memories']} FATOS"
        total, enabled = s["automations_total"], s["automations_enabled"]
        if total is None:
            auto, auto_txt = "off", "SEM DADOS"
        elif total == 0:
            auto, auto_txt = "off", "NENHUMA"
        elif enabled == 0:
            auto, auto_txt = "off", f"0/{total} ATIVAS"
        else:
            auto, auto_txt = True, f"{enabled}/{total} ATIVAS"
        return [("NÚCLEO VISUAL", True, "ATIVO"),
                ("RECONHECIMENTO DE VOZ", st["mic"], None),
                ("SÍNTESE DE VOZ", st["tts"], None),
                ("IA LOCAL (OLLAMA)", ia, ia_txt),
                ("VISÃO LOCAL", vision, vis_txt),
                ("TELEMETRIA", tel, tel_txt),
                ("MEMÓRIA", mem, mem_txt),
                ("AUTOMAÇÃO", auto, auto_txt)]

    def paint_body(self, p, r):
        mods = self.modules()
        rh = r.height() / len(mods)
        for i, (name, st, txt) in enumerate(mods):
            y = r.top() + i * rh
            if i == self._hover:
                p.setPen(QPen(acol(RED, 110), 1))
                p.setBrush(acol(RED, 26))
                p.drawRect(QRectF(r.left() - 6, y + 1, r.width() + 12, rh - 2))
            if st is True:
                c, t = GREEN, txt or "ATIVO"
            elif st is False:
                c, t = ERR, txt or "FALHA"
            elif st == "off":
                c, t = MUTED, txt
            else:
                c, t = AMBER, "AGUARDANDO"
            blink = 0.65 + 0.35 * math.sin(anim.t * 3 + i) if st is True else 1.0
            cy = y + rh / 2
            g = QRadialGradient(r.left() + 6, cy, 9)
            g.setColorAt(0, acol(c, 255 * blink))
            g.setColorAt(.4, acol(c, 90 * blink))
            g.setColorAt(1, acol(c, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(r.left() + 6, cy), 9, 9)
            p.setBrush(acol(c, 255))
            p.drawEllipse(QPointF(r.left() + 6, cy), 3, 3)
            p.setFont(F(8))
            p.setPen(acol(TEXT))
            p.drawText(QRectF(r.left() + 22, y, r.width() - 140, rh), Qt.AlignVCenter | Qt.AlignLeft, name)
            p.setFont(F(7.5, True))
            p.setPen(acol(c))
            p.drawText(QRectF(r.right() - 120, y, 120, rh), Qt.AlignVCenter | Qt.AlignRight, t)


class DiagPanel(HudPanel):
    """Integridade dos módulos, latência real do Ollama, sinal de rede e forma de onda real do microfone."""

    def donut(self, p, cx, cy, rad, v, lab, text=None):
        known = v is not None
        v = clamp(v if known else 0.0)
        rect = QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(acol(RED_DEEP), 5))
        p.drawEllipse(QPointF(cx, cy), rad, rad)
        pen = QPen(acol(anim.color), 5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        if known:
            p.drawArc(rect, 90 * 16, int(-v * 360 * 16))
        p.setFont(F(8, True))
        p.setPen(acol(WHITE if known else MUTED))
        p.drawText(rect, Qt.AlignCenter, text if text is not None else (f"{int(v * 100)}" if known else "N/D"))
        p.setFont(F(7))
        p.setPen(acol(MUTED))
        p.drawText(QRectF(cx - 40, cy + rad + 4, 80, 14), Qt.AlignCenter, lab)

    def metrics(self):
        s = live["s"]
        states = [backend.status["mic"], backend.status["tts"], ia_state()]
        integ = sum(1 for x in states if x is True) / len(states)
        ms = s["ollama_ms"]
        latency = (None, None) if ms is None else (clamp(1.0 - ms / 500.0), f"{ms:.0f}")
        if s["wifi_signal"] is not None:
            net = (s["wifi_signal"] / 100.0, f"{s['wifi_signal']}", "WI-FI")
        elif s["net_online"] is True:
            net = (1.0, "ON", "REDE")
        elif s["net_online"] is False:
            net = (0.0, "OFF", "REDE")
        else:
            net = (None, None, "REDE")
        return [(integ, None, "INTEGR."), (latency[0], latency[1], "IA (MS)"), (net[0], net[1], net[2])]

    def paint_body(self, p, r):
        vals = self.metrics()
        top_h = r.height() * .58
        cw = r.width() / 3
        rad = max(8, min(cw * .36, top_h * .34))
        for i, (v, text, lab) in enumerate(vals):
            self.donut(p, r.left() + cw * (i + .5), r.top() + top_h * .42, rad, v, lab, text)
        sr = QRectF(r.left(), r.top() + top_h + 6, r.width(), max(10, r.height() - top_h - 6))
        p.setPen(QPen(acol(RED_DARK, 200), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(sr)
        mid = sr.center().y()
        p.setPen(QPen(acol(RED_DEEP), 1))
        ln(p, sr.left(), mid, sr.right(), mid)
        hist = list(audio_hist)
        n = len(hist)
        p.setPen(QPen(acol(anim.color, 230), 1.6))
        for i, lv in enumerate(hist):
            x = sr.left() + 2 + i / (n - 1) * (sr.width() - 4)
            a = max(.6, lv * sr.height() * .46)
            ln(p, x, mid - a, x, mid + a)
        p.setFont(F(6))
        p.setPen(acol(MUTED))
        p.drawText(QRectF(sr.left() + 4, sr.top() + 1, sr.width() - 8, 11),
                   Qt.AlignLeft | Qt.AlignVCenter, "ENTRADA DO MICROFONE (REAL)")


# ============================================================ PAINÉIS DIREITOS
class NetworkPanel(HudPanel):
    """Rede real: interface, IP, Wi-Fi, Ollama e tráfego de entrada/saída dos últimos 60 s."""

    def spark(self, p, rect, data, peak, color):
        p.setPen(QPen(acol(RED_DEEP), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(rect)
        n = len(data)
        if n < 2 or rect.height() < 6:
            return
        path = QPainterPath()
        for i, v in enumerate(data):
            x = rect.left() + i / (n - 1) * rect.width()
            y = rect.bottom() - 1.5 - clamp(v / peak) * (rect.height() - 3)
            path.moveTo(QPointF(x, y)) if i == 0 else path.lineTo(QPointF(x, y))
        p.setPen(QPen(acol(color, 230), 1.4))
        p.drawPath(path)

    def paint_body(self, p, r):
        s = live["s"]
        p.setFont(F(7.5))
        if not s["psutil_ok"]:
            p.setPen(acol(AMBER))
            p.drawText(QRectF(r.left(), r.top(), r.width(), 16), Qt.AlignLeft | Qt.AlignVCenter,
                       "Telemetria de rede indisponível.")
            p.drawText(QRectF(r.left(), r.top() + 18, r.width(), 16), Qt.AlignLeft | Qt.AlignVCenter,
                       "Instale com:  pip install psutil")
            return
        if s["wifi_ssid"]:
            sig = f"  {s['wifi_signal']}%" if s["wifi_signal"] is not None else ""
            wifi = f"WI-FI  {short(s['wifi_ssid'], 22)}{sig}"
        else:
            wifi = "WI-FI  não conectado / não disponível"
        ok = s["ollama_ok"]
        if ok is True:
            ollama, ocol = f"OLLAMA  ONLINE  {s['ollama_ms']:.0f} ms", GREEN
        elif ok is False:
            ollama, ocol = "OLLAMA  OFFLINE", ERR
        else:
            ollama, ocol = "OLLAMA  verificando…", AMBER
        net = f"{s['net_iface'] or 'SEM REDE'}   {s['net_ip'] or ''}".rstrip()
        y = r.top()
        for text, col in ((net, TEXT), (wifi, TEXT), (ollama, ocol)):
            p.setPen(acol(col))
            p.drawText(QRectF(r.left(), y, r.width(), 14), Qt.AlignLeft | Qt.AlignVCenter, text)
            y += 15
        gh = max(26.0, (r.bottom() - y - 4) / 2)
        for label, data, now, color in (("↓ ENTRADA", s["down_hist"], s["net_down"], anim.color),
                                        ("↑ SAÍDA", s["up_hist"], s["net_up"], WHITE)):
            if y + gh > r.bottom() + 2:
                break
            peak = max(50 * 1024.0, max(data))
            p.setFont(F(7))
            p.setPen(acol(MUTED))
            p.drawText(QRectF(r.left(), y, r.width() * .5, 12), Qt.AlignLeft | Qt.AlignVCenter, label)
            p.setPen(acol(WHITE))
            p.drawText(QRectF(r.left(), y, r.width(), 12), Qt.AlignRight | Qt.AlignVCenter,
                       fmt_rate(now) if now is not None else "N/D")
            self.spark(p, QRectF(r.left(), y + 13, r.width(), gh - 15), data, peak, color)
            y += gh


class ActivityPanel(HudPanel):
    """Eventos REAIS do JARVIS (linhas do console) contados em janelas de 5 segundos.

    Passar o mouse sobre uma barra mostra quantos eventos ocorreram naquela janela.
    """

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, e):
        r = self.body()
        data = list(activity)
        n = len(data)
        pos = e.position()
        if n and r.left() <= pos.x() <= r.right() and r.top() + 20 <= pos.y() <= r.bottom():
            i = max(0, min(n - 1, int((pos.x() - r.left()) / (r.width() / n))))
            ago = int((n - 1 - i) * ACTIVITY_BUCKET_S)
            QToolTip.showText(e.globalPosition().toPoint(),
                              f"{data[i]} evento(s) — há {ago} s" if ago else f"{data[i]} evento(s) — agora", self)
        else:
            QToolTip.hideText()

    def paint_body(self, p, r):
        p.setFont(F(7.5))
        p.setPen(acol(TEXT))
        p.drawText(QRectF(r.left(), r.top(), r.width(), 14), Qt.AlignLeft | Qt.AlignVCenter,
                   f"EVENTOS REGISTRADOS: {stats['events']}")
        p.setFont(F(6.5))
        p.setPen(acol(MUTED))
        p.drawText(QRectF(r.left(), r.top(), r.width(), 14), Qt.AlignRight | Qt.AlignVCenter,
                   f"ÚLTIMOS {len(activity) * ACTIVITY_BUCKET_S / 60:.0f} MIN")
        ar = QRectF(r.left(), r.top() + 20, r.width(), max(10, r.height() - 20))
        data = list(activity)
        n = len(data)
        bw = ar.width() / n
        peak = max(4, max(data))
        for i, count in enumerate(data):
            hh = max(2.0, count / peak * ar.height())
            p.setPen(Qt.NoPen)
            p.setBrush(acol(anim.color, 60 if count == 0 else 120 + 120 * count / peak))
            p.drawRect(QRectF(ar.left() + i * bw + 1, ar.bottom() - hh, bw - 2, hh))


class ConsolePanel(HudPanel):
    """Console de eventos com filtro, copiar e limpar. A API add(texto) continua a mesma."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.entries = deque(maxlen=300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 44, 10, 12)
        lay.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(6)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filtrar eventos…")
        self.filter.setClearButtonEnabled(True)
        self.filter.setFixedHeight(26)
        self.filter.setStyleSheet("padding: 2px 8px; font-size: 8pt;")
        self.btn_copy = QPushButton("COPIAR")
        self.btn_clear = QPushButton("LIMPAR")
        for b, tip in ((self.btn_copy, "Copiar os eventos visíveis"), (self.btn_clear, "Limpar o console")):
            b.setObjectName("cbtn")
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(tip)
        row.addWidget(self.filter, 1)
        row.addWidget(self.btn_copy)
        row.addWidget(self.btn_clear)
        lay.addLayout(row)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(300)
        lay.addWidget(self.view, 1)
        self.filter.textChanged.connect(self._rerender)
        self.btn_copy.clicked.connect(self._copy)
        self.btn_clear.clicked.connect(self._clear)

    def _match(self, text):
        q = self.filter.text().strip().casefold()
        return not q or q in text.casefold()

    @staticmethod
    def _html(ts, text):
        return (f'<span style="color:{MUTED}">[{ts}]</span> <span style="color:{RED2}">▸</span> '
                f'<span style="color:{TEXT}">{html.escape(text)}</span>')

    def add(self, text):
        ts = time.strftime("%H:%M:%S")
        self.entries.append((ts, text))
        if self._match(text):
            self.view.appendHtml(self._html(ts, text))

    def _rerender(self):
        self.view.clear()
        for ts, text in self.entries:
            if self._match(text):
                self.view.appendHtml(self._html(ts, text))

    def _copy(self):
        lines = [f"[{ts}] {text}" for ts, text in self.entries if self._match(text)]
        QApplication.clipboard().setText("\n".join(lines))

    def _clear(self):
        self.entries.clear()
        self.view.clear()


# ============================================================ INTERAÇÃO
class HudButton(QPushButton):
    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.setFixedSize(42, 34)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)

    def paintEvent(self, e):
        p = QPainter(self)
        aa(p)
        hot, down = self.underMouse(), self.isDown()
        if self.kind == "mic":
            col = anim.color if backend.status["mic"] is True else QColor(MUTED)
        else:
            col = QColor(RED2)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(acol(col, 255 if hot else 150), 1.5))
        p.setBrush(acol(col, 80 if down else (45 if hot else 14)))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QPen(acol(WHITE, 230), 1.8))
        p.setBrush(Qt.NoBrush)
        cx, cy = r.center().x(), r.center().y()
        if self.kind == "min":
            ln(p, cx - 8, cy + 4, cx + 8, cy + 4)
        elif self.kind == "mic":
            p.drawRoundedRect(QRectF(cx - 3.5, cy - 9, 7, 12), 3.5, 3.5)
            p.drawArc(QRectF(cx - 7, cy - 6, 14, 12), 180 * 16, 180 * 16)
            ln(p, cx, cy + 6, cx, cy + 9)
            ln(p, cx - 4, cy + 9, cx + 4, cy + 9)
        else:
            p.drawPolygon(QPolygonF([QPointF(cx - 8, cy - 7), QPointF(cx + 9, cy),
                                     QPointF(cx - 8, cy + 7), QPointF(cx - 4, cy)]))


class StateChip(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(170, 34)

    def paintEvent(self, e):
        p = QPainter(self)
        aa(p)
        c = anim.color
        pulse = .6 + .4 * math.sin(anim.t * (3 + 4 * anim.energy))
        p.setPen(QPen(acol(RED_DARK), 1))
        p.setBrush(acol(dk(.05), 200))
        p.drawRoundedRect(QRectF(.5, .5, self.width() - 1, self.height() - 1), 6, 6)
        g = QRadialGradient(16, 17, 11)
        g.setColorAt(0, acol(c, 255 * pulse))
        g.setColorAt(1, acol(c, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(16, 17), 11, 11)
        p.setBrush(acol(c))
        p.drawEllipse(QPointF(16, 17), 4, 4)
        p.setFont(F(8, True, sp=1))
        p.setPen(acol(c))
        p.drawText(QRectF(30, 0, 90, self.height()), Qt.AlignVCenter | Qt.AlignLeft, anim.state)
        for i in range(5):
            h = 3 + (3 + 10 * clamp(anim.voice * .5 + anim.mic)) * noise(anim.t * 6 + i * 1.7)
            p.setPen(Qt.NoPen)
            p.setBrush(acol(c, 220))
            p.drawRect(QRectF(124 + i * 7, 17 - h / 2, 4, h))


class HistoryEdit(QLineEdit):
    """Campo de texto com histórico: setas para cima/baixo navegam pelas mensagens enviadas."""

    def __init__(self):
        super().__init__()
        self.hist, self.pos_, self.draft = [], 0, ""

    def remember(self, text):
        if text and (not self.hist or self.hist[-1] != text):
            self.hist.append(text)
            self.hist = self.hist[-50:]
        self.pos_, self.draft = len(self.hist), ""

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Up and self.hist:
            if self.pos_ == len(self.hist):
                self.draft = self.text()
            self.pos_ = max(0, self.pos_ - 1)
            self.setText(self.hist[self.pos_])
            return
        if e.key() == Qt.Key_Down and self.hist:
            self.pos_ = min(len(self.hist), self.pos_ + 1)
            self.setText(self.draft if self.pos_ == len(self.hist) else self.hist[self.pos_])
            return
        super().keyPressEvent(e)


class InteractionPanel(HudPanel):
    """Conversa com atalhos: comandos rápidos, parar, copiar resposta, limpar e histórico (↑/↓)."""
    submitted = Signal(str)
    micClicked = Signal()
    quickCommand = Signal(str)
    stopClicked = Signal()

    QUICK = (("STATUS", "status do sistema"), ("HORAS", "que horas são"))

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.last_ai = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 44, 16, 14)
        lay.setSpacing(8)
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setMaximumBlockCount(200)
        lay.addWidget(self.chat, 1)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for label, cmd in self.QUICK:
            b = self._chip(label, f"Enviar: “{cmd}”")
            b.clicked.connect(lambda _=False, c=cmd: self.quickCommand.emit(c))
            chips.addWidget(b)
        chips.addStretch(1)
        self.b_stop = self._chip("PARAR", "Interromper o plano em execução (Esc)", stop=True)
        self.b_copy = self._chip("COPIAR RESPOSTA", "Copiar a última resposta do J.A.R.V.I.S.")
        self.b_clear = self._chip("LIMPAR", "Limpar a conversa (Ctrl+L)")
        for b in (self.b_stop, self.b_copy, self.b_clear):
            chips.addWidget(b)
        lay.addLayout(chips)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.chip = StateChip()
        self.edit = HistoryEdit()
        self.edit.setPlaceholderText("Digite uma mensagem…  (↑ ↓ histórico)")
        self.mic, self.send = HudButton("mic"), HudButton("send")
        self.mic.setToolTip("Ativar / pausar a escuta")
        self.send.setToolTip("Enviar (Enter)")
        for w_ in (self.chip, self.edit, self.mic, self.send):
            row.addWidget(w_)
        row.setStretch(1, 1)
        lay.addLayout(row)
        self.edit.returnPressed.connect(self._submit)
        self.send.clicked.connect(self._submit)
        self.mic.clicked.connect(self.micClicked.emit)
        self.b_stop.clicked.connect(self.stopClicked.emit)
        self.b_copy.clicked.connect(self._copy_last)
        self.b_clear.clicked.connect(self.chat.clear)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.chat.clear)

    @staticmethod
    def _chip(text, tip, stop=False):
        b = QPushButton(text)
        b.setObjectName("cbtnStop" if stop else "cbtn")
        b.setFocusPolicy(Qt.NoFocus)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tip)
        return b

    def _copy_last(self):
        if self.last_ai:
            QApplication.clipboard().setText(self.last_ai)

    def _submit(self):
        t = self.edit.text().strip()
        if t:
            self.edit.remember(t)
            self.edit.clear()
            self.submitted.emit(t)

    def add_user(self, t):
        self.chat.appendHtml(f'<span style="color:{MUTED}">[{time.strftime("%H:%M")}]</span> '
                             f'<span style="color:{WHITE}"><b>VOCÊ ▸</b></span> '
                             f'<span style="color:{TEXT}">{html.escape(t)}</span>')

    def add_ai(self, t):
        self.last_ai = str(t)
        self.chat.appendHtml(f'<span style="color:{MUTED}">[{time.strftime("%H:%M")}]</span> '
                             f'<span style="color:{RED2}"><b>J.A.R.V.I.S. ▸</b></span> '
                             f'<span style="color:{WHITE}">{html.escape(t)}</span>')

    def add_sys(self, t):
        self.chat.appendHtml(f'<span style="color:{MUTED}">// {html.escape(t)}</span>')


# ============================================================ NÚCLEO
class CoreWidgetAvatarAntigo(QWidget):
    """(Mantido como reserva) Avatar humanoide anterior. Para voltar a ele, em MainWindow use
    CoreWidgetAvatarAntigo() no lugar de CoreWidget().

    Avatar holográfico central do J.A.R.V.I.S.

    O antigo reator circular foi substituído por uma silhueta humanoide em
    wireframe. É puramente visual: usa somente o estado real já existente em
    ``anim`` e ``live`` e não altera a lógica do agente.
    """
    def __init__(self):
        super().__init__()
        rnd = random.Random(17)
        self.parts = [
            (rnd.uniform(-1.0, 1.0), rnd.uniform(-1.0, 1.0),
             rnd.uniform(.6, 1.7), rnd.uniform(1.0, 2.8), rnd.uniform(0, math.tau))
            for _ in range(105)
        ]
        self.scan_offsets = [rnd.uniform(0, 1) for _ in range(34)]
        self.setMinimumSize(300, 300)

    def _line(self, p, a, b):
        p.drawLine(QPointF(*a), QPointF(*b))

    def _joint(self, p, x, y, r, col, alpha=210):
        p.setBrush(acol(col, alpha))
        p.setPen(QPen(acol(WHITE, min(230, alpha + 20)), .8))
        p.drawEllipse(QPointF(x, y), r, r)

    def _glow_line(self, p, a, b, col, width=1.0, alpha=180):
        # halo curto atrás da linha para criar sensação de projeção luminosa.
        p.setPen(QPen(acol(col, max(0, alpha // 4)), width * 4.5))
        self._line(p, a, b)
        p.setPen(QPen(acol(col, alpha), width))
        self._line(p, a, b)

    def paintEvent(self, ev):
        p = QPainter(self)
        aa(p)
        w, h = self.width(), self.height()
        if w < 260 or h < 260:
            return

        t, en, col = anim.t, anim.energy, anim.color
        k = clamp((anim.since - .1) / 1.15)
        k = 1 - (1 - k) ** 3
        p.setOpacity(k)

        cx = w * .5
        base_y = h * .72
        scale = min(w / 700.0, h / 620.0)
        # busto ocupa o centro sem esmagar os painéis laterais.
        head_r = 61 * scale
        neck = 34 * scale
        shoulder_y = base_y - 205 * scale
        head_y = shoulder_y - 96 * scale
        torso_bottom = base_y + 25 * scale
        shoulder_x = 155 * scale
        arm_drop = 145 * scale

        # --------------------------- atmosfera holográfica
        glow = QRadialGradient(cx, shoulder_y - 45 * scale, 270 * scale)
        glow.setColorAt(0, acol(col, int(35 + 42 * en)))
        glow.setColorAt(.34, acol(col, 15))
        glow.setColorAt(1, acol(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, shoulder_y - 45 * scale), 270 * scale, 270 * scale)

        # plataforma de projeção
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(acol(col, 75), 1))
        p.drawEllipse(QPointF(cx, base_y + 30 * scale), 175 * scale, 30 * scale)
        p.drawEllipse(QPointF(cx, base_y + 30 * scale), 130 * scale, 19 * scale)
        for i in range(12):
            a = t * .4 + i * math.tau / 12
            r1, r2 = 132 * scale, (158 + 8 * math.sin(t + i)) * scale
            self._line(p,
                       (cx + math.cos(a) * r1, base_y + 30 * scale + math.sin(a) * 17 * scale),
                       (cx + math.cos(a) * r2, base_y + 30 * scale + math.sin(a) * 22 * scale))

        # --------------------------- scan horizontal do corpo
        scan = (t * .23) % 1.0
        sy = (base_y - 275 * scale) + scan * (340 * scale)
        p.setPen(QPen(acol(col, 80), 1))
        p.drawLine(QPointF(cx - 205 * scale, sy), QPointF(cx + 205 * scale, sy))
        sg = QLinearGradient(0, sy - 28 * scale, 0, sy + 28 * scale)
        sg.setColorAt(0, acol(col, 0)); sg.setColorAt(.5, acol(col, 24)); sg.setColorAt(1, acol(col, 0))
        p.setPen(Qt.NoPen); p.setBrush(sg)
        p.drawRect(QRectF(cx - 210 * scale, sy - 28 * scale, 420 * scale, 56 * scale))

        # --------------------------- pontos de projeção ao redor
        p.setPen(Qt.NoPen)
        for i, (ox, oy, sp, size, ph) in enumerate(self.parts):
            # concentração em torno da silhueta, com partículas que sobem.
            px = cx + ox * 210 * scale
            py = shoulder_y + oy * 280 * scale - ((t * 18 * sp + i * 3) % 95) * scale
            tw = .35 + .65 * (.5 + .5 * math.sin(t * (1.8 + sp) + ph))
            p.setBrush(acol(col, int(22 + 92 * tw)))
            p.drawEllipse(QPointF(px, py), size * .75, size * .75)

        # --------------------------- cabeça / crânio
        head_glow = QRadialGradient(cx, head_y, head_r * 1.55)
        head_glow.setColorAt(0, acol(col, 35 + int(35 * en)))
        head_glow.setColorAt(1, acol(col, 0))
        p.setBrush(head_glow); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, head_y), head_r * 1.55, head_r * 1.55)

        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(acol(col, 205), 1.4))
        p.drawEllipse(QPointF(cx, head_y), head_r, head_r * 1.13)
        p.setPen(QPen(acol(col, 125), 1))
        p.drawArc(QRectF(cx-head_r, head_y-head_r*1.13, head_r*2, head_r*2.26), 20*16, 145*16)
        p.drawArc(QRectF(cx-head_r, head_y-head_r*1.13, head_r*2, head_r*2.26), 205*16, 120*16)

        # malha da cabeça
        p.setPen(QPen(acol(col, 70), .7))
        for off in (-.62, -.30, 0, .30, .62):
            x = cx + off * head_r
            p.drawLine(QPointF(x, head_y-head_r*.85), QPointF(x*.999, head_y+head_r*.85))
        for yy in (-.65, -.32, 0, .32, .65):
            p.drawEllipse(QPointF(cx, head_y + yy * head_r), head_r * math.sqrt(max(.05, 1-yy*yy)), 5 * scale)

        # rosto minimalista, deliberadamente geométrico.
        eye_y = head_y - 8 * scale
        eye_dx = 23 * scale
        p.setPen(QPen(acol(col, 220), 2.2))
        self._glow_line(p, (cx-eye_dx-15*scale, eye_y), (cx-eye_dx+9*scale, eye_y-2*scale), col, 1.8, 220)
        self._glow_line(p, (cx+eye_dx-9*scale, eye_y-2*scale), (cx+eye_dx+15*scale, eye_y), col, 1.8, 220)
        p.setPen(QPen(acol(WHITE, 165), .8))
        self._line(p, (cx, head_y-4*scale), (cx-3*scale, head_y+22*scale))
        self._line(p, (cx-3*scale, head_y+22*scale), (cx+8*scale, head_y+25*scale))
        p.setPen(QPen(acol(col, 130), 1))
        p.drawArc(QRectF(cx-24*scale, head_y+24*scale, 48*scale, 20*scale), 205*16, 130*16)

        # --------------------------- pescoço e tronco
        neck_top = head_y + head_r * .90
        neck_bottom = shoulder_y - 35 * scale
        self._glow_line(p, (cx-neck*.72, neck_top), (cx-neck*.92, neck_bottom), col, 1.4, 190)
        self._glow_line(p, (cx+neck*.72, neck_top), (cx+neck*.92, neck_bottom), col, 1.4, 190)

        # clavículas e ombros
        ls = (cx - shoulder_x, shoulder_y)
        rs = (cx + shoulder_x, shoulder_y)
        self._glow_line(p, ls, (cx-50*scale, shoulder_y-24*scale), col, 1.8, 220)
        self._glow_line(p, rs, (cx+50*scale, shoulder_y-24*scale), col, 1.8, 220)
        self._glow_line(p, (cx-50*scale, shoulder_y-24*scale), (cx, shoulder_y-7*scale), col, 1.2, 170)
        self._glow_line(p, (cx+50*scale, shoulder_y-24*scale), (cx, shoulder_y-7*scale), col, 1.2, 170)

        waist_y = base_y - 18 * scale
        chest_l = (cx - 105*scale, shoulder_y + 35*scale)
        chest_r = (cx + 105*scale, shoulder_y + 35*scale)
        waist_l = (cx - 75*scale, waist_y)
        waist_r = (cx + 75*scale, waist_y)
        for a,b in ((chest_l, chest_r),(chest_l,waist_l),(chest_r,waist_r),(waist_l,waist_r)):
            self._glow_line(p,a,b,col,1.5,180)

        # grelha torácica
        p.setPen(QPen(acol(col, 75), .75))
        for frac in (.18,.35,.52,.69,.86):
            yy = shoulder_y + frac * (waist_y - shoulder_y)
            half = (104 - frac * 28) * scale
            p.drawLine(QPointF(cx-half, yy), QPointF(cx+half, yy))
        for frac in (-.7,-.35,0,.35,.7):
            x = cx + frac * 92 * scale
            p.drawLine(QPointF(x, shoulder_y+28*scale), QPointF(x*.998, waist_y-2*scale))

        # reator do peito
        reactor_y = shoulder_y + 75 * scale
        rr = 28 * scale
        rg = QRadialGradient(cx, reactor_y, rr*2.5)
        rg.setColorAt(0, acol(WHITE, 245)); rg.setColorAt(.22, acol(col, 245)); rg.setColorAt(.55, acol(col, 90)); rg.setColorAt(1, acol(col, 0))
        p.setBrush(rg); p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(cx, reactor_y), rr*2.5, rr*2.5)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(acol(WHITE, 210), 1.5))
        p.drawEllipse(QPointF(cx, reactor_y), rr, rr)
        p.setPen(QPen(acol(col, 210), 2))
        p.drawArc(QRectF(cx-rr*1.45, reactor_y-rr*1.45, rr*2.9, rr*2.9), int(t*80*16), 250*16)
        p.setPen(QPen(acol(col, 120), 1))
        for i in range(8):
            a = t*.6 + i*math.tau/8
            self._line(p, (cx+math.cos(a)*rr*1.05, reactor_y+math.sin(a)*rr*1.05),
                       (cx+math.cos(a)*rr*1.55, reactor_y+math.sin(a)*rr*1.55))

        # --------------------------- braços articulados
        elbow_l = (cx - shoulder_x - 37*scale, shoulder_y + 95*scale)
        elbow_r = (cx + shoulder_x + 37*scale, shoulder_y + 95*scale)
        hand_l = (elbow_l[0] - 10*scale, elbow_l[1] + arm_drop*.55)
        hand_r = (elbow_r[0] + 10*scale, elbow_r[1] + arm_drop*.55)
        for shoulder, elbow, hand, side in ((ls,elbow_l,hand_l,-1),(rs,elbow_r,hand_r,1)):
            self._glow_line(p, shoulder, elbow, col, 1.8, 205)
            self._glow_line(p, elbow, hand, col, 1.4, 175)
            self._joint(p,*shoulder,5*scale,col)
            self._joint(p,*elbow,4*scale,col,180)
            self._joint(p,*hand,3.5*scale,col,190)
            # dedos/feixe de mão
            for j in range(4):
                dx = side * (8 + j*4) * scale
                self._glow_line(p, (hand[0],hand[1]), (hand[0]+dx,hand[1]+(j%2-0.5)*8*scale), col, .7, 130)

        # linhas internas de energia dos braços
        p.setPen(QPen(acol(WHITE, 75), .7))
        for side in (-1,1):
            x0 = cx + side*shoulder_x
            for j in range(4):
                off = j*7*scale
                self._line(p,(x0-side*off, shoulder_y+10*scale),(elbow_l[0] if side<0 else elbow_r[0]-side*off, elbow_l[1]))

        # --------------------------- cortes/scanlines no holograma
        p.setPen(QPen(acol(WHITE, 55), .7))
        for i in range(8):
            yy = shoulder_y - 40*scale + ((t*.08 + i/8) % 1) * 285*scale
            width = 125 * scale * (0.45 + .55 * math.sin((yy-shoulder_y)/(285*scale)*math.pi)**2)
            p.drawLine(QPointF(cx-width, yy), QPointF(cx+width, yy))

        # --------------------------- telemetria do avatar
        p.resetTransform()
        p.setFont(F(7, True, "Consolas", 1.0))
        p.setPen(acol(col, 185))
        p.drawText(QRectF(6, 4, 270, 14), Qt.AlignLeft, "HOLOGRAPHIC AVATAR // ONLINE")
        p.setFont(F(6.5, False, "Consolas", .7))
        p.setPen(acol(TEXT, 125))
        p.drawText(QRectF(6, 20, 270, 13), Qt.AlignLeft, "PROJECTION MATRIX // MARK VII")
        p.drawText(QRectF(w-280, 4, 274, 14), Qt.AlignRight, "PERCEPTION // ACTIVE")
        p.drawText(QRectF(w-280, 20, 274, 13), Qt.AlignRight, "CORE // " + backend.OLLAMA_MODEL.upper())

        # estado abaixo da figura
        p.setFont(F(20, True, "Segoe UI", 4))
        p.setPen(acol(col))
        p.drawText(QRectF(0, h-74, w, 28), Qt.AlignCenter, anim.state)
        p.setFont(F(8, False, "Consolas", 1.3))
        p.setPen(acol(TEXT))
        p.drawText(QRectF(0, h-48, w, 18), Qt.AlignCenter, STATE_SUB[anim.state])
        p.setFont(F(6.5, False, "Consolas", .6))
        p.setPen(acol(MUTED))
        ms = live["s"]["ollama_ms"]
        p.drawText(QRectF(8, h-18, 240, 14), Qt.AlignLeft, f"MIC {int(anim.mic*100):03d}%")
        p.drawText(QRectF(w-248, h-18, 240, 14), Qt.AlignRight,
                   "LATÊNCIA IA N/D" if ms is None else f"LATÊNCIA IA {ms:.0f} MS")


class CoreWidget(QWidget):
    """Núcleo holográfico profissional.

    Globo wireframe 3D, anel de áudio com o nível REAL do microfone, medidores de CPU e RAM
    reais, e seis nós com o estado real dos módulos. Nada aqui é simulado: tudo vem de
    ``anim``, ``live``, ``audio_hist`` e ``backend.status``.

    Interativo: o ponteiro inclina o globo; clique no núcleo liga/pausa o microfone; passar o
    mouse em um nó mostra o estado do módulo e clicar nele abre os detalhes.
    """
    clicked = Signal()
    nodeClicked = Signal(str)

    NODE_IDX = (1, 2, 3, 4, 6, 7)          # posições em ModulesPanel.modules()
    NODE_ANG = (150, 90, 30, 330, 270, 210)  # graus (sentido anti-horário, 0 = direita)
    SEGS = 40

    def __init__(self):
        super().__init__()
        self.setMinimumSize(300, 300)
        self.setMouseTracking(True)
        self._px = self._py = 0.0           # ponteiro (-1..1)
        self._sx = self._sy = 0.0           # ponteiro suavizado
        self._hover = None                  # ("core", 0) | ("node", i) | None
        self._nodes = []                    # [(x, y, nome, texto, cor)]
        self._geo = (0.0, 0.0, 1.0)         # cx, cy, R
        n = self.SEGS
        ring = [i * math.tau / n for i in range(n + 1)]
        self._lats = []
        for deg in (-60, -30, 0, 30, 60):
            f = math.radians(deg)
            self._lats.append([(math.cos(f) * math.cos(a), math.sin(f), math.cos(f) * math.sin(a)) for a in ring])
        self._lons = []
        for i in range(8):
            lam = i * math.pi / 8
            self._lons.append([(math.cos(a) * math.cos(lam), math.sin(a), math.cos(a) * math.sin(lam)) for a in ring])
        rnd = random.Random(7)
        self.dust = [(rnd.uniform(0, math.tau), rnd.uniform(1.18, 2.15), rnd.uniform(.25, .9),
                      rnd.uniform(1.0, 2.2)) for _ in range(46)]

    # ------------------------------------------------------------ geometria
    @staticmethod
    def _rot(x, y, z, ya, xb):
        X = x * math.cos(ya) + z * math.sin(ya)
        Z = -x * math.sin(ya) + z * math.cos(ya)
        Y = y * math.cos(xb) - Z * math.sin(xb)
        Z2 = y * math.sin(xb) + Z * math.cos(xb)
        return X, Y, Z2

    def _poly3(self, p, pts, ya, xb, cx, cy, R, col, a_front, a_back, wd=1.0):
        front, back = QPainterPath(), QPainterPath()
        prev = None
        for x, y, z in pts:
            X, Y, Z = self._rot(x, y, z, ya, xb)
            sp = QPointF(cx + X * R, cy + Y * R)
            side = Z >= 0
            path = front if side else back
            if prev is not None and prev[0] == side:
                path.lineTo(sp)
            else:
                if prev is not None:
                    path.moveTo(prev[1])
                    path.lineTo(sp)
                else:
                    path.moveTo(sp)
            prev = (side, sp)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(acol(col, a_back), wd))
        p.drawPath(back)
        p.setPen(QPen(acol(col, a_front), wd))
        p.drawPath(front)

    @staticmethod
    def _level_color(v):
        if v is not None:
            if v >= .90:
                return QColor(ERR)
            if v >= .75:
                return QColor(AMBER)
        return anim.color

    def _gauge(self, p, cx, cy, rad, side, v, label, w):
        rect = QRectF(cx - rad, cy - rad, 2 * rad, 2 * rad)
        p.setBrush(Qt.NoBrush)
        track = QPen(acol(RED_DEEP, 255), 4)
        track.setCapStyle(Qt.RoundCap)
        p.setPen(track)
        p.drawArc(rect, (120 if side < 0 else -60) * 16, 120 * 16)
        c = self._level_color(v)
        if v is not None:
            pen = QPen(acol(c, 235), 4)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            if side < 0:
                p.drawArc(rect, 240 * 16, int(-clamp(v) * 120 * 16))
            else:
                p.drawArc(rect, -60 * 16, int(clamp(v) * 120 * 16))
        text = f"{label}\n{'N/D' if v is None else str(int(v * 100)) + '%'}"
        p.setFont(F(7.5, True, sp=.6))
        p.setPen(acol(WHITE if v is not None else MUTED))
        if side < 0:
            x = max(2.0, cx - rad - 76)
            p.drawText(QRectF(x, cy - 16, 68, 32), Qt.AlignRight | Qt.AlignVCenter, text)
        else:
            x = min(w - 70.0, cx + rad + 8)
            p.drawText(QRectF(x, cy - 16, 68, 32), Qt.AlignLeft | Qt.AlignVCenter, text)

    # ------------------------------------------------------------ interação
    def _hit(self, pos):
        for i, (x, y, _n, _t, _c) in enumerate(self._nodes):
            if math.hypot(pos.x() - x, pos.y() - y) <= 12:
                return ("node", i)
        cx, cy, R = self._geo
        if math.hypot(pos.x() - cx, pos.y() - cy) <= R * 1.05:
            return ("core", 0)
        return None

    def mouseMoveEvent(self, e):
        pos = e.position()
        self._px = clamp(pos.x() / max(1, self.width()) * 2 - 1, -1, 1)
        self._py = clamp(pos.y() / max(1, self.height()) * 2 - 1, -1, 1)
        hit = self._hit(pos)
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.PointingHandCursor if hit else Qt.ArrowCursor)
        if hit is None:
            QToolTip.hideText()
        elif hit[0] == "node" and hit[1] < len(self._nodes):
            _x, _y, name, txt, _c = self._nodes[hit[1]]
            QToolTip.showText(e.globalPosition().toPoint(), f"{name}: {txt}\nClique para ver detalhes", self)
        else:
            on = backend.status["mic"] is True
            QToolTip.showText(e.globalPosition().toPoint(),
                              "Clique para pausar a escuta" if on else "Clique para ativar a escuta", self)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or self._hover is None:
            return
        if self._hover[0] == "core":
            self.clicked.emit()
        elif self._hover[1] < len(self._nodes):
            self.nodeClicked.emit(self._nodes[self._hover[1]][2])

    def leaveEvent(self, e):
        self._hover = None
        self._px = self._py = 0.0
        self.setCursor(Qt.ArrowCursor)
        QToolTip.hideText()

    # ------------------------------------------------------------ desenho
    def paintEvent(self, ev):
        p = QPainter(self)
        aa(p)
        w, h = self.width(), self.height()
        if w < 260 or h < 260:
            return

        t, en, col = anim.t, anim.energy, anim.color
        k = clamp((anim.since - .1) / 1.15)
        k = 1 - (1 - k) ** 3
        p.setOpacity(k)
        self._sx += (self._px - self._sx) * .08
        self._sy += (self._py - self._sy) * .08

        top, bottom = 44.0, h - 86.0
        cx = w * .5
        cy = (top + bottom) / 2 - 4
        R = max(40.0, min(w * .165, (bottom - top) / 2 / 2.1))
        self._geo = (cx, cy, R)
        s = live["s"]

        # ---- atmosfera
        glow = QRadialGradient(cx, cy, R * 3.2)
        glow.setColorAt(0, acol(col, int(30 + 40 * en)))
        glow.setColorAt(.45, acol(col, 12))
        glow.setColorAt(1, acol(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QPointF(cx, cy), R * 3.2, R * 3.2)

        # ---- plataforma e feixe de projeção
        fy = cy + R * 1.58
        beam = QLinearGradient(0, cy + R * .6, 0, fy)
        beam.setColorAt(0, acol(col, 0))
        beam.setColorAt(1, acol(col, int(26 + 30 * en)))
        p.setBrush(beam)
        p.drawPolygon(QPolygonF([QPointF(cx - R * .95, fy), QPointF(cx + R * .95, fy),
                                 QPointF(cx + R * .3, cy + R * .7), QPointF(cx - R * .3, cy + R * .7)]))
        p.setBrush(Qt.NoBrush)
        for rx, alpha in ((2.25, 70), (1.65, 55), (1.05, 45)):
            p.setPen(QPen(acol(col, alpha), 1))
            p.drawEllipse(QPointF(cx, fy), R * rx, R * rx * .17)
        p.setPen(QPen(acol(col, 90), 1))
        for i in range(48):
            a = -t * .12 + i * math.tau / 48
            L = 7 if i % 4 == 0 else 3.5
            x1, y1 = cx + math.cos(a) * R * 2.25, fy + math.sin(a) * R * 2.25 * .17
            x2, y2 = cx + math.cos(a) * (R * 2.25 + L), fy + math.sin(a) * (R * 2.25 + L * .17)
            ln(p, x1, y1, x2, y2)

        # ---- anel graduado
        rt = R * 1.62
        for i in range(120):
            a = i * math.tau / 120 + t * .05
            major = i % 10 == 0
            L = 9 if major else 4
            p.setPen(QPen(acol(col, 150 if major else 60), 1.2 if major else 1))
            ln(p, cx + math.cos(a) * rt, cy + math.sin(a) * rt,
               cx + math.cos(a) * (rt + L), cy + math.sin(a) * (rt + L))

        # ---- arcos ativos (velocidades diferentes)
        p.setBrush(Qt.NoBrush)
        for rad, sp_, span, alpha, wd in ((1.47, 38, 62, 150, 2.0), (1.47, -26, 34, 110, 1.5),
                                          (1.54, 52, 20, 190, 2.4)):
            pen = QPen(acol(col, alpha), wd)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            rr = R * rad
            p.drawArc(QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr), int((anim.spin * sp_) * 16), span * 16)

        # ---- partículas atrás do globo
        def dust(front):
            p.setPen(Qt.NoPen)
            for a0, f, sp_, size in self.dust:
                a = a0 + t * .12 * sp_
                depth = math.sin(a)
                if (depth >= 0) != front:
                    continue
                x = cx + math.cos(a) * R * f
                y = cy + depth * R * f * .30 - (f - 1.2) * R * .12
                tw = .5 + .5 * math.sin(t * 1.6 + a0 * 3)
                p.setBrush(acol(col, int((30 if not front else 70) + 70 * tw * (.4 + en * .6))))
                p.drawEllipse(QPointF(x, y), size * .6, size * .6)
        dust(False)

        # ---- anel de áudio (nível REAL do microfone)
        n = 90
        r0 = R * 1.14
        mix = clamp(anim.mic * 1.3 + anim.voice * .35)
        hist = list(audio_hist)
        pen = QPen(acol(col, 175), 2.0)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        for i in range(n):
            j = i if i <= n // 2 else n - i
            hv = hist[-1 - (j * 2) % len(hist)]
            a = i * math.tau / n - math.pi / 2
            amp = R * .035 + R * .30 * clamp(hv * 1.2 + mix * .45 * noise(t * 5 + i * .8) + en * .06)
            c_, s_ = math.cos(a), math.sin(a)
            ln(p, cx + c_ * r0, cy + s_ * r0, cx + c_ * (r0 + amp), cy + s_ * (r0 + amp))

        # ---- globo wireframe 3D
        ya = anim.spin * .55 + self._sx * .7
        xb = .38 + self._sy * .32
        body = QRadialGradient(cx - R * .25, cy - R * .3, R * 1.2)
        body.setColorAt(0, acol(col, int(30 + 30 * en)))
        body.setColorAt(1, acol(col, 4))
        p.setPen(Qt.NoPen)
        p.setBrush(body)
        p.drawEllipse(QPointF(cx, cy), R, R)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(acol(col, 210), 1.4))
        p.drawEllipse(QPointF(cx, cy), R, R)
        for pts in self._lats:
            self._poly3(p, pts, ya, xb, cx, cy, R, col, 135, 45)
        for pts in self._lons:
            self._poly3(p, pts, ya, xb, cx, cy, R, col, 120, 38)
        # plano de varredura que sobe e desce
        phi = math.sin(t * (.5 + .9 * anim.think)) * 1.1
        scan = [(math.cos(phi) * math.cos(a), math.sin(phi), math.cos(phi) * math.sin(a))
                for a in [i * math.tau / self.SEGS for i in range(self.SEGS + 1)]]
        self._poly3(p, scan, ya, xb, cx, cy, R, WHITE, 190, 40, 1.4)

        # ---- núcleo de energia
        pulse = .5 + .5 * math.sin(t * 3.0)
        pr = R * (.20 + .035 * pulse * (.5 + en) + .07 * anim.mic)
        cg = QRadialGradient(cx, cy, pr * 2.6)
        cg.setColorAt(0, acol(WHITE, 250))
        cg.setColorAt(.22, acol(col, 240))
        cg.setColorAt(.55, acol(col, 80))
        cg.setColorAt(1, acol(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(cg)
        p.drawEllipse(QPointF(cx, cy), pr * 2.6, pr * 2.6)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(acol(WHITE, 170), 1.2))
        p.drawEllipse(QPointF(cx, cy), pr * 1.25, pr * 1.25)
        if anim.think > .02:                           # pensando / executando: arcos internos
            for i, (rad, sp_) in enumerate(((.62, 240), (.5, -320), (.4, 410))):
                pen = QPen(acol(WHITE, int(190 * anim.think)), 1.6)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                rr = R * rad
                p.drawArc(QRectF(cx - rr, cy - rr, 2 * rr, 2 * rr), int((t * sp_ + i * 70) * 16), 80 * 16)

        dust(True)

        # ---- medidores reais de CPU (esquerda) e RAM (direita)
        gr = R * 1.92
        self._gauge(p, cx, cy, gr, -1, s["cpu"], "CPU", w)
        self._gauge(p, cx, cy, gr, 1, s["ram"], "RAM", w)

        # ---- nós dos módulos (estado real)
        mods = ModulesPanel.modules()
        self._nodes = []
        for i, (idx, ang) in enumerate(zip(self.NODE_IDX, self.NODE_ANG)):
            name, st, txt = mods[idx]
            c, text = module_view(st, txt)
            a = math.radians(ang)
            nx, ny = cx + math.cos(a) * R * 1.62, cy - math.sin(a) * R * 1.62
            self._nodes.append((nx, ny, name, text, c))
            hot = self._hover == ("node", i)
            blink = .7 + .3 * math.sin(t * 3 + i) if st is True else 1.0
            g = QRadialGradient(nx, ny, 14 if hot else 11)
            g.setColorAt(0, acol(c, 255 * blink))
            g.setColorAt(.45, acol(c, 90 * blink))
            g.setColorAt(1, acol(c, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawEllipse(QPointF(nx, ny), 14 if hot else 11, 14 if hot else 11)
            p.setBrush(acol(c, 255))
            p.setPen(QPen(acol(WHITE, 230 if hot else 150), 1))
            p.drawEllipse(QPointF(nx, ny), 5.5 if hot else 4, 5.5 if hot else 4)
        if self._hover == ("core", 0):
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(acol(WHITE, 160), 1.2, Qt.DashLine))
            p.drawEllipse(QPointF(cx, cy), R * 1.05, R * 1.05)

        # ---- textos fixos
        p.resetTransform()
        p.setFont(F(7, True, "Consolas", 1.0))
        p.setPen(acol(col, 185))
        p.drawText(QRectF(6, 4, 270, 14), Qt.AlignLeft, "HOLOGRAPHIC CORE // ONLINE")
        p.setFont(F(6.5, False, "Consolas", .7))
        p.setPen(acol(TEXT, 125))
        p.drawText(QRectF(6, 20, 270, 13), Qt.AlignLeft, "PROJECTION MATRIX // MARK VII")
        p.drawText(QRectF(w - 280, 4, 274, 14), Qt.AlignRight, "PERCEPTION // ACTIVE")
        p.drawText(QRectF(w - 280, 20, 274, 13), Qt.AlignRight, "CORE // " + backend.OLLAMA_MODEL.upper())

        p.setFont(F(20, True, "Segoe UI", 4))
        p.setPen(acol(col))
        p.drawText(QRectF(0, h - 74, w, 28), Qt.AlignCenter, anim.state)
        p.setFont(F(8, False, "Consolas", 1.3))
        p.setPen(acol(TEXT))
        p.drawText(QRectF(0, h - 48, w, 18), Qt.AlignCenter, STATE_SUB[anim.state])
        p.setFont(F(6.5, False, "Consolas", .6))
        p.setPen(acol(MUTED))
        ms = s["ollama_ms"]
        p.drawText(QRectF(8, h - 18, 240, 14), Qt.AlignLeft, f"MIC {int(anim.mic * 100):03d}%")
        p.drawText(QRectF(w - 248, h - 18, 240, 14), Qt.AlignRight,
                   "LATÊNCIA IA N/D" if ms is None else f"LATÊNCIA IA {ms:.0f} MS")


# ============================================================ BARRA SUPERIOR
class TopBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(64)
        self.setToolTip("Clique no logotipo para trocar o tema (automático, vermelho, amarelo, azul, roxo)")

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().x() < 340:
            cur = THEME_LOCK[0]
            THEME_LOCK[0] = 0 if cur is None else (cur + 1 if cur + 1 < len(THEMES) else None)
            name = "AUTOMÁTICO" if THEME_LOCK[0] is None else THEME_NAMES[THEME_LOCK[0]]
            QToolTip.showText(e.globalPosition().toPoint(), f"Tema: {name}", self)

    def paintEvent(self, e):
        p = QPainter(self)
        aa(p)
        w, h, t, col = self.width(), self.height(), anim.t, anim.color
        k = clamp(anim.since / .8)
        p.setOpacity(k)

        # mini reator
        p.save()
        p.translate(38, 32)
        p.setBrush(Qt.NoBrush)
        for r_, sp_, c_ in [(18, 40, RED2), (12, -70, RED), (6, 100, WHITE)]:
            pen = QPen(acol(c_, 230), 2)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            for m in range(3):
                p.drawArc(QRectF(-r_, -r_, 2 * r_, 2 * r_), int((anim.spin * sp_ + m * 120) * 16), 70 * 16)
        p.restore()

        p.setFont(F(22, True, "Segoe UI", 3))
        p.setPen(acol(RED, 90))
        for dx, dy in ((-1, 0), (1, 0), (0, 1), (0, -1)):
            p.drawText(QRectF(70 + dx, 6 + dy, 260, 32), Qt.AlignVCenter | Qt.AlignLeft, "J.A.R.V.I.S.")
        p.setPen(acol(WHITE))
        p.drawText(QRectF(70, 6, 260, 32), Qt.AlignVCenter | Qt.AlignLeft, "J.A.R.V.I.S.")
        p.setFont(F(6.5, sp=1))
        p.setPen(acol(TEXT))
        p.drawText(QRectF(71, 38, 360, 14), Qt.AlignVCenter | Qt.AlignLeft,
                   "JUST A RATHER VERY INTELLIGENT SYSTEM  //  MARK VII")

        # relógio e data
        lt = time.localtime()
        p.setFont(F(18, True))
        p.setPen(acol(WHITE))
        p.drawText(QRectF(w - 190, 6, 170, 30), Qt.AlignVCenter | Qt.AlignRight, time.strftime("%H:%M:%S"))
        p.setFont(F(7.5))
        p.setPen(acol(TEXT))
        p.drawText(QRectF(w - 240, 38, 220, 14), Qt.AlignVCenter | Qt.AlignRight,
                   f"{DIAS[lt.tm_wday]} {lt.tm_mday:02d} {MESES[lt.tm_mon - 1]} {lt.tm_year}")

        # estado
        sx = w - 190 - 150
        pulse = .6 + .4 * math.sin(t * 4)
        g = QRadialGradient(sx, 24, 10)
        g.setColorAt(0, acol(col, 255 * pulse))
        g.setColorAt(1, acol(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(sx, 24), 10, 10)
        p.setBrush(acol(col))
        p.drawEllipse(QPointF(sx, 24), 4, 4)
        p.setFont(F(9, True, sp=1))
        p.setPen(acol(col))
        p.drawText(QRectF(sx + 12, 14, 130, 20), Qt.AlignVCenter | Qt.AlignLeft, anim.state)

        # LEDs de módulos reais
        st = backend.status
        lx = sx - 96
        p.setFont(F(6.5, True))
        for i, (nm, v) in enumerate((("MIC", st["mic"]), ("TTS", st["tts"]), ("IA", ia_state()))):
            c = GREEN if v is True else ERR if v is False else AMBER
            x = lx + i * 32
            p.setPen(Qt.NoPen)
            p.setBrush(acol(c))
            p.drawEllipse(QPointF(x + 6, 21), 3, 3)
            p.setPen(acol(TEXT))
            p.drawText(QRectF(x - 6, 28, 26, 12), Qt.AlignCenter, nm)

        # indicadores REAIS (substituem a antiga navegação decorativa)
        s_ = live["s"]
        if s_["battery"] is None:
            bat = "SEM BATERIA" if s_["psutil_ok"] else "N/D"
        else:
            bat = f"{s_['battery']:.0f}%" + (" ⚡" if s_["battery_plugged"] else "")
        if s_["wifi_ssid"]:
            net_txt = short(s_["wifi_ssid"], 13)
        elif s_["net_online"] is None:
            net_txt = "N/D"
        else:
            net_txt = "ONLINE" if s_["net_online"] else "OFFLINE"
        chips = (("BATERIA", bat), ("REDE", net_txt), ("MODELO", short(backend.OLLAMA_MODEL.upper(), 13)),
                 ("SESSÃO", fmt_uptime(s_["uptime"])))
        nx0, nx1 = 400, lx - 20
        x = nx0
        for label, value in chips:
            if x + 112 > nx1:
                break
            rr = QRectF(x, 14, 106, 34)
            p.setPen(QPen(acol(RED_DEEP), 1))
            p.setBrush(acol("#0A0A0C", 160))
            p.drawRect(rr)
            p.setFont(F(6, True, sp=1))
            p.setPen(acol(MUTED))
            p.drawText(QRectF(x, 16, 106, 12), Qt.AlignCenter, label)
            p.setFont(F(8, True))
            p.setPen(acol(WHITE))
            p.drawText(QRectF(x, 28, 106, 18), Qt.AlignCenter, value)
            x += 112

        lg = QLinearGradient(0, 0, w, 0)
        lg.setColorAt(0, acol(RED, 230))
        lg.setColorAt(.5, acol(RED_DARK, 160))
        lg.setColorAt(1, acol(RED, 230))
        p.setPen(QPen(lg, 1))
        ln(p, 0, h - 2, w, h - 2)
        bx = ((t * .22) % 1) * w
        p.setPen(QPen(acol(WHITE, 220), 2))
        ln(p, bx, h - 2, min(bx + 70, w), h - 2)


# ============================================================ FUNDO
class Background(QWidget):
    def __init__(self):
        super().__init__()
        rnd = random.Random(5)
        self.pts = [[rnd.random(), rnd.random(), rnd.uniform(.008, .03),
                     rnd.uniform(.6, 2.2), rnd.random() * math.tau] for _ in range(80)]
        self.grid = None

    def resizeEvent(self, e):
        if getattr(self.window(), "display_mode", "full") != "full":
            self.grid = None
            return
        w, h = max(1, self.width()), max(1, self.height())
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        for y in range(0, h, 3):
            ln(p, 0, y, w, y)
        p.end()
        self.grid = pm

    def paintEvent(self, e):
        p = QPainter(self)
        aa(p)
        w, h = self.width(), self.height()
        if getattr(self.window(), "display_mode", "full") != "full":
            p.setCompositionMode(QPainter.CompositionMode_Source)
            p.fillRect(self.rect(), QColor(0, 0, 0, 0))
            p.setCompositionMode(QPainter.CompositionMode_SourceOver)
            for index, (x, y, speed, size, phase) in enumerate(self.pts[:14]):
                yy = (y - anim.t * speed) % 1
                xx = x + .01 * math.sin(anim.t * .5 + phase)
                alpha = 16 + 28 * (.5 + .5 * math.sin(anim.t + phase))
                p.setPen(Qt.NoPen)
                p.setBrush(acol(anim.color, alpha))
                p.drawEllipse(QPointF(xx * w, yy * h), size, size)
            return

        g = QRadialGradient(w / 2, h / 2, max(w, h) * .65)
        idle_palette = anim.state in ("IDLE", "WAKE", "RETURNING_IDLE")
        kb = clamp(SIM.build * 1.4)
        g.setColorAt(0, QColor(mix_hex(BG, dk(.09), kb)))
        g.setColorAt(1, QColor(BG))
        p.fillRect(self.rect(), g)
        p.setPen(QPen(acol(RED, 16 * kb), 1))
        for x in range(0, w, 40):
            ln(p, x, 0, x, h)
        for y in range(0, h, 40):
            ln(p, 0, y, w, y)
        if self.grid:
            p.drawPixmap(0, 0, self.grid)
        p.setPen(Qt.NoPen)
        for x, y, sp, sz, ph in self.pts:
            yy = (y - anim.t * sp) % 1
            xx = x + .01 * math.sin(anim.t * .5 + ph)
            a = 40 + 70 * (.5 + .5 * math.sin(anim.t * 1.5 + ph))
            p.setBrush(acol(RED2, a * kb))
            p.drawEllipse(QPointF(xx * w, yy * h), sz, sz)
        sy = (anim.t * 90) % (h + 240) - 120
        sg = QLinearGradient(0, sy - 60, 0, sy + 60)
        sg.setColorAt(0, acol(anim.color, 0))
        sg.setColorAt(.5, acol(anim.color, 22 * kb))
        sg.setColorAt(1, acol(anim.color, 0))
        p.fillRect(QRectF(0, sy - 60, w, 120), sg)
        v = QRadialGradient(w / 2, h / 2, max(w, h) * .75)
        v.setColorAt(.6, QColor(0, 0, 0, 0))
        v.setColorAt(1, QColor(0, 0, 0, 190))
        p.fillRect(self.rect(), v)


class CinematicOverlay(QWidget):
    """Camada visual cinematográfica ligada ao estado real do JARVIS.

    Não executa lógica nem simula telemetria. Apenas transforma o estado atual
    em elementos visuais discretos: moldura, retícula, varredura e diagnóstico.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.progress = 0.0
        self.flash = 0.0
        self.last_state = anim.state
        self.boot_started = time.monotonic()

    def set_boot_progress(self, value):
        self.progress = clamp(value)
        self.update()

    def notify_state(self, state):
        if state != self.last_state:
            self.flash = 1.0
            self.last_state = state
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        aa(p)
        w, h = self.width(), self.height()
        if w < 300 or h < 200:
            return

        t = anim.t
        col = anim.color
        margin = 22
        arm = 34
        alpha = 115 + int(45 * (0.5 + 0.5 * math.sin(t * 2.1)))

        # Moldura técnica nos quatro cantos.
        pen = QPen(acol(col, alpha), 1.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        for x, y, sx, sy in (
            (margin, margin, 1, 1),
            (w - margin, margin, -1, 1),
            (margin, h - margin, 1, -1),
            (w - margin, h - margin, -1, -1),
        ):
            ln(p, x, y, x + arm * sx, y)
            ln(p, x, y, x, y + arm * sy)
            ln(p, x + 5 * sx, y + 7 * sy, x + 17 * sx, y + 7 * sy)

        # Retícula central muito discreta.
        cx, cy = w / 2, h / 2
        r = min(w, h) * .31
        p.setPen(QPen(acol(col, 26), 1))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.drawEllipse(QPointF(cx, cy), r * .78, r * .78)
        for a in range(0, 360, 45):
            rad = math.radians(a + t * 7)
            x1 = cx + math.cos(rad) * r * .91
            y1 = cy + math.sin(rad) * r * .91
            x2 = cx + math.cos(rad) * r * .99
            y2 = cy + math.sin(rad) * r * .99
            ln(p, x1, y1, x2, y2)

        # Linha de varredura independente do fundo.
        sy = (t * 115) % (h + 180) - 90
        sg = QLinearGradient(0, sy - 28, 0, sy + 28)
        sg.setColorAt(0, acol(col, 0))
        sg.setColorAt(.5, acol(col, 25))
        sg.setColorAt(1, acol(col, 0))
        p.fillRect(QRectF(0, sy - 28, w, 56), sg)

        # (textos SYSTEM/CORE/PERCEPTION/VERIFICATION removidos: colidiam com a barra de automação
        #  e já aparecem no núcleo e no seletor de estado)

        # Barra de atividade no rodapé.
        bar_w = min(430, w * .34)
        bx = (w - bar_w) / 2
        by = h - 30
        p.setPen(QPen(acol(RED_DARK, 160), 1))
        p.drawRect(QRectF(bx, by, bar_w, 3))
        level = clamp(anim.energy * .72 + anim.mic * .28)
        p.setPen(Qt.NoPen)
        p.setBrush(acol(col, 175))
        p.drawRect(QRectF(bx, by, bar_w * level, 3))

        # Flash breve quando o núcleo muda de estado.
        if self.flash > .001:
            p.setBrush(acol(col, int(42 * self.flash)))
            p.setPen(Qt.NoPen)
            p.drawRect(self.rect())
            self.flash *= .86
            self.update()

        # Sequência de inicialização visual — baseada no tempo real da janela.
        if self.progress < 1.0:
            p.setFont(F(6, True, "Consolas", 1))
            p.setPen(acol(col, 160))
            p.drawText(QRectF(bx, by - 16, bar_w, 12),
                       Qt.AlignCenter, f"INITIALIZING CORE  {int(self.progress * 100):03d}%")



class CompactWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = 0.0
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setCursor(Qt.PointingHandCursor)

    def set_progress(self, value):
        self.progress = clamp(value)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            backend.activate()

    def paintEvent(self, event):
        painter = QPainter(self)
        aa(painter)
        w, h = self.width(), self.height()
        SIM.step(anim, live, backend)
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        veil = QRadialGradient(w / 2, h * .46, min(w, h) * .52)      # breu escuridão atrás do cérebro
        veil.setColorAt(0, QColor(1, 6, 16, 205))
        veil.setColorAt(.7, QColor(1, 6, 16, 120))
        veil.setColorAt(1, QColor(1, 6, 16, 0))
        painter.fillRect(self.rect(), veil)
        SIM.draw(painter, w / 2, h * .44, min(min(w, h) * .22, 130), w, h, False)


def _topmost(widget):
    """Reafirma sempre-no-topo no Windows sem roubar o foco."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            fn = ctypes.windll.user32.SetWindowPos
            fn.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, wintypes.UINT]
            fn.restype = wintypes.BOOL
            fn(wintypes.HWND(int(widget.winId())), wintypes.HWND(-1),
               0, 0, 0, 0, 0x0013)
        else:
            widget.raise_()
    except Exception:
        pass


class FloatingButton(QWidget):
    """Botão flutuante: janela independente, sem bordas, sempre no topo, que não rouba o foco.
    Clique = minimizar/restaurar a HUD. Arraste = muda de canto. Botão direito = menu."""
    SIZE = 60
    MARGIN = 20
    clicked_toggle = Signal()
    cornerChanged = Signal(str)
    menuRequested = Signal(QPoint)

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(FLOAT_FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setMask(QRegion(0, 0, self.SIZE, self.SIZE, QRegion.Ellipse))   # só o círculo recebe cliques
        self.setCursor(Qt.PointingHandCursor)
        self.setWindowTitle("JARVIS botão")
        self.mode, self.paused, self.monitor, self.pending, self.hud_open = copilot.MODE_OFF, False, "off", 0, False
        self._press_global = None
        self._press_offset = QPoint()
        self._dragging = False

    # ---- estado
    def set_status(self, mode, paused, monitor, pending, hud_open):
        changed = (mode, paused, monitor, pending, hud_open) != (
            self.mode, self.paused, self.monitor, self.pending, self.hud_open)
        self.mode, self.paused, self.monitor, self.pending, self.hud_open = mode, paused, monitor, pending, hud_open
        if changed:
            tela = {"active": "monitorando a tela", "paused": "monitoramento pausado",
                    "skipped": "observação suspensa", "off": "tela não monitorada"}.get(monitor, monitor)
            self.setToolTip(f"J.A.R.V.I.S. — modo {copilot.MODE_SHORT[mode]} — {tela}\n"
                            f"Clique: {'minimizar' if hud_open else 'abrir'} a HUD · arraste: mudar de canto · "
                            f"botão direito: menu")
            self.update()

    def keep_on_top(self):
        if self.isVisible():
            _topmost(self)

    # ---- posição
    def _screen_rect(self, point=None):
        screen = QApplication.screenAt(point) if point is not None else None
        screen = screen or QApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

    def place(self, corner):
        area = self._screen_rect(self.geometry().center() if self.isVisible() else None)
        left = area.left() + self.MARGIN
        right = area.right() - self.SIZE - self.MARGIN + 1
        top = area.top() + self.MARGIN
        bottom = area.bottom() - self.SIZE - self.MARGIN + 1
        x = left if corner.endswith("left") else right
        y = top if corner.startswith("top") else bottom
        self.move(x, y)

    def corner_now(self):
        area = self._screen_rect(self.geometry().center())
        c = self.geometry().center()
        vertical = "top" if c.y() < area.center().y() else "bottom"
        horizontal = "left" if c.x() < area.center().x() else "right"
        return f"{vertical}-{horizontal}"

    # ---- mouse
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._press_offset = self._press_global - self.frameGeometry().topLeft()
            self._dragging = False
        elif e.button() == Qt.RightButton:
            self.menuRequested.emit(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self._press_global is None or not (e.buttons() & Qt.LeftButton):
            return
        pos = e.globalPosition().toPoint()
        if not self._dragging and (pos - self._press_global).manhattanLength() > 6:
            self._dragging = True
        if self._dragging:
            self.move(pos - self._press_offset)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self._press_global is None:
            return
        was_drag = self._dragging
        self._press_global, self._dragging = None, False
        if was_drag:
            corner = self.corner_now()          # encaixa no canto mais próximo
            self.place(corner)
            self.cornerChanged.emit(corner)
        else:
            self.clicked_toggle.emit()

    # ---- desenho (mesma linguagem visual do núcleo da HUD)
    def paintEvent(self, e):
        p = QPainter(self)
        aa(p)
        w = self.width()
        cx = cy = w / 2
        col = anim.color
        mode_col = QColor(MODE_COLORS[self.mode])
        pulse = 1 + .05 * math.sin(anim.t * 2.4)
        g = QRadialGradient(cx, cy, w * .5)
        g.setColorAt(0, acol(col, 95))
        g.setColorAt(.6, acol(col, 28))
        g.setColorAt(1, acol(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(cx, cy), w * .5, w * .5)

        p.setBrush(acol(dk(.06), 235))
        p.setPen(QPen(acol(col, 220), 1.6))
        p.drawEllipse(QPointF(cx, cy), 21 * pulse, 21 * pulse)

        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(acol(col, 235), 1.6))
        p.drawArc(QRectF(cx - 25, cy - 25, 50, 50), int((anim.t * 40) % 360 * 16), int(110 * 16))

        if self.hud_open:                         # HUD aberta: ícone "recolher"
            p.setPen(QPen(acol(WHITE, 235), 2.4, Qt.SolidLine, Qt.RoundCap))
            ln(p, cx - 7, cy + 4, cx + 7, cy + 4)
        else:                                     # HUD recolhida: núcleo (clique para abrir)
            core = QRadialGradient(cx, cy, 11)
            core.setColorAt(0, acol(WHITE, 250))
            core.setColorAt(.45, acol(col, 245))
            core.setColorAt(1, acol(col, 40))
            p.setPen(Qt.NoPen)
            p.setBrush(core)
            p.drawEllipse(QPointF(cx, cy), 9 * pulse, 9 * pulse)

        if self.monitor == "active":              # anel vermelho pulsante = tela SENDO monitorada
            a = int(120 + 120 * (.5 + .5 * math.sin(anim.t * 4)))
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(acol(ERR, a), 2.2))
            p.drawEllipse(QPointF(cx, cy), 28, 28)

        # ponto do modo (cinza = desativado, verde = assistente, âmbar = autônomo)
        p.setPen(QPen(acol(BG, 255), 2))
        p.setBrush(mode_col)
        p.drawEllipse(QPointF(w - 12, 12), 6, 6)
        if self.paused:                           # pausa: barrinhas no ponto
            p.setPen(QPen(acol(BG, 255), 1.6))
            ln(p, w - 14, 9.5, w - 14, 14.5)
            ln(p, w - 10, 9.5, w - 10, 14.5)
        if self.pending > 0:                      # sugestões pendentes
            p.setPen(QPen(acol(BG, 255), 2))
            p.setBrush(QColor(AMBER))
            p.drawEllipse(QPointF(12, w - 12), 7, 7)
            p.setPen(QColor(BG))
            p.setFont(F(7, True, "Segoe UI"))
            p.drawText(QRectF(5, w - 19, 14, 14), Qt.AlignCenter, str(min(self.pending, 9)))


class SuggestionToast(QWidget):
    """Aviso discreto ao lado do botão flutuante. Não rouba o foco. Sugestões: some sozinho depois de
    TOAST_SECONDS (continua pendente, com o contador no botão). Resultados: ficam até você fechar."""
    TOAST_SECONDS = 14
    accepted = Signal(int)
    dismissed = Signal(int)

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(FLOAT_FLAGS)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedWidth(340)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.sid = None
        self.anchor = None
        self.setStyleSheet(
            f"SuggestionToast {{ background: #0B0C0E; border: 1px solid {RED}; border-radius: 8px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(8)
        self.title = QLabel("")
        self.title.setObjectName("clabel")
        self.body = QLabel("")
        self.body.setWordWrap(True)
        self.body.setObjectName("csug")
        self.body.setTextInteractionFlags(Qt.NoTextInteraction)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.ok = QPushButton("EXECUTAR")
        self.ok.setObjectName("cbtn")
        self.no = QPushButton("IGNORAR")
        self.no.setObjectName("cbtn")
        for b in (self.ok, self.no):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
        row.addStretch(1)
        row.addWidget(self.ok)
        row.addWidget(self.no)
        lay.addWidget(self.title)
        lay.addWidget(self.body)
        lay.addLayout(row)
        self.ok.clicked.connect(self._accept)
        self.no.clicked.connect(self._dismiss)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    @staticmethod
    def action_label(s):
        if s.get("kind") == "analyze":
            return "ANALISAR"
        if not s.get("tool"):
            return "OK"
        return "CONFIRMAR" if s.get("tier") == "confirm" else "EXECUTAR"

    def show_suggestion(self, s, anchor):
        self.sid, self.anchor = s["id"], anchor
        self.title.setText("J.A.R.V.I.S. ▸ SUGESTÃO")
        self.body.setText(s["text"])
        self.ok.setText(self.action_label(s))
        self.ok.show()
        self.no.setText("IGNORAR")
        self._show(self.TOAST_SECONDS * 1000)

    def show_notice(self, title, text, anchor):
        self.sid, self.anchor = None, anchor
        self.title.setText(f"J.A.R.V.I.S. ▸ {title.upper()}")
        self.body.setText(text)
        self.ok.hide()
        self.no.setText("FECHAR")
        self._show(0)

    def drop(self, sid):
        if self.sid == sid and self.isVisible():
            self.hide()

    def _show(self, ms):
        self.adjustSize()
        self.reposition()
        self.show()
        _topmost(self)
        self._hide_timer.stop()
        if ms:
            self._hide_timer.start(ms)

    def reposition(self):
        if self.anchor is None:
            return
        a = self.anchor
        screen = QApplication.screenAt(a.center()) or QApplication.primaryScreen()
        area = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        x = a.right() - self.width() + 1 if a.center().x() > area.center().x() else a.left()
        y = a.top() - self.height() - 10 if a.center().y() > area.center().y() else a.bottom() + 10
        self.move(max(area.left(), min(x, area.right() - self.width() + 1)),
                  max(area.top(), min(y, area.bottom() - self.height() + 1)))

    def keep_on_top(self):
        _topmost(self)

    def _accept(self):
        sid, self.sid = self.sid, None
        self.hide()
        if sid is not None:
            self.accepted.emit(sid)

    def _dismiss(self):
        sid, self.sid = self.sid, None
        self.hide()
        if sid is not None:
            self.dismissed.emit(sid)


class ExcludedAppsDialog(QDialog):
    """Apps (nome do processo ou trecho do título da janela) que o JARVIS NUNCA captura."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apps sem monitoramento")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        info = QLabel("O JARVIS não captura a tela quando o programa ou a janela contém um destes textos.\n"
                      "Gerenciadores de senha e janelas de login/banco já são sempre ignorados.\n"
                      "Ex.: whatsapp, outlook.exe, extrato")
        info.setObjectName("clabel")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.list = QListWidget()
        lay.addWidget(self.list, 1)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("nome do programa ou trecho do título...")
        lay.addWidget(self.edit)
        row = QHBoxLayout()
        add, rem, close = QPushButton("ADICIONAR"), QPushButton("REMOVER SELECIONADO"), QPushButton("FECHAR")
        for b in (add, rem, close):
            b.setObjectName("cbtn")
            row.addWidget(b)
        lay.addLayout(row)
        add.clicked.connect(self._add)
        rem.clicked.connect(self._remove)
        close.clicked.connect(self.accept)
        self.edit.returnPressed.connect(self._add)
        self._refresh()

    def _refresh(self):
        self.list.clear()
        self.list.addItems(copilot.excluded_apps())

    def _add(self):
        if copilot.add_excluded(self.edit.text()):
            self.edit.clear()
        self._refresh()

    def _remove(self):
        item = self.list.currentItem()
        if item:
            copilot.remove_excluded(item.text())
        self._refresh()


class CopilotBar(QWidget):
    """Faixa de controle da automação: modo, pausar, parar tarefa, intervalo, apps excluídos, indicador."""
    minimizeRequested = Signal()
    excludedClicked = Signal()

    def __init__(self):
        super().__init__()
        self.setFixedHeight(44)
        self._consented = False
        self._auto_consented = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(8)

        def label(text):
            lb = QLabel(text)
            lb.setObjectName("clabel")
            return lb

        lay.addWidget(label("AUTOMAÇÃO ▸"))
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.mode_buttons = {}
        for mode, text, name, tip in (
            (copilot.MODE_OFF, "DESATIVADO", "modeOff", "Só responde quando você chama. Nenhuma captura de tela."),
            (copilot.MODE_ASSISTANT, "ASSISTENTE", "modeAssist", "Observa a tela autorizada e SUGERE. Não executa nada sozinho."),
            (copilot.MODE_AUTONOMOUS, "AUTÔNOMO SUPERVISIONADO", "modeAuto",
             "Executa sozinho só ações de baixo risco. O resto pede a sua confirmação."),
            (copilot.MODE_OBSERVER, "OBSERVADOR", "modeObserver",
             "Acompanha o contexto do computador e fala quando detectar algo realmente útil."),
        ):
            b = QPushButton(text)
            b.setObjectName(name)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, m=mode: self._choose(m))
            self.group.addButton(b)
            self.mode_buttons[mode] = b
            lay.addWidget(b)

        self.pause_btn = QPushButton("PAUSAR")
        self.pause_btn.setObjectName("cbtn")
        self.pause_btn.setCheckable(True)
        self.pause_btn.setToolTip("Pausa IMEDIATAMENTE a observação: nenhuma captura é feita enquanto pausado.")
        self.stop_btn = QPushButton("PARAR TAREFA")
        self.stop_btn.setObjectName("cbtnStop")
        self.stop_btn.setToolTip("Interrompe a tarefa em execução e descarta sugestões e confirmações pendentes.")
        for b in (self.pause_btn, self.stop_btn):
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            lay.addWidget(b)
        self.pause_btn.clicked.connect(lambda: copilot.toggle_pause())
        self.stop_btn.clicked.connect(lambda: copilot.stop_task())

        lay.addWidget(label("INTERVALO"))
        self.interval = QComboBox()
        self.interval.setObjectName("cbo")
        for sec in copilot.INTERVALS:
            self.interval.addItem(f"{sec} s", sec)
        self.interval.setToolTip("De quanto em quanto tempo o JARVIS confere a janela ativa. "
                                 "O modelo de visão só é chamado quando a tela muda de verdade.")
        self.interval.currentIndexChanged.connect(self._interval_changed)
        lay.addWidget(self.interval)

        self.apps_btn = QPushButton("APPS SEM MONITORAMENTO")
        self.apps_btn.setObjectName("cbtn")
        self.apps_btn.setFocusPolicy(Qt.NoFocus)
        self.apps_btn.clicked.connect(self.excludedClicked.emit)
        lay.addWidget(self.apps_btn)

        self.indicator = QLabel("")
        self.indicator.setObjectName("clabel")
        lay.addWidget(self.indicator, 1)

        self.min_btn = HudButton("min")
        self.min_btn.setToolTip("Minimizar a HUD (o botão flutuante continua na tela)")
        self.min_btn.clicked.connect(self.minimizeRequested.emit)
        lay.addWidget(self.min_btn)
        self.sync()

    def _choose(self, mode):
        parent = self.window()
        if mode != copilot.MODE_OFF and copilot.get_mode() == copilot.MODE_OFF and not self._consented:
            ans = QMessageBox.question(
                parent, "Monitoramento da tela",
                "O JARVIS vai observar a janela ativa e, quando a tela mudar, analisar uma captura com o modelo "
                "LOCAL do Ollama.\n\n• Nada é enviado para a internet.\n• Capturas não são salvas em disco.\n"
                "• Gerenciadores de senha e janelas de login/banco são ignorados.\n"
                "• Com a HUD aberta (ela cobre a tela) não há observação: minimize-a para ele trabalhar.\n\n"
                "Ativar o monitoramento?")
            if ans != QMessageBox.Yes:
                self.sync()
                return
            self._consented = True
        if mode == copilot.MODE_AUTONOMOUS and not self._auto_consented:
            ans = QMessageBox.question(
                parent, "Modo autônomo supervisionado",
                "Neste modo o JARVIS pode executar SOZINHO ações de baixo risco (abrir app da lista, pesquisar, "
                "mídia/volume, buscar arquivos).\n\nAbrir links, capturas de tela e qualquer ação sensível continuam "
                "pedindo a sua confirmação.\n\nAtivar o modo autônomo?")
            if ans != QMessageBox.Yes:
                self.sync()
                return
            self._auto_consented = True
        copilot.set_mode(mode)
        self.sync()

    def _interval_changed(self, _index):
        copilot.set_interval(self.interval.currentData())

    def sync(self):
        mode = copilot.get_mode()
        for m, b in self.mode_buttons.items():
            b.blockSignals(True)
            b.setChecked(m == mode)
            b.blockSignals(False)
        paused = copilot.is_paused()
        self.pause_btn.blockSignals(True)
        self.pause_btn.setChecked(paused)
        self.pause_btn.setText("RETOMAR" if paused else "PAUSAR")
        self.pause_btn.blockSignals(False)
        self.pause_btn.setEnabled(mode != copilot.MODE_OFF)
        idx = self.interval.findData(copilot.get_interval())
        self.interval.blockSignals(True)
        if idx >= 0:
            self.interval.setCurrentIndex(idx)
        self.interval.blockSignals(False)
        self.apps_btn.setText(f"APPS SEM MONITORAMENTO ({len(copilot.excluded_apps())})")
        state, reason = copilot.monitor_state()
        if mode == copilot.MODE_OFF:
            text, color = "○ TELA NÃO MONITORADA", MUTED
        elif paused:
            text, color = "❚❚ MONITORAMENTO PAUSADO — NENHUMA CAPTURA", AMBER
        elif state == "active":
            text, color = "● MONITORANDO A TELA (LOCAL)", ERR
        elif state == "skipped":
            hint = " — minimize a HUD para observar" if reason == "HUD aberta" else ""
            text, color = f"○ OBSERVAÇÃO SUSPENSA ({reason}){hint}", MUTED
        else:
            text, color = "○ AGUARDANDO", MUTED
        snapshot = copilot.status_snapshot()
        task = snapshot.get("task", {})
        task_state = task.get("state", "IDLE") if isinstance(task, dict) else "IDLE"
        if task_state not in ("IDLE", "COMPLETED", "CANCELLED"):
            goal = str(task.get("goal", "")).strip().replace("<", "&lt;").replace(">", "&gt;")[:72]
            text = f"{text}  •  {task_state}  •  {goal}"
        elif mode == copilot.MODE_OBSERVER:
            ctx = snapshot.get("context", {}) if isinstance(snapshot, dict) else {}
            app = str((ctx.get("application") or {}).get("name") or "").strip()[:28]
            activity = str(ctx.get("activity") or "").strip()[:32]
            if app or activity:
                detail = " • ".join(x for x in (app, activity) if x)
                text = f"{text}  •  CONTEXTO: {detail}"
        self.indicator.setText(f'<span style="color:{color}">{html.escape(text)}</span>')


class CopilotPanel(HudPanel):
    """Histórico das observações e ações + cartão da sugestão pendente."""
    COLORS = {"observação": TEXT, "sugestão": AMBER, "ação": GREEN, "erro": ERR, "sistema": MUTED}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 44, 10, 12)
        lay.setSpacing(6)
        self.card = QWidget()
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(4)
        self.sug_label = QLabel("")
        self.sug_label.setObjectName("csug")
        self.sug_label.setWordWrap(True)
        row = QHBoxLayout()
        self.ok = QPushButton("EXECUTAR")
        self.no = QPushButton("IGNORAR")
        for b in (self.ok, self.no):
            b.setObjectName("cbtn")
            b.setFocusPolicy(Qt.NoFocus)
        row.addStretch(1)
        row.addWidget(self.ok)
        row.addWidget(self.no)
        cl.addWidget(self.sug_label)
        cl.addLayout(row)
        self.card.hide()
        lay.addWidget(self.card)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(300)
        lay.addWidget(self.view, 1)
        self.current = None
        self.ok.clicked.connect(lambda: self.current is not None and copilot.accept_suggestion(self.current))
        self.no.clicked.connect(lambda: self.current is not None and copilot.dismiss_suggestion(self.current))
        for entry in list(copilot.history):
            self.add_history(entry)
        self.refresh()

    def add_history(self, entry):
        color = self.COLORS.get(entry["kind"], TEXT)
        self.view.appendHtml(
            f'<span style="color:{MUTED}">[{entry["t"]}]</span> '
            f'<span style="color:{color}">{html.escape(entry["kind"].upper())} ▸ {html.escape(entry["text"])}</span>')

    def refresh(self):
        pending = copilot.pending_suggestions()
        if not pending:
            self.current = None
            self.card.hide()
            return
        s = pending[0]
        self.current = s["id"]
        more = f"  (+{len(pending) - 1})" if len(pending) > 1 else ""
        self.sug_label.setText(f"SUGESTÃO ▸ {s['text']}{more}")
        self.ok.setText(SuggestionToast.action_label(s))
        self.card.show()


# ============================================================ JANELA
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(APP_TITLE)
        self.display_mode = "compact"
        self.hud_minimized = False
        self._covering = False
        self._saved_geometry = None
        self._saved_fullscreen = False
        self._transition_direction = None
        self._transition_start_progress = 0.0
        self._transition_end_progress = 0.0
        self.setMinimumSize(180, 180)
        self.resize(COMPACT_SIZE, COMPACT_SIZE)
        bg = Background()
        self.background = bg
        self.setCentralWidget(bg)
        self.cinematic = CinematicOverlay(bg)
        self.cinematic.setGeometry(bg.rect())
        self.cinematic.hide()
        root = QVBoxLayout(bg)
        root.setContentsMargins(14, 0, 14, 14)
        root.setSpacing(10)
        self.top = TopBar()
        root.addWidget(self.top)
        self.cbar = CopilotBar()
        root.addWidget(self.cbar)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        self.status_p = StatusPanel("STATUS DO SISTEMA", False, .3, -1)
        self.mods_p = ModulesPanel("MÓDULOS", False, .5, -1)
        self.diag_p = DiagPanel("DIAGNÓSTICO", False, .7, -1)
        self.core = NeuralCore(anim, live, backend)
        self.inter = InteractionPanel("INTERFACE DE INTERAÇÃO", False, .9, 0)
        self.net_p = NetworkPanel("REDE E CONEXÕES", False, .4, 1)
        self.act_p = ActivityPanel("HISTÓRICO DE ATIVIDADE", False, .6, 1)
        self.console = ConsolePanel("CONSOLE DE EVENTOS", False, .8, 1)
        self.cpanel = CopilotPanel("AUTOMAÇÃO INTELIGENTE", False, .85, 1)

        def column(widgets, stretches):
            c = QWidget()
            c.setMinimumWidth(250)
            c.setMaximumWidth(390)
            c.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            lay = QVBoxLayout(c)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(10)
            for w_, s_ in zip(widgets, stretches):
                lay.addWidget(w_, s_)
            return c

        left = column([self.status_p, self.mods_p, self.diag_p], [5, 5, 5])
        right = column([self.net_p, self.act_p, self.console, self.cpanel], [4, 2, 3, 5])
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)
        cl.addWidget(self.core, 5)
        self.inter.setMinimumHeight(220)
        cl.addWidget(self.inter, 2)
        body.addWidget(left, 3)
        body.addWidget(center, 6)
        body.addWidget(right, 3)

        from PySide6.QtWidgets import QGraphicsOpacityEffect
        self._fx = []                      # cada painel só existe quando o cérebro o materializa
        for key_, pan_ in (("status_p", self.status_p), ("mods_p", self.mods_p), ("diag_p", self.diag_p),
                           ("net_p", self.net_p), ("act_p", self.act_p), ("console", self.console), ("cpanel", self.cpanel)):
            fx = QGraphicsOpacityEffect(pan_)
            fx.setOpacity(0.0)
            pan_.setGraphicsEffect(fx)
            self._fx.append((key_, fx, pan_))
        self._ui_fx = []                   # barra superior e campo de comando: só quando acordado / sob o mouse
        for key_, wd_ in (("top", self.top), ("top", self.cbar), ("bottom", self.inter)):
            fx = QGraphicsOpacityEffect(wd_)
            fx.setOpacity(0.0)
            wd_.setGraphicsEffect(fx)
            self._ui_fx.append((key_, fx, wd_))
        self.flow = FlowLayer(bg, self.core, {k: p_ for k, _f, p_ in self._fx})
        self.flow.setGeometry(bg.rect())
        self.flow.hide()
        self.animated = [bg, self.top, self.core, self.status_p, self.mods_p, self.diag_p,
                         self.net_p, self.act_p, self.console, self.cpanel, self.inter, self.inter.chip,
                         self.inter.mic, self.inter.send, self.cinematic]
        self.full_widgets = [self.top, self.cbar, left, center, right]
        self.compact = CompactWidget(bg)
        self.compact.setGeometry(bg.rect())
        self.compact.show()
        for widget in self.full_widgets:
            widget.hide()
        self.animated.append(self.compact)

        self.transition_animation = QPropertyAnimation(self, b"geometry", self)
        self.transition_animation.setEasingCurve(QEasingCurve(QEasingCurve.Type.InOutCubic))
        self.transition_animation.valueChanged.connect(self._update_transition_visual)
        self.transition_animation.finished.connect(self._finish_transition)
        self.setGeometry(self._compact_geometry())
        self.last_interaction = time.monotonic()

        self.inter.submitted.connect(self.on_submit)
        self.inter.micClicked.connect(self.on_mic_clicked)
        self.inter.quickCommand.connect(self.on_submit)
        self.inter.stopClicked.connect(lambda: backend.abort_agent())
        self.core.clicked.connect(self.on_mic_clicked)
        self.core.nodeClicked.connect(self.on_module_clicked)
        self.mods_p.moduleClicked.connect(self.on_module_clicked)
        self.mods_p.moduleMenu.connect(self.show_module_menu)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fs)
        QShortcut(QKeySequence("Escape"), self, activated=self.on_escape)
        self._allow_exit = False
        self._hide_to_tray_pending = False
        self._setup_tray()

        self.fab = FloatingButton()
        self.animated.append(self.fab)
        self.fab.place(copilot.button_corner())
        self.fab.clicked_toggle.connect(self.toggle_hud)
        self.fab.cornerChanged.connect(copilot.set_button_corner)
        self.fab.menuRequested.connect(self.show_fab_menu)
        self.toast = SuggestionToast()
        self.toast.accepted.connect(copilot.accept_suggestion)
        self.toast.dismissed.connect(copilot.dismiss_suggestion)
        self.cbar.minimizeRequested.connect(self.minimize_hud)
        self.cbar.excludedClicked.connect(self.show_excluded_dialog)
        copilot.set_hud_probe(self._hud_covering)
        copilot.start()

        backend.add_log("Interface gráfica iniciada.")
        backend.start_voice()

        telemetria.start()
        live["s"] = telemetria.snapshot()
        self._next_tel = 0.0
        self._next_audio = 0.0
        self._bucket_t = time.monotonic()
        self.last = time.perf_counter()
        self.frame = 0
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def _sync_cinematic(self):
        if not hasattr(self, "cinematic"):
            return
        self.cinematic.setGeometry(self.background.rect())
        full = self.display_mode == "full" and self.isVisible() and not self.hud_minimized
        self.cinematic.setVisible(full and SIM.build > .35)
        if hasattr(self, "flow"):
            self.flow.setGeometry(self.background.rect())
            self.flow.setVisible(full)
            if full:
                self.flow.raise_()
        if full and SIM.build > .35:
            self.cinematic.raise_()
            self.cinematic.notify_state(anim.state)

    def _compact_geometry(self):
        fab = getattr(self, "fab", None)
        if fab is not None and fab.isVisible():              # o orbe nasce/volta no botão flutuante
            c = fab.geometry().center()
            scr = QApplication.screenAt(c) or QApplication.primaryScreen()
            area = scr.availableGeometry() if scr else QRect(0, 0, 1920, 1080)
            x = max(area.left(), min(c.x() - COMPACT_SIZE // 2, area.right() - COMPACT_SIZE + 1))
            y = max(area.top(), min(c.y() - COMPACT_SIZE // 2, area.bottom() - COMPACT_SIZE + 1))
            return QRect(x, y, COMPACT_SIZE, COMPACT_SIZE)
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        margin = 24
        return QRect(available.right() - COMPACT_SIZE - margin + 1,
                     available.bottom() - COMPACT_SIZE - margin + 1,
                     COMPACT_SIZE, COMPACT_SIZE)

    def _full_geometry(self):
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)
        return QRect(available)

    def _set_full_widgets_visible(self, visible):
        for widget in self.full_widgets:
            widget.setVisible(visible)

    def _begin_expansion(self):
        if self.display_mode == "full":
            return
        start_progress = self.compact.progress if self.display_mode == "contracting" else 0.0
        self.transition_animation.stop()
        self.display_mode = "expanding"
        self._transition_direction = "expand"
        self._transition_start_progress = start_progress
        self._transition_end_progress = 1.0
        self._set_full_widgets_visible(False)
        self.compact.show()
        self.compact.set_progress(start_progress)
        self.transition_animation.setDuration(TRANSITION_MS)
        self.transition_animation.setStartValue(self.geometry())
        self.transition_animation.setEndValue(self._full_geometry())
        self.transition_animation.start()

    def _begin_contraction(self):
        if self.display_mode == "compact":
            backend.finish_return_to_idle()
            return
        start_progress = self.compact.progress if self.display_mode == "expanding" else 1.0
        self.transition_animation.stop()
        self.display_mode = "contracting"
        self._transition_direction = "contract"
        self._transition_start_progress = start_progress
        self._transition_end_progress = 0.0
        self._set_full_widgets_visible(False)
        self.compact.show()
        self.compact.set_progress(start_progress)
        self.transition_animation.setDuration(TRANSITION_MS)
        self.transition_animation.setStartValue(self.geometry())
        self.transition_animation.setEndValue(self._compact_geometry())
        self.transition_animation.start()

    def _update_transition_visual(self, value):
        duration = max(1, self.transition_animation.duration())
        fraction = clamp(self.transition_animation.currentTime() / duration)
        progress = self._transition_start_progress + (
            self._transition_end_progress - self._transition_start_progress
        ) * fraction
        self.compact.set_progress(progress)

    def _finish_transition(self):
        direction = self._transition_direction
        self._transition_direction = None
        if direction == "expand":
            self.display_mode = "full"
            anim.summon_t = anim.t          # replay da animação de entrada dos painéis
            self._set_full_widgets_visible(True)
            self.compact.hide()
            self.compact.set_progress(0)
            self.background.resizeEvent(None)
            self.background.update()
            self.fab.keep_on_top()
        elif direction == "contract":
            self.display_mode = "compact"
            self._set_full_widgets_visible(False)
            self.compact.show()
            self.compact.set_progress(0)
            self.background.update()
            backend.finish_return_to_idle()
            if self._hide_to_tray_pending:
                self._hide_to_tray_pending = False
                self.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "compact"):
            self.compact.setGeometry(self.centralWidget().rect())
        if hasattr(self, "cinematic"):
            self.cinematic.setGeometry(self.centralWidget().rect())

    # ---- estado
    def set_state(self, state):
        if state not in backend.STATES:
            return
        anim.state = state
        if hasattr(self, "cinematic"):
            self.cinematic.notify_state(state)
        if state == "WAKE":
            if self.hud_minimized or not self.isVisible():
                self._show_window()
            self._begin_expansion()
        elif state == "RETURNING_IDLE":
            self._begin_contraction()
        elif state in ("LISTENING", "ERROR"):
            self.last_interaction = time.monotonic()

    def on_submit(self, text):
        self.last_interaction = time.monotonic()
        SIM.plan(text)
        threading.Thread(target=backend.process_command, args=(text,), daemon=True).start()

    def on_mic_clicked(self):
        backend.toggle_microphone()

    def on_module_clicked(self, name):
        self.last_interaction = time.monotonic()
        self.inter.add_sys(ModulesPanel.describe(name))

    def show_module_menu(self, name, pos):
        menu = QMenu(self)
        menu.addAction(name).setEnabled(False)
        menu.addSeparator()
        if name in ("RECONHECIMENTO DE VOZ", "SÍNTESE DE VOZ"):
            menu.addAction("Ativar / pausar escuta", self.on_mic_clicked)
            menu.addAction("Reiniciar voz", self.restart_voice)
        elif name == "AUTOMAÇÃO":
            menu.addAction("Pausar / retomar automação", lambda: copilot.toggle_pause())
            menu.addAction("Parar tarefa em execução", lambda: copilot.stop_task())
        menu.addAction("Copiar detalhes", lambda: QApplication.clipboard().setText(ModulesPanel.describe(name)))
        menu.exec(pos)

    def _setup_tray(self):
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("J.A.R.V.I.S.")
        menu = QMenu(self)
        menu.addAction("J.A.R.V.I.S.").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Abrir HUD", self.open_hud)
        menu.addAction("Minimizar HUD", self.compact_from_tray)
        menu.addAction("Pausar / retomar automação", lambda: copilot.toggle_pause())
        menu.addAction("Ativar / desativar escuta", backend.toggle_microphone)
        menu.addAction("Configurações", self.show_settings)
        menu.addAction("Reiniciar voz", self.restart_voice)
        import autostart
        self.autostart_action = menu.addAction("Iniciar com Windows")
        self.autostart_action.setCheckable(True)
        self.autostart_action.setChecked(autostart.is_enabled())
        self.autostart_action.toggled.connect(self.toggle_autostart)
        menu.addSeparator()
        menu.addAction("Sair", self.exit_from_tray)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        if self._tray_available:
            self.tray.show()

    # ---- minimizar / restaurar (botão flutuante, botão da HUD, bandeja)
    def _update_covering(self):
        """Calculado na thread da interface; o copilot (outra thread) só lê o valor em cache."""
        self._covering = bool(self.isVisible() and self.display_mode != "compact")

    def _hud_covering(self):
        """True quando a HUD (que ocupa a tela toda) está visível: então não há o que observar."""
        return self._covering

    def _show_window(self):
        self.hud_minimized = False
        self._hide_to_tray_pending = False
        self.show()
        self.raise_()
        self.activateWindow()
        self.fab.keep_on_top()
        self._update_covering()
        self._sync_fab()

    def minimize_hud(self):
        """Recolhe a HUD. O botão flutuante continua na tela. Só acontece por clique do usuário."""
        if self.hud_minimized:
            return
        self.hud_minimized = True
        self._saved_geometry = self.geometry()
        self._saved_fullscreen = self.isFullScreen()
        if self.isVisible() and backend.is_assistant_active() and backend.return_to_idle():
            self._hide_to_tray_pending = True       # contrai no orbe e esconde ao terminar a animação
        else:
            self._hide_to_tray_pending = False      # ocupado (pensando/falando/agindo): a tarefa continua
            self.hide()
        self.toast.hide()
        self._update_covering()
        self._sync_fab()

    def restore_hud(self):
        """Restaura a HUD; com a janela recolhida ela cresce a partir do botão flutuante."""
        was_hidden = self.hud_minimized or not self.isVisible()
        if self.display_mode == "compact":
            self.setGeometry(self._compact_geometry())       # o orbe nasce no botão flutuante
        self._show_window()
        if self.display_mode == "full" and was_hidden and self._saved_geometry is not None:
            if self._saved_fullscreen:
                self.showFullScreen()
            else:
                self.setGeometry(self._saved_geometry)   # tamanho e posição de antes de minimizar
        if not backend.is_assistant_active():
            backend.activate()                       # WAKE -> expansão
        elif self.display_mode == "compact":
            self._begin_expansion()
        self.toast.hide()

    def toggle_hud(self):
        if self.hud_minimized or not self.isVisible():
            self.restore_hud()
        else:
            self.minimize_hud()

    def start_minimized(self):
        """Inicia só com o botão flutuante visível (como a HUD só abre quando chamada)."""
        self.hud_minimized = True
        self.hide()
        self.fab.show()
        self.fab.keep_on_top()
        self._sync_fab()

    def _sync_fab(self):
        self.fab.set_status(copilot.get_mode(), copilot.is_paused(), copilot.monitor_state()[0],
                            len(copilot.pending_suggestions()), not self.hud_minimized and self.isVisible())

    def show_fab_menu(self, pos):
        menu = QMenu()
        hud_open = not self.hud_minimized and self.isVisible()
        menu.addAction("Minimizar HUD" if hud_open else "Abrir HUD", self.toggle_hud)
        menu.addSeparator()
        for mode in copilot.MODES:
            act = menu.addAction(f"Modo: {copilot.MODE_LABELS[mode].capitalize()}")
            act.setCheckable(True)
            act.setChecked(copilot.get_mode() == mode)
            act.triggered.connect(lambda _=False, m=mode: self.cbar._choose(m))
        pause = menu.addAction("Retomar automação" if copilot.is_paused() else "Pausar automação")
        pause.setEnabled(copilot.get_mode() != copilot.MODE_OFF)
        pause.triggered.connect(lambda: copilot.toggle_pause())
        menu.addAction("Parar tarefa em execução", lambda: copilot.stop_task())
        pending = copilot.pending_suggestions()
        if pending:
            menu.addSeparator()
            menu.addAction(f"Ver sugestão pendente ({len(pending)})",
                           lambda: self.toast.show_suggestion(pending[0], self.fab.geometry()))
        menu.exec(pos)

    def show_excluded_dialog(self):
        ExcludedAppsDialog(self).exec()
        self.cbar.sync()

    def _copilot_drain(self):
        changed = False
        while True:
            try:
                kind, d = copilot.events.get_nowait()
            except queue.Empty:
                break
            if kind == "history":
                self.cpanel.add_history(d["entry"])
                stats["events"] += 1
                activity[-1] += 1
            elif kind == "suggestion":
                self.cpanel.refresh()
                if not self._hud_covering():                 # HUD recolhida: aviso discreto ao lado do botão
                    self.toast.show_suggestion(d["s"], self.fab.geometry())
                changed = True
            elif kind == "suggestion_gone":
                self.cpanel.refresh()
                self.toast.drop(d["id"])
                changed = True
            elif kind == "notice":
                if not self._hud_covering():
                    self.toast.show_notice(d["title"], d["text"], self.fab.geometry())
            elif kind == "agent":
                # O agente autônomo escreve no histórico e, quando a HUD está recolhida,
                # mostra apenas uma notificação curta para não interromper o trabalho.
                if d.get("state") in ("started", "done", "error") and not self._hud_covering():
                    self.toast.show_notice("Agente JARVIS", str(d.get("text", ""))[:500], self.fab.geometry())
                changed = True
            else:                                            # mode | paused | monitor | interval | excluded
                changed = True
        if changed:
            self.cbar.sync()
            self._sync_fab()

    def open_hud(self):
        self.restore_hud()

    def compact_from_tray(self):
        self.minimize_hud()

    def show_settings(self):
        QMessageBox.information(
            self,
            "Configurações do J.A.R.V.I.S.",
            f"Modelo local: {backend.OLLAMA_MODEL}\n"
            f"Microfone: {backend.MIC_INDEX}\n"
            "Inicialização com Windows: use autostart.py on/off/status.",
        )

    def restart_voice(self):
        threading.Thread(target=backend.restart_voice, daemon=True).start()

    def toggle_autostart(self, enabled):
        import autostart
        try:
            autostart.enable() if enabled else autostart.disable()
        except OSError as exc:
            self.autostart_action.blockSignals(True)
            self.autostart_action.setChecked(not enabled)
            self.autostart_action.blockSignals(False)
            QMessageBox.warning(self, "Autostart", f"Não consegui atualizar o Registro: {exc}")

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_hud()

    def exit_from_tray(self):
        self._allow_exit = True
        self.close()
        QApplication.quit()

    # ---- eventos do backend (mesma semântica do process_events original)
    def drain(self):
        while True:
            try:
                action, value = backend.event_queue.get_nowait()
            except queue.Empty:
                break
            if action == "state":
                self.set_state(value)
            elif action == "heard":
                self.last_interaction = time.monotonic()
                backend.add_log(f"Você: {value}")
                SIM.plan(value)                         # intenção -> módulos do plano
                self.inter.add_user(value)
            elif action == "answer":
                backend.add_log(f"JARVIS: {value[:55]}")
                SIM.keep_open(6.0)
                SIM.note(value)
                self.inter.add_ai(value)
            elif action == "microphone":
                text = "Reconhecimento de voz ativado." if value else "Reconhecimento de voz pausado."
                self.inter.add_sys(text)
            elif action == "activity":
                self.last_interaction = time.monotonic()
            elif action == "log":
                stats["events"] += 1
                activity[-1] += 1
                SIM.note(value)
                self.console.add(value)

    def tick(self):
        now = time.perf_counter()
        dt = min(.05, now - self.last)
        self.last = now
        anim.update(dt)
        SIM.step(anim, live, backend)
        self._gate_ui(dt)
        self._sync_cinematic()
        mono = time.monotonic()
        if mono >= self._next_tel:
            live["s"] = telemetria.snapshot()
            self._next_tel = mono + .25
        if mono >= self._next_audio:
            audio_hist.append(anim.mic)
            self._next_audio = mono + .1
        while mono - self._bucket_t >= ACTIVITY_BUCKET_S:
            activity.append(0)
            self._bucket_t += ACTIVITY_BUCKET_S
        self.drain()
        if hasattr(self, "cinematic"):
            boot_age = time.monotonic() - self.cinematic.boot_started
            self.cinematic.set_boot_progress(min(1.0, boot_age / 3.0))
        self._update_covering()
        self._copilot_drain()
        # Minimizada + assistente ainda ativo (você minimizou no meio de uma tarefa): assim que a tarefa
        # termina, volta a exigir a palavra "Jarvis". Não é temporizador: é só o fim da tarefa.
        if (self.hud_minimized and backend.is_assistant_active() and anim.state == "LISTENING"
                and self.display_mode not in ("expanding", "contracting")):
            backend.return_to_idle()
        if self.frame % 90 == 0:                     # ~1,5 s: mantém botão/aviso acima das outras janelas
            self.fab.keep_on_top()
            if self.toast.isVisible():
                self.toast.keep_on_top()
            self._sync_fab()
        if self.display_mode in ("expanding", "contracting"):
            self._update_transition_visual(None)
        self.frame += 1
        for w in self.animated:
            if w is self.core or w is self.inter.chip or self.frame % 2 == 0:
                w.update()

    def _gate_ui(self, dt):
        """O cérebro decide o que existe: painéis pelos módulos que chegaram; barras só quando necessárias."""
        if not hasattr(self, "_fx"):
            return
        for key_, fx_, pan_ in self._fx:
            o_ = SIM.po[key_]
            if abs(o_ - fx_.opacity()) > .003:
                fx_.setOpacity(o_)
            pan_.setAttribute(Qt.WA_TransparentForMouseEvents, o_ < .1)
        pos = self.mapFromGlobal(QCursor.pos())
        near = {"top": 0 <= pos.y() < 96, "bottom": pos.y() > self.height() - 280}
        fw = QApplication.focusWidget()
        typing = fw is not None and self.inter.isAncestorOf(fw)
        for key_, fx_, wd_ in self._ui_fx:
            goal = 1.0 if (SIM.build > .3 or near[key_] or (key_ == "bottom" and typing)) else 0.0
            o_ = fx_.opacity() + (goal - fx_.opacity()) * min(1.0, dt * 4.0)
            fx_.setOpacity(o_ if abs(goal - o_) > .01 else goal)
            wd_.setAttribute(Qt.WA_TransparentForMouseEvents, fx_.opacity() < .1)
        if hasattr(self, "flow") and self.flow.isVisible():
            self.flow.tick(dt)

    def toggle_fs(self):
        if self.display_mode != "full":
            backend.activate()
            return
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def on_escape(self):
        if anim.state in ("THINKING", "TOOL_EXECUTION") and backend.abort_agent():
            return
        if self.isFullScreen():
            self.showNormal()
        # Esc NÃO minimiza mais a HUD: só o botão de minimizar / botão flutuante.

    def closeEvent(self, e):
        if self._allow_exit:
            backend.stop()
            telemetria.stop()
            copilot.stop()
            self.fab.close()
            self.toast.close()
            self.tray.hide()
            e.accept()
            return
        e.ignore()
        self.minimize_hud()                     # fechar a janela = minimizar (o botão flutuante permanece)


def main():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))   # modelo Vosk em caminho relativo
    if sys.stderr is None or sys.stdout is None:            # pythonw (sem console): registra em arquivo
        try:
            if os.path.getsize("jarvis.log") > 5_000_000:   # evita log gigante
                os.replace("jarvis.log", "jarvis.old.log")
        except OSError:
            pass
        log = open("jarvis.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    if not backend.acquire_single_instance():
        return
    backend.BOOT = "--boot" in sys.argv                     # o backend espera Ollama/áudio sem travar a HUD
    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.start_minimized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
