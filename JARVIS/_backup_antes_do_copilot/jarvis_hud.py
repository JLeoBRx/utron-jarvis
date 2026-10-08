"""
J.A.R.V.I.S. // MARK VII — HUD em PySide6
Somente interface. Voz, Ollama e TTS continuam em backend.py.
Todos os dados exibidos são REAIS (telemetria.py e backend.py). O que não estiver
disponível aparece como N/D; nada é simulado.
"""
import os
import sys
import math
import time
import random
import queue
import html
import threading
from collections import deque

from PySide6.QtCore import (
    Qt, QTimer, QPointF, QRect, QRectF, Signal, QPropertyAnimation, QEasingCurve,
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QFont, QRadialGradient, QConicalGradient,
    QLinearGradient, QPainterPath, QPolygonF, QPixmap, QShortcut, QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPlainTextEdit, QLineEdit, QPushButton, QSizePolicy, QMenu,
    QMessageBox, QSystemTrayIcon, QStyle,
)

import backend
import telemetria

APP_TITLE = "J.A.R.V.I.S. // MARK VII"
IDLE_TIMEOUT = 7
COMPACT_SIZE = 196
TRANSITION_MS = 1000

# ============================================================ CORES
BG = "#030405"
ERR = "#FF2A3D"            # erro/falha (fixo)
WHITE = "#F5F6F7"
TEXT = "#B5B3B6"
MUTED = "#656164"
GREEN = "#29F29A"
AMBER = "#FFB84D"

# Tema que muda sozinho: vermelho -> amarelo -> azul escuro -> roxo -> (volta)
# (principal, claro, escuro, muito escuro)
THEMES = [
    ("#FF2A3D", "#FF4D59", "#64111A", "#26080C"),   # vermelho
    ("#FFC21A", "#FFD54D", "#66500B", "#261E04"),   # amarelo
    ("#2D5BFF", "#5C86FF", "#12307A", "#08122E"),   # azul escuro
    ("#A63DFF", "#BE6BFF", "#451A70", "#190A2B"),   # roxo
]
THEME_HOLD, THEME_BLEND = 14.0, 5.0                 # segundos parado / em transição
# RED* seguem o tema atual (o nome foi mantido para não mexer no resto do código).
RED, RED2, RED_DARK, RED_DEEP = THEMES[0]


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
    """CPU, RAM, GPU, microfone e rede: todos lidos de telemetria.py / backend.py."""

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
                p.setBrush(acol(anim.color, 230) if lit else acol(RED_DEEP, 255))
                p.drawRect(QRectF(r.left() + j * sw, by, sw - 2, 6))


class ModulesPanel(HudPanel):
    """Estado real de cada módulo (backend.status + telemetria + banco local)."""

    def modules(self):
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
    """Eventos REAIS do JARVIS (linhas do console) contados em janelas de 5 segundos."""

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
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 44, 10, 12)
        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(300)
        lay.addWidget(self.view)

    def add(self, text):
        ts = time.strftime("%H:%M:%S")
        self.view.appendHtml(
            f'<span style="color:{MUTED}">[{ts}]</span> <span style="color:{RED2}">▸</span> '
            f'<span style="color:{TEXT}">{html.escape(text)}</span>')


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
        if self.kind == "mic":
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


class InteractionPanel(HudPanel):
    submitted = Signal(str)
    micClicked = Signal()

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 44, 16, 14)
        lay.setSpacing(8)
        self.chat = QPlainTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setMaximumBlockCount(200)
        lay.addWidget(self.chat, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.chip = StateChip()
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Digite uma mensagem...")
        self.mic, self.send = HudButton("mic"), HudButton("send")
        for w_ in (self.chip, self.edit, self.mic, self.send):
            row.addWidget(w_)
        row.setStretch(1, 1)
        lay.addLayout(row)
        self.edit.returnPressed.connect(self._submit)
        self.send.clicked.connect(self._submit)
        self.mic.clicked.connect(self.micClicked.emit)

    def _submit(self):
        t = self.edit.text().strip()
        if t:
            self.edit.clear()
            self.submitted.emit(t)

    def add_user(self, t):
        self.chat.appendHtml(f'<span style="color:{WHITE}"><b>VOCÊ ▸</b></span> '
                             f'<span style="color:{TEXT}">{html.escape(t)}</span>')

    def add_ai(self, t):
        self.chat.appendHtml(f'<span style="color:{RED2}"><b>J.A.R.V.I.S. ▸</b></span> '
                             f'<span style="color:{WHITE}">{html.escape(t)}</span>')

    def add_sys(self, t):
        self.chat.appendHtml(f'<span style="color:{MUTED}">// {html.escape(t)}</span>')


# ============================================================ NÚCLEO
class CoreWidget(QWidget):
    def __init__(self):
        super().__init__()
        rnd = random.Random(3)
        self.parts = [(rnd.uniform(.28, .98), rnd.uniform(0, math.tau),
                       rnd.choice((-1, 1)) * rnd.uniform(.15, .9), rnd.uniform(1.2, 3.2))
                      for _ in range(70)]
        self.setMinimumSize(300, 300)

    def paintEvent(self, ev):
        p = QPainter(self)
        aa(p)
        w, h = self.width(), self.height()
        lab = 56
        ah = h - lab
        R = min(w / 2, ah / 2) * .95
        k = clamp((anim.since - .3) / 1.4)
        k = 1 - (1 - k) ** 3
        p.setOpacity(k)
        t, s, en, col = anim.t, anim.spin, anim.energy, anim.color

        p.translate(w / 2, ah / 2)
        sc = (.9 + .1 * k) * (1 + .010 * math.sin(t * 1.3))
        p.scale(sc, sc)

        def circle(r, wd, c, dash=None):
            pen = QPen(c, wd)
            if dash:
                pen.setDashPattern(dash)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(0, 0), r, r)

        # brilho ambiente
        g = QRadialGradient(0, 0, R * 1.08)
        g.setColorAt(0, acol(col, 70 + 60 * en))
        g.setColorAt(.45, acol(col, 18))
        g.setColorAt(1, acol(col, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(0, 0), R * 1.08, R * 1.08)

        # disco escuro de profundidade
        g = QRadialGradient(0, 0, R * .9)
        g.setColorAt(0, acol(dk(.04), 235))
        g.setColorAt(1, acol(dk(.02), 150))
        p.setBrush(g)
        p.drawEllipse(QPointF(0, 0), R * .9, R * .9)

        # varredura (sweep)
        cg = QConicalGradient(0, 0, (-s * 70) % 360)
        cg.setColorAt(0, acol(col, 110))
        cg.setColorAt(.14, acol(col, 0))
        cg.setColorAt(1, acol(col, 0))
        p.setBrush(cg)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(0, 0), R * .8, R * .8)

        # anéis estáticos
        circle(R * .99, 1, acol(RED_DARK))
        circle(R * .90, 1.6, acol(RED_DARK, 220), [3, 7])
        circle(R * .60, 1, acol(RED_DARK))
        circle(R * .50, 1, acol(col, 90), [2, 5])

        # ticks externos
        p.save()
        p.rotate(s * 6)
        n = 120
        pa, pb = QPen(acol(col, 210), 1.6), QPen(acol(RED_DARK), 1)
        for i in range(n):
            lg = i % 5 == 0
            p.setPen(pa if lg else pb)
            ln(p, R * (.93 if lg else .95), 0, R * .99, 0)
            p.rotate(360 / n)
        p.restore()

        # anel tracejado girando
        p.save()
        p.rotate(-s * 9)
        circle(R * .88, 2, acol(RED2, 150), [4, 8])
        p.restore()

        # arcos segmentados (velocidades e sentidos diferentes)
        for rr, wd, span, spd, off, al, cnt in [
                (.84, 5, 50, -22, 0, 230, 3), (.84, 2, 20, 34, 40, 170, 6),
                (.78, 3, 90, 15, 200, 200, 2), (.72, 2, 30, -48, 60, 200, 4),
                (.66, 4, 40, 28, 300, 255, 3)]:
            rect = QRectF(-R * rr, -R * rr, 2 * R * rr, 2 * R * rr)
            pen = QPen(acol(col, al), wd)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            for m in range(cnt):
                p.drawArc(rect, int((off + s * spd + m * 360 / cnt) * 16), int(span * 16))

        # divisões radiais
        p.save()
        p.rotate(-s * 3)
        p.setPen(QPen(acol(RED2, 170), 1))
        for i in range(48):
            ln(p, R * .50, 0, R * (.58 if i % 4 else .63), 0)
            p.rotate(7.5)
        p.restore()

        # geometria interna
        p.save()
        p.rotate(s * 10)
        poly = QPolygonF([QPointF(R * .44 * math.cos(i * math.tau / 6),
                                  R * .44 * math.sin(i * math.tau / 6)) for i in range(6)])
        p.setPen(QPen(acol(col, 150), 1.3))
        p.setBrush(Qt.NoBrush)
        p.drawPolygon(poly)
        p.rotate(-s * 26)
        tri = QPolygonF([QPointF(R * .36 * math.cos(i * math.tau / 3),
                                 R * .36 * math.sin(i * math.tau / 3)) for i in range(3)])
        p.setPen(QPen(acol(WHITE, 110), 1))
        p.drawPolygon(tri)
        p.restore()

        # ondas de energia
        for i in range(3):
            ph = (t * (.25 + .5 * en) + i / 3) % 1
            circle(R * (.30 + .62 * ph), 2, acol(col, (1 - ph) * (60 + 140 * en)))

        # anel de áudio (a amplitude reage ao nível REAL do microfone)
        p.setPen(QPen(acol(col, 230), 2))
        p.save()
        nb = 64
        for i in range(nb):
            amp = (anim.voice * .6 + anim.mic * 1.4) * (.05 + .09 * abs(math.sin(t * 8 + i * .9) * math.sin(t * 3.3 + i * .37))) + .012
            ln(p, R * .295, 0, R * (.295 + amp), 0)
            p.rotate(360 / nb)
        p.restore()

        # bits de processamento (THINKING)
        if anim.think > .02:
            rect = QRectF(-R * .69, -R * .69, 2 * R * .69, 2 * R * .69)
            pen = QPen(acol(WHITE, 255 * anim.think), 3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            for i in range(8):
                p.drawArc(rect, int((s * 140 + i * 45) * 16), 10 * 16)

        # partículas orbitais
        p.setPen(Qt.NoPen)
        for rf, a0, sp, sz in self.parts:
            ang = a0 + s * sp * .6
            x, y = R * rf * math.cos(ang), R * rf * math.sin(ang) * .94
            tw = .5 + .5 * math.sin(t * 2 + a0 * 5)
            p.setBrush(acol(col, 30 + 30 * tw))
            p.drawEllipse(QPointF(x, y), sz * 2.6, sz * 2.6)
            p.setBrush(acol(WHITE if sz > 2.6 else col, 90 + 160 * tw))
            p.drawEllipse(QPointF(x, y), sz * .7, sz * .7)

        # centro luminoso
        pulse = .5 + .5 * math.sin(t * (2.2 + 2.5 * en))
        r0 = R * (.15 + .02 * pulse * (.5 + en))
        g = QRadialGradient(0, 0, r0 * 2.6)
        g.setColorAt(0, acol(WHITE, 255))
        g.setColorAt(.28, acol(col, 255))
        g.setColorAt(.6, acol(col, 90 + 60 * en))
        g.setColorAt(1, acol(col, 0))
        p.setBrush(g)
        p.drawEllipse(QPointF(0, 0), r0 * 2.6, r0 * 2.6)
        circle(r0 * 1.3, 2, acol(WHITE, 200))
        circle(r0 * 1.7, 1, acol(col, 200), [2, 4])

        # textos
        p.resetTransform()
        p.setFont(F(21, True, "Segoe UI", 4))
        p.setPen(acol(col))
        p.drawText(QRectF(0, ah + 2, w, 30), Qt.AlignCenter, anim.state)
        p.setFont(F(8, sp=1.5))
        p.setPen(acol(TEXT))
        sub = STATE_SUB[anim.state]
        p.drawText(QRectF(0, ah + 33, w, 18), Qt.AlignCenter, sub)

        p.setFont(F(7))
        p.setPen(acol(MUTED))
        ms = live["s"]["ollama_ms"]
        p.drawText(QRectF(8, 4, 260, 14), Qt.AlignLeft, f"CORE // {backend.OLLAMA_MODEL.upper()}")
        p.drawText(QRectF(w - 228, 4, 220, 14), Qt.AlignRight,
                   "LATÊNCIA IA N/D" if ms is None else f"LATÊNCIA IA {ms:.0f} MS")
        p.drawText(QRectF(8, ah - 16, 220, 14), Qt.AlignLeft, f"MIC {int(anim.mic * 100):03d}%")
        p.drawText(QRectF(w - 228, ah - 16, 220, 14), Qt.AlignRight,
                   f"SESSÃO {fmt_uptime(live['s']['uptime'])}")


# ============================================================ BARRA SUPERIOR
class TopBar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(64)

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
        g.setColorAt(0, QColor(dk(.09)))
        g.setColorAt(1, QColor(BG))
        p.fillRect(self.rect(), g)
        p.setPen(QPen(acol(RED, 16), 1))
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
            p.setBrush(acol(RED2, a))
            p.drawEllipse(QPointF(xx * w, yy * h), sz, sz)
        sy = (anim.t * 90) % (h + 240) - 120
        sg = QLinearGradient(0, sy - 60, 0, sy + 60)
        sg.setColorAt(0, acol(anim.color, 0))
        sg.setColorAt(.5, acol(anim.color, 22))
        sg.setColorAt(1, acol(anim.color, 0))
        p.fillRect(QRectF(0, sy - 60, w, 120), sg)
        v = QRadialGradient(w / 2, h / 2, max(w, h) * .75)
        v.setColorAt(.6, QColor(0, 0, 0, 0))
        v.setColorAt(1, QColor(0, 0, 0, 190))
        p.fillRect(self.rect(), v)


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
        width, height = self.width(), self.height()
        cx, cy = width / 2, height / 2
        size = min(width, height)
        progress = self.progress
        color = anim.color
        pulse = 1 + .035 * math.sin(anim.t * 2.1)
        radius = size * (.18 + .16 * progress) * pulse

        glow = QRadialGradient(cx, cy, max(radius * 3.2, size * .48))
        glow.setColorAt(0, acol(color, 82))
        glow.setColorAt(.45, acol(color, 22))
        glow.setColorAt(1, acol(color, 0))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), size * .48, size * .48)

        painter.setBrush(Qt.NoBrush)
        for ring_radius, alpha, line_width in (
            (radius * 1.45, 110, 1.2),
            (radius * (2.0 + .65 * progress), 90, 1.0),
        ):
            painter.setPen(QPen(acol(color, alpha), line_width))
            painter.drawEllipse(QPointF(cx, cy), ring_radius, ring_radius)

        painter.setPen(QPen(acol(color, 235), 1.6))
        painter.drawArc(QRectF(cx - radius * 1.8, cy - radius * 1.8,
                               radius * 3.6, radius * 3.6),
                        int((anim.t * 24) % 360 * 16), int(238 * 16))

        core_glow = QRadialGradient(cx, cy, radius)
        core_glow.setColorAt(0, acol(WHITE, 245))
        core_glow.setColorAt(.3, acol(color, 245))
        core_glow.setColorAt(1, acol(color, 25))
        painter.setBrush(core_glow)
        painter.setPen(QPen(acol(WHITE, 180), 1))
        painter.drawEllipse(QPointF(cx, cy), radius * .55, radius * .55)

        reach_x = width * .46 * progress
        reach_y = height * .46 * progress
        if progress > .03:
            painter.setPen(QPen(acol(color, int(180 * progress)), 1))
            painter.drawLine(QPointF(cx - reach_x, cy), QPointF(cx + reach_x, cy))
            painter.drawLine(QPointF(cx, cy - reach_y), QPointF(cx, cy + reach_y))

        particle_radius = radius * 1.65 + size * .24 * progress
        painter.setPen(Qt.NoPen)
        for index in range(12):
            angle = anim.t * (.22 + progress * .45) + index * math.tau / 12
            x = cx + math.cos(angle) * particle_radius
            y = cy + math.sin(angle) * particle_radius
            painter.setBrush(acol(color, int((35 + 100 * progress) * (.6 + .4 * noise(index + anim.t)))))
            painter.drawEllipse(QPointF(x, y), 1.5 + progress, 1.5 + progress)

        if progress < .18:
            painter.setFont(F(8, True, "Segoe UI"))
            painter.setPen(acol(WHITE, 220))
            painter.drawText(QRectF(0, cy + radius * 1.5, width, 18), Qt.AlignCenter, "J.A.R.V.I.S.")
            painter.setFont(F(6.5, True))
            painter.setPen(acol(color, 210))
            painter.drawText(QRectF(0, cy + radius * 1.5 + 16, width, 14), Qt.AlignCenter, anim.state)


# ============================================================ JANELA
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(APP_TITLE)
        self.display_mode = "compact"
        self._transition_direction = None
        self._transition_start_progress = 0.0
        self._transition_end_progress = 0.0
        self.setMinimumSize(180, 180)
        self.resize(COMPACT_SIZE, COMPACT_SIZE)
        bg = Background()
        self.background = bg
        self.setCentralWidget(bg)
        root = QVBoxLayout(bg)
        root.setContentsMargins(14, 0, 14, 14)
        root.setSpacing(10)
        self.top = TopBar()
        root.addWidget(self.top)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        self.status_p = StatusPanel("STATUS DO SISTEMA", False, .3, -1)
        self.mods_p = ModulesPanel("MÓDULOS", False, .5, -1)
        self.diag_p = DiagPanel("DIAGNÓSTICO", False, .7, -1)
        self.core = CoreWidget()
        self.inter = InteractionPanel("INTERFACE DE INTERAÇÃO", False, .9, 0)
        self.net_p = NetworkPanel("REDE E CONEXÕES", False, .4, 1)
        self.act_p = ActivityPanel("HISTÓRICO DE ATIVIDADE", False, .6, 1)
        self.console = ConsolePanel("CONSOLE DE EVENTOS", False, .8, 1)

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
        right = column([self.net_p, self.act_p, self.console], [5, 3, 5])
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(10)
        cl.addWidget(self.core, 5)
        self.inter.setMinimumHeight(190)
        cl.addWidget(self.inter, 2)
        body.addWidget(left, 3)
        body.addWidget(center, 6)
        body.addWidget(right, 3)

        self.animated = [bg, self.top, self.core, self.status_p, self.mods_p, self.diag_p,
                         self.net_p, self.act_p, self.console, self.inter, self.inter.chip, self.inter.mic,
                         self.inter.send]
        self.full_widgets = [self.top, left, center, right]
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
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fs)
        QShortcut(QKeySequence("Escape"), self, activated=self.on_escape)
        self._allow_exit = False
        self._hide_to_tray_pending = False
        self._setup_tray()

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

    def _compact_geometry(self):
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

    # ---- estado
    def set_state(self, state):
        if state not in backend.STATES:
            return
        anim.state = state
        if state == "WAKE":
            self._begin_expansion()
        elif state == "RETURNING_IDLE":
            self._begin_contraction()
        elif state in ("LISTENING", "ERROR"):
            self.last_interaction = time.monotonic()

    def on_submit(self, text):
        self.last_interaction = time.monotonic()
        threading.Thread(target=backend.process_command, args=(text,), daemon=True).start()

    def on_mic_clicked(self):
        backend.toggle_microphone()

    def _setup_tray(self):
        self._tray_available = QSystemTrayIcon.isSystemTrayAvailable()
        icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("J.A.R.V.I.S.")
        menu = QMenu(self)
        menu.addAction("J.A.R.V.I.S.").setEnabled(False)
        menu.addSeparator()
        menu.addAction("Abrir HUD", self.open_hud)
        menu.addAction("Modo compacto", self.compact_from_tray)
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

    def open_hud(self):
        self._hide_to_tray_pending = False
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        if not backend.is_assistant_active():
            backend.activate()

    def compact_from_tray(self):
        self._hide_to_tray_pending = False
        self.show()
        if backend.is_assistant_active():
            backend.return_to_idle()

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
                self.inter.add_user(value)
            elif action == "answer":
                backend.add_log(f"JARVIS: {value[:55]}")
                self.inter.add_ai(value)
            elif action == "microphone":
                text = "Reconhecimento de voz ativado." if value else "Reconhecimento de voz pausado."
                self.inter.add_sys(text)
            elif action == "activity":
                self.last_interaction = time.monotonic()
            elif action == "log":
                stats["events"] += 1
                activity[-1] += 1
                self.console.add(value)

    def tick(self):
        now = time.perf_counter()
        dt = min(.05, now - self.last)
        self.last = now
        anim.update(dt)
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
        if (self.display_mode == "full" and backend.is_assistant_active()
            and anim.state in ("LISTENING", "ERROR")
                and time.monotonic() - self.last_interaction >= IDLE_TIMEOUT):
            backend.return_to_idle()
        if self.display_mode in ("expanding", "contracting"):
            self._update_transition_visual(None)
        self.frame += 1
        for w in self.animated:
            if w is self.core or w is self.inter.chip or self.frame % 2 == 0:
                w.update()

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
        elif self.display_mode == "full" and backend.is_assistant_active():
            backend.return_to_idle()

    def closeEvent(self, e):
        if self._allow_exit:
            backend.stop()
            telemetria.stop()
            self.tray.hide()
            e.accept()
            return
        e.ignore()
        if not self._tray_available:
            if backend.is_assistant_active():
                backend.return_to_idle()
            return
        if backend.is_assistant_active() and backend.return_to_idle():
            self._hide_to_tray_pending = True
        else:
            self.hide()


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
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
