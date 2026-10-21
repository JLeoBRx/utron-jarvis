"""DIAGNÓSTICOS — o Painel de Sistemas dentro da plataforma, com o que faltava do JARVIS original.

Abas: VOZ · REDE LOCAL · AUTONOMIA · DESEMPENHO E SAÚDE (as do Painel de Sistemas) e as novas:

* **EVENTOS** — o CONSOLE DE EVENTOS do original: até 300 entradas "[HH:MM:SS] ▸ texto", filtro sem
  diferenciar maiúsculas, COPIAR (só as linhas visíveis), LIMPAR e PAUSAR. Mostra os eventos reais do
  barramento desde a abertura do JARVIS (mesmo antes de a página ser aberta);
* **LOG** — as últimas linhas do arquivo de log (lido fora da thread da interface), com filtro de nível;
* **SERVIÇOS E GPU** — componentes, workers, modelos, provedor externo, privacidade e a GPU (lista do
  sistema e, sob pedido, o renderizador OpenGL que o Qt consegue abrir).
"""
from __future__ import annotations

import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWidgets

from . import theme
from .panels import _button, _label
from .systems_panel import TABS as SYSTEM_TABS
from .systems_panel import SystemsPanel

TABS = SYSTEM_TABS + (("eventos", "EVENTOS"), ("log", "LOG"), ("servicos", "SERVIÇOS E GPU"))
CONSOLE_LIMIT = 300
SUMMARY_KEYS = ("text", "description", "notice", "title", "skill", "component", "status", "state", "error", "reason",
                "kind", "model", "provider", "fallback", "source", "view")
QUIET = {"ACTIVITY_UPDATED", "COGNITIVE_PHASE"}          # frequentes e sem informação nova no console


def summarize(kind: str, payload: dict) -> str:
    """Uma linha legível com os campos mais informativos do evento (sem despejar o payload inteiro)."""
    parts = []
    for key in SUMMARY_KEYS:
        value = payload.get(key)
        if value in (None, "", [], {}):
            continue
        text = " ".join(str(value).split())
        parts.append(f"{key}={text[:90]}")
        if len(parts) >= 4:
            break
    return f"{kind} · {' · '.join(parts)}" if parts else kind


class EventConsole(QtWidgets.QWidget):
    def __init__(self, source: deque | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.entries: deque = deque(maxlen=CONSOLE_LIMIT)
        self.paused = False
        title = _label("CONSOLE DE EVENTOS", "PanelTitle")
        self.filter = QtWidgets.QLineEdit()
        self.filter.setPlaceholderText("Filtrar (sem diferenciar maiúsculas)…")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(lambda *_: self.render())
        copy = _button("COPIAR", "Copiar as linhas visíveis")
        copy.clicked.connect(self.copy_visible)
        clear = _button("LIMPAR", "Limpar o console (os eventos continuam acontecendo)")
        clear.clicked.connect(self.clear)
        self.pause = _button("PAUSAR", "Congelar a lista para ler com calma")
        self.pause.setCheckable(True)
        self.pause.toggled.connect(self._toggle_pause)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.filter, 1)
        row.addWidget(self.pause)
        row.addWidget(copy)
        row.addWidget(clear)
        self.view = QtWidgets.QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(CONSOLE_LIMIT)
        self.view.setFont(theme.font(9, mono=True))
        self.status = _label("", "PanelDim")
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(row)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.status)
        for at, kind, payload in list(source or ()):
            self.add(kind, payload, at, render=False)
        self.render()

    @staticmethod
    def line(at: float, kind: str, payload: dict) -> str:
        return f"[{time.strftime('%H:%M:%S', time.localtime(at))}] ▸ {summarize(kind, payload)}"

    def add(self, kind: str, payload: dict, at: float, *, render: bool = True) -> None:
        if kind in QUIET:
            return
        text = self.line(at, kind, payload)
        self.entries.append(text)
        if render and not self.paused and self._matches(text):
            self.view.appendPlainText(text)
            self._count()

    def _matches(self, text: str) -> bool:
        wanted = self.filter.text().strip().casefold()
        return not wanted or wanted in text.casefold()

    def visible_lines(self) -> list[str]:
        return [t for t in self.entries if self._matches(t)]

    def render(self) -> None:
        self.view.setPlainText("\n".join(self.visible_lines()))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        self._count()

    def _count(self) -> None:
        visible = len(self.visible_lines()) if self.filter.text().strip() else len(self.entries)
        self.status.setText(f"{visible} de {len(self.entries)} evento(s)" + (" · PAUSADO" if self.paused else ""))

    def _toggle_pause(self, on: bool) -> None:
        self.paused = bool(on)
        self.pause.setText("RETOMAR" if on else "PAUSAR")
        if not on:
            self.render()
        self._count()

    def copy_visible(self) -> None:
        QtGui.QGuiApplication.clipboard().setText("\n".join(self.visible_lines()))
        self.status.setText("Linhas visíveis copiadas.")

    def clear(self) -> None:
        self.entries.clear()
        self.view.clear()
        self._count()


class LogViewer(QtWidgets.QWidget):
    _loaded = QtCore.Signal(object)
    LINES = 400

    def __init__(self, path: Path, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.path = Path(path)
        self.lines: list[str] = []
        self._loaded.connect(self._show, QtCore.Qt.QueuedConnection)
        title = _label("REGISTRO (LOG)", "PanelTitle")
        self.level = QtWidgets.QComboBox()
        self.level.addItem("Todas as linhas", "")
        self.level.addItem("Avisos e erros", "WARNING")
        self.level.addItem("Só erros", "ERROR")
        self.level.currentIndexChanged.connect(lambda *_: self.render())
        refresh = _button("ATUALIZAR", "Ler de novo o fim do arquivo")
        refresh.clicked.connect(self.reload)
        copy = _button("COPIAR", "Copiar as linhas visíveis")
        copy.clicked.connect(lambda: QtGui.QGuiApplication.clipboard().setText(self.view.toPlainText()))
        folder = _button("ABRIR PASTA")
        folder.clicked.connect(lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.path.parent))))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.level)
        row.addStretch(1)
        row.addWidget(refresh)
        row.addWidget(copy)
        row.addWidget(folder)
        self.view = QtWidgets.QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(theme.font(8.5, mono=True))
        self.view.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        self.status = _label("", "PanelDim")
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(row)
        layout.addWidget(self.view, 1)
        layout.addWidget(self.status)

    @staticmethod
    def tail(path: Path, count: int) -> list[str]:
        if not path.is_file():
            return []
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            block = min(size, 256 * 1024)
            handle.seek(size - block)
            data = handle.read().decode("utf-8", errors="replace")
        return data.splitlines()[-count:]

    def reload(self) -> None:
        self.status.setText("Lendo o log…")

        def work():
            try:
                lines = self.tail(self.path, self.LINES)
                self._loaded.emit({"lines": lines})
            except OSError as exc:
                self._loaded.emit({"error": str(exc)})

        threading.Thread(target=work, name="ultron-log-viewer", daemon=True).start()

    def _show(self, data: dict) -> None:
        if data.get("error"):
            self.status.setText(f"Não foi possível ler o log: {data['error']}")
            return
        self.lines = data.get("lines", [])
        self.render()

    def render(self) -> None:
        level = self.level.currentData() or ""
        wanted = {"WARNING": ("WARNING", "ERROR", "CRITICAL"), "ERROR": ("ERROR", "CRITICAL")}.get(level)
        lines = [ln for ln in self.lines if not wanted or any(f" {w} " in ln or f" {w}" in ln[:40] for w in wanted)]
        self.view.setPlainText("\n".join(lines))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())
        self.status.setText(f"{len(lines)} linha(s) de {self.path}" if self.path.is_file()
                            else f"Arquivo de log ainda não existe: {self.path}")

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self.reload()


class ServicesView(QtWidgets.QWidget):
    _loaded = QtCore.Signal(object)
    _gpu = QtCore.Signal(object)

    def __init__(self, core, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.core = core
        self._loaded.connect(self._show, QtCore.Qt.QueuedConnection)
        self._gpu.connect(self._show_gpu, QtCore.Qt.QueuedConnection)
        title = _label("SERVIÇOS, MODELOS E GPU", "PanelTitle")
        refresh = _button("ATUALIZAR")
        refresh.clicked.connect(self.reload)
        detect = _button("DETECTAR OPENGL", "Abrir um contexto OpenGL de teste e ler o renderizador (para a "
                                            "renderização 3D opcional por GPU)")
        detect.clicked.connect(self.detect_opengl)
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(detect)
        row.addWidget(refresh)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["ITEM", "ESTADO", "DETALHE"])
        self.tree.setColumnWidth(0, 240)
        self.tree.setColumnWidth(1, 140)
        self.status = _label("", "PanelDim")
        self.opengl: dict | None = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(title)
        layout.addLayout(row)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.status)

    def collect(self) -> dict:
        core = self.core
        data: dict[str, Any] = {"components": core.lifecycle.statuses(), "workers": core.runtime.status()}
        try:
            data["models"] = core.router.status().to_dict()
        except Exception as exc:
            data["models"] = {"error": str(exc)}
        openai = getattr(core, "openai", None)
        data["openai"] = openai.status() if openai is not None else None
        try:
            privacy = core.privacy.status()
            data["privacy"] = {k: privacy.get(k) for k in ("mode", "local_mode", "external_models", "strict_block")}
        except Exception as exc:
            data["privacy"] = {"error": str(exc)}
        try:
            from ..perception.system import gpu_static
            data["gpus"] = gpu_static()
        except Exception as exc:
            data["gpus"] = [{"name": f"não detectada ({type(exc).__name__})"}]
        data["telemetry"] = core.state.get("telemetry") or {}
        return data

    def reload(self) -> None:
        self.status.setText("Lendo…")

        def work():
            try:
                self._loaded.emit(self.collect())
            except Exception as exc:
                self._loaded.emit({"error": str(exc)})

        threading.Thread(target=work, name="ultron-services-view", daemon=True).start()

    def _row(self, parent, name: str, state: str, detail: str = "", *, bad: bool = False):
        item = QtWidgets.QTreeWidgetItem([name, state, detail])
        if bad:
            item.setForeground(1, theme.ALERT)
        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _show(self, data: dict) -> None:
        self.tree.clear()
        if data.get("error"):
            self.status.setText(f"Falha ao ler: {data['error']}")
            return
        group = self._row(None, "Componentes", f"{len(data['components'])}")
        for name, status in sorted(data["components"].items()):
            self._row(group, name, status, bad=status not in ("RUNNING", "STOPPED"))
        group = self._row(None, "Workers", f"{len(data['workers'])}")
        for name, info in sorted(data["workers"].items()):
            self._row(group, name, "vivo" if info.get("alive") else "PARADO",
                      f"fila {info.get('pending')} · processados {info.get('processed')} · falhas {info.get('failed')}"
                      + (f" · agora: {info['current']}" if info.get("current") else ""), bad=not info.get("alive"))
        models = data.get("models") or {}
        group = self._row(None, "Ollama", "ONLINE" if models.get("ollama_alive") else "OFFLINE",
                          f"{models.get('version', '')} · {models.get('latency_ms') or '—'} ms",
                          bad=not models.get("ollama_alive"))
        for task, selection in (models.get("selections") or {}).items():
            self._row(group, f"tarefa {task}", str(selection.get("model") or "—") if isinstance(selection, dict)
                      else str(selection), str(selection.get("reason", "")) if isinstance(selection, dict) else "")
        if models.get("missing"):
            self._row(group, "faltando", ", ".join(map(str, models["missing"])), bad=True)
        openai = data.get("openai")
        if openai is not None:
            self._row(None, "OpenAI", "em uso" if openai.get("chosen") and openai.get("available") else
                      ("bloqueada" if openai.get("chosen") else "não escolhida"),
                      f"modelo {openai.get('model')} · chave: {openai.get('key')} · chamadas {openai.get('calls')}"
                      + (f" · {openai.get('blocked')}" if openai.get("blocked") and openai.get("chosen") else ""))
        privacy = data.get("privacy") or {}
        self._row(None, "Privacidade", str(privacy.get("mode", "—")).upper(),
                  f"modelos externos: {'sim' if privacy.get('external_models') else 'não'}")
        group = self._row(None, "GPU", f"{len(data.get('gpus') or [])} detectada(s)")
        for gpu in data.get("gpus") or []:
            self._row(group, gpu.get("name", "—"), f"{gpu.get('memory_mb', '—')} MB" if gpu.get("memory_mb") else "",
                      f"driver {gpu.get('driver')}" if gpu.get("driver") else "")
        usage = (data.get("telemetry") or {}).get("gpu")
        if usage is not None:
            self._row(group, "uso atual", f"{usage}")
        if self.opengl is not None:
            self._show_gpu(self.opengl, add_only=True)
        self.tree.expandAll()
        self.status.setText(f"Lido às {time.strftime('%H:%M:%S')}. Nada estimado: o que não pôde ser lido aparece "
                            "como \"—\".")

    def detect_opengl(self) -> None:
        """No thread da interface (exigência do Qt), com um contexto fora da tela; falha é relatada."""
        info: dict[str, Any] = {}
        try:
            context = QtGui.QOpenGLContext()
            if not context.create():
                raise RuntimeError("o Qt não conseguiu criar um contexto OpenGL")
            surface = QtGui.QOffscreenSurface()
            surface.setFormat(context.format())
            surface.create()
            if not context.makeCurrent(surface):
                raise RuntimeError("contexto OpenGL criado, mas não pôde ser ativado")
            functions = context.functions()
            info = {"renderer": functions.glGetString(0x1F01) if hasattr(functions, "glGetString") else "",
                    "vendor": functions.glGetString(0x1F00) if hasattr(functions, "glGetString") else "",
                    "version": f"{context.format().majorVersion()}.{context.format().minorVersion()}",
                    "ok": True}
            context.doneCurrent()
        except Exception as exc:
            info = {"ok": False, "error": str(exc)}
        self._gpu.emit(info)

    def _show_gpu(self, info: dict, add_only: bool = False) -> None:
        self.opengl = info
        if info.get("ok"):
            self._row(None, "OpenGL (Qt)", f"versão {info.get('version')}",
                      f"{info.get('renderer') or 'renderizador não informado'} · {info.get('vendor') or ''}")
            text = "OpenGL disponível: a renderização por GPU pode ser usada (Aparência > Renderização 3D)."
        else:
            self._row(None, "OpenGL (Qt)", "INDISPONÍVEL", info.get("error", ""), bad=True)
            text = "OpenGL indisponível: a renderização fica na CPU."
        if not add_only:
            self.status.setText(text)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt)
        super().showEvent(event)
        self.reload()


class DiagnosticsPanel(SystemsPanel):
    """O Painel de Sistemas como página DIAGNÓSTICOS, com EVENTOS, LOG e SERVIÇOS E GPU."""

    def __init__(self, core, *, state: dict | None = None, profile=None, events: deque | None = None):
        super().__init__(core, state=state, profile=profile)
        self.setWindowTitle("JARVIS — Diagnósticos")
        from ..config import paths
        self.console = EventConsole(events)
        self.log_viewer = LogViewer(paths.logs_dir() / "ultron.log")
        self.services = ServicesView(core)
        self.tabs.addTab(self.console, "EVENTOS")
        self.tabs.addTab(self.log_viewer, "LOG")
        self.tabs.addTab(self.services, "SERVIÇOS E GPU")
        title = self.findChild(QtWidgets.QLabel)
        if title is not None and title.text() == "JARVIS · SISTEMAS":
            title.setText("JARVIS · DIAGNÓSTICOS")

    def visible_keys(self) -> set[str]:
        index = self.tabs.currentIndex()
        key = TABS[index][0] if 0 <= index < len(TABS) else ""
        return {key} & set(self.pages)

    def show_section(self, section: str | None) -> None:
        keys = [key for key, _ in TABS]
        if section in keys:
            self.tabs.setCurrentIndex(keys.index(section))
        self._tab_changed(self.tabs.currentIndex())

    def _tab_changed(self, index: int) -> None:
        if 0 <= index < len(TABS) and TABS[index][0] in self.pages and self.isVisible():
            self.ensure_loaded(TABS[index][0])

    def platform_event(self, kind: str, payload: dict, at: float) -> None:
        self.console.add(kind, payload, at)
