"""Widget do avatar na página JARVIS.

* Recebe do controlador o estado central, os eventos e a telemetria REAIS; resolve um dos 12 estados
  (``states.resolve``) e o animador leva o rosto até a expressão daquele estado.
* A boca lê ``mouth()`` do ``Speaker`` (trilha labial do áudio real, pela posição real de reprodução);
  a legenda lê ``caption()`` e destaca as palavras já ditas.
* Projeções de dados: estado e motivo, modelo de IA, microfone, tarefa em curso — só dados reais;
  sem dado, nada é mostrado.
* Clique no rosto: liga/desliga o microfone (como o clique no núcleo do JARVIS original).
* CPU (``AvatarView``, QWidget) por padrão; GPU opcional (``AvatarGLView``, QOpenGLWidget) com o MESMO
  desenho — se o OpenGL não abrir, o controlador volta para a CPU e diz o motivo.
* Mede o próprio custo (``frame_times``) para o controlador limitar os quadros por segundo.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from .. import theme
from .animator import Animator
from .renderer import AvatarRenderer, quality_for
from .states import ALERT_WINDOW, ERROR_WINDOW, AvatarSignals, resolve

TARDIS_EVENTS_START = {"TARDIS_TASK_STARTED"}
TARDIS_EVENTS_END = {"TARDIS_TASK_FINISHED", "TARDIS_TASK_FAILED", "TARDIS_TASK_CANCELLED"}


class _AvatarCore:
    """Estado e desenho compartilhados pelas versões CPU e GPU do widget."""

    face_clicked: QtCore.Signal

    def _init_avatar(self, *, mouth: Callable[[], dict] | None = None,
                     caption: Callable[[], dict] | None = None, audible: Callable[[], bool] | None = None) -> None:
        self.renderer = AvatarRenderer()
        self.animator = Animator()
        self.signals = AvatarSignals(now=time.time())
        self.resolved = resolve(self.signals)
        self.quality = quality_for("balanced")
        self.effects = True
        self.captions_enabled = True
        self.mouth_source = mouth or (lambda: None)
        self.caption_source = caption or (lambda: {"text": "", "progress": 0.0, "active": False})
        self.audible_source = audible or (lambda: False)
        self.mic_level = 0.0
        self.out_level = 0.0
        self.projections: dict[str, str] = {}
        self.frame_times: deque = deque(maxlen=120)
        self.paint_count = 0
        self.bottom_reserved = 16
        self._boot_progress = 0.0
        self._tardis_tasks: set[str] = set()
        self._requested_noctario_disconnect = False

    # ------------------------------------------------------------ dados reais (do controlador)
    def on_state(self, state: dict) -> None:
        s = self.signals
        s.runtime_state = str(state.get("runtime_state") or "IDLE")
        shield = state.get("privacy_shield") or {}
        s.privacy_shield = bool(shield.get("active"))
        pending = state.get("pending_authorization")
        s.authorization = bool(pending and pending.get("status") == "pending")
        s.authorization_text = str(pending.get("description", "")) if s.authorization else ""
        boot = state.get("boot") or {}
        if boot.get("total"):
            self._boot_progress = min(1.0, float(boot.get("done", 0)) / float(boot["total"]))
        if s.runtime_state not in ("BOOTING", "") and self._boot_progress >= 0.999:
            s.booted = True
        s.boot_progress = self._boot_progress
        model = str(state.get("active_model") or "")
        action = state.get("current_action") or {}
        self.projections = {k: v for k, v in (
            ("modelo", model),
            ("tarefa", str(action.get("description") or action.get("skill") or "")),
            ("fase", str(state.get("cognitive_phase") or "")),
        ) if v}

    def on_event(self, kind: str, payload: dict) -> None:
        now = time.time()
        s = self.signals
        if kind == "COMPONENT_STARTED":
            self.animator.component_started()
        elif kind == "SYSTEM_READY":
            s.booted = True
            self._boot_progress = 1.0
            s.boot_progress = 1.0
        elif kind == "COMPONENT_FAILED":
            s.error_until, s.error_text = now + ERROR_WINDOW, f"{payload.get('component', '?')}: " \
                                                              f"{str(payload.get('error', ''))[:80]}"
            self.animator.component_lost()
        elif kind == "MODEL_UNAVAILABLE":
            s.error_until = now + ERROR_WINDOW
            fallback = payload.get("fallback")
            s.error_text = (f"{payload.get('provider', 'modelo')} indisponível" +
                            (f" — usando {fallback}" if fallback else ""))
            self.animator.component_lost()
        elif kind == "REMINDER_DUE" and not payload.get("silent"):
            s.alert_until, s.alert_text = now + ALERT_WINDOW, str(payload.get("notice") or payload.get("title") or "")
        elif kind == "NOCTARIO_ALERT":
            s.alert_until, s.alert_text = now + ALERT_WINDOW, str(payload.get("text") or "Noctário")
        elif kind == "NOCTARIO_LINK":
            if payload.get("link") == "perdido" and not payload.get("requested"):
                s.error_until, s.error_text = now + ERROR_WINDOW, "link do Noctário perdido"
                self.animator.component_lost()
            elif payload.get("link") == "conectado":
                self.animator.component_started()
        elif kind in TARDIS_EVENTS_START and payload.get("origin") == "jarvis":
            self._tardis_tasks.add(str(payload.get("id")))
            s.tardis_text = str(payload.get("kind_label") or payload.get("kind") or "")
        elif kind in TARDIS_EVENTS_END:
            self._tardis_tasks.discard(str(payload.get("id")))
        s.tardis = bool(self._tardis_tasks)

    def on_telemetry(self, telemetry: dict) -> None:
        self.mic_level = float(telemetry.get("mic_level") or 0.0)
        self.out_level = float(telemetry.get("out_level") or 0.0)
        self.signals.listening = bool(telemetry.get("listening"))
        self.signals.recognizing = bool(telemetry.get("recognizing"))

    def set_profile(self, profile_name: str, *, effects: bool) -> None:
        self.quality = quality_for(profile_name)
        self.effects = bool(effects)

    # ------------------------------------------------------------ relógio
    def update_state(self):
        """Resolve o estado agora (barato; vale mesmo com outra página à frente)."""
        s = self.signals
        s.now = time.time()
        try:
            s.audible = bool(self.audible_source())
        except Exception:
            s.audible = False
        self.resolved = resolve(s)
        return self.resolved

    def step(self, dt: float) -> None:
        self.update_state()
        s = self.signals
        mouth = None
        if self.resolved.key == "falando":
            try:
                mouth = self.mouth_source()
            except Exception:
                mouth = None
        self.animator.step(dt, self.resolved, mouth=mouth, mic_level=self.mic_level, out_level=self.out_level,
                           boot_progress=s.boot_progress if not s.booted else 1.0)

    def in_motion(self) -> bool:
        return self.animator.in_motion() or self.mic_level > 0.02

    # ------------------------------------------------------------ desenho
    def _paint(self, painter: QtGui.QPainter, width: int, height: int) -> None:
        started = time.perf_counter()
        self.renderer.render(painter, width, height, self.animator.rig, self.animator.t, self.quality,
                             effects=self.effects)
        self._overlay(painter, width, height)
        self.paint_count += 1
        self.frame_times.append(time.perf_counter() - started)

    def _overlay(self, p: QtGui.QPainter, width: int, height: int) -> None:
        resolved = self.resolved
        color = QtGui.QColor(*[int(c) for c in self.animator.rig.rgb])
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        # estado (canto superior esquerdo) e motivo
        p.setPen(theme.TEXT_BRIGHT)
        p.setFont(theme.font(13, weight=700, spacing=4.0))
        p.drawText(QtCore.QRectF(26, 18, width * 0.6, 26), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, "JARVIS")
        p.setPen(color)
        p.setFont(theme.font(8, weight=600, spacing=2.6))
        p.drawText(QtCore.QRectF(28, 44, width * 0.7, 18), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                   resolved.label + ("  ·  ALERTA" if resolved.alert_tint else ""))
        if resolved.detail:
            p.setPen(theme.TEXT_DIM)
            p.setFont(theme.font(8))
            metrics = QtGui.QFontMetricsF(p.font())
            p.drawText(QtCore.QRectF(28, 62, width * 0.5, 18), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter,
                       metrics.elidedText(resolved.detail, QtCore.Qt.ElideRight, width * 0.5))
        # projeções de dados reais (direita)
        if self.projections:
            p.setFont(theme.font(7.5, spacing=1.4))
            y = 24.0
            for label, value in self.projections.items():
                metrics = QtGui.QFontMetricsF(p.font())
                text = metrics.elidedText(value, QtCore.Qt.ElideRight, 240)
                p.setPen(theme.TEXT_DIM)
                p.drawText(QtCore.QRectF(width - 290, y, 70, 16), QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
                           label.upper())
                p.setPen(theme.TEXT)
                p.drawText(QtCore.QRectF(width - 212, y, 200, 16), QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, text)
                y += 18
        # legenda sincronizada
        if self.captions_enabled:
            caption = self.caption_source() or {}
            text = str(caption.get("text") or "")
            if text:
                self._draw_caption(p, width, height, text, float(caption.get("progress") or 0.0),
                                   bool(caption.get("active")), color)

    def _draw_caption(self, p: QtGui.QPainter, width: int, height: int, text: str, progress: float, active: bool,
                      color: QtGui.QColor) -> None:
        words = text.split()
        spoken = int(round(progress * len(words)))
        font = theme.font(12.5, weight=500)
        p.setFont(font)
        metrics = QtGui.QFontMetricsF(font)
        max_width = min(width - 80.0, 900.0)
        lines: list[list[tuple[str, bool]]] = [[]]
        line_width = 0.0
        for index, word in enumerate(words):
            w = metrics.horizontalAdvance(word + " ")
            if line_width + w > max_width and lines[-1]:
                lines.append([])
                line_width = 0.0
            lines[-1].append((word, index < spoken))
            line_width += w
        current_line = 0
        for i, line in enumerate(lines):
            if any(done for _w, done in line):
                current_line = i
        shown = lines[max(0, current_line - 1): current_line + 1] if len(lines) > 2 else lines
        box_h = 30.0 * len(shown) + 16
        top = height - self.bottom_reserved - box_h - 14
        box = QtCore.QRectF((width - max_width) / 2 - 16, top, max_width + 32, box_h)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(theme.with_alpha(theme.BG, 0.72 if active else 0.5))
        p.drawRoundedRect(box, 6, 6)
        y = top + 8
        for line in shown:
            total = sum(metrics.horizontalAdvance(word + " ") for word, _ in line)
            x = (width - total) / 2
            for word, done in line:
                p.setPen(theme.TEXT_BRIGHT if done else theme.with_alpha(theme.TEXT_DIM, 0.85 if active else 0.6))
                p.drawText(QtCore.QPointF(x, y + 21), word)
                x += metrics.horizontalAdvance(word + " ")
            y += 30

    def _face_hit(self, pos: QtCore.QPointF, width: int, height: int) -> bool:
        cx, cy, scale = self.renderer.frame(width, height)
        dx, dy = (pos.x() - cx) / (scale * 0.85), (pos.y() - cy) / (scale * 1.1)
        return dx * dx + dy * dy <= 1.0


class AvatarView(QtWidgets.QWidget, _AvatarCore):
    face_clicked = QtCore.Signal()
    backend = "cpu"

    def __init__(self, parent=None, **sources: Any):
        super().__init__(parent)
        self._init_avatar(**sources)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        self.setMinimumSize(480, 360)
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.setToolTip("Clique no rosto para ligar ou desligar o microfone")

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        painter = QtGui.QPainter(self)
        self._paint(painter, self.width(), self.height())
        painter.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() == QtCore.Qt.LeftButton and self._face_hit(event.position(), self.width(), self.height()):
            self.face_clicked.emit()


def create_gl_view(parent=None, **sources: Any):
    """Versão por GPU (QOpenGLWidget). Levanta RuntimeError se o OpenGL não estiver disponível."""
    from PySide6 import QtOpenGLWidgets

    class AvatarGLView(QtOpenGLWidgets.QOpenGLWidget, _AvatarCore):
        face_clicked = QtCore.Signal()
        backend = "gpu"

        def __init__(self, parent=None, **inner: Any):
            super().__init__(parent)
            self._init_avatar(**inner)
            self.setMinimumSize(480, 360)
            self.setToolTip("Clique no rosto para ligar ou desligar o microfone")

        def paintGL(self) -> None:  # noqa: N802 (Qt)
            painter = QtGui.QPainter(self)
            self._paint(painter, self.width(), self.height())
            painter.end()

        def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
            if event.button() == QtCore.Qt.LeftButton and self._face_hit(event.position(), self.width(),
                                                                         self.height()):
                self.face_clicked.emit()

    context = QtGui.QOpenGLContext()
    if not context.create():
        raise RuntimeError("o Qt não conseguiu criar um contexto OpenGL nesta máquina")
    return AvatarGLView(parent, **sources)
