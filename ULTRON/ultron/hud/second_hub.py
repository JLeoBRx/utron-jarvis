"""HUB 2 — JARVIS SECOND BRAIN.

O impacto prático da atividade do JARVIS: prioridades do dia, compromissos, atrasados, linha do
tempo, tarefas, projetos, ideias e notas, busca na memória, central de notificações, dispositivos
da rede, saúde do sistema, revisão do que foi inferido e lixeira.

Regras desta tela:

* é o MESMO programa e o MESMO estado do HUB 1 (cache de estado do controlador + eventos do
  barramento) — não existe um segundo sistema de estado;
* nenhuma consulta roda na thread da interface: cada seção pede seus dados a uma thread de
  leitura própria e recebe o resultado por sinal (respostas antigas são descartadas);
* atualização por EVENTO (registro criado/alterado, lembrete, rede…): só as seções afetadas
  ficam "sujas" e só a visível recarrega (com debounce); seções ocultas carregam ao abrir;
* toda alteração passa pelo Neural Core (``core.run_skill``): autonomia, autorização específica,
  auditoria e verificação lida do banco. A tela mostra o resultado real — falha aparece como
  falha, e "executado sem confirmação" nunca vira animação de sucesso;
* só dados reais: listas vazias dizem que estão vazias.
"""
from __future__ import annotations

import datetime as dt
import html
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from PySide6 import QtCore, QtGui, QtWidgets

from ..secondbrain import timeutil
from ..secondbrain.models import ACTIONABLE, KINDS, PRIORITIES, RELATIONS, STATUS_LABELS
from . import theme
from .window import DecisionBar, app_icon

log = logging.getLogger("ultron.hub2")

SECTIONS = (("today", "HOJE"), ("timeline", "LINHA DO TEMPO"), ("tasks", "TAREFAS"), ("projects", "PROJETOS"),
            ("ideas", "IDEIAS & NOTAS"), ("search", "BUSCA NA MEMÓRIA"), ("notifications", "NOTIFICAÇÕES"),
            ("network", "REDE"), ("system", "SISTEMA"), ("review", "REVISÃO & LIXEIRA"))
RECORD_SECTIONS = frozenset({"today", "timeline", "tasks", "projects", "ideas", "search", "review"})
EVENT_SECTIONS = {
    "RECORD_CREATED": RECORD_SECTIONS, "RECORD_UPDATED": RECORD_SECTIONS, "RECORD_RESTORED": RECORD_SECTIONS,
    "RECORD_DELETED": RECORD_SECTIONS | {"notifications"},
    "REMINDER_DUE": frozenset({"notifications", "today", "timeline"}),
    "REMINDER_SNOOZED": frozenset({"notifications", "today", "timeline"}),
    "NOTIFICATION": frozenset({"notifications"}),
    "NETWORK_INVENTORY_UPDATED": frozenset({"network"}), "DEVICE_UPDATED": frozenset({"network"}),
    "HEALTH_UPDATED": frozenset({"system"}),
}
OPEN = ("open", "in_progress", "waiting")
RELOAD_DEBOUNCE_MS = 250

STYLE = """
QWidget#Hub2 { background: #070706; }
QWidget#Hub2 QLabel { color: #e8decc; }
QLabel#H2Title { color: #d6a242; font-size: 10pt; letter-spacing: 3px; }
QLabel#H2Dim { color: #968c7c; font-size: 9pt; }
QLabel#H2Big { color: #fff0d6; font-size: 13pt; }
QLabel#H2Answer { color: #f0e6d2; background: rgba(214,162,66,18); border-left: 2px solid #d6a242; padding: 8px; }
QListWidget#H2Nav { background: #0b0a09; border: none; border-right: 1px solid rgba(214,162,66,40);
    color: #b9ab93; font-size: 9pt; outline: none; }
QListWidget#H2Nav::item { padding: 11px 14px; letter-spacing: 2px; }
QListWidget#H2Nav::item:selected { background: rgba(214,162,66,34); color: #ffe6b8;
    border-left: 2px solid #d6a242; }
QListWidget#H2Nav::item:hover { color: #f0e6d2; }
QFrame#H2Card { background: #0e0d0c; border: 1px solid rgba(214,162,66,38); border-radius: 4px; }
QListWidget, QTreeWidget, QTableView, QPlainTextEdit, QTextBrowser {
    background: #0b0a09; color: #e8decc; border: 1px solid rgba(214,162,66,30);
    selection-background-color: rgba(214,162,66,70); selection-color: #fff0d6; alternate-background-color: #100f0d; }
QHeaderView::section { background: #12100e; color: #d6a242; border: none; border-bottom: 1px solid rgba(214,162,66,60);
    padding: 5px 6px; font-size: 8pt; letter-spacing: 1px; }
QTableView { gridline-color: rgba(214,162,66,14); }
QLineEdit, QComboBox { background: #0e0d0c; color: #f0e6d2; border: 1px solid rgba(214,162,66,60);
    border-radius: 3px; padding: 5px 8px; }
QComboBox QAbstractItemView { background: #121110; color: #e8decc; selection-background-color: rgba(214,162,66,70); }
QCheckBox { color: #e8decc; }
QScrollBar:vertical { background: #0b0a09; width: 10px; }
QScrollBar::handle:vertical { background: rgba(214,162,66,60); border-radius: 4px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""


# ====================================================================== utilidades
def _button(text: str, tip: str = "", *, primary: bool = False) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setObjectName("HudPrimary" if primary else "HudButton")
    button.setCursor(QtCore.Qt.PointingHandCursor)
    if tip:
        button.setToolTip(tip)
    return button


def _label(text: str = "", name: str = "") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(True)
    return label


def _when_text(record: dict, now: dt.datetime) -> str:
    if not record.get("due_local"):
        return ""
    try:
        text = timeutil.describe(timeutil.parse_wall(record["due_local"]), all_day=record.get("all_day", False), now=now)
    except ValueError:
        return record["due_local"]
    return text + (" ↻" if record.get("recurrence") else "")


def record_row(record: dict, now: dt.datetime, now_epoch: float) -> dict:
    """Linha pronta para exibição (calculada na thread de leitura, não na da interface)."""
    due_at = record.get("due_at")
    open_ = record.get("status") in OPEN and not record.get("deleted_at") and not record.get("archived_at")
    overdue = bool(open_ and due_at is not None and record.get("kind") in ACTIONABLE and
                   now_epoch > due_at + (86400 if record.get("all_day") else 0))
    origin = "confirmado" if record.get("confirmed", True) else f"inferido ({float(record.get('confidence', 0)):.0%})"
    return {"record": record, "overdue": overdue, "inferred": not record.get("confirmed", True),
            "cells": (KINDS.get(record.get("kind"), "Registro"), record.get("title", ""), _when_text(record, now),
                      PRIORITIES.get(int(record.get("priority", 2)), ""),
                      ("ATRASADO" if overdue else STATUS_LABELS.get(record.get("status"), record.get("status", ""))),
                      origin)}


def rows_of(service, records) -> list[dict]:
    now, epoch = service.now_wall(), service.now()
    return [record_row(r.to_dict() if hasattr(r, "to_dict") else r, now, epoch) for r in records]


# ====================================================================== leitura fora da interface
class _Reader(QtCore.QObject):
    """Uma thread de leitura para o HUB 2. Cada seção tem uma geração: respostas antigas são ignoradas."""

    loaded = QtCore.Signal(str, int, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ultron-hub2")
        self._generation: dict[str, int] = {}
        self._closed = False
        self.loads = 0

    def request(self, key: str, fn: Callable[[], Any]) -> None:
        if self._closed:
            return
        generation = self._generation.get(key, 0) + 1
        self._generation[key] = generation
        try:
            self._pool.submit(self._run, key, generation, fn)
        except RuntimeError:                     # já encerrado
            pass

    def _run(self, key: str, generation: int, fn: Callable[[], Any]) -> None:
        if self._closed or self._generation.get(key) != generation:
            return                               # pedido superado por outro mais novo
        try:
            data = fn()
        except Exception as exc:                 # erro real vai para a tela, sem derrubar nada
            log.warning("HUB 2: leitura de %s falhou: %s", key, exc)
            data = exc
        if not self._closed:
            self.loads += 1
            self.loaded.emit(key, generation, data)

    def current(self, key: str, generation: int) -> bool:
        return self._generation.get(key) == generation

    def shutdown(self) -> None:
        self._closed = True
        self._pool.shutdown(wait=False, cancel_futures=True)


# ====================================================================== modelos de tabela (virtualizados)
class RecordModel(QtCore.QAbstractTableModel):
    HEADERS = ("TIPO", "TÍTULO", "QUANDO", "PRIORIDADE", "ESTADO", "ORIGEM")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []

    def set_rows(self, rows: list[dict]) -> None:
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802 (Qt)
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802 (Qt)
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):  # noqa: N802 (Qt)
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.rows[index.row()]
        if role == QtCore.Qt.DisplayRole:
            return row["cells"][index.column()]
        if role == QtCore.Qt.ForegroundRole:
            if row["overdue"]:
                return theme.ALERT
            if row["record"].get("status") in ("done", "cancelled"):
                return theme.TEXT_DIM
            if row["inferred"]:
                return QtGui.QColor(196, 178, 140)
            return None
        if role == QtCore.Qt.FontRole and row["inferred"]:
            font = QtGui.QFont()
            font.setItalic(True)
            return font
        if role == QtCore.Qt.ToolTipRole:
            record = row["record"]
            tip = record.get("body") or ""
            if not record.get("confirmed", True):
                tip = (tip + "\n" if tip else "") + f"Inferido de: “{record.get('origin_detail', '')}”"
            return tip or None
        if role == QtCore.Qt.UserRole:
            return row["record"]
        return None

    def record(self, row: int) -> dict | None:
        return self.rows[row]["record"] if 0 <= row < len(self.rows) else None


class DeviceModel(QtCore.QAbstractTableModel):
    HEADERS = ("NOME", "IP", "MAC", "FABRICANTE", "TIPO", "ESTADO", "CONFIANÇA", "ÚLTIMA VEZ", "CONHECIDO")
    SORT_ROLE = QtCore.Qt.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self.devices: list[dict] = []

    def set_devices(self, devices: list[dict]) -> None:
        self.beginResetModel()
        self.devices = list(devices)
        self.endResetModel()

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802 (Qt)
        return 0 if parent.isValid() else len(self.devices)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802 (Qt)
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):  # noqa: N802 (Qt)
        if orientation == QtCore.Qt.Horizontal and role == QtCore.Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    def _cell(self, d: dict, column: int):
        if column == 0:
            return d.get("name", "")
        if column == 1:
            return d.get("ip", "") + (f"  (+{len(d['ipv6'])} IPv6)" if d.get("ipv6") else "")
        if column == 2:
            return d.get("mac") or "—"
        if column == 3:
            return d.get("vendor") or "—"
        if column == 4:
            return d.get("kind_label", "")
        if column == 5:
            return d.get("state_label", "")
        if column == 6:
            return f"{float(d.get('confidence') or 0):.0%}"
        if column == 7:
            return time.strftime("%d/%m %H:%M", time.localtime(d["last_seen"])) if d.get("last_seen") else "—"
        return "sim" if d.get("trusted") else "não"

    def data(self, index, role=QtCore.Qt.DisplayRole):
        if not index.isValid():
            return None
        d = self.devices[index.row()]
        if role == QtCore.Qt.DisplayRole:
            return self._cell(d, index.column())
        if role == self.SORT_ROLE:
            if index.column() == 1:
                try:
                    return tuple(int(x) for x in d.get("ip", "").split("."))
                except ValueError:
                    return (999,)
            if index.column() == 6:
                return float(d.get("confidence") or 0)
            if index.column() == 7:
                return float(d.get("last_seen") or 0)
            return str(self._cell(d, index.column())).casefold()
        if role == QtCore.Qt.ForegroundRole:
            if d.get("status") == "absent":
                return theme.TEXT_DIM
            if d.get("status") == "online" and not d.get("trusted"):
                return theme.ALERT
            return None
        if role == QtCore.Qt.ToolTipRole:
            parts = [f"Métodos: {', '.join(d.get('method_labels') or []) or '—'}"]
            if d.get("ipv6"):
                parts.append("IPv6: " + ", ".join(d["ipv6"]))
            if d.get("vendor_source"):
                parts.append(f"Fabricante via: {d['vendor_source']}")
            if d.get("notes"):
                parts.append(f"Notas: {d['notes']}")
            return "\n".join(parts)
        if role == QtCore.Qt.UserRole:
            return d
        return None


class _DeviceProxy(QtCore.QSortFilterProxyModel):
    def lessThan(self, left, right) -> bool:  # noqa: N802 (Qt)
        a, b = left.data(DeviceModel.SORT_ROLE), right.data(DeviceModel.SORT_ROLE)
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


def _table(model, *, stretch: int = 1) -> QtWidgets.QTableView:
    view = QtWidgets.QTableView()
    view.setModel(model)
    view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
    view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
    view.setAlternatingRowColors(True)
    view.verticalHeader().setVisible(False)
    view.verticalHeader().setDefaultSectionSize(26)
    view.setShowGrid(False)
    view.setWordWrap(False)
    view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
    header = view.horizontalHeader()
    header.setStretchLastSection(False)
    header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
    header.setSectionResizeMode(stretch, QtWidgets.QHeaderView.Stretch)
    return view


# ====================================================================== cabeçalho
class Header(QtWidgets.QWidget):
    """Título, estado de atividade compartilhado com o HUB 1 e indicadores do resumo central."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(74)
        self.activity = "IDLE"
        self.reason = ""
        self.summary: dict = {}
        self.network: dict = {}
        self.pulse = 0.0                    # brilho âmbar breve quando um lembrete dispara

    def set_state(self, state: dict) -> None:
        self.activity = str(state.get("activity") or "IDLE")
        self.reason = str(state.get("runtime_reason") or "")
        self.summary = dict(state.get("second_brain") or {})
        self.network = dict(state.get("network_state") or {})
        self.update()

    def chips(self) -> list[tuple[str, bool]]:
        s, n = self.summary, self.network
        chips = [(f"ABERTAS {s.get('open_tasks', 0)}", False), (f"ATRASADAS {s.get('overdue', 0)}", bool(s.get("overdue"))),
                 (f"HOJE {s.get('today', 0)}", False), (f"REVISAR {s.get('unreviewed', 0)}", bool(s.get("unreviewed"))),
                 (f"AVISOS {s.get('unread_notifications', 0)}", bool(s.get("unread_notifications")))]
        nxt = s.get("next_reminder") or {}
        if nxt:
            chips.append((f"PRÓXIMO: {str(nxt.get('title', ''))[:22]} · {nxt.get('when_text', '')}", False))
        if n:
            if not n.get("discovery_enabled", True):
                chips.append(("REDE: DESCOBERTA DESLIGADA", False))
            elif n.get("scan_error"):
                chips.append(("REDE: INDISPONÍVEL", True))
            else:
                chips.append((f"REDE {n.get('devices_online', 0)} PRESENTES · {n.get('devices_untrusted_online', 0)} "
                              f"NÃO CONHECIDOS", bool(n.get("devices_untrusted_online"))))
        return chips

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt)
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        grad = QtGui.QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QtGui.QColor(16, 14, 12))
        grad.setColorAt(1, QtGui.QColor(8, 8, 7))
        p.fillRect(self.rect(), grad)
        if self.pulse > 0:
            p.fillRect(self.rect(), theme.with_alpha(theme.ALERT, 0.12 * self.pulse))
        p.setPen(QtGui.QPen(theme.with_alpha(theme.PRIMARY, 0.55), 1))
        p.drawLine(0, h - 1, w, h - 1)
        p.setPen(theme.PRIMARY)
        p.setFont(theme.font(13, weight=600, spacing=4))
        p.drawText(QtCore.QRectF(20, 8, 420, 28), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, "JARVIS · SECOND BRAIN")
        p.setFont(theme.font(8.5, spacing=2))
        p.setPen(theme.TEXT_DIM)
        today = dt.date.today()
        p.drawText(QtCore.QRectF(20, 34, 420, 18), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft,
                   f"{timeutil.DIAS[today.weekday()].upper()} · {today:%d/%m/%Y}")
        # atividade (o mesmo contrato do HUB 1)
        tone = theme.ALERT if self.activity in ("ERROR", "RECOVERY", "REMINDING") else theme.PRIMARY
        p.setPen(tone)
        p.setFont(theme.font(9, weight=600, spacing=3))
        right = QtCore.QRectF(w - 380, 8, 360, 22)
        p.drawText(right, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight, f"● {self.activity}")
        if self.reason:
            p.setPen(theme.TEXT_DIM)
            p.setFont(theme.font(8))
            p.drawText(QtCore.QRectF(w - 380, 30, 360, 18), QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight,
                       self.reason[:60])
        # indicadores
        x = 20.0
        p.setFont(theme.font(7.5, weight=600, spacing=1.5))
        metrics = QtGui.QFontMetricsF(p.font())
        for text, alert in self.chips():
            width = metrics.horizontalAdvance(text) + 18
            if x + width > w - 20:
                break
            rect = QtCore.QRectF(x, 52, width, 17)
            p.setPen(QtGui.QPen(theme.with_alpha(theme.ALERT if alert else theme.PRIMARY, 0.65 if alert else 0.35), 1))
            p.setBrush(theme.with_alpha(theme.ALERT if alert else theme.PRIMARY, 0.10 if alert else 0.04))
            p.drawRoundedRect(rect, 3, 3)
            p.setPen(theme.TEXT_BRIGHT if alert else theme.TEXT)
            p.drawText(rect, QtCore.Qt.AlignCenter, text)
            x += width + 8
        p.end()


# ====================================================================== diálogo de registro
class RecordDialog(QtWidgets.QDialog):
    """Criar ou editar um registro. Datas em português ("amanhã às 18h") ou "AAAA-MM-DD HH:MM"."""

    def __init__(self, parent=None, *, record: dict | None = None, kind: str = "task"):
        super().__init__(parent)
        self.record = record
        self.setWindowTitle("Editar registro" if record else "Novo registro")
        self.setObjectName("Hub2")
        self.setMinimumWidth(520)
        form = QtWidgets.QFormLayout(self)
        self.kind = QtWidgets.QComboBox()
        for key, label in KINDS.items():
            self.kind.addItem(label, key)
        self.kind.setCurrentIndex(max(0, self.kind.findData((record or {}).get("kind", kind))))
        self.title = QtWidgets.QLineEdit((record or {}).get("title", ""))
        self.when = QtWidgets.QLineEdit((record or {}).get("due_local", ""))
        self.when.setPlaceholderText("amanhã às 18h · sexta · 2026-10-20 14:00 · vazio = sem data")
        self.remind = QtWidgets.QCheckBox("Lembrar no horário")
        self.priority = QtWidgets.QComboBox()
        for value, label in PRIORITIES.items():
            self.priority.addItem(label, value)
        self.priority.setCurrentIndex(max(0, self.priority.findData(int((record or {}).get("priority", 2)))))
        self.status = QtWidgets.QComboBox()
        for key, label in STATUS_LABELS.items():
            self.status.addItem(label, key)
        self.status.setCurrentIndex(max(0, self.status.findData((record or {}).get("status", "open"))))
        self.project = QtWidgets.QLineEdit()
        self.project.setPlaceholderText("nome do projeto (opcional)")
        self.body = QtWidgets.QPlainTextEdit((record or {}).get("body", ""))
        self.body.setFixedHeight(110)
        self.confirm = QtWidgets.QCheckBox("Confirmar (era inferido)")
        form.addRow("Tipo", self.kind)
        form.addRow("Título", self.title)
        form.addRow("Quando", self.when)
        if record is None:
            form.addRow("", self.remind)
        form.addRow("Prioridade", self.priority)
        if record is not None:
            form.addRow("Estado", self.status)
        form.addRow("Projeto", self.project)
        form.addRow("Descrição", self.body)
        if record is not None and not record.get("confirmed", True):
            self.confirm.setChecked(True)
            form.addRow("", self.confirm)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self) -> None:
        if not self.title.text().strip():
            self.title.setFocus()
            return
        self.accept()

    def create_args(self) -> dict:
        title = " ".join(self.title.text().split())
        args = {"text": title, "title": title, "kind": self.kind.currentData(), "priority": self.priority.currentData()}
        if self.when.text().strip():
            args["when"] = self.when.text().strip()
            args["remind"] = self.remind.isChecked()
        if self.project.text().strip():
            args["project"] = self.project.text().strip()
        if self.body.toPlainText().strip():
            args["body"] = self.body.toPlainText().strip()
        return args

    def update_args(self) -> dict:
        record = self.record or {}
        args: dict[str, Any] = {"ref": record["id"]}
        title = " ".join(self.title.text().split())
        if title != record.get("title"):
            args["title"] = title
        if self.kind.currentData() != record.get("kind"):
            args["kind"] = self.kind.currentData()
        if int(self.priority.currentData()) != int(record.get("priority", 2)):
            args["priority"] = self.priority.currentData()
        if self.status.currentData() != record.get("status"):
            args["status"] = self.status.currentData()
        when = self.when.text().strip()
        if when and when != record.get("due_local", ""):
            args["when"] = when
        if self.body.toPlainText().strip() != (record.get("body") or "").strip() and self.body.toPlainText().strip():
            args["body"] = self.body.toPlainText().strip()
        if self.project.text().strip():
            args["project"] = self.project.text().strip()
        if self.confirm.isChecked() and not record.get("confirmed", True):
            args["confirm"] = True
        return args


# ====================================================================== páginas
class Page(QtWidgets.QWidget):
    key = ""
    title = ""

    def __init__(self, hub: "SecondBrainWindow"):
        super().__init__()
        self.hub = hub
        self.service = hub.core.second_brain
        self.layout_ = QtWidgets.QVBoxLayout(self)
        self.layout_.setContentsMargins(22, 16, 22, 12)
        self.layout_.setSpacing(10)
        head = QtWidgets.QHBoxLayout()
        head.addWidget(_label(self.title, "H2Title"))
        head.addStretch(1)
        self.toolbar = QtWidgets.QHBoxLayout()
        self.toolbar.setSpacing(6)
        head.addLayout(self.toolbar)
        self.layout_.addLayout(head)
        self.status = _label("", "H2Dim")

    def fetch(self) -> Callable[[], Any]:     # pragma: no cover - cada página define
        raise NotImplementedError

    def apply(self, data: Any) -> None:       # pragma: no cover
        raise NotImplementedError

    def failed(self, exc: Exception) -> None:
        self.status.setText(f"Falha ao carregar: {exc}")

    def run(self, label: str, skill: str, args: dict | None = None) -> None:
        self.hub.run_action(label, skill, args or {})


class RecordsPage(Page):
    """Tabela de registros + painel de detalhes (relações, origem, histórico) + ações."""

    allow_complete = True
    new_kind = "task"

    def __init__(self, hub):
        super().__init__(hub)
        self.model = RecordModel(self)
        self.table = _table(self.model)
        self.table.doubleClicked.connect(lambda _i: self.edit())
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._selected())
        self.detail = QtWidgets.QTextBrowser()
        self.detail.setMinimumWidth(300)
        self.detail.setOpenLinks(False)
        split = QtWidgets.QSplitter()
        split.addWidget(self.table)
        split.addWidget(self.detail)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.filters = QtWidgets.QHBoxLayout()
        self.layout_.addLayout(self.filters)
        self.layout_.addWidget(split, 1)
        self.layout_.addWidget(self.status)
        self.add_actions()

    def add_actions(self) -> None:
        new = _button("+ NOVO", "Criar um registro", primary=True)
        new.clicked.connect(self.new)
        self.toolbar.addWidget(new)
        if self.allow_complete:
            done = _button("CONCLUIR", "Marcar o selecionado como concluído")
            done.clicked.connect(lambda: self._act("Concluir", "secondbrain.complete"))
            self.toolbar.addWidget(done)
        edit = _button("EDITAR")
        edit.clicked.connect(self.edit)
        archive = _button("ARQUIVAR", "Tirar das listas sem excluir")
        archive.clicked.connect(lambda: self._act("Arquivar", "secondbrain.archive"))
        trash = _button("LIXEIRA", "Mandar para a lixeira (recuperável)")
        trash.clicked.connect(lambda: self._act("Lixeira", "secondbrain.delete"))
        for button in (edit, archive, trash):
            self.toolbar.addWidget(button)

    def selected(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        return self.model.record(rows[0].row()) if rows else None

    def _act(self, label: str, skill: str) -> None:
        record = self.selected()
        if record is None:
            self.status.setText("Selecione um registro.")
            return
        self.run(f"{label}: {record['title']}", skill, {"ref": record["id"]})

    def new(self) -> None:
        dialog = RecordDialog(self, kind=self.new_kind)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            args = dialog.create_args()
            self.run(f"Registrar: {args['title']}", "secondbrain.capture", args)

    def edit(self) -> None:
        record = self.selected()
        if record is None:
            self.status.setText("Selecione um registro.")
            return
        dialog = RecordDialog(self, record=record)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            args = dialog.update_args()
            if len(args) > 1:
                self.run(f"Editar: {record['title']}", "secondbrain.update", args)

    def apply_rows(self, rows: list[dict], *, empty: str) -> None:
        selected = (self.selected() or {}).get("id")
        self.model.set_rows(rows)
        self.status.setText(f"{len(rows)} registro(s)." if rows else empty)
        if selected:
            for i, row in enumerate(rows):
                if row["record"]["id"] == selected:
                    self.table.selectRow(i)
                    break
        if not rows:
            self.detail.clear()

    def _selected(self) -> None:
        record = self.selected()
        if record is None:
            return
        service = self.service

        def work():
            return {"record": record, "history": service.history(record["id"])[:10],
                    "related": service.related(record["id"]),
                    "project": service.get(record["project_id"]).title if record.get("project_id") and
                    service.get(record["project_id"]) else ""}

        self.hub.reader.request(f"detail:{self.key}", work)

    def show_detail(self, data: dict) -> None:
        r = data["record"]
        now = self.service.now_wall()

        def e(text) -> str:
            return html.escape(str(text))

        origin = ("Confirmado" if r.get("confirmed", True) else
                  f"<span style='color:#ec8426'>Inferido ({float(r.get('confidence', 0)):.0%}) — confirme ou corrija</span>")
        lines = [f"<div style='color:#fff0d6;font-size:13pt'>{e(r['title'])}</div>",
                 f"<div style='color:#d6a242;letter-spacing:2px'>{e(KINDS.get(r['kind'], ''))} · "
                 f"{e(STATUS_LABELS.get(r['status'], r['status']))} · prioridade {e(PRIORITIES.get(int(r.get('priority', 2)), ''))}</div>"]
        if r.get("due_local"):
            lines.append(f"<p>Quando: {e(_when_text(r, now))} <span style='color:#968c7c'>({e(r['due_local'])}"
                         f"{' · fuso ' + e(r['tz']) if r.get('tz') else ''})</span></p>")
        if data.get("project"):
            lines.append(f"<p>Projeto: {e(data['project'])}</p>")
        if r.get("body"):
            lines.append(f"<p style='white-space:pre-wrap'>{e(r['body'])}</p>")
        lines.append(f"<p>Origem: {origin}<br><span style='color:#968c7c'>{e(r.get('origin', ''))}"
                     f"{': “' + e(r['origin_detail']) + '”' if r.get('origin_detail') else ''}</span></p>")
        if data.get("related"):
            lines.append("<p style='color:#d6a242'>RELAÇÕES</p><ul>")
            for rel in data["related"][:12]:
                label = RELATIONS.get(rel["type"], rel["type"])
                text = (f"{label} {rel['record']['title']}" if rel.get("direction") == "out" else
                        f"{rel['record']['title']} {label} este")
                lines.append(f"<li>{e(text)}</li>")
            lines.append("</ul>")
        if data.get("history"):
            lines.append("<p style='color:#d6a242'>HISTÓRICO</p><ul>")
            for item in data["history"]:
                when = time.strftime("%d/%m %H:%M", time.localtime(item.get("at", 0)))
                lines.append(f"<li><span style='color:#968c7c'>{when}</span> {e(item.get('action', ''))}"
                             f"{' · ' + e(item.get('origin')) if item.get('origin') else ''}</li>")
            lines.append("</ul>")
        self.detail.setHtml("".join(lines))


class TodayPage(Page):
    key, title = "today", "HOJE"

    def __init__(self, hub):
        super().__init__(hub)
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(12)
        self.lists = {}
        for i, (key, title) in enumerate((("priorities", "PRIORIDADES"), ("events", "COMPROMISSOS DE HOJE"),
                                          ("overdue", "ATRASADOS"), ("reminders", "PRÓXIMOS LEMBRETES"),
                                          ("activity", "ATIVIDADE RECENTE"))):
            card = QtWidgets.QFrame()
            card.setObjectName("H2Card")
            box = QtWidgets.QVBoxLayout(card)
            box.setContentsMargins(12, 10, 12, 10)
            box.addWidget(_label(title, "H2Title"))
            widget = QtWidgets.QListWidget()
            widget.setFrameShape(QtWidgets.QFrame.NoFrame)
            widget.itemDoubleClicked.connect(self._open)
            box.addWidget(widget, 1)
            self.lists[key] = widget
            grid.addWidget(card, i // 2 if i < 4 else 2, i % 2 if i < 4 else 0, 1, 1 if i < 4 else 2)
        self.layout_.addLayout(grid, 1)
        self.layout_.addWidget(self.status)
        new = _button("+ ANOTAR", "Novo registro", primary=True)
        new.clicked.connect(lambda: self.hub.focus_capture())
        self.toolbar.addWidget(new)

    def fetch(self):
        service = self.service

        def work():
            day = service.today()
            return {"priorities": rows_of(service, day["priorities"]), "events": rows_of(service, day["events"]),
                    "overdue": rows_of(service, day["overdue"]), "reminders": day["upcoming_reminders"],
                    "activity": service.activity(limit=14)}
        return work

    def _fill(self, key: str, items: list[tuple[str, Any, bool]], empty: str) -> None:
        widget = self.lists[key]
        widget.clear()
        if not items:
            item = QtWidgets.QListWidgetItem(empty)
            item.setForeground(theme.TEXT_DIM)
            item.setFlags(QtCore.Qt.NoItemFlags)
            widget.addItem(item)
            return
        for text, payload, alert in items:
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, payload)
            if alert:
                item.setForeground(theme.ALERT)
            widget.addItem(item)

    def apply(self, data: dict) -> None:
        def rec(rows):
            return [(f"{r['cells'][1]}" + (f" — {r['cells'][2]}" if r["cells"][2] else "") +
                     (" · inferido" if r["inferred"] else ""), r["record"], r["overdue"]) for r in rows]

        self._fill("priorities", rec(data["priorities"]), "Nenhuma prioridade registrada para hoje.")
        self._fill("events", rec(data["events"]), "Nenhum compromisso hoje.")
        self._fill("overdue", rec(data["overdue"]), "Nada atrasado.")
        self._fill("reminders", [(f"{r['title']} — {r['when_text']}", None, False) for r in data["reminders"]],
                   "Nenhum lembrete agendado.")
        names = {"created": "criado", "updated": "editado", "edited": "editado", "completed": "concluído",
                 "reminded": "lembrete disparado", "reminder_set": "lembrete agendado", "snoozed": "adiado",
                 "deleted": "na lixeira", "restored": "restaurado", "archived": "arquivado", "confirmed": "confirmado"}
        self._fill("activity", [(f"{time.strftime('%d/%m %H:%M', time.localtime(a['at']))}  "
                                 f"{names.get(a['action'], a['action'])} · {a.get('title') or '(excluído)'}", None, False)
                                for a in data["activity"]], "Sem atividade ainda.")
        self.status.setText("Dados do Second Brain local. Dê dois cliques num item para abrir em Tarefas.")

    def _open(self, item) -> None:
        record = item.data(QtCore.Qt.UserRole)
        if isinstance(record, dict):
            self.hub.show_section("tasks")


class TimelinePage(Page):
    key, title = "timeline", "LINHA DO TEMPO · 14 DIAS"

    def __init__(self, hub):
        super().__init__(hub)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["QUANDO", "O QUÊ", "TIPO"])
        self.tree.setColumnWidth(0, 220)
        self.tree.setColumnWidth(1, 460)
        self.layout_.addWidget(self.tree, 1)
        self.layout_.addWidget(self.status)

    def fetch(self):
        service = self.service

        def work():
            return {"items": service.timeline(days=14), "now": service.now_wall(), "tz": service.tz}
        return work

    def apply(self, data: dict) -> None:
        self.tree.clear()
        days: dict[str, QtWidgets.QTreeWidgetItem] = {}
        now = data["now"]
        for item in data["items"]:
            wall = timeutil.from_epoch(item["at"], data["tz"]) if item.get("at") else None
            if wall is None:
                continue
            day_key = wall.date().isoformat()
            if day_key not in days:
                label = timeutil.describe(wall, all_day=True, now=now)
                top = QtWidgets.QTreeWidgetItem([label.upper(), "", ""])
                top.setForeground(0, theme.PRIMARY)
                self.tree.addTopLevelItem(top)
                days[day_key] = top
            if item["kind"] == "record":
                record = item["record"]
                child = QtWidgets.QTreeWidgetItem(["dia inteiro" if record.get("all_day") else f"{wall:%H:%M}",
                                                   record["title"], KINDS.get(record["kind"], "")])
                if not record.get("confirmed", True):
                    child.setForeground(1, QtGui.QColor(196, 178, 140))
            else:
                rem = item["reminder"]
                child = QtWidgets.QTreeWidgetItem([f"{wall:%H:%M}", f"lembrete: {rem['title']}", "Lembrete"])
                child.setForeground(1, theme.ALERT)
            days[day_key].addChild(child)
        self.tree.expandAll()
        self.status.setText(f"{len(data['items'])} item(ns) nos próximos 14 dias." if data["items"] else
                            "Nada agendado nos próximos 14 dias.")


class TasksPage(RecordsPage):
    key, title = "tasks", "TAREFAS, COMPROMISSOS E PRAZOS"

    def __init__(self, hub):
        super().__init__(hub)
        self.scope = QtWidgets.QComboBox()
        for key, label in (("open", "Abertas"), ("overdue", "Atrasadas"), ("today", "Hoje"), ("week", "Até domingo"),
                           ("done", "Concluídas"), ("all", "Todas")):
            self.scope.addItem(label, key)
        self.kind = QtWidgets.QComboBox()
        self.kind.addItem("Todos os tipos", "")
        for key in ACTIONABLE:
            self.kind.addItem(KINDS[key], key)
        for combo in (self.scope, self.kind):
            combo.currentIndexChanged.connect(lambda *_: self.hub.reload(self.key))
            self.filters.addWidget(combo)
        self.filters.addStretch(1)

    def fetch(self):
        service, scope, kind = self.service, self.scope.currentData(), self.kind.currentData()
        kinds = (kind,) if kind else ACTIONABLE

        def work():
            if scope == "overdue":
                records = [r for r in service.overdue(limit=300) if r.kind in kinds]
            elif scope == "today":
                start, end = service._day_bounds()
                records = service.due_between(start, end, kinds=kinds)
            elif scope == "week":
                records = service.week_open(kinds=kinds)
            elif scope == "done":
                records = service.list(kinds=kinds, status=("done", "cancelled"), order="recent", limit=300)
            elif scope == "all":
                records = service.list(kinds=kinds, limit=500)
            else:
                records = service.list(kinds=kinds, status=OPEN, limit=500)
            return rows_of(service, records)
        return work

    def apply(self, rows) -> None:
        self.apply_rows(rows, empty="Nenhum registro neste filtro.")


class IdeasPage(RecordsPage):
    key, title = "ideas", "IDEIAS, NOTAS E PESSOAS"
    allow_complete = False
    new_kind = "idea"

    def __init__(self, hub):
        super().__init__(hub)
        self.kind = QtWidgets.QComboBox()
        for key, label in (("idea", "Ideias"), ("note", "Notas"), ("person", "Pessoas"), ("", "Todas")):
            self.kind.addItem(label, key)
        self.kind.currentIndexChanged.connect(lambda *_: self.hub.reload(self.key))
        self.filters.addWidget(self.kind)
        self.filters.addStretch(1)

    def fetch(self):
        service, kind = self.service, self.kind.currentData()

        def work():
            kinds = (kind,) if kind else ("idea", "note", "person")
            return rows_of(service, service.list(kinds=kinds, order="recent", limit=500))
        return work

    def apply(self, rows) -> None:
        self.apply_rows(rows, empty="Nada salvo nesta categoria.")


class ProjectsPage(RecordsPage):
    key, title = "projects", "PROJETOS ATIVOS"
    new_kind = "project"

    def __init__(self, hub):
        super().__init__(hub)
        self.projects = QtWidgets.QListWidget()
        self.projects.setMaximumWidth(280)
        self.projects.currentItemChanged.connect(lambda *_: self.hub.reload(self.key, keep_projects=True))
        split = self.table.parentWidget()
        split.insertWidget(0, self.projects)
        self._project_cache: list[dict] = []

    def fetch(self):
        service = self.service
        current = self.projects.currentItem()
        project_id = current.data(QtCore.Qt.UserRole) if current is not None else None

        def work():
            projects = service.projects()
            pid = project_id or (projects[0]["record"]["id"] if projects else None)
            records = service.list(project=pid, order="smart", limit=400) if pid else []
            return {"projects": projects, "project_id": pid, "rows": rows_of(service, records)}
        return work

    def apply(self, data) -> None:
        if [p["record"]["id"] for p in data["projects"]] != [p["record"]["id"] for p in self._project_cache] or \
                data["projects"] != self._project_cache:
            self._project_cache = data["projects"]
            self.projects.blockSignals(True)
            self.projects.clear()
            for p in data["projects"]:
                counts = ", ".join(f"{n} {KINDS.get(k, k).lower()}" for k, n in sorted(p["counts"].items()))
                item = QtWidgets.QListWidgetItem(f"{p['record']['title']}\n{p['open']} aberto(s) · {counts or 'vazio'}")
                item.setData(QtCore.Qt.UserRole, p["record"]["id"])
                self.projects.addItem(item)
                if p["record"]["id"] == data["project_id"]:
                    self.projects.setCurrentItem(item)
            self.projects.blockSignals(False)
        self.apply_rows(data["rows"], empty="Nenhum projeto ativo." if not data["projects"] else
                        "Nada registrado neste projeto ainda.")


class SearchPage(RecordsPage):
    key, title = "search", "BUSCA NA MEMÓRIA"
    allow_complete = False

    def __init__(self, hub):
        super().__init__(hub)
        self.query = QtWidgets.QLineEdit()
        self.query.setPlaceholderText("Buscar ou perguntar: \"o que está atrasado?\", \"ideias para o projeto Atlas\"…")
        self.kind = QtWidgets.QComboBox()
        self.kind.addItem("Todos", "")
        for key, label in KINDS.items():
            self.kind.addItem(label, key)
        self.done = QtWidgets.QCheckBox("incluir concluídos")
        self.done.setChecked(True)
        self.answer = _label("", "H2Answer")
        self.answer.hide()
        self._debounce = QtCore.QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(lambda: self.hub.reload(self.key))
        self.query.textChanged.connect(lambda *_: self._debounce.start())
        self.kind.currentIndexChanged.connect(lambda *_: self.hub.reload(self.key))
        self.done.toggled.connect(lambda *_: self.hub.reload(self.key))
        self.filters.addWidget(self.query, 1)
        self.filters.addWidget(self.kind)
        self.filters.addWidget(self.done)
        self.layout_.insertWidget(2, self.answer)

    def fetch(self):
        from ..secondbrain import queries
        service, text, kind, done = self.service, self.query.text().strip(), self.kind.currentData(), self.done.isChecked()

        def work():
            if not text:
                return {"rows": [], "answer": "", "text": ""}
            found = queries.classify(text)
            if found is not None and found[0] != "search":
                result = queries.answer(service, text)            # pergunta: resposta só com dados salvos
                records = [r for r in result.records if isinstance(r, dict) and r.get("id")] or []
                return {"rows": rows_of(service, records), "answer": result.text, "text": text}
            records = service.search(text, kinds=(kind,) if kind else None, include_done=done, limit=200)
            return {"rows": rows_of(service, records), "answer": "", "text": text}
        return work

    def apply(self, data) -> None:
        self.answer.setVisible(bool(data["answer"]))
        self.answer.setText(data["answer"])
        empty = "Digite para buscar." if not data["text"] else f"Não encontrei registros sobre “{data['text']}”."
        self.apply_rows(data["rows"], empty=empty)


class ReviewPage(Page):
    key, title = "review", "REVISÃO DO QUE FOI INFERIDO · LIXEIRA"

    def __init__(self, hub):
        super().__init__(hub)
        self.inferred = RecordModel(self)
        self.trash = RecordModel(self)
        self.inferred_view = _table(self.inferred)
        self.trash_view = _table(self.trash)
        self.layout_.addWidget(_label("Capturas automáticas ficam marcadas como INFERIDAS até você confirmar, corrigir "
                                      "ou descartar. Nada inferido vira compromisso confirmado sozinho.", "H2Dim"))
        row = QtWidgets.QHBoxLayout()
        for text, tip, fn, primary in (("CONFIRMAR", "Confirmar como está", self._confirm, True),
                                       ("CORRIGIR", "Editar antes de confirmar", self._edit, False),
                                       ("DESCARTAR", "Mandar para a lixeira", self._discard, False)):
            button = _button(text, tip, primary=primary)
            button.clicked.connect(fn)
            row.addWidget(button)
        row.addStretch(1)
        self.layout_.addLayout(row)
        self.layout_.addWidget(self.inferred_view, 1)
        self.layout_.addWidget(_label("LIXEIRA", "H2Title"))
        row2 = QtWidgets.QHBoxLayout()
        for text, tip, fn in (("RESTAURAR", "Voltar a ativo", self._restore),
                              ("EXCLUIR DEFINITIVAMENTE", "Sem recuperação — pede autorização", self._purge),
                              ("ESVAZIAR LIXEIRA", "Exclui tudo da lixeira — pede autorização", self._empty)):
            button = _button(text, tip)
            button.clicked.connect(fn)
            row2.addWidget(button)
        row2.addStretch(1)
        self.layout_.addLayout(row2)
        self.layout_.addWidget(self.trash_view, 1)
        self.layout_.addWidget(self.status)

    def fetch(self):
        service = self.service

        def work():
            return {"inferred": rows_of(service, service.review_queue()), "trash": rows_of(service, service.trash())}
        return work

    def apply(self, data) -> None:
        self.inferred.set_rows(data["inferred"])
        self.trash.set_rows(data["trash"])
        self.status.setText(f"{len(data['inferred'])} para revisar · {len(data['trash'])} na lixeira.")

    @staticmethod
    def _pick(view, model) -> dict | None:
        rows = view.selectionModel().selectedRows()
        return model.record(rows[0].row()) if rows else None

    def _confirm(self):
        record = self._pick(self.inferred_view, self.inferred)
        if record:
            self.run(f"Confirmar: {record['title']}", "secondbrain.update", {"ref": record["id"], "confirm": True})

    def _edit(self):
        record = self._pick(self.inferred_view, self.inferred)
        if record:
            dialog = RecordDialog(self, record=record)
            if dialog.exec() == QtWidgets.QDialog.Accepted:
                self.run(f"Corrigir: {record['title']}", "secondbrain.update", dialog.update_args())

    def _discard(self):
        record = self._pick(self.inferred_view, self.inferred)
        if record:
            self.run(f"Descartar: {record['title']}", "secondbrain.delete", {"ref": record["id"]})

    def _restore(self):
        record = self._pick(self.trash_view, self.trash)
        if record:
            self.run(f"Restaurar: {record['title']}", "secondbrain.restore", {"ref": record["id"]})

    def _purge(self):
        record = self._pick(self.trash_view, self.trash)
        if record:
            self.run(f"Excluir definitivamente: {record['title']}", "secondbrain.delete",
                     {"ref": record["id"], "permanent": True})

    def _empty(self):
        if self.trash.rows:
            self.run("Esvaziar a lixeira", "secondbrain.empty_trash", {})


class NotificationsPage(Page):
    key, title = "notifications", "CENTRAL DE NOTIFICAÇÕES"

    def __init__(self, hub):
        super().__init__(hub)
        self.list = QtWidgets.QListWidget()
        self._latest: dict | None = None
        self.layout_.addWidget(self.list, 1)
        row = QtWidgets.QHBoxLayout()
        for text, fn in (("ADIAR 10 MIN", lambda: self._snooze(10)), ("ADIAR 1 H", lambda: self._snooze(60)),
                         ("CIENTE", self._dismiss), ("CONCLUIR ITEM", self._complete),
                         ("MARCAR TODAS COMO VISTAS", self._seen)):
            button = _button(text)
            button.clicked.connect(fn)
            row.addWidget(button)
        row.addStretch(1)
        self.layout_.addLayout(row)
        settings = QtWidgets.QFrame()
        settings.setObjectName("H2Card")
        form = QtWidgets.QFormLayout(settings)
        s = hub.core.settings()
        self.muted = QtWidgets.QCheckBox("Silenciar notificações (continuam registradas aqui)")
        self.muted.setChecked(bool(getattr(s, "notifications_muted", False)))
        self.muted.toggled.connect(lambda on: self._set(notifications_muted=on))
        self.enabled = QtWidgets.QCheckBox("Lembretes ativos")
        self.enabled.setChecked(bool(getattr(s, "reminders", True)))
        self.enabled.toggled.connect(lambda on: self._set(reminders=on))
        self.overdue = QtWidgets.QCheckBox("Aviso diário de atrasados")
        self.overdue.setChecked(bool(getattr(s, "overdue_alerts", True)))
        self.overdue.toggled.connect(lambda on: self._set(overdue_alerts=on))
        self.auto = QtWidgets.QCheckBox("Captura automática (registros inferidos para revisão)")
        self.auto.setChecked(bool(getattr(s, "auto_capture", True)))
        self.auto.toggled.connect(lambda on: self._set(auto_capture=on))
        self.quiet = QtWidgets.QLineEdit(str(getattr(s, "quiet_hours", "") or ""))
        self.quiet.setPlaceholderText("22:00-07:00 (vazio = sem horário de silêncio)")
        self.quiet.editingFinished.connect(lambda: self._set(quiet_hours=self.quiet.text().strip()))
        self.leads = QtWidgets.QLineEdit(", ".join(str(x) for x in getattr(s, "reminder_default_leads", ("10",))))
        self.leads.setPlaceholderText("minutos: 10, 60, 1440")
        self.leads.editingFinished.connect(
            lambda: self._set(reminder_default_leads=tuple(x.strip() for x in self.leads.text().split(",") if x.strip())))
        for widget in (self.muted, self.enabled, self.overdue, self.auto):
            form.addRow("", widget)
        form.addRow("Horário de silêncio", self.quiet)
        form.addRow("Avisos antecipados (compromissos)", self.leads)
        self.layout_.addWidget(settings)
        self.layout_.addWidget(self.status)

    def _set(self, **values) -> None:
        try:
            self.hub.core.settings_manager.update(**values)
            self.status.setText("Configuração salva.")
        except Exception as exc:
            self.status.setText(f"Configuração recusada: {exc}")

    def fetch(self):
        service = self.service

        def work():
            reminders = service.reminders
            return {"items": service.notifications(limit=150),
                    "latest": reminders.latest_fired().to_dict() if reminders is not None and reminders.latest_fired()
                    else None}
        return work

    def apply(self, data) -> None:
        self.list.clear()
        self._latest = data.get("latest")
        for n in data["items"]:
            when = time.strftime("%d/%m %H:%M", time.localtime(n["at"]))
            flags = (" · silenciado" if n.get("silent") else "") + ("" if n.get("state") != "new" else " · novo")
            item = QtWidgets.QListWidgetItem(f"{when}  {n['title']}" + (f" — {n['body']}" if n.get("body") else "") + flags)
            item.setData(QtCore.Qt.UserRole, n)
            if n.get("state") == "new":
                item.setForeground(theme.ALERT if n.get("kind") in ("missed", "overdue") else theme.TEXT_BRIGHT)
            else:
                item.setForeground(theme.TEXT_DIM)
            self.list.addItem(item)
        if not data["items"]:
            self.list.addItem("Nenhuma notificação.")
        self.status.setText("Lembretes disparam mesmo com o HUB minimizado; aqui fica o histórico completo.")

    def _target(self) -> dict:
        item = self.list.currentItem()
        n = item.data(QtCore.Qt.UserRole) if item is not None else None
        return n if isinstance(n, dict) else {}

    def _snooze(self, minutes: int) -> None:
        n = self._target()
        args = {"minutes": minutes}
        if n.get("record_id"):
            args["ref"] = n["record_id"]
        self.run(f"Adiar {minutes} min", "secondbrain.snooze", args)

    def _dismiss(self) -> None:
        reminder = self._target().get("reminder_id") or (self._latest or {}).get("id")
        if reminder:
            self.run("Ciente", "secondbrain.dismiss", {"reminder": reminder})
        else:
            self.status.setText("Selecione um lembrete.")

    def _complete(self) -> None:
        record = self._target().get("record_id")
        if record:
            self.run("Concluir", "secondbrain.complete", {"ref": record})
        else:
            self.status.setText("Selecione uma notificação de um registro.")

    def _seen(self) -> None:
        service = self.service
        self.hub.reader.request("notifications:seen", lambda: service.mark_notifications(state="seen"))
        self.hub.reload(self.key)


class NetworkPage(Page):
    key, title = "network", "DISPOSITIVOS DA REDE LOCAL"

    def __init__(self, hub):
        super().__init__(hub)
        self.summary = _label("", "H2Dim")
        self.layout_.addWidget(self.summary)
        filters = QtWidgets.QHBoxLayout()
        self.scope = QtWidgets.QComboBox()
        for key, label in (("all", "Todos"), ("online", "Presentes"), ("unknown", "Desconhecidos"),
                           ("absent", "Ausentes"), ("untrusted", "Não marcados como conhecidos")):
            self.scope.addItem(label, key)
        self.scope.currentIndexChanged.connect(lambda *_: self.hub.reload(self.key))
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Filtrar por nome, IP, MAC, fabricante, notas…")
        filters.addWidget(self.scope)
        filters.addWidget(self.search, 1)
        self.layout_.addLayout(filters)
        self.model = DeviceModel(self)
        self.proxy = _DeviceProxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.proxy.setFilterKeyColumn(-1)
        self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.table = _table(self.proxy, stretch=0)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, QtCore.Qt.AscendingOrder)
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._selected())
        form_box = QtWidgets.QFrame()
        form_box.setObjectName("H2Card")
        form = QtWidgets.QFormLayout(form_box)
        self.detail = _label("Selecione um dispositivo.", "H2Dim")
        self.alias = QtWidgets.QLineEdit()
        self.alias.setMaxLength(60)
        self.notes = QtWidgets.QPlainTextEdit()
        self.notes.setFixedHeight(90)
        self.trusted = QtWidgets.QCheckBox("Conhecido / confiável")
        save = _button("SALVAR", primary=True)
        save.clicked.connect(self._save)
        check = _button("VERIFICAR CONEXÃO", "Ping e tabela de vizinhos deste aparelho")
        check.clicked.connect(self._check)
        form.addRow(self.detail)
        form.addRow("Apelido", self.alias)
        form.addRow("Notas", self.notes)
        form.addRow("", self.trusted)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addWidget(save)
        buttons.addWidget(check)
        form.addRow(buttons)
        split = QtWidgets.QSplitter()
        split.addWidget(self.table)
        split.addWidget(form_box)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        self.layout_.addWidget(split, 1)
        self.layout_.addWidget(_label("A presença de um aparelho na rede não identifica a pessoa que o usa. O inventário "
                                      "pode estar incompleto: aparelhos que bloqueiam ping e estão ociosos podem não "
                                      "aparecer.", "H2Dim"))
        self.layout_.addWidget(self.status)
        scan = _button("VARRER AGORA", "Varredura da sub-rede privada deste computador")
        scan.clicked.connect(lambda: self.run("Varredura da rede", "network.scan"))
        export = _button("EXPORTAR")
        menu = QtWidgets.QMenu(export)
        for fmt, label in (("md", "Relatório (Markdown)"), ("csv", "Planilha (CSV)"), ("json", "Dados (JSON)")):
            menu.addAction(label, lambda f=fmt: self.run(f"Exportar ({f})", "network.export", {"format": f}))
        export.setMenu(menu)
        router = _button("ABRIR ROTEADOR", "Página oficial de administração do gateway (pede autorização)")
        router.clicked.connect(lambda: self.run("Abrir roteador", "network.open_admin"))
        for button in (scan, export, router):
            self.toolbar.addWidget(button)

    def fetch(self):
        net, scope = self.hub.core.network, self.scope.currentData()

        def work():
            inventory = net.inventory
            if scope == "untrusted":
                devices = inventory.devices(trusted=False)
            else:
                devices = inventory.devices(status=None if scope == "all" else scope)
            return {"devices": [d.to_dict() for d in devices], "counts": inventory.counts(),
                    "last_scan": dict(net.last_scan), "last_passive": net.last_passive}
        return work

    def apply(self, data) -> None:
        selected = (self._current() or {}).get("key")
        self.model.set_devices(data["devices"])
        counts, scan = data["counts"], data["last_scan"]
        when = time.strftime("%d/%m %H:%M", time.localtime(scan["timestamp"])) if scan.get("timestamp") else "nenhuma nesta sessão"
        enabled = bool(getattr(self.hub.core.settings(), "network_discovery", True))
        state = "INDISPONÍVEL — " + scan["error"] if scan.get("error") else ("ativa" if enabled else "DESLIGADA nas configurações")
        self.summary.setText(f"{counts['online']} presente(s) · {counts['unknown']} desconhecido(s) · {counts['absent']} "
                             f"ausente(s) · {counts['trusted']} conhecido(s) · última varredura: {when} · descoberta: {state}"
                             + (f" · rede {scan.get('network')}" if scan.get("network") else ""))
        limits = scan.get("limitations") or []
        self.status.setText(("Limitações: " + "; ".join(limits) + ".") if limits else
                            "Fontes: tabela de vizinhos, ping de um pacote e DNS reverso — apenas na sub-rede autorizada.")
        if selected:
            for row in range(self.proxy.rowCount()):
                if (self.proxy.index(row, 0).data(QtCore.Qt.UserRole) or {}).get("key") == selected:
                    self.table.selectRow(row)
                    break

    def _current(self) -> dict | None:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].data(QtCore.Qt.UserRole) if rows else None

    def _selected(self) -> None:
        d = self._current()
        if not d:
            return
        check = d.get("last_check") or {}
        lines = [f"{d['name']} — {d['ip']}" + (f" · {d['mac']}" if d.get("mac") else " · MAC desconhecido"),
                 f"{d.get('kind_label', '')} · {d.get('state_label', '')} · confiança {float(d.get('confidence') or 0):.0%}",
                 "Métodos: " + (", ".join(d.get("method_labels") or []) or "—"),
                 "Fabricante: " + (d.get("vendor") or "desconhecido") + (f" (via {d['vendor_source']})" if d.get("vendor_source") else ""),
                 "Nome na rede: " + (d.get("hostname") or "desconhecido")]
        if d.get("ipv6"):
            lines.append("IPv6: " + ", ".join(d["ipv6"]))
        if check:
            lines.append(f"Última verificação: {check.get('verdict', '')}")
        self.detail.setText("\n".join(lines))
        self.alias.setText(d.get("alias", ""))
        self.notes.setPlainText(d.get("notes", ""))
        self.trusted.setChecked(bool(d.get("trusted")))

    def _save(self) -> None:
        d = self._current()
        if not d:
            self.status.setText("Selecione um dispositivo.")
            return
        self.run(f"Atualizar {d['name']}", "network.device_update",
                 {"ref": d["key"], "alias": self.alias.text().strip(), "notes": self.notes.toPlainText().strip(),
                  "trusted": self.trusted.isChecked()})

    def _check(self) -> None:
        d = self._current()
        if d:
            self.run(f"Verificar {d['name']}", "network.check_device", {"ref": d["key"]})


class SystemPage(Page):
    key, title = "system", "SAÚDE DO SISTEMA E DESEMPENHO"

    def __init__(self, hub):
        super().__init__(hub)
        top = QtWidgets.QHBoxLayout()
        self.profile = QtWidgets.QComboBox()
        for name, label in (("performance", "Performance — fluidez máxima"), ("balanced", "Balanced — equilíbrio"),
                            ("cinematic", "Cinematic — efeitos completos")):
            self.profile.addItem(label, name)
        self.profile.setCurrentIndex(max(0, self.profile.findData(hub.profile.name)))
        self.profile.currentIndexChanged.connect(
            lambda *_: self.hub.core.settings_manager.update(performance_profile=self.profile.currentData()))
        top.addWidget(_label("Perfil de desempenho:", "H2Dim"))
        top.addWidget(self.profile)
        s = hub.core.settings()
        self.discovery = QtWidgets.QCheckBox("Descoberta de rede")
        self.discovery.setChecked(bool(getattr(s, "network_discovery", True)))
        self.discovery.toggled.connect(lambda on: self.hub.core.settings_manager.update(network_discovery=on))
        self.ssdp = QtWidgets.QCheckBox("Anúncios SSDP/UPnP")
        self.ssdp.setChecked(bool(getattr(s, "network_ssdp", False)))
        self.ssdp.toggled.connect(lambda on: self.hub.core.settings_manager.update(network_ssdp=on))
        top.addWidget(self.discovery)
        top.addWidget(self.ssdp)
        top.addStretch(1)
        self.layout_.addLayout(top)
        self.health = QtWidgets.QTreeWidget()
        self.health.setHeaderLabels(["COMPONENTE", "ESTADO", "DETALHE"])
        self.health.setColumnWidth(0, 170)
        self.health.setColumnWidth(1, 110)
        self.metrics = QtWidgets.QTreeWidget()
        self.metrics.setHeaderLabels(["MÉTRICA", "VALOR"])
        self.metrics.setColumnWidth(0, 300)
        split = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        split.addWidget(self.health)
        split.addWidget(self.metrics)
        self.layout_.addWidget(split, 1)
        self.layout_.addWidget(self.status)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(lambda: self.hub.reload(self.key))

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._timer.start()                      # métricas em memória, só enquanto a página está visível
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._timer.stop()
        super().hideEvent(event)

    def fetch(self):
        core = self.hub.core

        def work():
            return {"health": dict((core.health.last or {}).get("checks") or {}),
                    "metrics": core.metrics.snapshot() if getattr(core, "metrics", None) else {},
                    "hub_loads": self.hub.reader.loads}
        return work

    def apply(self, data) -> None:
        self.health.clear()
        for name, check in sorted(data["health"].items()):
            item = QtWidgets.QTreeWidgetItem([name, check.get("status", ""), check.get("detail", "")])
            if check.get("status") in ("FAIL", "WARN"):
                item.setForeground(1, theme.ALERT)
            self.health.addTopLevelItem(item)
        if not data["health"]:
            self.health.addTopLevelItem(QtWidgets.QTreeWidgetItem(["—", "", "verificação de saúde ainda não concluída"]))
        m = data["metrics"]
        series = m.get("series") or {}
        gauges = m.get("gauges") or {}
        process = m.get("process") or {}

        def ms(name, key="p95"):
            s = series.get(name) or {}
            return f"{s[key] * 1000:.1f} ms" if s.get("n") and key in s else "sem amostras"

        rows = [("Interface: quadros/s (alvo)", f"{gauges.get('ui.fps', '—')} ({gauges.get('ui.target_fps', '—')})"),
                ("Interface: tempo de quadro p50 / p95", f"{ms('ui.frame', 'p50')} / {ms('ui.frame')}"),
                ("Interface: atraso do laço p95", ms("ui.lag")),
                ("Interface: atraso de eventos p95", ms("ui.event_delay")),
                ("Pedido completo p50 / p95", f"{ms('request', 'p50')} / {ms('request')}"),
                ("Modelo: inferência p50", ms("model.inference", "p50")),
                ("Modelo: carregamento p50", ms("model.load", "p50")),
                ("Modelo: requisição total p95", ms("model.request")),
                ("CPU do processo", f"{process.get('cpu', '—')} %"), ("Memória (RSS)", f"{process.get('rss_mb', '—')} MB"),
                ("Threads", str(process.get("threads", "—"))),
                ("Tarefas na fila", str(m.get("queued", "—"))),
                ("Workers vivos", str(m.get("workers_alive", "—"))),
                ("Exceções registradas", str(m.get("exceptions", "—"))),
                ("Eventos visuais descartados", str(gauges.get("ui.events_dropped", 0))),
                ("Fila do barramento", str((m.get("bus") or {}).get("queued", "—"))),
                ("Leituras do HUB 2", str(data["hub_loads"]))]
        for name in sorted(k for k in series if k.startswith("perception.")):
            rows.append((f"Percepção {name.split('.', 1)[1]} p95", ms(name)))
        self.metrics.clear()
        for label, value in rows:
            self.metrics.addTopLevelItem(QtWidgets.QTreeWidgetItem([label, value]))
        self.status.setText("Medidas reais deste processo (janela recente). Nada estimado.")

    def on_profile(self, name: str) -> None:
        index = self.profile.findData(name)
        if index >= 0 and index != self.profile.currentIndex():
            self.profile.blockSignals(True)
            self.profile.setCurrentIndex(index)
            self.profile.blockSignals(False)


# ====================================================================== janela
class SecondBrainWindow(QtWidgets.QWidget):
    authorization_decided = QtCore.Signal(bool)
    _action_done = QtCore.Signal(str, object)

    PAGES = (TodayPage, TimelinePage, TasksPage, ProjectsPage, IdeasPage, SearchPage, NotificationsPage,
             NetworkPage, SystemPage, ReviewPage)

    def __init__(self, core, *, state: dict | None = None, profile=None):
        super().__init__()
        self.core = core
        self.state = state if state is not None else core.state.as_dict()
        self.profile = profile
        self.setObjectName("Hub2")
        self.setWindowTitle("JARVIS — Second Brain")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE)
        self.resize(1280, 800)
        self.setMinimumSize(900, 560)
        self.reader = _Reader(self)
        self.reader.loaded.connect(self._loaded)
        self._action_done.connect(self._finished, QtCore.Qt.QueuedConnection)
        self.dirty: set[str] = {key for key, _ in SECTIONS}
        self.loaded_once: set[str] = set()
        self._closed = False
        self.header = Header(self)
        self.nav = QtWidgets.QListWidget()
        self.nav.setObjectName("H2Nav")
        self.nav.setFixedWidth(200)
        self.stack = QtWidgets.QStackedWidget()
        self.pages: dict[str, Page] = {}
        for cls, (key, label) in zip(self.PAGES, SECTIONS):
            self.nav.addItem(label)
            page = cls(self)
            self.pages[key] = page
            self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self._nav_changed)
        self.capture = QtWidgets.QLineEdit()
        self.capture.setObjectName("HudLine")
        self.capture.setPlaceholderText("Anotar ou perguntar: \"reunião com a equipe quarta às 14h\", "
                                        "\"ideia: …\", \"o que está atrasado?\"")
        self.capture.returnPressed.connect(self._capture)
        self.capture_kind = QtWidgets.QComboBox()
        self.capture_kind.addItem("Automático", "")
        for key, label in KINDS.items():
            self.capture_kind.addItem(label, key)
        send = _button("REGISTRAR", primary=True)
        send.clicked.connect(self._capture)
        self.feedback = _label("", "H2Dim")
        self.authorization = DecisionBar("AUTORIZAR", "NEGAR", self)
        self.authorization.decided.connect(self.authorization_decided)
        bottom = QtWidgets.QHBoxLayout()
        bottom.setContentsMargins(22, 6, 22, 4)
        bottom.addWidget(self.capture, 1)
        bottom.addWidget(self.capture_kind)
        bottom.addWidget(send)
        body = QtWidgets.QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 8)
        root.setSpacing(0)
        root.addWidget(self.header)
        root.addLayout(body, 1)
        root.addWidget(self.authorization)
        root.addLayout(bottom)
        root.addWidget(self.feedback)
        self.feedback.setContentsMargins(24, 0, 24, 0)
        self._reload_timer = QtCore.QTimer(self)
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(RELOAD_DEBOUNCE_MS)
        self._reload_timer.timeout.connect(self._reload_visible)
        self._pulse_timer = QtCore.QTimer(self)
        self._pulse_timer.setInterval(60)
        self._pulse_timer.timeout.connect(self._pulse_step)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+N"), self, activated=self.focus_capture)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+F"), self, activated=lambda: self.show_section("search"))
        self.header.set_state(self.state)
        self._present_authorization(self.state.get("pending_authorization"))
        self.nav.setCurrentRow(0)

    # ------------------------------------------------------------ navegação e carregamento sob demanda
    def show_section(self, section: str | None) -> None:
        keys = [key for key, _ in SECTIONS]
        if section and section in keys:
            self.nav.setCurrentRow(keys.index(section))
        if section == "search":
            self.pages["search"].query.setFocus()

    def current_key(self) -> str:
        index = self.stack.currentIndex()
        return SECTIONS[index][0] if 0 <= index < len(SECTIONS) else ""

    def _nav_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)
        key = SECTIONS[row][0]
        if key in self.dirty or key not in self.loaded_once:
            self.reload(key)

    def reload(self, key: str, **_ignored) -> None:
        page = self.pages.get(key)
        if page is None or self._closed:
            return
        self.dirty.discard(key)
        try:
            work = page.fetch()
        except Exception as exc:
            page.failed(exc)
            return
        self.reader.request(key, work)

    def _reload_visible(self) -> None:
        key = self.current_key()
        if key in self.dirty and self.isVisible():
            self.reload(key)

    @QtCore.Slot(str, int, object)
    def _loaded(self, key: str, generation: int, data: Any) -> None:
        if self._closed or not self.reader.current(key, generation):
            return
        if key.startswith("detail:"):
            page = self.pages.get(key.split(":", 1)[1])
            if page is not None and isinstance(data, dict) and hasattr(page, "show_detail"):
                page.show_detail(data)
            return
        page = self.pages.get(key)
        if page is None:
            return
        if isinstance(data, Exception):
            page.failed(data)
            return
        self.loaded_once.add(key)
        try:
            page.apply(data)
        except Exception:
            log.exception("HUB 2: falha ao exibir %s", key)

    # ------------------------------------------------------------ estado e eventos compartilhados
    def on_state(self, state: dict, names) -> None:
        self.state = state
        names = set(names or ())
        if names & {"activity", "runtime_state", "runtime_reason", "second_brain", "network_state"}:
            self.header.set_state(state)
        if "pending_authorization" in names:
            self._present_authorization(state.get("pending_authorization"))

    def on_event(self, kind: str, payload: dict) -> None:
        sections = EVENT_SECTIONS.get(kind)
        if sections:
            self.dirty |= sections
            if self.current_key() in sections and self.isVisible():
                self._reload_timer.start()          # debounce: rajadas de eventos → uma leitura
        if kind == "REMINDER_DUE" and not payload.get("silent"):
            self.feedback.setText(f"Lembrete: {payload.get('title', '')} — {payload.get('when_text', '')}")
            if self.profile is None or getattr(self.profile, "name", "") != "performance":
                self.header.pulse = 1.0
                self._pulse_timer.start()
            else:
                self.header.update()

    def on_profile(self, profile) -> None:
        self.profile = profile
        self.pages["system"].on_profile(getattr(profile, "name", ""))

    def _pulse_step(self) -> None:
        self.header.pulse = max(0.0, self.header.pulse - 0.04)
        self.header.update()
        if self.header.pulse <= 0:
            self._pulse_timer.stop()

    def _present_authorization(self, pending: dict | None) -> None:
        if pending and pending.get("status") == "pending":
            scope = f" [{pending['category_label']}]" if pending.get("category_label") else ""
            self.authorization.present(f"Autorização específica{scope}: {pending.get('description', '')}")
        else:
            self.authorization.present(None)

    # ------------------------------------------------------------ ações (sempre pelo Neural Core)
    def run_action(self, label: str, skill: str, args: dict) -> None:
        self.feedback.setText(f"{label}…")

        def work():
            try:
                outcome = self.core.run_skill(skill, args, origin="user")
            except Exception as exc:
                outcome = {"success": False, "verified": False, "status": "failed", "error": str(exc), "text": "",
                           "data": {}}
            if not self._closed:
                self._action_done.emit(label, outcome)

        self.core.runtime.submit("actions", work, name=f"hub2:{skill}")

    @QtCore.Slot(str, object)
    def _finished(self, label: str, outcome: dict) -> None:
        if self._closed:
            return
        if outcome.get("success") and (outcome.get("data") or {}).get("clarify"):
            text = f"Esclarecimento necessário — {outcome.get('text', '')}"
        elif outcome.get("success") and outcome.get("verified"):
            text = outcome.get("text") or f"{label}: concluído."
        elif outcome.get("success"):
            text = f"{outcome.get('text') or label} (sem confirmação independente)"
        elif outcome.get("status") in ("denied", "cancelled"):
            text = f"{label}: não autorizado. Nada foi alterado."
        else:
            text = f"{label}: FALHOU — {outcome.get('error') or outcome.get('status')}"
        self.feedback.setText(text)
        if outcome.get("success"):
            current = self.current_key()
            if current in ("network", "system", "notifications"):
                self.dirty.add(current)
                self._reload_timer.start()

    def focus_capture(self) -> None:
        self.capture.setFocus()

    def _capture(self) -> None:
        text = " ".join(self.capture.text().split())
        if not text:
            return
        self.capture.clear()
        kind = self.capture_kind.currentData()
        from ..secondbrain import queries
        if not kind and (text.endswith("?") or queries.classify(text) is not None and
                         queries.classify(text)[0] != "search"):
            self.pages["search"].query.setText(text)
            self.show_section("search")
            return
        args = {"text": text}
        if kind:
            args["kind"] = kind
        self.run_action(f"Registrar: {text[:40]}", "secondbrain.capture", args)

    # ------------------------------------------------------------ ciclo de vida
    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        key = self.current_key()
        if key in self.dirty or key not in self.loaded_once:
            self.reload(key)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt)
        event.ignore()                           # fechar só esconde; "Sair" no menu encerra
        self.hide()

    def shutdown(self) -> None:
        self._closed = True
        for timer in (self._reload_timer, self._pulse_timer, self.pages["system"]._timer):
            timer.stop()
        self.reader.shutdown()
        self.hide()
