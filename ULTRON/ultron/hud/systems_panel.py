"""PAINEL DE SISTEMAS do JARVIS CORE: voz, rede local e desempenho/saúde.

Fica no HUB principal porque trata do cérebro operacional do computador (o TARDIS cuida da
memória pessoal). É a mesma infraestrutura de páginas do TARDIS (``panels.PageHost``):
leitura fora da thread gráfica, recarga por evento e ações pelo Neural Core.
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .panels import NetworkPage, PageHost, SystemPage, _label
from .voice_panel import VoicePanel

TABS = (("voice", "VOZ"), ("network", "REDE LOCAL"), ("system", "DESEMPENHO E SAÚDE"))


class SystemsPanel(PageHost):
    def __init__(self, core, *, state: dict | None = None, profile=None):
        super().__init__(core, state=state, profile=profile)
        self.setObjectName("Panel")
        self.setWindowTitle("JARVIS — Sistemas")
        self.resize(1180, 760)
        self.setMinimumSize(860, 540)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.voice = VoicePanel(core, self)
        self.tabs.addTab(self.voice, "VOZ")
        self.tabs.addTab(self.add_page(NetworkPage(self)), "REDE LOCAL")
        self.tabs.addTab(self.add_page(SystemPage(self)), "DESEMPENHO E SAÚDE")
        self.tabs.currentChanged.connect(self._tab_changed)
        title = _label("JARVIS · SISTEMAS", "PanelTitle")
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 10)
        root.addWidget(title)
        root.addWidget(self.tabs, 1)
        root.addWidget(self.authorization)
        root.addWidget(self.feedback)
        QtGui.QShortcut(QtGui.QKeySequence("Esc"), self, activated=self.hide)
        self.present_authorization(self.state.get("pending_authorization"))

    def visible_keys(self) -> set[str]:
        key = TABS[self.tabs.currentIndex()][0] if 0 <= self.tabs.currentIndex() < len(TABS) else ""
        return {key} & set(self.pages)

    def show_section(self, section: str | None) -> None:
        keys = [key for key, _ in TABS]
        if section in keys:
            self.tabs.setCurrentIndex(keys.index(section))
        self._tab_changed(self.tabs.currentIndex())

    def _tab_changed(self, index: int) -> None:
        if 0 <= index < len(TABS) and TABS[index][0] in self.pages and self.isVisible():
            self.ensure_loaded(TABS[index][0])

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        QtCore.QTimer.singleShot(0, lambda: self._tab_changed(self.tabs.currentIndex()))
