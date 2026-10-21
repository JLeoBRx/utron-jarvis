"""PLATAFORMA JARVIS ULTIMATE — uma janela, seis módulos.

    JARVIS · TARDIS · NOCTÁRIO · ATIVIDADES · CONFIGURAÇÕES · DIAGNÓSTICOS

* Páginas criadas sob demanda (na primeira visita) e nunca destruídas: trocar de página só muda o que
  está à frente; câmera e região do TARDIS, filtros, rolagens e textos digitados ficam como estavam.
* Transição holográfica (~300 ms): a página que sai vira uma projeção que se desfaz em faixas de
  varredura enquanto a nova surge por baixo. Sem "efeitos pesados" (ou no perfil econômico) a troca é
  imediata. A transição só pinta uma imagem já capturada: não custa nada ao núcleo.
* Barra superior (como no JARVIS original): mini-reator e identidade, navegação (F1–F7), estado com
  LED e níveis REAIS de áudio, indicadores de microfone, voz, IA, Noctário, rede, bateria, Observador e
  sessão, relógio e data em pt-BR. Indicador sem dado real mostra "—"; nada é estimado.
* Barra inferior: entrada de texto global (vale em qualquer página), MIC, VOZ, ENVIAR e as barras de
  decisão (autorização e sugestão) — exceto quando a página tem as próprias barras (TARDIS, Sistemas).

API compatível com a antiga ``HudWindow`` (``input``, ``authorization``, ``suggestion``,
``refresh_layout``, ``focus_input``, ``toggle_fullscreen``, ``hide_to_tray``, sinais de recolher/fechar).
"""
from __future__ import annotations

import math
import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from . import palette, theme
from .conversation import ConversationPanel
from .window import DecisionBar, InputBar, app_icon

NAV = (
    ("jarvis", "JARVIS", ("F1",), "#00D9FF", "Assistente: conversa, voz e núcleo"),
    ("tardis", "TARDIS", ("F2",), "#FFB347", "Segundo cérebro: memória pessoal, lembretes e organização"),
    ("noctario", "NOCTÁRIO", ("F4",), "#3DFFA8", "Robô seguidor de linha: conexão, telemetria e comandos"),
    ("atividades", "ATIVIDADES", ("F5",), "#67F3FF", "Histórico de atividades: pedidos, ações, confirmações e falhas"),
    ("configuracoes", "CONFIGURAÇÕES", ("F6",), "#67F3FF", "Voz, áudio, inteligência, privacidade, permissões, "
                                                           "aparência e Noctário"),
    ("diagnosticos", "DIAGNÓSTICOS", ("F3", "F7"), "#67F3FF", "Voz, rede local, autonomia, desempenho, eventos e log"),
)
NAV_KEYS = tuple(item[0] for item in NAV)
PAGE_TITLES = {item[0]: item[1] for item in NAV}
TRANSITION_MS = 300
WEEKDAYS = ("SEG", "TER", "QUA", "QUI", "SEX", "SÁB", "DOM")
MONTHS = ("JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ")
LEVEL_COLORS = {"ok": "#3DFFA8", "info": "#00D9FF", "warn": "#FFB547", "error": "#FF5D73", "off": "#3D5873"}
COVERING_FRACTION = 0.6            # a interface cobre a tela: a observação fica suspensa (como no original)


# ============================================================================ dados dos indicadores
@dataclass
class Chip:
    key: str
    label: str
    value: str
    level: str = "ok"            # ok | info | warn | error | off
    tip: str = ""


def _rate(bps: Any) -> str:
    if not isinstance(bps, (int, float)):
        return "—"
    value = float(bps)
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1024 or unit == "GB/s":
            return f"{value:.0f} {unit}" if unit == "B/s" else f"{value:.1f} {unit}"
        value /= 1024
    return "—"


def _clock_text(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def date_text(at: float | None = None) -> str:
    """Data em pt-BR como no original: "SEG 01 JAN 2026"."""
    t = time.localtime(at if at is not None else time.time())
    return f"{WEEKDAYS[t.tm_wday]} {t.tm_mday:02d} {MONTHS[t.tm_mon - 1]} {t.tm_year}"


def compute_chips(core, state: dict, *, now: float | None = None, covering: bool = False) -> list[Chip]:
    """Indicadores da barra superior a partir do estado REAL (sem valores inventados)."""
    now = now if now is not None else time.time()
    chips: list[Chip] = []
    settings = core.settings() if core is not None else None
    # microfone
    if core is None or not getattr(core, "enable_voice", False):
        chips.append(Chip("mic", "MIC", "—", "off", "voz desativada nesta execução"))
    elif getattr(core, "privacy_shield", False):
        chips.append(Chip("mic", "MIC", "PRIVACIDADE", "warn", "Modo privacidade: microfone FECHADO. "
                                                              "Clique para gerenciar."))
    else:
        probe = core.voice.mic_probe()
        if not probe.get("enabled", True):
            chips.append(Chip("mic", "MIC", "OFF", "off", "Microfone desligado (Ctrl+M liga)"))
        elif probe.get("capturing"):
            chips.append(Chip("mic", "MIC", "ON", "ok", f"Captando: {probe.get('device') or 'dispositivo padrão'}"
                                                         f"\nReconhecimento: {probe.get('stt') or '—'}"))
        else:
            chips.append(Chip("mic", "MIC", "—", "warn", f"Microfone sem captura: {probe.get('reason') or 'iniciando'}"))
    # voz (síntese)
    if core is None:
        chips.append(Chip("tts", "VOZ", "—", "off"))
    else:
        speaker = core.speaker
        out = getattr(core, "audio_out", None)
        if speaker.muted:
            chips.append(Chip("tts", "VOZ", "MUDA", "off", "Fala do JARVIS silenciada (clique para ligar)"))
        elif out is not None and not getattr(out, "available", False):
            chips.append(Chip("tts", "VOZ", "SEM SAÍDA", "warn", f"Saída de áudio indisponível: "
                                                                 f"{getattr(out, 'reason', '') or 'sem dispositivo'}"))
        elif speaker.speaking:
            chips.append(Chip("tts", "VOZ", "FALANDO", "info", "O JARVIS está falando (Esc interrompe)"))
        else:
            chips.append(Chip("tts", "VOZ", "PRONTA", "ok", f"Saída: {getattr(out, 'backend', '—')}"))
    # inteligência
    models = state.get("models") or {}
    active = str(state.get("active_model") or "")
    provider = getattr(settings, "ai_provider", "ollama") if settings is not None else "ollama"
    openai = getattr(core, "openai", None) if core is not None else None
    if provider == "openai" and openai is not None and openai.available():
        chips.append(Chip("ai", "IA", f"OpenAI {openai.model}", "ok", "Cérebro: OpenAI (Responses API). As ferramentas "
                                                                      "rodam localmente."))
    elif models.get("ollama_alive") and active:
        tip = f"Ollama local · {active}"
        level = "ok"
        if provider == "openai" and openai is not None:
            tip += f"\nOpenAI escolhida, mas bloqueada: {openai.blocked_reason()}"
            level = "warn"
        chips.append(Chip("ai", "IA", active, level, tip))
    elif models and not models.get("ollama_alive"):
        chips.append(Chip("ai", "IA", "OFFLINE", "error", f"Ollama não respondeu: {models.get('error') or 'sem conexão'}"))
    else:
        chips.append(Chip("ai", "IA", "—", "off", "Modelo ainda não verificado"))
    # Noctário
    service = getattr(core, "noctario", None) if core is not None else None
    if service is None:
        chips.append(Chip("noct", "NOCTÁRIO", "SEM CONEXÃO", "off", "Serviço do Noctário não iniciado: nenhum dado "
                                                                     "do robô é exibido sem conexão real."))
    else:
        status = service.status()
        link = status.get("link", "desconectado")
        robot = status.get("confirmed", {}).get("state") or "—"
        level = {"conectado": "ok", "conectando": "info", "perdido": "error"}.get(link, "off")
        chips.append(Chip("noct", "NOCTÁRIO", robot.upper() if link == "conectado" else link.upper(), level,
                          status.get("summary", "")))
    # rede
    network = state.get("network_state") or {}
    telemetry = state.get("telemetry") or {}
    traffic = f"↓ {_rate(telemetry.get('net_rx_bps'))}  ↑ {_rate(telemetry.get('net_tx_bps'))}"
    if not network:
        chips.append(Chip("net", "REDE", "—", "off", "Sem leitura da rede ainda"))
    elif not network.get("online"):
        chips.append(Chip("net", "REDE", "OFFLINE", "error", "Nenhuma interface com rota padrão"))
    else:
        wifi = network.get("wifi") or {}
        tip = f"{network.get('interface', '')} · {network.get('ipv4', '')}\n{traffic}"
        if wifi.get("ssid"):
            signal = f" {wifi['signal']}%" if wifi.get("signal") not in (None, "") else ""
            chips.append(Chip("net", "Wi-Fi", f"{wifi['ssid']}{signal}", "ok", tip))
        else:
            chips.append(Chip("net", "REDE", "ON", "ok", tip))
    # bateria (sem bateria: o indicador não aparece)
    battery = telemetry.get("battery")
    if isinstance(battery, dict) and battery.get("percent") is not None:
        percent = int(battery["percent"])
        plugged = bool(battery.get("plugged"))
        level = "ok" if plugged or percent > 30 else ("warn" if percent > 15 else "error")
        chips.append(Chip("bat", "BAT", f"{percent}%{' ⚡' if plugged else ''}", level,
                          "Na tomada" if plugged else "Na bateria"))
    # Observador
    observer = state.get("observer") or {}
    mode = observer.get("mode") or (getattr(settings, "observer_mode", "off") if settings is not None else "off")
    if getattr(core, "privacy_shield", False):
        chips.append(Chip("obs", "OBSERVADOR", "SUSPENSO", "warn", "Modo privacidade: observação da tela suspensa"))
    elif mode == "off":
        chips.append(Chip("obs", "OBSERVADOR", "DESLIGADO", "off", "Observação da tela desligada (clique para os modos)"))
    elif observer.get("paused"):
        chips.append(Chip("obs", "OBSERVADOR", "PAUSADO", "warn", "Observação pausada (clique para retomar)"))
    elif covering:
        chips.append(Chip("obs", "OBSERVADOR", "SUSPENSO", "warn", "Observação suspensa — a interface do JARVIS cobre "
                                                                   "a tela"))
    else:
        label = {"assistant": "ASSISTENTE", "observer": "ATIVO"}.get(mode, mode.upper())
        chips.append(Chip("obs", "OBSERVADOR", label, "info", "A tela é observada localmente para sugerir ajuda"))
    # sessão (tempo de execução, como no original) e modo de privacidade
    started = getattr(core, "started_at", 0.0) if core is not None else 0.0
    privacy = getattr(settings, "privacy_mode", "local") if settings is not None else "local"
    privacy_label = "LOCAL" if privacy == "local" else "PADRÃO"
    chips.append(Chip("session", "SESSÃO", (_clock_text(now - started) if started else "—") + f" · {privacy_label}",
                      "info" if started else "off",
                      ("LOCAL MODE: nada sai do computador" if privacy == "local" else
                       "Modo padrão: serviços externos só com permissão explícita")))
    return chips


# ============================================================================ widgets da barra superior
class BrandMark(QtWidgets.QWidget):
    """Mini-reator de três arcos girando + "J.A.R.V.I.S." (identidade do original)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.angle = 0.0
        self.animated = True
        self.color = QtGui.QColor(theme.PRIMARY)
        self.compact = False
        self.setFixedHeight(46)
        self.setMinimumWidth(170)
        self.setToolTip("JUST A RATHER VERY INTELLIGENT SYSTEM")

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802 (Qt)
        return QtCore.QSize(170 if self.compact else 300, 46)

    def step(self, dt: float) -> None:
        if self.animated and self.isVisible():
            self.angle = (self.angle + dt * 50.0) % 360.0
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        cx, cy, r = 24.0, self.height() / 2, 15.0
        p.setBrush(QtCore.Qt.NoBrush)
        for index, (radius, speed, span, width) in enumerate(((r, 1.0, 110, 2.0), (r - 4.5, -1.6, 80, 1.6),
                                                             (r - 8.5, 2.3, 60, 1.4))):
            pen = QtGui.QPen(theme.with_alpha(self.color, 0.95 - index * 0.18), width)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            p.setPen(pen)
            rect = QtCore.QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
            start = (self.angle * speed + index * 40) % 360
            for k in range(3):
                p.drawArc(rect, int((start + k * 120) * 16), int(span / 3 * 16))
        core = QtGui.QRadialGradient(cx, cy, 6)
        core.setColorAt(0, theme.TEXT_BRIGHT)
        core.setColorAt(0.6, theme.with_alpha(self.color, 0.8))
        core.setColorAt(1, theme.with_alpha(self.color, 0.0))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(core)
        p.drawEllipse(QtCore.QPointF(cx, cy), 6, 6)
        p.setPen(theme.TEXT_BRIGHT)
        p.setFont(theme.font(13, weight=700, spacing=3.0))
        p.drawText(QtCore.QRectF(48, 4, 260, 22), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, "J.A.R.V.I.S.")
        if not self.compact:
            p.setPen(theme.TEXT_DIM)
            p.setFont(theme.font(6.5, spacing=1.6))
            p.drawText(QtCore.QRectF(49, 25, 260, 14), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                       "JUST A RATHER VERY INTELLIGENT SYSTEM")
        p.end()


class NavBar(QtWidgets.QWidget):
    """Navegação entre módulos; a marca do módulo atual desliza até o item escolhido."""

    selected = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFixedHeight(46)
        self.current = "jarvis"
        self.hover = ""
        self._rects: dict[str, QtCore.QRectF] = {}
        self._marker = QtCore.QRectF()
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_marker)
        self._font = theme.font(9, weight=600, spacing=2.4)

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802 (Qt)
        metrics = QtGui.QFontMetricsF(self._font)
        return QtCore.QSize(int(sum(metrics.horizontalAdvance(label) + 30 for _, label, *_ in NAV)), 46)

    def minimumSizeHint(self) -> QtCore.QSize:  # noqa: N802 (Qt)
        return QtCore.QSize(420, 46)

    def _layout(self) -> None:
        metrics = QtGui.QFontMetricsF(self._font)
        widths = [metrics.horizontalAdvance(label) + 30 for _, label, *_ in NAV]
        scale = min(1.0, self.width() / max(1.0, sum(widths)))
        x = 0.0
        self._rects = {}
        for (key, *_rest), width in zip(NAV, widths):
            self._rects[key] = QtCore.QRectF(x, 0, width * scale, self.height())
            x += width * scale

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._layout()
        rect = self._rects.get(self.current)
        if rect is not None:
            self._marker = QtCore.QRectF(rect)
        super().resizeEvent(event)

    def set_current(self, key: str, *, animate: bool = True) -> None:
        if key not in NAV_KEYS:
            return
        self.current = key
        if not self._rects:
            self._layout()
        target = self._rects.get(key, QtCore.QRectF())
        if animate and not self._marker.isNull() and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(QtCore.QRectF(self._marker))
            self._anim.setEndValue(QtCore.QRectF(target))
            self._anim.start()
        else:
            self._marker = QtCore.QRectF(target)
        self.update()

    def _on_marker(self, value) -> None:
        self._marker = QtCore.QRectF(value)
        self.update()

    def _key_at(self, pos: QtCore.QPointF) -> str:
        for key, rect in self._rects.items():
            if rect.contains(pos):
                return key
        return ""

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt)
        key = self._key_at(event.position())
        if key != self.hover:
            self.hover = key
            self.setCursor(QtCore.Qt.PointingHandCursor if key else QtCore.Qt.ArrowCursor)
            item = next((i for i in NAV if i[0] == key), None)
            self.setToolTip(f"{item[1]} ({' / '.join(item[2])}) — {item[4]}" if item else "")
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.hover = ""
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        key = self._key_at(event.position())
        if key and event.button() == QtCore.Qt.LeftButton:
            self.selected.emit(key)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        if not self._rects:
            self._layout()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setFont(self._font)
        accent = {item[0]: QtGui.QColor(item[3]) for item in NAV}
        for key, label, *_ in NAV:
            rect = self._rects[key]
            if key == self.current:
                p.setPen(theme.TEXT_BRIGHT)
            elif key == self.hover:
                p.setPen(theme.GLOW)
            else:
                p.setPen(theme.TEXT_DIM)
            p.drawText(rect, QtCore.Qt.AlignCenter, label)
        if not self._marker.isNull():
            color = accent.get(self.current, theme.PRIMARY)
            line = QtCore.QRectF(self._marker.left() + 12, self.height() - 4, self._marker.width() - 24, 2)
            glow = QtGui.QLinearGradient(line.left(), 0, line.right(), 0)
            glow.setColorAt(0.0, theme.with_alpha(color, 0.0))
            glow.setColorAt(0.5, theme.with_alpha(color, 1.0))
            glow.setColorAt(1.0, theme.with_alpha(color, 0.0))
            p.fillRect(line, glow)
            halo = QtCore.QRectF(line.left(), line.top() - 6, line.width(), 8)
            soft = QtGui.QLinearGradient(0, halo.top(), 0, halo.bottom())
            soft.setColorAt(0.0, theme.with_alpha(color, 0.0))
            soft.setColorAt(1.0, theme.with_alpha(color, 0.22))
            p.fillRect(halo, soft)
        p.end()


class StateChip(QtWidgets.QWidget):
    """LED + nome do estado + 5 barras com o nível REAL de áudio (microfone ou fala)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.activity = "BOOTING"
        self.label = "INICIALIZANDO"
        self.levels = [0.0] * 5
        self.setFixedSize(176, 30)

    def set_state(self, activity: str) -> None:
        activity = str(activity or "IDLE")
        label = "INICIALIZANDO" if activity == "BOOTING" else palette.state_label(activity)
        if (activity, label) != (self.activity, self.label):
            self.activity, self.label = activity, label
            self.setToolTip(f"Estado do JARVIS: {label}")
            self.update()

    def set_level(self, level: float) -> None:
        level = max(0.0, min(1.0, float(level or 0.0) * 6.0))
        self.levels = self.levels[1:] + [level]
        if self.isVisible():
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        color = theme.state_color(self.activity) if self.activity != "BOOTING" else theme.PRIMARY
        if self.activity == "IDLE":
            color = theme.PRIMARY_DIM
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QtGui.QPen(theme.with_alpha(color, 0.55), 1))
        p.setBrush(theme.with_alpha(theme.BG2, 0.85))
        p.drawRoundedRect(rect, 4, 4)
        pulse = 0.65 + 0.35 * math.sin(time.monotonic() * 4.0) if self.activity not in ("IDLE",) else 0.8
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(theme.with_alpha(color, pulse))
        p.drawEllipse(QtCore.QPointF(13, rect.center().y()), 4, 4)
        p.setPen(theme.TEXT)
        p.setFont(theme.font(8, weight=600, spacing=1.8))
        p.drawText(QtCore.QRectF(24, 0, 110, self.height()), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, self.label)
        x0 = self.width() - 40
        for index, level in enumerate(self.levels):
            height = 4 + level * 14
            bar = QtCore.QRectF(x0 + index * 6, rect.center().y() - height / 2, 3.5, height)
            p.setBrush(theme.with_alpha(color, 0.35 + 0.65 * level))
            p.drawRoundedRect(bar, 1.5, 1.5)
        p.end()


class ChipBar(QtWidgets.QWidget):
    """Indicadores compactos (LED + rótulo + valor), com dicas e clique."""

    clicked = QtCore.Signal(str)
    PRIORITY = ("mic", "tts", "ai", "noct", "net", "bat", "obs", "session")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chips: list[Chip] = []
        self._rects: list[tuple[QtCore.QRectF, Chip]] = []
        self._label_font = theme.font(7, weight=600, spacing=1.4)
        self._value_font = theme.font(8, weight=500, spacing=0.6)
        self.setMouseTracking(True)
        self.setFixedHeight(30)
        self.setMinimumWidth(120)

    def set_chips(self, chips: list[Chip]) -> None:
        if [(c.key, c.value, c.level, c.tip) for c in chips] == [(c.key, c.value, c.level, c.tip) for c in self.chips]:
            return
        self.chips = list(chips)
        self.updateGeometry()
        self.update()

    def value(self, key: str) -> str:
        chip = next((c for c in self.chips if c.key == key), None)
        return chip.value if chip else ""

    def _width(self, chip: Chip) -> float:
        label = QtGui.QFontMetricsF(self._label_font).horizontalAdvance(chip.label)
        value = QtGui.QFontMetricsF(self._value_font).horizontalAdvance(chip.value)
        return 24 + label + 6 + min(value, 170) + 10

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802 (Qt)
        return QtCore.QSize(int(sum(self._width(c) + 6 for c in self.chips)) or 120, 30)

    def _layout(self) -> None:
        order = sorted(self.chips, key=lambda c: self.PRIORITY.index(c.key) if c.key in self.PRIORITY else 99)
        shown, used = [], 0.0
        for chip in order:
            width = self._width(chip) + 6
            if used + width > self.width():
                continue                              # pouco espaço: os menos importantes saem
            shown.append(chip)
            used += width
        shown.sort(key=lambda c: self.chips.index(c))
        x = self.width() - used
        self._rects = []
        for chip in shown:
            width = self._width(chip)
            self._rects.append((QtCore.QRectF(x, 1, width, self.height() - 2), chip))
            x += width + 6

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._layout()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        for rect, chip in self._rects:
            led = QtGui.QColor(LEVEL_COLORS.get(chip.level, LEVEL_COLORS["off"]))
            p.setPen(QtGui.QPen(theme.with_alpha(theme.PRIMARY, 0.28), 1))
            p.setBrush(theme.with_alpha(theme.BG2, 0.85))
            p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(led)
            p.drawEllipse(QtCore.QPointF(rect.left() + 11, rect.center().y()), 3.2, 3.2)
            p.setPen(theme.TEXT_DIM)
            p.setFont(self._label_font)
            label_w = QtGui.QFontMetricsF(self._label_font).horizontalAdvance(chip.label)
            p.drawText(QtCore.QRectF(rect.left() + 20, rect.top(), label_w + 2, rect.height()),
                       QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, chip.label)
            p.setPen(theme.TEXT_BRIGHT if chip.level != "off" else theme.TEXT_DIM)
            p.setFont(self._value_font)
            value_rect = QtCore.QRectF(rect.left() + 26 + label_w, rect.top(), rect.right() - rect.left() - 30 - label_w,
                                       rect.height())
            text = QtGui.QFontMetricsF(self._value_font).elidedText(chip.value, QtCore.Qt.ElideRight, value_rect.width())
            p.drawText(value_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)
        p.end()

    def _chip_at(self, pos: QtCore.QPointF) -> Chip | None:
        for rect, chip in self._rects:
            if rect.contains(pos):
                return chip
        return None

    def event(self, event) -> bool:
        if event.type() == QtCore.QEvent.ToolTip:
            chip = self._chip_at(QtCore.QPointF(event.pos()))
            if chip is not None:
                QtWidgets.QToolTip.showText(event.globalPos(), f"{chip.label}: {chip.value}\n{chip.tip}".strip(), self)
            else:
                QtWidgets.QToolTip.hideText()
            return True
        return super().event(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.setCursor(QtCore.Qt.PointingHandCursor if self._chip_at(event.position()) else QtCore.Qt.ArrowCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        chip = self._chip_at(event.position())
        if chip is not None and event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(chip.key)


class ClockWidget(QtWidgets.QWidget):
    """HH:MM:SS e data em pt-BR ("TER 21 OUT 2026"), como no original."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(112, 40)
        self._text = ("", "")

    def tick(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        text = (time.strftime("%H:%M:%S", time.localtime(now)), date_text(now))
        if text != self._text:
            self._text = text
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.setPen(theme.TEXT_BRIGHT)
        p.setFont(theme.font(12, weight=600, spacing=1.5, mono=True))
        p.drawText(QtCore.QRectF(0, 0, self.width(), 24), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, self._text[0])
        p.setPen(theme.TEXT_DIM)
        p.setFont(theme.font(7, spacing=1.4))
        p.drawText(QtCore.QRectF(0, 22, self.width(), 16), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, self._text[1])
        p.end()


class TopBar(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(56)
        self.brand = BrandMark(self)
        self.nav = NavBar(self)
        self.state_chip = StateChip(self)
        self.chips = ChipBar(self)
        self.clock = ClockWidget(self)
        self.sweep = 0.0
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 14, 6)
        layout.setSpacing(14)
        layout.addWidget(self.brand)
        layout.addWidget(self.nav, 3)
        layout.addWidget(self.state_chip)
        layout.addWidget(self.chips, 4)
        layout.addWidget(self.clock)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        compact = self.width() < 1500
        if compact != self.brand.compact:
            self.brand.compact = compact
            self.brand.updateGeometry()
        self.state_chip.setVisible(self.width() >= 1100)
        super().resizeEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), theme.with_alpha(theme.BG, 0.96))
        y = self.height() - 1
        line = QtGui.QLinearGradient(0, 0, self.width(), 0)
        line.setColorAt(0.0, theme.with_alpha(theme.PRIMARY, 0.05))
        line.setColorAt(0.5, theme.with_alpha(theme.PRIMARY, 0.45))
        line.setColorAt(1.0, theme.with_alpha(theme.PRIMARY, 0.05))
        p.fillRect(QtCore.QRectF(0, y, self.width(), 1), line)
        x = self.sweep * self.width()                     # brilho que corre pela linha (só com efeitos)
        if self.sweep > 0:
            glow = QtGui.QLinearGradient(x - 90, 0, x + 90, 0)
            glow.setColorAt(0.0, theme.with_alpha(theme.GLOW, 0.0))
            glow.setColorAt(0.5, theme.with_alpha(theme.TEXT_BRIGHT, 0.85))
            glow.setColorAt(1.0, theme.with_alpha(theme.GLOW, 0.0))
            p.fillRect(QtCore.QRectF(x - 90, y - 0.5, 180, 2), glow)
        p.end()


# ============================================================================ transição holográfica
class TransitionOverlay(QtWidgets.QWidget):
    """A página que sai se desfaz em faixas de varredura enquanto uma linha de luz desce pela tela."""

    BANDS = 22

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self._pixmap: QtGui.QPixmap | None = None
        self._t = 1.0
        self._offsets: list[float] = []
        self.accent = QtGui.QColor(theme.PRIMARY)
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(TRANSITION_MS)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QtCore.QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.finished.connect(self._finish)
        self.runs = 0
        self.hide()

    @property
    def running(self) -> bool:
        return self._anim.state() == QtCore.QAbstractAnimation.Running

    def start(self, pixmap: QtGui.QPixmap, accent: QtGui.QColor | None = None) -> None:
        self._anim.stop()
        self._pixmap = pixmap
        self.accent = QtGui.QColor(accent or theme.PRIMARY)
        rng = random.Random(self.runs)
        self._offsets = [rng.uniform(-1.0, 1.0) for _ in range(self.BANDS)]
        self.runs += 1
        self._t = 0.0
        self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()
        self._anim.start()

    def _on_value(self, value) -> None:
        self._t = float(value)
        self.update()

    def _finish(self) -> None:
        self._pixmap = None
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self._pixmap is None:
            return
        p = QtGui.QPainter(self)
        w, h = self.width(), self.height()
        t = self._t
        line_y = t * h
        band_h = h / self.BANDS
        dpr = self._pixmap.devicePixelRatio() or 1.0
        for index in range(self.BANDS):
            top = index * band_h
            if top + band_h <= line_y:
                continue                                       # acima da linha: a página nova já apareceu
            local = max(0.0, min(1.0, (t * 1.35) - (index / self.BANDS) * 0.35))
            alpha = (1.0 - t) ** 1.4 * (1.0 - 0.6 * local)
            if alpha <= 0.02:
                continue
            dx = self._offsets[index] * 26.0 * t
            p.setOpacity(alpha)
            source = QtCore.QRectF(0, top * dpr, w * dpr, band_h * dpr)
            p.drawPixmap(QtCore.QRectF(dx, top, w, band_h), self._pixmap, source)
        p.setOpacity(1.0)
        # tinta holográfica sobre o que resta da página antiga
        tint = theme.with_alpha(self.accent, 0.10 * (1.0 - t))
        p.fillRect(QtCore.QRectF(0, line_y, w, h - line_y), tint)
        # linha de varredura e seu halo
        glow = QtGui.QLinearGradient(0, line_y - 26, 0, line_y + 3)
        glow.setColorAt(0.0, theme.with_alpha(self.accent, 0.0))
        glow.setColorAt(0.85, theme.with_alpha(self.accent, 0.35 * (1.0 - t * 0.5)))
        glow.setColorAt(1.0, theme.with_alpha(theme.TEXT_BRIGHT, 0.9 * (1.0 - t * 0.4)))
        p.fillRect(QtCore.QRectF(0, line_y - 26, w, 29), glow)
        p.setPen(QtGui.QPen(theme.with_alpha(self.accent, 0.12 * (1.0 - t)), 1))
        for x in range(0, w, 48):                              # grade que pisca na passagem
            p.drawLine(QtCore.QPointF(x, line_y - 26), QtCore.QPointF(x, line_y + 2))
        p.end()


# ============================================================================ páginas próprias
class UnavailablePage(QtWidgets.QWidget):
    """Página de um módulo que ainda não pode funcionar — diz exatamente o porquê."""

    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setStyleSheet(theme.PANEL_STYLESHEET)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.addStretch(1)
        head = QtWidgets.QLabel(title)
        head.setObjectName("PanelTitle")
        head.setAlignment(QtCore.Qt.AlignCenter)
        body = QtWidgets.QLabel(text)
        body.setObjectName("PanelDim")
        body.setWordWrap(True)
        body.setAlignment(QtCore.Qt.AlignCenter)
        self.body = body
        layout.addWidget(head)
        layout.addWidget(body)
        layout.addStretch(2)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), theme.BG2)
        p.end()


class JarvisPage(QtWidgets.QWidget):
    """O assistente: a vista central (núcleo neural; o rosto holográfico na Fase 4) e a conversa."""

    CONVERSATION_WIDTH = 380

    def __init__(self, central: QtWidgets.QWidget, conversation: ConversationPanel, parent=None):
        super().__init__(parent)
        self.central = central
        self.conversation = conversation
        central.setParent(self)
        conversation.setParent(self)
        self.toggle = QtWidgets.QPushButton("CONVERSA", self)
        self.toggle.setObjectName("HudButton")
        self.toggle.setToolTip("Mostrar a conversa")
        self.toggle.setCursor(QtCore.Qt.PointingHandCursor)
        self.toggle.setFocusPolicy(QtCore.Qt.NoFocus)
        self.toggle.clicked.connect(lambda: self.show_conversation(True))
        conversation.close_requested.connect(lambda: self.show_conversation(False))
        self.toggle.hide()
        if hasattr(central, "bottom_reserved"):
            central.bottom_reserved = 16              # a entrada fica fora da vista, na barra inferior

    def set_central(self, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """Troca a vista central (ex.: rosto holográfico ↔ núcleo neural). Devolve a anterior (oculta)."""
        old = self.central
        if widget is old:
            return old
        old.hide()
        widget.setParent(self)
        self.central = widget
        if hasattr(widget, "bottom_reserved"):
            widget.bottom_reserved = 16
        widget.show()
        self.toggle.raise_()
        self._layout()
        return old

    def show_conversation(self, visible: bool) -> None:
        self.conversation.setVisible(visible)
        self.toggle.setVisible(not visible)
        self._layout()

    def _layout(self) -> None:
        w, h = self.width(), self.height()
        side = min(self.CONVERSATION_WIDTH, max(280, int(w * 0.32))) if self.conversation.isVisibleTo(self) else 0
        self.central.setGeometry(0, 0, w - side, h)
        if side:
            self.conversation.setGeometry(w - side, 0, side, h)
        self.toggle.adjustSize()
        self.toggle.move(w - self.toggle.width() - 14, 12)
        self.toggle.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._layout()
        super().resizeEvent(event)


# ============================================================================ janela
class PlatformWindow(QtWidgets.QWidget):
    collapse_requested = QtCore.Signal()
    second_brain_requested = QtCore.Signal()       # compatível com a HudWindow (F2 → TARDIS)
    systems_requested = QtCore.Signal()            # compatível com a HudWindow (F3 → Diagnósticos)
    closing = QtCore.Signal()
    page_changed = QtCore.Signal(str)
    chip_clicked = QtCore.Signal(str)
    interrupt_requested = QtCore.Signal()          # Esc
    stop_requested = QtCore.Signal()               # PARAR (conversa)
    conversation_command = QtCore.Signal(str)      # STATUS / HORAS

    EVENT_LOG = 300

    def __init__(self, view: QtWidgets.QWidget, *, core=None, effects: Callable[[], bool] | None = None):
        super().__init__()
        self.core = core
        self.view = view
        self.setWindowTitle("J.A.R.V.I.S.")
        self.setWindowIcon(app_icon())
        self.resize(1440, 880)
        self.setMinimumSize(980, 600)
        self.setStyleSheet(theme.PANEL_STYLESHEET)
        self._effects = effects or (lambda: True)
        self.state: dict = {}
        self.covering = False
        self.hide_to_tray = True
        self.event_log: deque = deque(maxlen=self.EVENT_LOG)   # console de eventos (antes de abrir a página)
        self._factories: dict[str, Callable[[], QtWidgets.QWidget]] = {}
        self._pages: dict[str, QtWidgets.QWidget] = {}
        self.current_key = "jarvis"
        # barra superior
        self.top = TopBar(self)
        self.nav = self.top.nav
        self.chips = self.top.chips
        self.nav.selected.connect(self.navigate)
        self.chips.clicked.connect(self.chip_clicked)
        # páginas
        self.conversation = ConversationPanel()
        self.conversation.command.connect(self.conversation_command)
        self.conversation.stop_requested.connect(self.stop_requested)
        self.jarvis_page = JarvisPage(view, self.conversation)
        self.stack_host = QtWidgets.QWidget(self)
        self.stack = QtWidgets.QStackedWidget(self.stack_host)
        self.stack.addWidget(self.jarvis_page)
        self._pages["jarvis"] = self.jarvis_page
        self.overlay = TransitionOverlay(self.stack_host)
        # decisões e entrada
        self.authorization = DecisionBar("AUTORIZAR", "NEGAR", self, always="SEMPRE (24 h)")
        self.suggestion = DecisionBar("SIM", "NÃO", self)
        self.decisions = QtWidgets.QWidget(self)
        decisions = QtWidgets.QVBoxLayout(self.decisions)
        decisions.setContentsMargins(16, 0, 16, 0)
        decisions.setSpacing(6)
        decisions.addWidget(self.authorization)
        decisions.addWidget(self.suggestion)
        self.input = InputBar(self)
        self.input.sys.hide()                      # a navegação já leva a TARDIS e Diagnósticos
        self.input.brain.hide()
        self.input.collapse.connect(self.collapse_requested)
        bottom = QtWidgets.QWidget(self)
        bottom_layout = QtWidgets.QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 6, 16, 10)
        bottom_layout.addWidget(self.input)
        self.bottom = bottom
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.top)
        root.addWidget(self.stack_host, 1)
        root.addWidget(self.decisions)
        root.addWidget(bottom)
        # atalhos
        self._shortcuts: dict[str, QtGui.QShortcut] = {}
        for key, _label, keys, *_rest in NAV:
            for sequence in keys:
                QtGui.QShortcut(QtGui.QKeySequence(sequence), self, activated=lambda k=key: self.navigate(k))
        QtGui.QShortcut(QtGui.QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+M"), self, activated=self.input.mic.toggle)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+L"), self, activated=self.conversation.clear)
        self.escape = QtGui.QShortcut(QtGui.QKeySequence("Esc"), self, activated=self.interrupt_requested)
        # relógios da barra superior
        self._last_anim = time.perf_counter()
        self._anim_timer = QtCore.QTimer(self)
        self._anim_timer.timeout.connect(self._animate)
        self._anim_timer.start(66)
        self._chip_timer = QtCore.QTimer(self)
        self._chip_timer.timeout.connect(self.refresh_chips)
        self._chip_timer.start(1000)
        self.top.clock.tick()
        self.refresh_chips()

    # ------------------------------------------------------------ páginas
    def set_factory(self, key: str, factory: Callable[[], QtWidgets.QWidget]) -> None:
        self._factories[key] = factory

    def page(self, key: str) -> QtWidgets.QWidget | None:
        return self._pages.get(key)

    def ensure_page(self, key: str) -> QtWidgets.QWidget:
        widget = self._pages.get(key)
        if widget is not None:
            return widget
        factory = self._factories.get(key)
        widget = factory() if factory is not None else UnavailablePage(
            PAGE_TITLES.get(key, key), "Este módulo não está disponível nesta execução.")
        self.stack.addWidget(widget)
        self._pages[key] = widget
        self._disable_page_escape(widget)
        return widget

    @staticmethod
    def _disable_page_escape(widget: QtWidgets.QWidget) -> None:
        """Páginas que eram janelas (Sistemas) fechavam com Esc: aqui, Esc é da plataforma."""
        if getattr(widget, "keeps_escape", False):
            return
        escape = QtGui.QKeySequence("Esc")
        for shortcut in widget.findChildren(QtGui.QShortcut):
            if shortcut.key() == escape and shortcut.parent() is widget and not hasattr(widget, "open_region"):
                shortcut.setEnabled(False)

    def navigate(self, key: str, *, animate: bool = True) -> QtWidgets.QWidget | None:
        if key not in NAV_KEYS:
            return None
        widget = self.ensure_page(key)
        old = self.stack.currentWidget()
        if widget is not old:
            if animate and old is not None and self.isVisible() and old.isVisible() and self._effects():
                accent = QtGui.QColor(next(item[3] for item in NAV if item[0] == key))
                self.overlay.setGeometry(self.stack_host.rect())
                self.overlay.start(old.grab(), accent)
            self.stack.setCurrentWidget(widget)
        self.current_key = key
        self.nav.set_current(key, animate=animate)
        self.setWindowTitle("J.A.R.V.I.S." if key == "jarvis" else f"J.A.R.V.I.S. — {PAGE_TITLES[key]}")
        self._sync_escape()
        self.refresh_layout()
        if key == "jarvis":
            self.focus_input()
        self.page_changed.emit(key)
        return widget

    def _sync_escape(self) -> None:
        """O TARDIS usa Esc para fechar a região aberta; nas outras páginas, Esc é da plataforma
        (dois atalhos iguais ativos ao mesmo tempo anulariam um ao outro no Qt)."""
        page = self.stack.currentWidget()
        self.escape.setEnabled(not hasattr(page, "open_region"))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._layout_stack)

    def _layout_stack(self) -> None:
        rect = self.stack_host.rect()
        self.stack.setGeometry(rect)
        self.overlay.setGeometry(rect)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self._layout_stack()

    # ------------------------------------------------------------ decisões (compatível com a HudWindow)
    def _page_has_own_decisions(self) -> bool:
        page = self.stack.currentWidget()
        return isinstance(getattr(page, "authorization", None), DecisionBar)

    def refresh_layout(self) -> None:
        self.decisions.setVisible(not self._page_has_own_decisions()
                                  and (self.authorization.isVisibleTo(self.decisions)
                                       or self.suggestion.isVisibleTo(self.decisions)))

    def focus_input(self) -> None:
        self.input.line.setFocus()

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    # ------------------------------------------------------------ dados vindos do controlador
    def on_event(self, kind: str, payload: dict, at: float | None = None) -> None:
        at = at or time.time()
        self.event_log.append((at, kind, payload))
        self.conversation.on_event(kind, payload, at)
        for page in self._pages.values():
            handler = getattr(page, "platform_event", None)
            if handler is not None:
                handler(kind, payload, at)

    def on_state(self, state: dict, names=None) -> None:
        self.state = state
        self.top.state_chip.set_state(str(state.get("activity") or state.get("runtime_state") or "IDLE"))
        if names is None or {"models", "network_state", "telemetry", "observer", "privacy_shield",
                             "active_model"} & set(names):
            self.refresh_chips()

    def on_telemetry(self, telemetry: dict) -> None:
        level = telemetry.get("out_level", 0.0) if telemetry.get("speaking") else telemetry.get("mic_level", 0.0)
        self.top.state_chip.set_level(level)

    def refresh_chips(self) -> None:
        self.covering = self._compute_covering()
        try:
            chips = compute_chips(self.core, self.state, covering=self.covering)
        except Exception:                                   # um indicador nunca derruba a janela
            chips = []
        self.chips.set_chips(chips)
        self.top.clock.tick()

    def _compute_covering(self) -> bool:
        """A interface cobre a tela? (a observação fica suspensa, como no JARVIS original)."""
        if not self.isVisible() or self.isMinimized():
            return False
        if self.isFullScreen() or self.isMaximized():
            return True
        screen = self.screen()
        if screen is None:
            return False
        area = screen.availableGeometry()
        mine = self.frameGeometry().intersected(area)
        total = max(1, area.width() * area.height())
        return mine.width() * mine.height() / total >= COVERING_FRACTION

    def _animate(self) -> None:
        now = time.perf_counter()
        dt, self._last_anim = now - self._last_anim, now
        if not self.isVisible() or self.isMinimized():
            return
        effects = self._effects()
        self.top.brand.animated = effects
        if effects:
            self.top.brand.step(dt)
            self.top.sweep = (self.top.sweep + dt / 6.0) % 1.0
            self.top.update()
        elif self.top.sweep:
            self.top.sweep = 0.0
            self.top.update()
        if self.top.state_chip.isVisible() and self.top.state_chip.activity not in ("IDLE",):
            self.top.state_chip.update()

    # ------------------------------------------------------------ teclado e fechamento
    def closeEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self.hide_to_tray:
            event.ignore()                     # continua na bandeja; "Sair" encerra de fato
            self.hide()
            self.closing.emit()
        else:
            super().closeEvent(event)

    def shutdown(self) -> None:
        for timer in (self._anim_timer, self._chip_timer):
            timer.stop()
        for page in self._pages.values():
            stop = getattr(page, "shutdown", None)
            if stop is not None and page is not self.jarvis_page:
                try:
                    stop()
                except Exception:
                    pass
