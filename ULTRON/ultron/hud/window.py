"""Janela principal do ULTRON NEURAL HUB e seus controles.

A janela é só apresentação e entrada: o texto digitado, os botões de autorização e o
microfone são repassados ao Neural Core pelo controlador. F11 alterna tela cheia; Esc
recolhe para o orbe compacto.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from . import theme
from .brain_view import BrainView


def app_icon(size: int = 64) -> QtGui.QIcon:
    """Ícone procedural: anel dourado com núcleo."""
    pix = QtGui.QPixmap(size, size)
    pix.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(pix)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setBrush(QtGui.QColor(10, 9, 8))
    p.setPen(QtGui.QPen(theme.GOLD, size * 0.07))
    margin = size * 0.1
    p.drawEllipse(QtCore.QRectF(margin, margin, size - 2 * margin, size - 2 * margin))
    grad = QtGui.QRadialGradient(size / 2, size / 2, size * 0.24)
    grad.setColorAt(0, theme.WARM_WHITE)
    grad.setColorAt(0.5, theme.GOLD)
    grad.setColorAt(1, QtGui.QColor(0, 0, 0, 0))
    p.setBrush(grad)
    p.setPen(QtCore.Qt.NoPen)
    p.drawEllipse(QtCore.QPointF(size / 2, size / 2), size * 0.24, size * 0.24)
    p.end()
    return QtGui.QIcon(pix)


class InputBar(QtWidgets.QWidget):
    submitted = QtCore.Signal(str)
    mic_toggled = QtCore.Signal(bool)
    voice_toggled = QtCore.Signal(bool)
    collapse = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HudInput")
        self._history: list[str] = []
        self._cursor = 0
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.line = QtWidgets.QLineEdit()
        self.line.setObjectName("HudLine")
        self.line.setPlaceholderText("Diga \"Ultron\" ou digite um comando…")
        self.line.returnPressed.connect(self._submit)
        self.line.installEventFilter(self)
        self.mic = self._button("MIC", "Microfone ligado/desligado (Ctrl+M)", checkable=True)
        self.mic.setChecked(True)
        self.mic.toggled.connect(self.mic_toggled)
        self.voice = self._button("VOZ", "Fala do ULTRON ligada/desligada", checkable=True)
        self.voice.setChecked(True)
        self.voice.toggled.connect(self.voice_toggled)
        self.orb = self._button("ORBE", "Recolher para o orbe compacto (Esc)")
        self.orb.clicked.connect(self.collapse)
        layout.addWidget(self.line, 1)
        layout.addWidget(self.mic)
        layout.addWidget(self.voice)
        layout.addWidget(self.orb)

    @staticmethod
    def _button(text: str, tip: str, *, checkable: bool = False) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(text)
        button.setObjectName("HudButton")
        button.setToolTip(tip)
        button.setCheckable(checkable)
        button.setCursor(QtCore.Qt.PointingHandCursor)
        button.setFocusPolicy(QtCore.Qt.NoFocus)
        return button

    def _submit(self) -> None:
        text = self.line.text().strip()
        if not text:
            return
        self._history.append(text)
        del self._history[:-50]
        self._cursor = len(self._history)
        self.line.clear()
        self.submitted.emit(text)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 (Qt)
        if obj is self.line and event.type() == QtCore.QEvent.KeyPress and self._history:
            if event.key() == QtCore.Qt.Key_Up:
                self._cursor = max(0, self._cursor - 1)
                self.line.setText(self._history[self._cursor])
                return True
            if event.key() == QtCore.Qt.Key_Down:
                self._cursor = min(len(self._history), self._cursor + 1)
                self.line.setText(self._history[self._cursor] if self._cursor < len(self._history) else "")
                return True
        return super().eventFilter(obj, event)


class DecisionBar(QtWidgets.QWidget):
    """Barra de decisão (autorização ou sugestão): texto + dois botões."""

    decided = QtCore.Signal(bool)

    def __init__(self, yes: str, no: str, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 8, 8)
        layout.setSpacing(10)
        self.label = QtWidgets.QLabel()
        self.label.setObjectName("HudLabel")
        self.label.setWordWrap(True)
        self.yes = QtWidgets.QPushButton(yes)
        self.yes.setObjectName("HudPrimary")
        self.no = QtWidgets.QPushButton(no)
        self.no.setObjectName("HudButton")
        for button, value in ((self.yes, True), (self.no, False)):
            button.setCursor(QtCore.Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, v=value: self.decided.emit(v))
        layout.addWidget(self.label, 1)
        layout.addWidget(self.yes)
        layout.addWidget(self.no)
        self.setAutoFillBackground(False)
        self.hide()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor(14, 12, 10, 225))
        p.setPen(QtGui.QPen(theme.with_alpha(theme.AMBER, 0.8), 1))
        p.drawLine(0, 0, self.width(), 0)
        p.end()

    def present(self, text: str | None) -> None:
        if text:
            self.label.setText(text)
            if not self.isVisible():
                self.show()
                self.yes.setFocus()
        else:
            self.hide()


class HudWindow(QtWidgets.QWidget):
    collapse_requested = QtCore.Signal()
    closing = QtCore.Signal()

    def __init__(self, view: BrainView):
        super().__init__()
        self.setWindowTitle("ULTRON — Neural Hub")
        self.setWindowIcon(app_icon())
        self.resize(1320, 820)
        self.setMinimumSize(820, 540)
        self.view = view
        view.setParent(self)
        self.input = InputBar(self)
        self.authorization = DecisionBar("AUTORIZAR", "NEGAR", self)
        self.suggestion = DecisionBar("SIM", "NÃO", self)
        self.input.collapse.connect(self.collapse_requested)
        QtGui.QShortcut(QtGui.QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QtGui.QShortcut(QtGui.QKeySequence("Esc"), self, activated=self.collapse_requested)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+M"), self, activated=self.input.mic.toggle)
        self.hide_to_tray = True

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt)
        w, h = self.width(), self.height()
        self.view.setGeometry(0, 0, w, h)
        bar_w = min(820, w - 48)
        x = (w - bar_w) // 2
        self.input.setGeometry(x, h - 62, bar_w, 40)
        self._layout_bars()
        super().resizeEvent(event)

    def _layout_bars(self) -> None:
        w, h = self.width(), self.height()
        bar_w = min(820, w - 48)
        x = (w - bar_w) // 2
        y = h - 62 - 8
        for bar in (self.authorization, self.suggestion):
            height = 54
            bar.setGeometry(x, y - height, bar_w, height)
            if bar.isVisible():
                y -= height + 6
        self.view.bottom_reserved = h - y

    def refresh_layout(self) -> None:
        self._layout_bars()

    def toggle_fullscreen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def focus_input(self) -> None:
        self.input.line.setFocus()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt)
        if self.hide_to_tray:
            event.ignore()                     # continua na bandeja; "Sair" encerra de fato
            self.hide()
            self.closing.emit()
        else:
            super().closeEvent(event)
