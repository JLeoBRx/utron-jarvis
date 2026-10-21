"""Página TARDIS da plataforma: a SALA DE CONTROLE (console 3D + painéis) e o ARQUIVO (memória espacial).

Acesso direto à TARDIS, sem passar pelo JARVIS: cada painel do console tem os seus comandos —

* ANÁLISE: consulta contextual (com fontes) e a memória de projeto (gravar e ler notas e decisões);
* PLANEJAMENTO: decompor um objetivo em etapas (exige o modelo; sem ele, falha com o motivo);
* ARQUIVO: organização da memória pessoal e a entrada da memória espacial;
* ROTINAS: lembretes futuros, recorrências e automações;
* TELEMETRIA: as voltas gravadas do Noctário (sem voltas, a análise diz que não há dado);
* DIAGNÓSTICO: verificação dos módulos e o estado de cada um agora (coordenação).

O resultado mostra o resumo, os itens com a fonte de cada um, o modelo usado e as ações PROPOSTAS. Uma
ação só roda pelo botão APLICAR, pelo caminho central do JARVIS (permissões, confirmação, verificação).
Tudo o que aparece aqui vem do motor da TARDIS — sem conexão com ele, a página diz isso.
"""
from __future__ import annotations

import html
import logging
import threading
import time

from PySide6 import QtCore, QtGui, QtWidgets

from ...tardis.protocol import KINDS, PANEL_LABELS, PANELS, STATE_LABELS
from .. import theme
from .scene import AMBER, ICE, RED, TEAL, RoomScene
from .view import RoomView

log = logging.getLogger("ultron.hud.tardis")

ACCENT = "#FFB347"
ROOM_MAX_FPS = 24
PAINT_BUDGET = 0.25
ROOM_STYLESHEET = theme.PANEL_STYLESHEET + """
QFrame#RoomSide { background: #071426; border-left: 1px solid rgba(255, 179, 71, 70); }
QLabel#RoomTitle { color: #FFB347; font-size: 11pt; letter-spacing: 3px; }
QLabel#RoomDim { color: #7F9BB7; font-size: 9pt; }
QLabel#RoomNote { color: #9FB9D3; font-size: 8pt; }
QLabel#RoomStatus { color: #DCEEFF; font-size: 9pt; }
QPushButton#RoomTab { background: #050E1C; color: #C9A46B; border: 1px solid rgba(255, 179, 71, 50);
    border-radius: 3px; padding: 6px 4px; font-size: 8pt; letter-spacing: 1px; }
QPushButton#RoomTab:hover { color: #FFE2B8; border-color: rgba(255, 179, 71, 140); }
QPushButton#RoomTab:checked { background: rgba(255, 179, 71, 40); color: #FFF4E2; border-color: #FFB347; }
QPushButton#RoomPrimary { background: rgba(255, 179, 71, 46); color: #FFF4E2; border: 1px solid rgba(255, 179, 71, 200);
    border-radius: 4px; padding: 6px 12px; font-size: 9pt; letter-spacing: 2px; }
QPushButton#RoomPrimary:hover { background: rgba(255, 179, 71, 82); }
QPushButton#RoomPrimary:disabled { color: #6B5A43; background: rgba(120, 80, 20, 30); border-color: rgba(120, 80, 20, 90); }
QPushButton#RoomButton { background: #050E1C; color: #FFD9A0; border: 1px solid rgba(255, 179, 71, 80);
    border-radius: 4px; padding: 6px 10px; font-size: 8pt; letter-spacing: 1px; }
QPushButton#RoomButton:hover { border-color: rgba(255, 179, 71, 190); color: #FFF4E2; }
QPushButton#RoomButton:disabled { color: #5B4B36; border-color: rgba(120, 80, 20, 80); }
QTextBrowser#RoomResult { background: #050E1C; border: 1px solid rgba(255, 179, 71, 40); }
QListWidget#RoomTasks { background: #050E1C; border: 1px solid rgba(255, 179, 71, 30); font-size: 9pt; }
QListWidget#RoomTasks::item:selected { background: rgba(255, 179, 71, 45); color: #FFF4E2; }
"""
PANEL_HELP = {
    "analise": "Consulta contextual: a TARDIS junta o que existe na memória pessoal, nos fatos, nas notas de "
               "projeto e no histórico — com a fonte de cada item. Nada encontrado = nenhuma resposta inventada.",
    "planejamento": "Decompõe um objetivo em etapas verificáveis e aponta riscos. Usa o mesmo modelo do JARVIS; "
                    "sem modelo disponível, a tarefa falha com o motivo. Nenhuma etapa é executada.",
    "arquivo": "Organização da memória pessoal: atrasados, conflitos, duplicados, tarefas sem data e registros "
               "aguardando revisão. A memória espacial abre aqui.",
    "rotinas": "Lembretes futuros, registros recorrentes e automações configuradas.",
    "telemetria": "Análise das voltas gravadas do Noctário: tempo, erro, oscilação, saturação e perdas de linha. "
                  "Sem voltas gravadas (robô ou simulador rotulado), não há o que analisar.",
    "diagnostico": "Verificação de saúde, componentes, workers, voz e Noctário (diagnóstico) e a fotografia do "
                   "estado de cada módulo agora (coordenação).",
}
SEVERITY_COLORS = {"alta": "#FF5D73", "média": "#FFB347", "baixa": "#7F9BB7"}
STATE_COLORS = {"DONE": "#3DFFA8", "FAILED": "#FF5D73", "REJECTED": "#FF5D73", "CANCELLED": "#7F9BB7",
                "RUNNING": "#FFB347", "QUEUED": "#67F3FF"}
ORIGIN_LABELS = {"jarvis": "JARVIS", "usuario": "você", "tardis": "TARDIS", "agendador": "agendador"}


def _button(text: str, tip: str = "", *, primary: bool = False) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setObjectName("RoomPrimary" if primary else "RoomButton")
    button.setCursor(QtCore.Qt.PointingHandCursor)
    if tip:
        button.setToolTip(tip)
    return button


def _label(text: str = "", name: str = "RoomDim") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    return label


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _seconds(ms) -> str:
    if ms is None:
        return ""
    return f"{ms / 1000:.1f} s".replace(".", ",")


def task_html(task) -> str:
    """Resultado de uma tarefa em HTML — todo texto escapado (conteúdo do modelo e do usuário é dado)."""
    e = html.escape
    color = STATE_COLORS.get(task.state, "#DCEEFF")
    head = (f"<div style='color:{ACCENT};letter-spacing:2px'>{e(task.label.upper())}</div>"
            f"<div style='color:{color}'>{e(STATE_LABELS.get(task.state, task.state))}"
            + (f" · {_seconds(task.duration_ms)}" if task.duration_ms is not None else "")
            + f" · pedida por {e(ORIGIN_LABELS.get(task.origin, task.origin))}</div>")
    question = next((task.input.get(k) for k in ("question", "goal", "project", "search") if task.input.get(k)), "")
    if question:
        head += f"<div style='color:#9FB9D3'>entrada: {e(str(question))}</div>"
    head += f"<div style='color:#7F9BB7'>modelo: {e(task.model or ('—' if not task.final else 'sem modelo'))}</div>"
    parts = [head]
    if task.error:
        parts.append(f"<p style='color:#FF5D73'><b>{e(str(task.error.get('code', '')))}</b>: "
                     f"{e(str(task.error.get('message', '')))}</p>")
    result = task.result
    if result is not None:
        parts.append(f"<p style='color:#F0FAFF'>{e(result.summary)}</p>")
        if result.items:
            rows = []
            for item in result.items[:40]:
                severity = item.get("severity")
                dot = f"<span style='color:{SEVERITY_COLORS.get(severity, '#67F3FF')}'>●</span> "
                detail = f" — <span style='color:#9FB9D3'>{e(str(item.get('detail', '')))}</span>" \
                    if item.get("detail") else ""
                source = f" <span style='color:#5F7E9C'>[{e(str(item.get('source', '')))}]</span>" \
                    if item.get("source") else ""
                rows.append(f"<div>{dot}{e(str(item.get('title', '')))}{detail}{source}</div>")
            parts.append("".join(rows))
        if result.sources:
            parts.append(f"<p style='color:#7F9BB7'>fontes: {e(', '.join(str(s) for s in result.sources))}</p>")
    elif not task.final:
        parts.append("<p style='color:#FFB347'>em andamento…</p>")
    if task.log:
        log_lines = "<br>".join(e(line) for line in task.log[-8:])
        parts.append(f"<p style='color:#5F7E9C;font-size:8pt'>{log_lines}</p>")
    return "".join(parts)


class _Runner(QtCore.QObject):
    """Executa chamadas fora da thread da interface e devolve o resultado por sinal."""

    done = QtCore.Signal(str, object)

    def run(self, key: str, fn, *args, **kwargs) -> None:
        def work() -> None:
            try:
                value = fn(*args, **kwargs)
            except Exception as exc:                 # vira mensagem na tela, nunca derruba a interface
                value = exc
            self.done.emit(key, value)

        threading.Thread(target=work, name=f"ultron-tardis-ui-{key.split(':')[0]}", daemon=True).start()


class TardisRoomPage(QtWidgets.QWidget):
    """A sala de controle: console 3D à esquerda, painéis da TARDIS à direita."""

    archive_requested = QtCore.Signal()
    escape_unhandled = QtCore.Signal()

    def __init__(self, core, *, profile=None, effects=None, parent=None):
        super().__init__(parent)
        self.core = core
        self.engine = getattr(core, "tardis", None)
        self.profile = profile
        self._effects = effects or (lambda: True)
        self.setObjectName("Panel")
        self.setStyleSheet(ROOM_STYLESHEET)
        self.scene = RoomScene()
        self.view = RoomView(self.scene, self)
        self.view.panel_clicked.connect(self.select_panel)
        self.runner = _Runner(self)
        self.runner.done.connect(self._runner_done, QtCore.Qt.QueuedConnection)
        self.current_panel = "analise"
        self.shown_task = ""
        self._history: list = []
        self._history_loaded = False
        self._action_rows: list[tuple[QtWidgets.QPushButton, QtWidgets.QLabel]] = []
        self.target_fps = 0
        self._last_tick = time.perf_counter()
        self._paint_ema = 0.0
        self._painted = 0
        self._build()
        self._clock = QtCore.QTimer(self)
        self._clock.setTimerType(QtCore.Qt.PreciseTimer)
        self._clock.timeout.connect(self._tick)
        self._refresh = QtCore.QTimer(self)
        self._refresh.setSingleShot(True)
        self._refresh.setInterval(120)
        self._refresh.timeout.connect(self.refresh)
        QtGui.QShortcut(QtGui.QKeySequence("Esc"), self, activated=self._escape,
                        context=QtCore.Qt.WidgetWithChildrenShortcut)
        self.on_profile(profile)
        if self.engine is not None:
            self.scene.set_engine_state(self.engine.state())
        self.select_panel("analise", rotate=False)
        self.refresh()

    # ------------------------------------------------------------ montagem
    def _build(self) -> None:
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.view, 1)
        side = QtWidgets.QFrame()
        side.setObjectName("RoomSide")
        side.setMinimumWidth(380)
        side.setMaximumWidth(470)
        lay = QtWidgets.QVBoxLayout(side)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        tabs = QtWidgets.QGridLayout()
        tabs.setSpacing(4)
        self.tab_group = QtWidgets.QButtonGroup(self)
        self.tab_group.setExclusive(True)
        self.tabs: dict[str, QtWidgets.QPushButton] = {}
        for index, key in enumerate(PANELS):
            button = QtWidgets.QPushButton(PANEL_LABELS[key])
            button.setObjectName("RoomTab")
            button.setCheckable(True)
            button.setCursor(QtCore.Qt.PointingHandCursor)
            button.clicked.connect(lambda _=False, k=key: self.select_panel(k))
            self.tab_group.addButton(button)
            self.tabs[key] = button
            tabs.addWidget(button, index // 3, index % 3)
        lay.addLayout(tabs)
        self.panel_title = _label("", "RoomTitle")
        self.panel_help = _label("", "RoomDim")
        lay.addWidget(self.panel_title)
        lay.addWidget(self.panel_help)
        self.controls = QtWidgets.QStackedWidget()
        self.controls.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self._control_pages = {key: getattr(self, f"_controls_{key}")() for key in PANELS}
        for page in self._control_pages.values():
            self.controls.addWidget(page)
        lay.addWidget(self.controls)
        self.status = _label("", "RoomStatus")
        lay.addWidget(self.status)
        result_head = QtWidgets.QHBoxLayout()
        result_head.addWidget(_label("RESULTADO", "RoomTitle"), 1)
        self.cancel_button = _button("CANCELAR", "Cancelar esta análise (na fila ou em execução)")
        self.cancel_button.clicked.connect(self._cancel_shown)
        self.cancel_button.hide()
        result_head.addWidget(self.cancel_button)
        lay.addLayout(result_head)
        self.result = QtWidgets.QTextBrowser()
        self.result.setObjectName("RoomResult")
        self.result.setOpenLinks(False)
        self.result.setOpenExternalLinks(False)
        lay.addWidget(self.result, 3)
        self.actions_box = QtWidgets.QWidget()
        self.actions_layout = QtWidgets.QVBoxLayout(self.actions_box)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(4)
        lay.addWidget(self.actions_box)
        tasks_head = QtWidgets.QHBoxLayout()
        tasks_head.addWidget(_label("TAREFAS", "RoomTitle"), 1)
        self.tasks_note = _label("", "RoomNote")
        tasks_head.addWidget(self.tasks_note)
        lay.addLayout(tasks_head)
        self.tasks = QtWidgets.QListWidget()
        self.tasks.setObjectName("RoomTasks")
        self.tasks.currentItemChanged.connect(self._task_selected)
        lay.addWidget(self.tasks, 2)
        root.addWidget(side)
        if self.engine is None:
            for button in self.findChildren(QtWidgets.QPushButton):
                if button.objectName() in ("RoomPrimary", "RoomButton"):
                    button.setEnabled(False)
            self.status.setText("A TARDIS não está ativa nesta execução: nenhuma análise pode ser feita.")

    def _form(self) -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
        page = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        return page, lay

    def _controls_analise(self) -> QtWidgets.QWidget:
        page, lay = self._form()
        row = QtWidgets.QHBoxLayout()
        self.question = QtWidgets.QLineEdit()
        self.question.setPlaceholderText("Pergunta (ex.: o que decidi sobre o Kd do Noctário?)")
        self.question.setMaxLength(400)
        self.question.returnPressed.connect(self._consult)
        ask = _button("CONSULTAR", "Consulta contextual com fontes", primary=True)
        ask.clicked.connect(self._consult)
        row.addWidget(self.question, 1)
        row.addWidget(ask)
        lay.addLayout(row)
        lay.addWidget(_label("MEMÓRIA DE PROJETO — notas, decisões e parâmetros (nunca senhas)", "RoomNote"))
        row2 = QtWidgets.QHBoxLayout()
        self.note_project = QtWidgets.QLineEdit()
        self.note_project.setPlaceholderText("projeto")
        self.note_project.setMaxLength(80)
        self.note_project.setMaximumWidth(110)
        self.note_kind = QtWidgets.QComboBox()
        for key, label in (("nota", "nota"), ("decisao", "decisão"), ("parametro", "parâmetro")):
            self.note_kind.addItem(label, key)
        row2.addWidget(self.note_project)
        row2.addWidget(self.note_kind)
        lay.addLayout(row2)
        row3 = QtWidgets.QHBoxLayout()
        self.note_text = QtWidgets.QLineEdit()
        self.note_text.setPlaceholderText("texto da nota")
        self.note_text.setMaxLength(600)
        self.note_text.returnPressed.connect(self._save_note)
        save = _button("GRAVAR", "Grava pelo JARVIS (permissão: modificar arquivos e dados pessoais)")
        save.clicked.connect(self._save_note)
        read = _button("LER NOTAS", "Ler a memória de projeto (filtra pelo projeto, se informado)")
        read.clicked.connect(lambda: self.submit("projeto", {"project": self.note_project.text().strip()}))
        row3.addWidget(self.note_text, 1)
        row3.addWidget(save)
        row3.addWidget(read)
        lay.addLayout(row3)
        return page

    def _controls_planejamento(self) -> QtWidgets.QWidget:
        page, lay = self._form()
        row = QtWidgets.QHBoxLayout()
        self.goal = QtWidgets.QLineEdit()
        self.goal.setPlaceholderText("Objetivo (ex.: montar a pista de testes do Noctário)")
        self.goal.setMaxLength(400)
        self.goal.returnPressed.connect(self._plan)
        plan = _button("PLANEJAR", "Decompor em etapas (nada é executado)", primary=True)
        plan.clicked.connect(self._plan)
        row.addWidget(self.goal, 1)
        row.addWidget(plan)
        lay.addLayout(row)
        return page

    def _controls_arquivo(self) -> QtWidgets.QWidget:
        page, lay = self._form()
        row = QtWidgets.QHBoxLayout()
        organize = _button("ORGANIZAR", "Analisar a memória pessoal (só leitura; ações ficam propostas)",
                           primary=True)
        organize.clicked.connect(lambda: self.submit("organizacao", {}))
        archive = _button("ABRIR MEMÓRIA ESPACIAL", "O arquivo navegável da memória pessoal")
        archive.clicked.connect(self.archive_requested)
        row.addWidget(organize)
        row.addWidget(archive)
        row.addStretch(1)
        lay.addLayout(row)
        return page

    def _controls_rotinas(self) -> QtWidgets.QWidget:
        page, lay = self._form()
        check = _button("VERIFICAR ROTINAS", "Lembretes futuros, recorrências e automações", primary=True)
        check.clicked.connect(lambda: self.submit("rotinas", {}))
        lay.addWidget(check, 0, QtCore.Qt.AlignLeft)
        return page

    def _controls_telemetria(self) -> QtWidgets.QWidget:
        page, lay = self._form()
        analyze = _button("ANALISAR VOLTAS", "Métricas das voltas gravadas do Noctário", primary=True)
        analyze.clicked.connect(lambda: self.submit("telemetria", {}))
        lay.addWidget(analyze, 0, QtCore.Qt.AlignLeft)
        lay.addWidget(_label("Sugestões são hipóteses explicadas; nenhuma é aplicada sem o seu APLICAR e a "
                             "confirmação de comandos ao robô. Nenhuma promete tempo de volta.", "RoomNote"))
        return page

    def _controls_diagnostico(self) -> QtWidgets.QWidget:
        page, lay = self._form()
        row = QtWidgets.QHBoxLayout()
        diagnose = _button("DIAGNOSTICAR", "Saúde, componentes, workers, voz e Noctário", primary=True)
        diagnose.clicked.connect(lambda: self.submit("diagnostico", {}))
        coordinate = _button("ESTADO DOS MÓDULOS", "Fotografia do estado de cada módulo agora")
        coordinate.clicked.connect(lambda: self.submit("coordenacao", {}))
        row.addWidget(diagnose)
        row.addWidget(coordinate)
        row.addStretch(1)
        lay.addLayout(row)
        return page

    # ------------------------------------------------------------ painéis
    def select_panel(self, key: str, *, rotate: bool = True) -> None:
        if key not in PANELS:
            return
        self.current_panel = key
        self.tabs[key].setChecked(True)
        self.panel_title.setText(PANEL_LABELS[key])
        self.panel_help.setText(PANEL_HELP[key])
        for name, page in self._control_pages.items():      # só a página atual ocupa altura
            policy = QtWidgets.QSizePolicy.Preferred if name == key else QtWidgets.QSizePolicy.Ignored
            page.setSizePolicy(policy, policy)
        self.controls.setCurrentWidget(self._control_pages[key])
        self.controls.adjustSize()
        if rotate:
            self.scene.select(key)
            self._wake()
        latest = next((t for t in self._tasks() if KINDS[t.kind].panel == key), None)
        if latest is not None:
            self.show_task(latest.id)

    def show_section(self, section: str | None) -> None:
        if section in PANELS:
            self.select_panel(section)

    def _escape(self) -> None:
        if self.scene.selected:
            self.scene.select("")
            self._wake()
        else:
            self.escape_unhandled.emit()

    # ------------------------------------------------------------ comandos
    def submit(self, kind: str, data: dict) -> None:
        if self.engine is None:
            return
        clean = {k: v for k, v in data.items() if v}
        self.status.setText(f"Enviando à TARDIS: {KINDS[kind].label}…")
        self.runner.run("submit", self.engine.submit, kind, clean, origin="usuario")

    def _consult(self) -> None:
        question = " ".join(self.question.text().split())
        if not question:
            self.status.setText("Escreva a pergunta para a consulta.")
            return
        self.submit("consulta", {"question": question})

    def _plan(self) -> None:
        goal = " ".join(self.goal.text().split())
        if not goal:
            self.status.setText("Escreva o objetivo a planejar.")
            return
        self.submit("planejamento", {"goal": goal})

    def _save_note(self) -> None:
        text = " ".join(self.note_text.text().split())
        if not text:
            self.status.setText("Escreva o texto da nota.")
            return
        args = {"text": text, "kind": self.note_kind.currentData()}
        project = self.note_project.text().strip()
        if project:
            args["project"] = project
        self.status.setText("Gravando na memória de projeto pelo JARVIS…")
        self.runner.run("note", self.core.run_skill, "tardis.note", args, origin="user")

    def _apply(self, index: int, action: dict) -> None:
        button, label = self._action_rows[index]
        button.setEnabled(False)
        label.setText("executando pelo JARVIS (pode pedir confirmação)…")
        self.runner.run(f"apply:{index}:{self.shown_task}", self.core.run_skill, action["skill"],
                        dict(action.get("args") or {}), origin="user")

    def _cancel_shown(self) -> None:
        if self.engine is not None and self.shown_task:
            self.runner.run("cancel", self.engine.cancel, self.shown_task, "cancelada na sala de controle")

    @QtCore.Slot(str, object)
    def _runner_done(self, key: str, value) -> None:
        if key == "submit":
            if isinstance(value, Exception):
                self.status.setText(f"A TARDIS não aceitou o pedido: {value}")
                return
            if value.state == "REJECTED":
                self.status.setText(f"Recusada: {(value.error or {}).get('message', '')}")
            else:
                self.status.setText(f"{_cap(value.label)}: na fila.")
            self.show_task(value.id)
            self.refresh()
        elif key == "note":
            self.status.setText(self._outcome_text(value, "Nota gravada."))
            if isinstance(value, dict) and value.get("success"):
                self.note_text.clear()
        elif key.startswith("apply:"):
            _, index, task_id = key.split(":", 2)
            if task_id == self.shown_task and int(index) < len(self._action_rows):
                self._action_rows[int(index)][1].setText(self._outcome_text(value, "feito."))
        elif key == "cancel":
            self.status.setText("Cancelamento pedido." if value else "Nada a cancelar: a tarefa já terminou.")
        elif key == "history":
            self._history = [] if isinstance(value, Exception) else list(value or [])
            self._history_loaded = True
            self.refresh()

    @staticmethod
    def _outcome_text(value, ok: str) -> str:
        if isinstance(value, Exception):
            return f"falhou: {value}"
        if not isinstance(value, dict):
            return "sem resposta"
        if value.get("success") and value.get("verified"):
            return f"{value.get('text') or ok} (verificado)"
        if value.get("success"):
            return f"{value.get('text') or ok} (sem confirmação independente)"
        if value.get("status") == "denied":
            return "negado: nada foi feito."
        return f"não feito: {value.get('error') or value.get('status')}"

    # ------------------------------------------------------------ tarefas
    def _tasks(self) -> list:
        if self.engine is None:
            return []
        recent = self.engine.recent(40)
        seen = {t.id for t in recent}
        return recent + [t for t in self._history if t.id not in seen]

    def refresh(self) -> None:
        """Lista, tela do resultado e telas da sala — tudo do motor (memória), nada do banco aqui."""
        tasks = self._tasks()
        current = self.shown_task
        self.tasks.blockSignals(True)
        self.tasks.clear()
        for task in tasks[:80]:
            when = time.strftime("%H:%M:%S", time.localtime(task.created))
            text = f"{when}  {task.label}  ·  {STATE_LABELS.get(task.state, task.state)}" + \
                   (f"  ·  {_seconds(task.duration_ms)}" if task.duration_ms is not None else "")
            item = QtWidgets.QListWidgetItem(text)
            item.setData(QtCore.Qt.UserRole, task.id)
            item.setForeground(QtGui.QColor(STATE_COLORS.get(task.state, "#DCEEFF")))
            item.setToolTip(f"origem: {ORIGIN_LABELS.get(task.origin, task.origin)} · id {task.id}")
            self.tasks.addItem(item)
            if task.id == current:
                self.tasks.setCurrentItem(item)
        self.tasks.blockSignals(False)
        self.tasks_note.setText("desta sessão" + (" + anteriores" if self._history else ""))
        if current:
            self.show_task(current, rebuild_actions=False)
        self._update_screens()

    def _task_selected(self, item, _previous=None) -> None:
        if item is not None:
            self.show_task(str(item.data(QtCore.Qt.UserRole)))

    def show_task(self, task_id: str, *, rebuild_actions: bool = True) -> None:
        if self.engine is None:
            return
        task = self.engine.get(task_id) or next((t for t in self._history if t.id == task_id), None)
        if task is None:
            return
        changed = task_id != self.shown_task
        self.shown_task = task_id
        bar = self.result.verticalScrollBar()
        position = bar.value()
        self.result.setHtml(task_html(task))
        if not changed:
            bar.setValue(position)
        if task.final:
            duration = f" em {_seconds(task.duration_ms)}" if task.duration_ms is not None and task.state == "DONE" else ""
            self.status.setText(f"{_cap(task.label)}: {STATE_LABELS.get(task.state, task.state)}{duration}.")
        self.cancel_button.setVisible(not task.final)
        if rebuild_actions or changed or (task.final and not self._action_rows and task.result
                                          and task.result.actions):
            self._build_actions(task)

    def _build_actions(self, task) -> None:
        while self.actions_layout.count():
            item = self.actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._action_rows = []
        actions = task.result.actions if task.result is not None else []
        registry = getattr(self.core, "registry", None)
        for index, action in enumerate(actions[:6]):
            data = action.to_dict() if hasattr(action, "to_dict") else dict(action)
            row = QtWidgets.QWidget()
            lay = QtWidgets.QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            apply = _button("APLICAR", f"Executar pelo JARVIS: {data['skill']} (passa por permissões, confirmação "
                                       f"e verificação)", primary=True)
            available = registry is None or data["skill"] in registry
            apply.setEnabled(available)
            text = _label(f"{data['description']} — {data.get('reason', '')}" if data.get("reason")
                          else data["description"], "RoomStatus")
            text.setToolTip(f"skill: {data['skill']} · argumentos: {data.get('args')}")
            outcome = _label("" if available else "esta ação não está disponível nesta execução", "RoomNote")
            column = QtWidgets.QVBoxLayout()
            column.addWidget(text)
            column.addWidget(outcome)
            lay.addWidget(apply, 0, QtCore.Qt.AlignTop)
            lay.addLayout(column, 1)
            apply.clicked.connect(lambda _=False, i=index, a=data: self._apply(i, a))
            self.actions_layout.addWidget(row)
            self._action_rows.append((apply, outcome))
        if actions:
            self.actions_layout.addWidget(_label("Ações PROPOSTAS pela TARDIS: só rodam pelo APLICAR, com as "
                                                 "permissões e confirmações do JARVIS.", "RoomNote"))

    def _update_screens(self) -> None:
        if self.engine is None:
            self.scene.screens = {"center": ("TARDIS", ["indisponível nesta execução"], RED)}
            return
        snap = self.engine.snapshot()
        running = snap.get("running")
        self.scene.screens = {
            "left": ("FILA", [f"{snap.get('queued', 0)} na fila",
                              f"executando: {running['kind_label']}" if running else "nada em execução",
                              f"última hora: {snap.get('done_recent', 0)} concluída(s), "
                              f"{snap.get('failed_recent', 0)} falha(s)"],
                     TEAL if snap.get("mode") == "operacao" else AMBER),
        }
        last = next((t for t in self.engine.recent(10) if t.final), None)
        if last is not None:
            text = last.result.summary if last.result else (last.error or {}).get("message", "")
            self.scene.screens["right"] = (f"ÚLTIMA: {last.label.upper()}",
                                           [STATE_LABELS.get(last.state, last.state), text[:120]],
                                           RED if last.state == "FAILED" else ICE)

    # ------------------------------------------------------------ eventos e relógio
    def platform_event(self, kind: str, payload: dict, at: float | None = None) -> None:
        if kind == "TARDIS_STATE":
            self.scene.set_engine_state(payload)
            self._refresh.start()
            self._wake()
        elif kind.startswith("TARDIS_TASK_"):
            self.scene.task_event(kind, payload)
            self._refresh.start()
            self._wake()

    def on_profile(self, profile) -> None:
        self.profile = profile
        name = getattr(profile, "name", "balanced")
        self.view.set_profile(name, effects=self._effects())
        self._wake()

    def _fps(self) -> int:
        """Rotor e luzes são lentos: 24 quadros/s bastam com animação; em repouso, a cadência econômica do
        perfil. A pintura segura o GIL — nunca mais de 25% da thread da interface, para não atrasar a análise
        que a própria sala está mostrando."""
        profile = self.profile
        hud = int(getattr(self.core.settings(), "hud_fps", 60)) if hasattr(self.core, "settings") else 60
        active = min(ROOM_MAX_FPS, int(getattr(profile, "geometry_fps", 30)), hud)
        idle = min(active, int(getattr(profile, "idle_fps", 15)))
        fps = active if self.scene.in_motion() else idle
        if self._paint_ema > 0:
            fps = min(fps, max(min(idle, 8), int(PAINT_BUDGET / self._paint_ema)))
        return max(4, fps)

    def _wake(self) -> None:
        if self.isVisible() and not self._clock.isActive():
            self._last_tick = time.perf_counter()
            self._clock.start(16)

    def _tick(self) -> None:
        if not self.isVisible():
            self._clock.stop()
            return
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now
        self.scene.step(dt)
        if self.view.paint_count != self._painted and self.view.frame_times:
            self._painted = self.view.paint_count
            last = self.view.frame_times[-1]
            self._paint_ema = last if not self._paint_ema else self._paint_ema * 0.85 + last * 0.15
        fps = self._fps()
        self.target_fps = fps
        interval = max(7, int(1000 / fps))
        if self._clock.interval() != interval:
            self._clock.setInterval(interval)
        self.view.update()

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        if self.engine is not None:
            self.scene.set_engine_state(self.engine.state())
        if not self._history_loaded and self.engine is not None:
            self._history_loaded = True
            self.runner.run("history", self.engine.history, 60)
        self.refresh()
        self._wake()

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt)
        self._clock.stop()
        super().hideEvent(event)

    def shutdown(self) -> None:
        self._clock.stop()
        self._refresh.stop()


class TardisPage(QtWidgets.QWidget):
    """A página TARDIS: SALA DE CONTROLE e ARQUIVO (memória espacial), com o estado de cada um preservado.

    Esc: na sala, fecha o painel escolhido (sem painel, vai para a plataforma: parar fala, cancelar...); no
    ARQUIVO, fecha a região aberta. ``open_region`` existe para a plataforma deixar o Esc com esta página."""

    mode_changed = QtCore.Signal(str)
    escape_unhandled = QtCore.Signal()

    def __init__(self, core, *, archive_factory, profile=None, effects=None, parent=None):
        super().__init__(parent)
        self.core = core
        self._archive_factory = archive_factory
        self._archive = None
        self._archive_host = None
        self.stack = QtWidgets.QStackedLayout(self)
        self.room = TardisRoomPage(core, profile=profile, effects=effects)
        self.room.archive_requested.connect(lambda: self.show_archive())
        self.room.escape_unhandled.connect(self.escape_unhandled)
        self.stack.addWidget(self.room)
        self.mode = "sala"

    @property
    def archive(self):
        return self._archive

    @property
    def authorization(self):
        """A barra de autorização do ARQUIVO quando ele está à frente (senão, a da plataforma)."""
        if self.mode == "arquivo" and self._archive is not None:
            return getattr(self._archive, "authorization", None)
        return None

    def ensure_archive(self):
        if self._archive is None:
            self._archive = self._archive_factory()
            self._archive.setAttribute(QtCore.Qt.WA_StyledBackground, True)
            self.stack.addWidget(self._archive)
        return self._archive

    def show_archive(self, section: str | None = None):
        archive = self.ensure_archive()
        if self.stack.currentWidget() is not archive:
            self.stack.setCurrentWidget(archive)
        self.mode = "arquivo"
        if section:
            archive.show_section(section)
        self.mode_changed.emit(self.mode)
        return archive

    def show_room(self, panel: str | None = None):
        if self.stack.currentWidget() is not self.room:
            self.stack.setCurrentWidget(self.room)
        self.mode = "sala"
        if panel:
            self.room.select_panel(panel)
        self.mode_changed.emit(self.mode)
        return self.room

    def show_section(self, section: str | None) -> None:
        """Seções da sala (painéis) ou do ARQUIVO (regiões da memória espacial)."""
        if not section:
            return
        if section in ("sala", "room", "console"):
            self.show_room()
        elif section in PANELS and section != "arquivo":
            self.show_room(section)
        else:
            self.show_archive(None if section in ("arquivo", "memoria", "memoria_espacial") else section)

    def open_region(self, key: str) -> None:
        self.show_archive().open_region(key)

    def platform_event(self, kind: str, payload: dict, at: float | None = None) -> None:
        self.room.platform_event(kind, payload, at)

    def on_profile(self, profile) -> None:
        self.room.on_profile(profile)

    def shutdown(self) -> None:
        """Encerramento da plataforma: relógios da sala e a thread de leitura do ARQUIVO."""
        self.room.shutdown()
        if self._archive is not None:
            self._archive.shutdown()
