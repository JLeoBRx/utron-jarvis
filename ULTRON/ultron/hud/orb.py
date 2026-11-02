"""Orbe compacto: a forma recolhida do JARVIS (sempre visível, arrastável).

Com a central 3D ativa, o orbe mostra o ORBE 3D da PRÓPRIA cena (a mesma vista, emprestada enquanto a janela
principal está recolhida — um motor só): janela redonda por máscara, uma camada transparente por cima recebe
o mouse (arrastar, duplo clique, menu) e desenha o aro. Sem a cena 3D, o desenho 2D abaixo continua valendo.

O orbe mostra o mesmo estado real da cena: o cérebro em miniatura (a mesma malha, no
mesmo giro), brilho do núcleo pelo estado de runtime, anel de profundidade cognitiva,
nível do microfone ao escutar e âmbar quando há uma autorização pendente. Clique duplo
expande o HUB; botão direito abre o menu.
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtWidgets

from . import theme
from .brain_view import mini_brain
from .scene import NeuralScene

STATE_LEVEL = {"IDLE": 0.5, "LISTENING": 0.7, "THINKING": 0.6, "PLANNING": 0.65, "EXECUTING": 0.8,
               "VERIFYING": 0.75, "RECOVERY": 0.7, "SPEAKING": 0.7, "IMAGINING": 0.8, "SIMULATING": 0.8,
               "DREAMING": 0.3, "NETWORK": 0.6, "AWAITING_AUTHORIZATION": 0.9, "ERROR": 0.6, "BOOTING": 0.5}


class _OrbOverlay(QtWidgets.QWidget):
    """Por cima da cena 3D: passa o mouse para o orbe e desenha o aro (esconde o serrilhado da máscara)."""

    def __init__(self, orb: "OrbWindow"):
        super().__init__(orb)
        self.orb = orb
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground, True)
        self.setCursor(QtCore.Qt.OpenHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.orb.mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.orb.mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.orb.mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt)
        self.orb.mouseDoubleClickEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        s = min(self.width(), self.height())
        c = QtCore.QPointF(self.width() / 2, self.height() / 2)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(QtCore.Qt.NoBrush)
        p.setPen(QtGui.QPen(theme.with_alpha(theme.BG, 1.0), 4.0))
        p.drawEllipse(c, s / 2 - 1.5, s / 2 - 1.5)
        tone = theme.ALERT if self.orb.scene.runtime_state == "AWAITING_AUTHORIZATION" else theme.PRIMARY
        p.setPen(QtGui.QPen(theme.with_alpha(tone, 0.75), 1.4))
        p.drawEllipse(c, s / 2 - 3.5, s / 2 - 3.5)
        p.end()


class OrbWindow(QtWidgets.QWidget):
    expand_requested = QtCore.Signal()
    menu_requested = QtCore.Signal(QtCore.QPoint)
    moved = QtCore.Signal(QtCore.QPoint)

    SIZE = 104
    SIZE_3D = 136                       # o núcleo 3D precisa de um pouco mais de área para ser legível

    def __init__(self, scene: NeuralScene):
        super().__init__(None, QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.scene = scene
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setToolTip("JARVIS — clique duplo para expandir")
        self._drag: QtCore.QPoint | None = None
        self._dragged = False
        self.scene_view = None                      # a cena 3D emprestada (None = desenho 2D)
        self.overlay = _OrbOverlay(self)
        self.overlay.hide()

    # ------------------------------------------------------------ cena 3D emprestada
    def attach_scene(self, view) -> None:
        """Recebe a vista 3D da janela principal (recolhida). O centro do orbe fica onde estava."""
        center = self.geometry().center()
        self.scene_view = view
        self.setFixedSize(self.SIZE_3D, self.SIZE_3D)
        if center != QtCore.QPoint(0, 0) and self.pos() != QtCore.QPoint(0, 0):
            self.move(center - QtCore.QPoint(self.SIZE_3D // 2, self.SIZE_3D // 2))
        view.setParent(self)
        view.setMinimumSize(1, 1)
        view.setGeometry(self.rect())
        view.show()
        self.overlay.setGeometry(self.rect())
        self.overlay.show()
        self.overlay.raise_()
        self.setMask(QtGui.QRegion(self.rect().adjusted(1, 1, -1, -1), QtGui.QRegion.Ellipse))

    def detach_scene(self):
        """Devolve a vista 3D (a janela principal vai reaparecer); o orbe volta ao desenho 2D."""
        view, self.scene_view = self.scene_view, None
        if view is not None:
            view.setMinimumSize(480, 360)
        self.overlay.hide()
        self.clearMask()
        center = self.geometry().center()
        self.setFixedSize(self.SIZE, self.SIZE)
        self.move(center - QtCore.QPoint(self.SIZE // 2, self.SIZE // 2))
        return view

    def place_default(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            size = self.width()
            self.move(area.right() - size - 24, area.bottom() - size - 24)

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
        if self.scene_view is not None:             # a cena 3D desenha; o aro vem da camada de cima
            if self.overlay.isVisible():
                self.overlay.update()
            return
        scene = self.scene
        s = self.SIZE
        c = QtCore.QPointF(s / 2, s / 2)
        now = scene.clock()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(QtGui.QPen(theme.with_alpha(theme.PRIMARY, 0.55), 1.0))
        p.setBrush(theme.with_alpha(theme.BG2, 0.92))
        p.drawEllipse(c, s * 0.44, s * 0.44)
        p.setPen(QtCore.Qt.NoPen)
        authorization = scene.runtime_state == "AWAITING_AUTHORIZATION"
        tone = theme.ALERT if authorization else theme.PRIMARY
        level = STATE_LEVEL.get(scene.runtime_state, 0.3)
        breath = 0.5 + 0.5 * math.sin(2 * math.pi * scene.breath)
        mic = float(scene.telemetry.get("mic_level", 0.0)) if scene.telemetry.get("listening") else 0.0
        intensity = min(1.0, level * (0.85 + 0.15 * breath) + 0.6 * mic + 0.4 * scene.release)
        grad = QtGui.QRadialGradient(c, s * 0.36)
        grad.setColorAt(0.0, theme.with_alpha(theme.TEXT_BRIGHT, 0.55 * intensity))
        grad.setColorAt(0.3, theme.with_alpha(tone, 0.35 * intensity))
        grad.setColorAt(1.0, theme.with_alpha(tone, 0.0))
        p.setBrush(grad)
        p.drawEllipse(c, s * 0.36, s * 0.36)
        mini_brain(p, scene, c.x(), c.y() - s * 0.01, s * 0.235, 0.6 + 0.4 * intensity)
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
            pen = QtGui.QPen(theme.with_alpha(theme.TEXT_BRIGHT, 0.35 + 0.6 * mic), 1.2)
            p.setPen(pen)
            p.setBrush(QtCore.Qt.NoBrush)
            radius = s * (0.30 + 0.08 * mic)
            p.drawEllipse(c, radius, radius)
        if authorization:
            pulse = 0.5 + 0.5 * math.sin(now * 4)
            p.setPen(QtGui.QPen(theme.with_alpha(theme.ALERT, 0.5 + 0.5 * pulse), 1.6))
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawEllipse(c, s * 0.46, s * 0.46)
        p.end()
