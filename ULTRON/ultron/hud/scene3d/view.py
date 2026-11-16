"""A vista da central 3D (QWebEngineView) e a ponte com a página.

O widget se comporta como o rosto 2D para o controlador (``_AvatarCore``: ``on_state``, ``on_event``,
``on_telemetry``, ``step``, ``resolved``...): resolve o MESMO estado real e o envia à página. A página desenha
e devolve só pedidos (``request``) e escolhas de painel (``select``), que o controlador trata pelo caminho
normal da interface. Qualquer falha vira o sinal ``unavailable(motivo)`` — o controlador volta para 2D.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from PySide6 import QtCore, QtGui, QtWebChannel, QtWebEngineCore, QtWebEngineWidgets

from ..avatar.view import _AvatarCore
from . import INDEX, clear_marker, inside_web, mark_failed, mark_starting, read_marker

log = logging.getLogger("ultron.hud.scene3d")

ACTIVE = frozenset({"falando", "escutando", "reconhecendo", "inicializando"})
MOVING = frozenset({"falando", "escutando", "reconhecendo", "pensando", "executando", "tardis", "inicializando",
                    "alerta"})
REQUESTS = frozenset({"tardis", "jarvis", "mic", "restore"})
_inside_web = inside_web


class _Guard(QtWebEngineCore.QWebEngineUrlRequestInterceptor):
    """Nenhuma conexão de rede: a página só lê os próprios arquivos (e o qwebchannel.js embutido no Qt)."""

    def interceptRequest(self, info) -> None:  # noqa: N802 (Qt)
        url = info.requestUrl()
        scheme = url.scheme()
        if scheme in ("qrc", "data", "blob") or (scheme == "file" and _inside_web(url.toLocalFile())):
            return
        log.warning("cena 3D: pedido bloqueado (%s)", url.toString()[:200])
        info.block(True)


class _Page(QtWebEngineCore.QWebEnginePage):
    """Navegação restrita à pasta da cena; mensagens do console da página vão para o log."""

    _LEVELS = {0: logging.DEBUG, 1: logging.WARNING, 2: logging.ERROR}

    def acceptNavigationRequest(self, url, nav_type, is_main_frame) -> bool:  # noqa: N802 (Qt)
        allowed = url.scheme() == "file" and _inside_web(url.toLocalFile())
        if not allowed:
            log.warning("cena 3D: navegação recusada (%s)", url.toString()[:200])
        return allowed

    def javaScriptConsoleMessage(self, level, message, line, source) -> None:  # noqa: N802 (Qt)
        value = getattr(level, "value", level)
        log.log(self._LEVELS.get(int(value), logging.INFO), "cena 3D [js] %s (%s:%s)", message,
                Path(str(source)).name, line)

    def createWindow(self, _type):  # noqa: N802 (Qt) — a página não abre janelas
        return None


class _Bridge(QtCore.QObject):
    """Objeto "jarvis" no QWebChannel: só recebe texto; quem decide é o Python."""

    ready_received = QtCore.Signal(str)
    report_received = QtCore.Signal(str)
    select_received = QtCore.Signal(str)
    request_received = QtCore.Signal(str)

    @QtCore.Slot(str)
    def ready(self, info: str) -> None:
        self.ready_received.emit(str(info)[:20000])

    @QtCore.Slot(str)
    def report(self, data: str) -> None:
        self.report_received.emit(str(data)[:20000])

    @QtCore.Slot(str)
    def select(self, key: str) -> None:
        self.select_received.emit(str(key)[:40])

    @QtCore.Slot(str)
    def request(self, action: str) -> None:
        self.request_received.emit(str(action)[:40])


_GUARD: _Guard | None = None


def _guard_profile() -> QtWebEngineCore.QWebEngineProfile:
    """O perfil padrão (sem disco no Qt 6) com o bloqueio de rede — um por processo."""
    global _GUARD
    profile = QtWebEngineCore.QWebEngineProfile.defaultProfile()
    if _GUARD is None:
        _GUARD = _Guard(QtCore.QCoreApplication.instance())
        profile.setUrlRequestInterceptor(_GUARD)
        profile.setHttpCacheType(QtWebEngineCore.QWebEngineProfile.HttpCacheType.NoCache)
        profile.setPersistentCookiesPolicy(QtWebEngineCore.QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
    return profile


class Scene3DView(QtWebEngineWidgets.QWebEngineView, _AvatarCore):
    face_clicked = QtCore.Signal()
    became_ready = QtCore.Signal(dict)
    unavailable = QtCore.Signal(str)
    panel_selected = QtCore.Signal(str)
    action_requested = QtCore.Signal(str)
    backend = "3d"

    READY_TIMEOUT_MS = 25000
    PUSH_ACTIVE = 1 / 30          # fala e escuta: boca e níveis de áudio a 30 por segundo
    PUSH_IDLE = 0.25
    HEARTBEAT = 1.0               # sem mudança, um sinal por segundo (a página sabe que o SAFRA está vivo)

    def __init__(self, parent=None, *, profile_name: str = "balanced", effects: bool = True, **sources: Any):
        super().__init__(parent)
        self._init_avatar(**sources)
        self.setMinimumSize(480, 360)
        self.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        self.is_ready = False
        self.failed = ""
        self.info: dict = {}
        self.stats: dict = {}
        self.mode = "jarvis"
        self.compact = False
        self.ultron = False
        self.selected = ""
        self.mic_state = ""
        self.system: dict = {}
        self.profile_name = profile_name
        self.effects = bool(effects)
        self.debug = False
        self.js_errors = 0
        self.pushes = 0
        self._pending: dict[str, dict] = {}
        self._last_push = 0.0
        self._last_sig = ""
        self._disposed = False
        page = _Page(_guard_profile(), self)
        settings = page.settings()
        attr = QtWebEngineCore.QWebEngineSettings.WebAttribute
        for name, value in (("LocalContentCanAccessFileUrls", True), ("LocalContentCanAccessRemoteUrls", False),
                            ("WebGLEnabled", True), ("Accelerated2dCanvasEnabled", True),
                            ("JavascriptCanOpenWindows", False), ("JavascriptCanAccessClipboard", False),
                            ("PluginsEnabled", False), ("ErrorPageEnabled", False), ("PdfViewerEnabled", False),
                            ("ShowScrollBars", False), ("AllowRunningInsecureContent", False)):
            if hasattr(attr, name):
                settings.setAttribute(getattr(attr, name), value)
        page.setBackgroundColor(QtGui.QColor(2, 6, 17))
        self._bridge = _Bridge(self)
        self._bridge.ready_received.connect(self._on_ready)
        self._bridge.report_received.connect(self._on_report)
        self._bridge.select_received.connect(self._on_select)
        self._bridge.request_received.connect(self._on_request)
        self._channel = QtWebChannel.QWebChannel(page)
        self._channel.registerObject("jarvis", self._bridge)
        page.setWebChannel(self._channel)
        page.renderProcessTerminated.connect(self._render_died)
        self.setPage(page)
        self._ready_timer = QtCore.QTimer(self)
        self._ready_timer.setSingleShot(True)
        self._ready_timer.timeout.connect(self._ready_timeout)
        self._ready_timer.start(self.READY_TIMEOUT_MS)
        self._started = time.monotonic()
        mark_starting()
        self.setToolTip("Clique na cabeça do holograma para ligar ou desligar o microfone; arraste para girar, "
                        "role para aproximar; duplo clique volta ao enquadramento")
        self.load(QtCore.QUrl.fromLocalFile(str(INDEX)))

    # ------------------------------------------------------------ página → Python
    @QtCore.Slot(str)
    def _on_ready(self, text: str) -> None:
        if self.is_ready or self.failed:
            return
        self._ready_timer.stop()
        try:
            self.info = json.loads(text)
        except ValueError:
            self.info = {}
        self.is_ready = True
        clear_marker()
        log.info("cena 3D pronta em %.1f s: WebGL 2 (%s), three r%s, %s vértices no holograma",
                 time.monotonic() - self._started, self.info.get("renderer", "?"), self.info.get("three", "?"),
                 (self.info.get("avatar") or {}).get("vertices", "?"))
        self._send({"type": "init", "profile": self.profile_name, "effects": self.effects, "mode": self.mode,
                    "selected": self.selected, "debug": self.debug, "compact": self.compact}, force=True)
        for msg in list(self._pending.values()):
            self._send(msg, force=True)
        self._pending.clear()
        self._push(force=True)
        self.became_ready.emit(dict(self.info))

    @QtCore.Slot(str)
    def _on_report(self, text: str) -> None:
        try:
            data = json.loads(text)
        except ValueError:
            return
        kind = data.get("type")
        if kind == "stats":
            self.stats = data
        elif kind == "failed":
            self._fail(str(data.get("reason") or "a página 3D informou falha"))
        elif kind == "error":
            self.js_errors += 1
            log.warning("cena 3D: erro na página: %s %s", str(data.get("message", ""))[:300], data.get("where", ""))
        elif kind == "context":
            (log.warning if data.get("state") == "perdido" else log.info)("cena 3D: contexto WebGL %s",
                                                                          data.get("state"))
        elif kind == "quality":
            log.info("cena 3D: qualidade %s, redução %s", data.get("profile"), data.get("level"))

    @QtCore.Slot(str)
    def _on_select(self, key: str) -> None:
        self.panel_selected.emit(key)

    @QtCore.Slot(str)
    def _on_request(self, action: str) -> None:
        if action not in REQUESTS:
            log.warning("cena 3D: pedido desconhecido ignorado (%s)", action)
            return
        if action == "mic":
            self.face_clicked.emit()
        else:
            self.action_requested.emit(action)

    def _render_died(self, status, code) -> None:
        name = getattr(status, "name", str(status))
        if self._disposed or "Normal" in name:
            return
        self._fail(f"o processo de desenho da página 3D terminou ({name}, código {code})")

    def _ready_timeout(self) -> None:
        if not self.is_ready:
            self._fail(f"a página 3D não respondeu em {self.READY_TIMEOUT_MS // 1000} s")

    def _fail(self, reason: str) -> None:
        if self.failed or self._disposed:
            return
        self.failed = reason
        self._ready_timer.stop()
        mark_failed(reason)
        log.error("cena 3D indisponível: %s — a interface volta para a vista 2D", reason)
        self.unavailable.emit(reason)

    # ------------------------------------------------------------ Python → página
    def _send(self, msg: dict, *, force: bool = False) -> None:
        if self.failed or self._disposed:
            return
        if not self.is_ready and not force:
            self._pending[str(msg.get("type"))] = msg
            return
        payload = json.dumps(msg, ensure_ascii=False, default=str)
        self.page().runJavaScript(f"window.JARVIS&&window.JARVIS.receive({payload})")
        self.pushes += 1

    def _signal(self) -> dict:
        r = self.resolved
        style = r.style
        mouth = None
        if r.key == "falando":
            try:
                mouth = self.mouth_source()
            except Exception:
                mouth = None
        caption = None
        if self.captions_enabled:
            try:
                caption = self.caption_source()
            except Exception:
                caption = None
        s = self.signals
        return {"type": "sig", "state": r.key, "label": r.label + ("  ·  ALERTA" if r.alert_tint else ""),
                "detail": r.detail, "alert": bool(r.alert_tint or r.key == "alerta"),
                "rgb": list(style.rgb), "iris": list(style.iris),
                "mouth": mouth or {"open": 0.0, "wide": 0.0, "round": 0.0, "energy": 0.0},
                "out_level": round(float(self.out_level), 3), "mic_level": round(float(self.mic_level), 3),
                "mic_state": self.mic_state, "boot": round(1.0 if s.booted else float(s.boot_progress), 3),
                "task": self.projections.get("tarefa", "") if r.key == "executando" else "",
                "projections": dict(self.projections), "caption": caption, "system": dict(self.system)}

    def _push(self, *, force: bool = False) -> None:
        now = time.monotonic()
        key = self.resolved.key
        interval = self.PUSH_ACTIVE if key in ACTIVE else self.PUSH_IDLE
        if not force and now - self._last_push < interval:
            return
        sig = self._signal()
        text = json.dumps(sig, ensure_ascii=False, sort_keys=True, default=str)
        if not force and text == self._last_sig and now - self._last_push < self.HEARTBEAT:
            return
        self._last_sig = text
        self._last_push = now
        self._send(sig)

    # ------------------------------------------------------------ dados reais (do controlador)
    def on_state(self, state: dict) -> None:
        super().on_state(state)
        health = state.get("health") or {}
        checks = health.get("checks") or {}
        problems = [name for name, c in checks.items() if isinstance(c, dict) and c.get("status") in ("WARN", "FAIL")]
        self.system = {k: v for k, v in (
            ("model", str(state.get("active_model") or "")),
            ("health", {"status": str(health.get("overall")), "detail": ", ".join(problems[:3])}
             if health.get("overall") else None),
            ("uptime", self.system.get("uptime")), ("workers", self.system.get("workers")),
        ) if v is not None}

    def on_telemetry(self, telemetry: dict) -> None:
        super().on_telemetry(telemetry)
        self.mic_state = str(telemetry.get("mic_state") or "")
        if isinstance(telemetry.get("uptime"), (int, float)):
            self.system["uptime"] = float(telemetry["uptime"])
        if isinstance(telemetry.get("workers"), dict):
            self.system["workers"] = dict(telemetry["workers"])

    def set_profile(self, profile_name: str, *, effects: bool) -> None:
        super().set_profile(profile_name, effects=effects)
        self.profile_name = profile_name
        self._send({"type": "profile", "profile": profile_name, "effects": bool(effects)})

    # ------------------------------------------------------------ controle da cena
    def set_mode(self, mode: str, *, animate: bool = True) -> None:
        """"jarvis" (convés) ou "tardis" (sala de controle) — a página faz a passagem pela porta."""
        if mode not in ("jarvis", "tardis"):
            return
        self.mode = mode
        self._send({"type": "mode", "mode": mode, "animate": bool(animate)})

    def set_compact(self, on: bool) -> None:
        """ORBE minimizado: a página mostra só o núcleo, sem interface por cima (a janela flutuante cuida do
        mouse). Desligar devolve a vista anterior sem perder estado."""
        self.compact = bool(on)
        self._send({"type": "compact", "on": self.compact})

    def set_ultron(self, on: bool, *, source: str = "", messages=(), label: str = "") -> None:
        """Protocolo ULTRON: só aparência (cores, postura, mensagens do personagem, rótulo de evento visual)."""
        self.ultron = bool(on)
        self._send({"type": "ultron", "on": self.ultron, "source": source, "messages": list(messages), "label": label})

    def select_panel(self, key: str) -> None:
        self.selected = key or ""
        self._send({"type": "select", "panel": self.selected})

    def push_room(self, snapshot: dict) -> None:
        self._send({"type": "room", **snapshot})

    def show_view(self, view: str) -> None:
        self._send({"type": "view", "view": view})

    # ------------------------------------------------------------ relógio (o mesmo do rosto 2D)
    def step(self, dt: float) -> None:
        started = time.perf_counter()
        self.update_state()
        self._push()
        self.paint_count += 1
        self.frame_times.append(time.perf_counter() - started)

    def in_motion(self) -> bool:
        return self.resolved.key in MOVING or self.mic_level > 0.02

    def dispose(self) -> None:
        """Encerramento: sem relatórios tardios; o marcador "iniciando" não fica para trás."""
        self._disposed = True
        self._ready_timer.stop()
        if read_marker().startswith("iniciando"):
            clear_marker()
