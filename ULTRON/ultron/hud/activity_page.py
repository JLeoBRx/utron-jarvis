"""ATIVIDADES — o histórico de atividades do JARVIS na tela.

Pedidos, ações, confirmações, verificações, lembretes e falhas, com origem, estado, duração e o
resultado ou o erro REAIS (``core.activity``). A tabela é atualizada ao vivo pelo evento
``ACTIVITY_UPDATED``; filtros e buscas releem o banco fora da thread da interface. "LIMPAR HISTÓRICO"
passa pelo executor (categoria "apagar dados": pede confirmação na barra de decisão).
"""
from __future__ import annotations

import json
import time
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from ..core.activity import KINDS
from . import theme
from .panels import _button, _label, _Reader

COLUMNS = ("QUANDO", "TIPO", "ORIGEM", "ATIVIDADE", "ESTADO", "DURAÇÃO", "RESULTADO OU ERRO")
STATE_GROUPS = {"": ("Todos os estados", None),
                "open": ("Em andamento", ("recebido", "executando", "aguardando_confirmacao")),
                "done": ("Concluídos e verificados", ("concluido", "verificado", "pergunta")),
                "unconfirmed": ("Sem confirmação", ("nao_confirmado",)),
                "failed": ("Falhas, negados e recusados", ("falhou", "negado", "recusado", "cancelado"))}
STATE_COLORS = {"verificado": "#3DFFA8", "concluido": "#9FE8C9", "pergunta": "#DCEEFF", "recebido": "#67F3FF",
                "executando": "#00D9FF", "aguardando_confirmacao": "#FFB547", "nao_confirmado": "#FFC870",
                "falhou": "#FF5D73", "negado": "#FF8A9A", "recusado": "#FF8A9A", "cancelado": "#9FB9D3",
                "aviso": "#FFC870"}
MAX_ROWS = 1000


def _when(ts: float | None) -> str:
    if not ts:
        return "—"
    today = time.localtime().tm_yday == time.localtime(ts).tm_yday
    return time.strftime("%H:%M:%S" if today else "%d/%m %H:%M", time.localtime(ts))


def _duration(seconds: float | None) -> str:
    if seconds is None:
        return "…"
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 120:
        return f"{seconds:.1f} s"
    return f"{seconds / 60:.1f} min"


class ActivityModel(QtCore.QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802 (Qt)
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802 (Qt)
        return len(COLUMNS)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):  # noqa: N802 (Qt)
        if role == QtCore.Qt.DisplayRole and orientation == QtCore.Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=QtCore.Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        item = self.rows[index.row()]
        column = index.column()
        if role == QtCore.Qt.DisplayRole:
            return (_when(item.get("started_at")), item.get("kind_label", ""), item.get("origin", ""),
                    item.get("title", ""), item.get("state_label", ""), _duration(item.get("seconds")),
                    item.get("error") or item.get("result") or "")[column]
        if role == QtCore.Qt.ForegroundRole:
            if column == 4:
                return QtGui.QColor(STATE_COLORS.get(item.get("state"), "#DCEEFF"))
            if column == 6 and item.get("error"):
                return QtGui.QColor("#FF8A9A")
        if role == QtCore.Qt.ToolTipRole and column in (3, 6):
            return item.get("title") if column == 3 else (item.get("error") or item.get("result") or "")
        if role == QtCore.Qt.UserRole:
            return item
        return None

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = list(rows)[:MAX_ROWS]
        self.endResetModel()

    def upsert(self, item: dict) -> None:
        for row, current in enumerate(self.rows):
            if current.get("id") == item.get("id"):
                self.rows[row] = item
                self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))
                return
        self.beginInsertRows(QtCore.QModelIndex(), 0, 0)
        self.rows.insert(0, item)
        self.endInsertRows()
        if len(self.rows) > MAX_ROWS:
            self.beginRemoveRows(QtCore.QModelIndex(), MAX_ROWS, len(self.rows) - 1)
            del self.rows[MAX_ROWS:]
            self.endRemoveRows()


class ActivityPage(QtWidgets.QWidget):
    """Página ATIVIDADES da plataforma."""

    _clear_done = QtCore.Signal(object)

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.core = core
        self._clear_done.connect(self._cleared, QtCore.Qt.QueuedConnection)
        self.setObjectName("Panel")
        self.setStyleSheet(theme.PANEL_STYLESHEET)
        self.reader = _Reader(self)
        self.reader.loaded.connect(self._loaded)
        self.loaded_once = False
        self._dirty = True
        self._closed = False
        self._notice = ""                         # resultado da última ação, mantido na próxima recarga
        title = _label("HISTÓRICO DE ATIVIDADES", "PanelTitle")
        intro = _label("Tudo o que o JARVIS recebeu, decidiu e fez — com o resultado real. Uma ação só aparece como "
                       "verificada quando a verificação independente confirmou.", "PanelDim")
        self.kind = QtWidgets.QComboBox()
        self.kind.addItem("Todos os tipos", "")
        for key, label in KINDS.items():
            self.kind.addItem(label, key)
        self.state = QtWidgets.QComboBox()
        for key, (label, _states) in STATE_GROUPS.items():
            self.state.addItem(label, key)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Buscar no título, na entrada, no resultado ou no erro…")
        self.search.setClearButtonEnabled(True)
        self._search_timer = QtCore.QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.reload)
        self.search.textChanged.connect(lambda *_: self._search_timer.start())
        self.kind.currentIndexChanged.connect(lambda *_: self.reload())
        self.state.currentIndexChanged.connect(lambda *_: self.reload())
        refresh = _button("ATUALIZAR")
        refresh.clicked.connect(self.reload)
        copy = _button("COPIAR", "Copiar as linhas visíveis (ou a selecionada) como texto")
        copy.clicked.connect(self.copy_visible)
        self.clear_button = _button("LIMPAR HISTÓRICO", "Apagar o histórico (categoria \"apagar dados\": pede "
                                                        "confirmação)")
        self.clear_button.clicked.connect(self.request_clear)
        filters = QtWidgets.QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(self.kind)
        filters.addWidget(self.state)
        filters.addWidget(self.search, 1)
        filters.addWidget(refresh)
        filters.addWidget(copy)
        filters.addWidget(self.clear_button)
        self.model = ActivityModel(self)
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        for column, width in enumerate((92, 86, 90, 330, 130, 74)):
            self.table.setColumnWidth(column, width)
        self.table.selectionModel().currentRowChanged.connect(lambda current, _prev: self._show_detail(current))
        self.detail = QtWidgets.QTextBrowser()
        self.detail.setOpenLinks(False)
        self.detail.setPlaceholderText("Selecione uma atividade para ver entrada, resultado, erro, detalhes e as "
                                       "ações ligadas a ela.")
        split = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.status = _label("", "PanelDim")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 12)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addLayout(filters)
        layout.addWidget(split, 1)
        layout.addWidget(self.status)

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), theme.BG2)
        p.end()

    # ------------------------------------------------------------ leitura
    def filters(self) -> dict:
        group = STATE_GROUPS.get(self.state.currentData() or "", ("", None))[1]
        kind = self.kind.currentData() or ""
        return {"kinds": [kind] if kind else None, "states": list(group) if group else None,
                "search": self.search.text().strip()}

    def reload(self) -> None:
        if self._closed:
            return
        activity = getattr(self.core, "activity", None)
        if activity is None:
            self.status.setText("Histórico de atividades indisponível nesta execução.")
            return
        self._dirty = False
        wanted = self.filters()
        self.reader.request("activity", lambda: {"rows": activity.recent(500, **wanted), "count": activity.count(),
                                                 "summary": activity.summary(since=time.time() - 86400)})

    @QtCore.Slot(str, int, object)
    def _loaded(self, key: str, generation: int, data) -> None:
        if self._closed or not self.reader.current(key, generation):
            return
        if isinstance(data, Exception):
            self.status.setText(f"Falha ao ler o histórico: {data}")
            return
        self.loaded_once = True
        self.model.set_rows(data["rows"])
        summary = data["summary"]
        failures = sum(summary.get(s, 0) for s in ("falhou", "negado", "recusado"))
        text = (f"{len(data['rows'])} exibida(s) de {data['count']} registrada(s) · últimas 24 h: "
                f"{summary.get('verificado', 0)} verificada(s), {failures} falha(s)/negada(s)/recusada(s)"
                f"{' · histórico DESLIGADO nas configurações' if not self._enabled() else ''}")
        if self._notice:
            text, self._notice = f"{self._notice} · {text}", ""
        self.status.setText(text)

    def _enabled(self) -> bool:
        return bool(getattr(self.core.settings(), "activity_history", True))

    def _matches(self, item: dict) -> bool:
        wanted = self.filters()
        if wanted["kinds"] and item.get("kind") not in wanted["kinds"]:
            return False
        if wanted["states"] and item.get("state") not in wanted["states"]:
            return False
        text = wanted["search"].casefold()
        if text and not any(text in str(item.get(k) or "").casefold() for k in ("title", "input", "result", "error")):
            return False
        return True

    def platform_event(self, kind: str, payload: dict, at: float) -> None:
        if kind != "ACTIVITY_UPDATED":
            return
        if not self.isVisible():
            self._dirty = True                       # relida ao aparecer
            return
        if self._matches(payload):
            self.model.upsert(payload)
            current = self.table.currentIndex()
            if current.isValid() and self.model.rows[current.row()].get("id") == payload.get("id"):
                self._show_detail(current)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        if self._dirty or not self.loaded_once:
            QtCore.QTimer.singleShot(0, self.reload)

    # ------------------------------------------------------------ detalhe e ações
    def _show_detail(self, index: QtCore.QModelIndex) -> None:
        if not index.isValid():
            self.detail.clear()
            return
        item = self.model.rows[index.row()]
        children = self.core.activity.children(item["id"]) if getattr(self.core, "activity", None) else []
        lines = [f"<b style='color:#67F3FF'>{_html(item['kind_label'])}</b> · "
                 f"<span style='color:{STATE_COLORS.get(item['state'], '#DCEEFF')}'>{item['state_label']}</span>",
                 f"<b>{_html(item['title'])}</b>",
                 f"<span style='color:#7F9BB7'>id {item['id']} · origem {_html(item['origin'])} · início "
                 f"{time.strftime('%d/%m/%Y %H:%M:%S', time.localtime(item['started_at']))} · duração "
                 f"{_duration(item['seconds'])}</span>"]
        if item.get("input"):
            lines.append(f"<p><b>Entrada</b><br>{_html(item['input'])}</p>")
        if item.get("result"):
            lines.append(f"<p><b>Resultado</b><br>{_html(item['result'])}</p>")
        if item.get("error"):
            lines.append(f"<p><b style='color:#FF8A9A'>Erro</b><br>{_html(item['error'])}</p>")
        if item.get("detail"):
            lines.append("<p><b>Detalhes</b><br><span style='color:#9FB9D3'>"
                         + "<br>".join(f"{_html(k)}: {_html(json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)}"
                                       for k, v in item["detail"].items()) + "</span></p>")
        if children:
            lines.append("<p><b>Ações deste pedido</b><br>" + "<br>".join(
                f"<span style='color:{STATE_COLORS.get(c['state'], '#DCEEFF')}'>● {c['state_label']}</span> "
                f"{_html(c['title'])} <span style='color:#7F9BB7'>({_duration(c['seconds'])})</span>"
                for c in children) + "</p>")
        self.detail.setHtml("<br>".join(lines[:3]) + "".join(lines[3:]))

    def visible_text(self) -> str:
        rows = self.model.rows
        current = self.table.currentIndex()
        chosen = [rows[current.row()]] if current.isValid() else rows
        return "\n".join(f"[{_when(r.get('started_at'))}] {r.get('kind_label')} · {r.get('origin')} · "
                         f"{r.get('title')} · {r.get('state_label')} · {_duration(r.get('seconds'))}"
                         + (f" · {r.get('error') or r.get('result')}" if (r.get('error') or r.get('result')) else "")
                         for r in chosen)

    def copy_visible(self) -> None:
        text = self.visible_text()
        if text:
            QtGui.QGuiApplication.clipboard().setText(text)
            self.status.setText("Copiado para a área de transferência.")

    def request_clear(self) -> None:
        """Pelo executor: categoria "apagar dados" → confirmação na barra de decisão da plataforma."""
        core = self.core

        def work():
            try:
                outcome = core.run_skill("activity.clear", {}, origin="user")
            except Exception as exc:
                outcome = {"success": False, "error": str(exc), "text": ""}
            if not self._closed:
                self._clear_done.emit(outcome)

        self.status.setText("Pedindo confirmação para apagar o histórico…")
        core.runtime.submit("actions", work, name="atividades:limpar")

    @QtCore.Slot(object)
    def _cleared(self, outcome: dict) -> None:
        if self._closed:
            return
        self._notice = (outcome.get("text") if outcome.get("success") else
                        f"Histórico mantido: {outcome.get('error') or 'não autorizado'}")
        self.status.setText(self._notice)
        self.reload()

    def shutdown(self) -> None:
        self._closed = True
        self.reader.shutdown()


def _html(value: Any) -> str:
    import html
    return html.escape(str(value or ""))
