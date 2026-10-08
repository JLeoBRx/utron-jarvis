"""Orbe compacto: a forma recolhida do ULTRON (sempre visível, arrastável).

O orbe mostra o mesmo estado real da cena: brilho do núcleo pelo estado de runtime,
anel de profundidade cognitiva, nível do microfone ao escutar e âmbar quando há uma
autorização pendente. Clique duplo expande o HUB; botão direito abre o menu.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from . import theme
from .scene import NeuralScene

STATE_LEVEL = {"IDLE": 0.5, "LISTENING": 0.7, "THINKING": 0.6, "PLANNING": 0.65, "EXECUTING": 0.8,
               "VERIFYING": 0.75, "RECOVERY": 0.7, "SPEAKING": 0.7, "IMAGINING": 0.8, "SIMULATING": 0.8,
               "DREAMING": 0.3, "NETWORK": 0.6, "AWAITING_AUTHORIZATION": 0.9, "ERROR": 0.6, "BOOTING": 0.5}


class OrbWindow(QtWidgets.QWidget):
    expand_requested = QtCore.Signal()
    menu_requested = QtCore.Signal(QtCore.QPoint)
    moved = QtCore.Signal(QtCore.QPoint)

    SIZE = 104

    def __init__(self, scene: NeuralScene):
        super().__init__(None, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.scene = scene
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setToolTip("ULTRON — clique duplo para expandir")
        self._drag: QtCore.QPoint | None = None
        self._dragged = False

    def place_default(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            self.move(area.right() - self.SIZE - 24, area.bottom() - self.SIZE - 24)

    # ------------------------------------------------------------ interação
    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        if event.button() == QtCore.Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._dragged = False
        elif event.button() == QtCore.Qt.RightButton:
            self.menu_requested.emit(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self._drag is not None and event.buttons() & QtCore.Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)
            self._dragged = True

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self._drag is not None and self._dragged:
            self.moved.emit(self.pos())
        self._drag = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.expand_requested.emit()

    # ------------------------------------------------------------ desenho
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        scene = self.scene
        s = self.SIZE
        c = QtCore.QPointF(s / 2, s / 2)
        now = scene.clock()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(theme.with_alpha(theme.GOLD, 0.55), 1.0))
        p.setBrush(QtGui.QColor(8, 8, 8, 235))
        p.drawEllipse(c, s * 0.44, s * 0.44)
        p.setPen(QtCore.Qt.NoPen)
        authorization = scene.runtime_state == "AWAITING_AUTHORIZATION"
        tone = theme.AMBER if authorization else theme.GOLD
        level = STATE_LEVEL.get(scene.runtime_state, 0.3)
        breath = 0.5 + 0.5 * math.sin(2 * math.pi * scene.breath)
        mic = float(scene.telemetry.get("mic_level", 0.0)) if scene.telemetry.get("listening") else 0.0
        intensity = min(1.0, level * (0.85 + 0.15 * breath) + 0.6 * mic + 0.4 * scene.release)
        grad = QtGui.QRadialGradient(c, s * 0.36)
        grad.setColorAt(0.0, theme.with_alpha(theme.WARM_WHITE, intensity))
        grad.setColorAt(0.25, theme.with_alpha(tone, 0.85 * intensity))
        grad.setColorAt(1.0, theme.with_alpha(tone, 0.0))
        p.setBrush(grad)
        p.drawEllipse(c, s * 0.36, s * 0.36)
        # anel de profundidade cognitiva (0–9)
        rect = QtCore.QRectF(s * 0.1, s * 0.1, s * 0.8, s * 0.8)
        for i in range(10):
            on = i < scene.depth_level
            pen = QtGui.QPen(theme.with_alpha(tone, 0.9 if on else 0.18), 2.2)
            pen.setCapStyle(QtCore.Qt.FlatCap)
            p.setPen(pen)
            start = 90 - i * 36
            p.drawArc(rect, int((start - 30) * 16), int(26 * 16))
        if scene.telemetry.get("listening"):
            pen = QtGui.QPen(theme.with_alpha(theme.WARM_WHITE, 0.35 + 0.6 * mic), 1.2)
            p.setPen(pen)
            p.setBrush(QtCore.Qt.NoBrush)
            radius = s * (0.30 + 0.08 * mic)
            p.drawEllipse(c, radius, radius)
        if authorization:
            pulse = 0.5 + 0.5 * math.sin(now * 4)
            p.setPen(QtGui.QPen(theme.with_alpha(theme.AMBER, 0.5 + 0.5 * pulse), 1.6))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawEllipse(c, s * 0.46, s * 0.46)
        p.end()
