"""Conversa da página JARVIS — a INTERFACE DE INTERAÇÃO do JARVIS original, de volta.

Como no original (jarvis_hud.py: conversa, STATUS/HORAS, PARAR, COPIAR RESPOSTA, LIMPAR, Ctrl+L):

* cada mensagem com horário: ``[HH:MM] VOCÊ ▸``, ``[HH:MM] J.A.R.V.I.S. ▸`` e ``// sistema``;
* até 200 linhas com rolagem (as mais antigas saem);
* STATUS ("status do sistema") e HORAS ("que horas são") enviam o pedido ao núcleo pelo mesmo caminho
  do teclado; PARAR cancela o que estiver em andamento (pedido, fala, autorização pendente);
* COPIAR RESPOSTA copia a última resposta do JARVIS; LIMPAR (ou Ctrl+L) limpa só a tela — o histórico
  de atividades continua registrado.

O painel só mostra o que chegou pelos eventos reais (USER_INPUT e RESPONSE_READY).
"""
from __future__ import annotations

import html
import time

from PySide6 import QtCore, QtGui, QtWidgets

from . import theme

MAX_LINES = 200
SOURCES = {"voice": "voz", "text": "texto", "hud": "interface", "tardis": "TARDIS", "sistemas": "sistemas"}
_DIM = "#7F9BB7"
_USER = "#9FB9D3"
_JARVIS = "#67F3FF"
_ERROR = "#FF8A9A"
_ALERT = "#FFC870"


def _clock(at: float | None) -> str:
    return time.strftime("%H:%M", time.localtime(at if at else time.time()))


class ConversationPanel(QtWidgets.QFrame):
    command = QtCore.Signal(str)              # STATUS / HORAS → pedido enviado ao núcleo
    stop_requested = QtCore.Signal()          # PARAR
    close_requested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Conversation")
        self.setStyleSheet(theme.PANEL_STYLESHEET + """
            QFrame#Conversation { background: rgba(5, 14, 28, 225); border-left: 1px solid rgba(0, 217, 255, 70); }
            QTextBrowser#ConversationLog { background: transparent; border: none; font-size: 10pt; }
        """)
        self.last_response = ""
        self.lines = 0
        title = QtWidgets.QLabel("INTERFACE DE INTERAÇÃO")
        title.setObjectName("PanelTitle")
        hide = QtWidgets.QPushButton("×")
        hide.setObjectName("HudButton")
        hide.setFixedWidth(30)
        hide.setToolTip("Esconder a conversa (o botão CONVERSA traz de volta)")
        hide.setCursor(QtCore.Qt.PointingHandCursor)
        hide.clicked.connect(self.close_requested)
        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.addWidget(title, 1)
        head.addWidget(hide)
        self.log = QtWidgets.QTextBrowser()
        self.log.setObjectName("ConversationLog")
        self.log.setOpenLinks(False)
        self.log.document().setMaximumBlockCount(MAX_LINES)
        self.log.setPlaceholderText("Nenhuma mensagem nesta sessão.")
        row1 = QtWidgets.QHBoxLayout()
        row2 = QtWidgets.QHBoxLayout()
        for row in (row1, row2):
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
        self.status_button = self._button("STATUS", "Status do sistema (mesmo pedido que \"status do sistema\")")
        self.status_button.clicked.connect(lambda: self.command.emit("status do sistema"))
        self.time_button = self._button("HORAS", "Que horas são")
        self.time_button.clicked.connect(lambda: self.command.emit("que horas são"))
        self.stop_button = self._button("PARAR", "Cancela o pedido em andamento, a fala e a autorização pendente (Esc)")
        self.stop_button.clicked.connect(self.stop_requested)
        self.copy_button = self._button("COPIAR RESPOSTA", "Copiar a última resposta do JARVIS")
        self.copy_button.clicked.connect(self.copy_last)
        self.clear_button = self._button("LIMPAR", "Limpar a conversa da tela (Ctrl+L); o histórico de atividades fica")
        self.clear_button.clicked.connect(self.clear)
        for button in (self.status_button, self.time_button, self.stop_button):
            row1.addWidget(button)
        for button in (self.copy_button, self.clear_button):
            row2.addWidget(button)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 12, 12)
        layout.setSpacing(8)
        layout.addLayout(head)
        layout.addWidget(self.log, 1)
        layout.addLayout(row1)
        layout.addLayout(row2)

    @staticmethod
    def _button(text: str, tip: str) -> QtWidgets.QPushButton:
        button = QtWidgets.QPushButton(text)
        button.setObjectName("HudButton")
        button.setToolTip(tip)
        button.setCursor(QtCore.Qt.PointingHandCursor)
        button.setFocusPolicy(QtCore.Qt.NoFocus)
        return button

    # ------------------------------------------------------------ mensagens
    def _append(self, html_line: str) -> None:
        bar = self.log.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self.log.append(html_line)
        self.lines = min(MAX_LINES, self.lines + 1)
        if at_bottom:
            bar.setValue(bar.maximum())

    def add_user(self, text: str, source: str = "text", at: float | None = None) -> None:
        origin = SOURCES.get(source, source)
        self._append(f'<span style="color:{_DIM}">[{_clock(at)}]</span> '
                     f'<span style="color:{_USER}"><b>VOCÊ</b> ({html.escape(origin)}) ▸</span> '
                     f'{html.escape(text)}')

    def add_jarvis(self, text: str, *, error: bool = False, at: float | None = None) -> None:
        self.last_response = text
        color = _ERROR if error else "#DCEEFF"
        self._append(f'<span style="color:{_DIM}">[{_clock(at)}]</span> '
                     f'<span style="color:{_JARVIS}"><b>J.A.R.V.I.S.</b> ▸</span> '
                     f'<span style="color:{color}">{html.escape(text)}</span>')

    def add_system(self, text: str, *, alert: bool = False, at: float | None = None) -> None:
        self._append(f'<span style="color:{_DIM}">[{_clock(at)}] // </span>'
                     f'<span style="color:{_ALERT if alert else _DIM}">{html.escape(text)}</span>')

    def on_event(self, kind: str, payload: dict, at: float | None = None) -> None:
        if kind == "USER_INPUT":
            text = str(payload.get("text") or "").strip()
            if text:
                self.add_user(text, str(payload.get("source") or "text"), at)
        elif kind == "RESPONSE_READY":
            text = str(payload.get("text") or "").strip()
            if not text:
                return
            response_kind = payload.get("kind", "answer")
            if not payload.get("partial"):
                self.add_jarvis(text, error=response_kind == "error", at=at)
            elif response_kind == "reminder":
                self.add_system(f"lembrete: {text}", alert=True, at=at)
            elif response_kind == "insight":
                self.add_system(f"sugestão: {text}", at=at)
            else:                                  # progresso, aviso de ocupado, confirmação de captura
                self.add_system(text, at=at)
        elif kind == "AUTHORIZATION_REQUIRED":
            self.add_system(f"autorização pedida: {payload.get('description', '')}", alert=True, at=at)
        elif kind == "AUTHORIZATION_RESOLVED" and payload.get("status") in ("approved", "denied", "expired"):
            outcome = {"approved": "autorizada", "denied": "negada", "expired": "expirou (negada)"}[payload["status"]]
            self.add_system(f"autorização {outcome}: {payload.get('description', '')}", at=at)

    # ------------------------------------------------------------ ações
    def clear(self) -> None:
        self.log.clear()
        self.lines = 0

    def copy_last(self) -> bool:
        if not self.last_response:
            return False
        QtGui.QGuiApplication.clipboard().setText(self.last_response)
        self.add_system("última resposta copiada")
        return True

    def text(self) -> str:
        return self.log.toPlainText()
