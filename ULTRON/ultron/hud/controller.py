"""Controlador da interface: liga o Neural Core aos dois hubs sem misturar responsabilidades.

* **HUB 1 — NEURAL CORE** (``HudWindow`` + orbe): atividade cognitiva e sistemas ativos.
* **HUB 2 — SECOND BRAIN** (``SecondBrainWindow``, criado sob demanda): o impacto prático
  dessa atividade — tarefas, compromissos, ideias, lembretes, rede e saúde.

Os dois hubs leem o MESMO estado central (ULTRON_STATE) e os MESMOS eventos:

* Event Bus → interface: eventos chegam em qualquer thread e entram numa fila limitada; a
  thread da interface drena em lotes (uma única chamada enfileirada por rajada). Em
  sobrecarga extrema, os eventos visuais mais antigos são descartados e contados — nunca há
  bloqueio de quem publica.
* Estado: ``STATE_CHANGED`` informa os campos alterados; a interface copia só esses campos
  (leitura incremental) num cache compartilhado pelos dois hubs.
* Relógio: ritmo de quadros adaptativo. No teto do perfil só enquanto há movimento real; em
  repouso, a cadência econômica; e nunca acima da carga que a pintura pode ocupar da thread
  da interface (o desenho do PySide6 não libera o GIL: pintar demais atrasa o núcleo inteiro).
* Trabalho pesado (snapshot do grafo, consultas do Second Brain) roda fora da thread da
  interface; o resultado volta por sinal.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque

from PySide6 import QtCore, QtGui, QtWidgets

from ..core.events import EventType
from ..health.monitor import format_report
from . import quality
from .brain_view import BrainView
from .orb import OrbWindow
from .scene import NeuralScene
from .window import HudWindow, app_icon

log = logging.getLogger("ultron.hud")

FORWARD = {t for t in EventType} - {EventType.STATE_CHANGED, EventType.LOG}
AUTO_EXPAND = {EventType.WAKE_WORD.value, EventType.AUTHORIZATION_REQUIRED.value}
PAINT_BUDGET = 0.45            # fração máxima da thread da interface ocupada pela pintura
PAINT_BUDGET_LOADED = 0.30     # com a CPU do sistema acima de 85%


class HudController(QtCore.QObject):
    _wake = QtCore.Signal()
    _settings_changed = QtCore.Signal(object)
    _graph_ready = QtCore.Signal(object)

    INBOX_LIMIT = 4000
    DRAIN_BATCH = 400

    def __init__(self, core, *, scene: NeuralScene | None = None):
        super().__init__()
        self.core = core
        settings = core.settings()
        self.profile = quality.get(getattr(settings, "performance_profile", quality.DEFAULT))
        self.scene = scene or NeuralScene(profile=self.profile)
        self.scene.profile = self.profile
        self.view = BrainView(self.scene)
        self.window = HudWindow(self.view)
        self.orb = OrbWindow(self.scene)
        self.second = None                          # HUB 2 (criado na primeira abertura)
        self.tray = self._make_tray()
        self._inbox: deque = deque()
        self._inbox_lock = threading.Lock()
        self._wake_pending = False
        self._dirty: set[str] = set()
        self._dirty_lock = threading.Lock()
        self.state_cache: dict = core.state.as_dict()
        self.dropped_events = 0
        self.notifications_shown = 0
        self._quitting = False
        self._last_tick = time.perf_counter()
        self._tick_times: deque = deque(maxlen=120)
        self.frame_rate = 0.0
        self._paint_ema = 0.0
        self._painted = 0
        self.target_fps = 0
        self._wake.connect(self._drain, QtCore.Qt.QueuedConnection)
        self._settings_changed.connect(self._apply_settings, QtCore.Qt.QueuedConnection)
        self._graph_ready.connect(self._on_graph, QtCore.Qt.QueuedConnection)
        core.bus.subscribe(None, self._from_bus, name="hud.bridge")
        core.hud_health = self.health
        core.settings_manager.on_change(lambda changed, s: self._settings_changed.emit(list(changed)))
        self._wire()
        self.scene.on_state(self.state_cache)
        self._load_graph_async()
        self._frame = QtCore.QTimer(self)
        self._frame.setTimerType(QtCore.Qt.PreciseTimer)
        self._frame.timeout.connect(self._tick)
        self._frame.start(max(7, int(1000 / quality.effective_fps(self.profile, self._hud_fps(), active=True))))
        self._state_timer = QtCore.QTimer(self)
        self._state_timer.timeout.connect(self._pull_state)
        self._state_timer.start(self.profile.state_ms)
        self._telemetry_timer = QtCore.QTimer(self)
        self._telemetry_timer.timeout.connect(self._pull_telemetry)
        self._telemetry_timer.start(self.profile.telemetry_ms)
        self._heartbeat_timer = QtCore.QTimer(self)
        self._heartbeat_timer.setTimerType(QtCore.Qt.PreciseTimer)
        self._heartbeat_timer.timeout.connect(self._heartbeat)
        self._last_beat = time.perf_counter()
        self._heartbeat_timer.start(200)

    def _hud_fps(self) -> int:
        return int(getattr(self.core.settings(), "hud_fps", 60))

    # ================================================================ ligação com o Core
    def _wire(self) -> None:
        w = self.window
        w.input.submitted.connect(lambda text: self.core.submit(text, source="text"))
        w.input.mic_toggled.connect(self._toggle_mic)
        w.input.voice_toggled.connect(self._toggle_voice)
        w.input.second_brain.connect(lambda: self.open_second_brain())
        w.authorization.decided.connect(lambda ok: self.core.authorizations.resolve(ok, by="hud"))
        w.suggestion.decided.connect(lambda ok: self.core.accept_suggestion(ok, by="hud"))
        w.collapse_requested.connect(self.collapse)
        w.second_brain_requested.connect(lambda: self.open_second_brain())
        w.closing.connect(self._closed_to_tray)
        self.orb.expand_requested.connect(self.expand)
        self.orb.menu_requested.connect(lambda pos: self._menu().exec(pos))

    def _from_bus(self, event) -> None:
        """Chamado na thread de quem publicou: só enfileira, nunca desenha nem consulta."""
        if event.type == EventType.STATE_CHANGED:
            with self._dirty_lock:
                self._dirty.update(event.payload.get("changed") or ())
            return
        if event.type not in FORWARD:
            return
        with self._inbox_lock:
            if len(self._inbox) >= self.INBOX_LIMIT:
                self._inbox.popleft()                     # o visual mais antigo perde a vez
                self.dropped_events += 1
            self._inbox.append((event.type.value, dict(event.payload), event.timestamp))
            if self._wake_pending:
                return
            self._wake_pending = True
        self._wake.emit()

    @QtCore.Slot()
    def _drain(self) -> None:
        with self._inbox_lock:
            batch = [self._inbox.popleft() for _ in range(min(self.DRAIN_BATCH, len(self._inbox)))]
            more = bool(self._inbox)
            if not more:
                self._wake_pending = False
        now = time.time()
        metrics = getattr(self.core, "metrics", None)
        for kind, payload, stamp in batch:
            if metrics is not None:
                metrics.record("ui.event_delay", max(0.0, now - stamp))
            try:
                self.scene.on_event(kind, payload)
                if self.second is not None:
                    self.second.on_event(kind, payload)
            except Exception:                               # um evento malformado nunca derruba a interface
                log.exception("falha ao tratar %s na interface", kind)
            if kind == EventType.SYSTEM_READY.value:
                self._load_graph_async()
            elif kind == EventType.REMINDER_DUE.value:
                self._notify(payload)
            elif kind == EventType.NOTIFICATION.value and payload.get("popup") and not payload.get("silent"):
                self._show_message(f"JARVIS · {payload.get('title', '')}", str(payload.get("body", "")))
            elif kind == EventType.UI_REQUEST.value and payload.get("view") == "second_brain":
                self.open_second_brain(payload.get("section") or None)
            if kind in AUTO_EXPAND and not self.window.isVisible() \
                    and getattr(self.core.settings(), "hud_auto_expand", True):
                self.expand()
        if more:
            QtCore.QTimer.singleShot(0, self._drain)

    def _pull_state(self) -> None:
        with self._dirty_lock:
            names, self._dirty = self._dirty, set()
        if not names:
            return
        self.state_cache.update(self.core.state.subset(names))
        self.scene.on_state(self.state_cache)
        if self.second is not None:
            self.second.on_state(self.state_cache, names)
        if "pending_authorization" in names:
            pending = self.state_cache.get("pending_authorization")
            self.window.authorization.present(
                f"Ação sensível: {pending.get('description', '')}"
                if pending and pending.get("status") == "pending" else None)
            self.window.refresh_layout()

    def _pull_telemetry(self) -> None:
        if not (self.window.isVisible() or self.orb.isVisible()):
            return                                        # só o HUB 1 e o orbe mostram níveis de áudio
        telemetry = self.core.telemetry()
        mic = self.core.voice.mic_probe() if self.core.enable_voice else {}
        if not mic.get("enabled", True):
            telemetry["mic_state"] = "MIC OFF"
        elif mic.get("capturing"):
            telemetry["mic_state"] = "MIC ON"
        else:
            telemetry["mic_state"] = "MIC —"
        self.scene.on_telemetry(telemetry)
        suggestion = telemetry.get("suggestion")
        if bool(suggestion) != self.window.suggestion.isVisible():
            self.window.suggestion.present(suggestion)
            self.window.refresh_layout()

    def _load_graph_async(self) -> None:
        """O snapshot do grafo (consulta e ordenação) roda fora da thread da interface."""
        def work() -> None:
            try:
                snapshot = self.core.memory.graph.snapshot(max_nodes=800)
            except Exception as exc:
                log.warning("snapshot do grafo falhou: %s", exc)
                return
            self._graph_ready.emit(snapshot)

        threading.Thread(target=work, name="ultron-hud-graph", daemon=True).start()

    @QtCore.Slot(object)
    def _on_graph(self, snapshot: dict) -> None:
        self.scene.load_graph(snapshot)

    # ================================================================ perfis e configuração
    @QtCore.Slot(object)
    def _apply_settings(self, changed: list) -> None:
        if "performance_profile" in changed or "hud_fps" in changed:
            self.set_profile(getattr(self.core.settings(), "performance_profile", quality.DEFAULT))

    def set_profile(self, name: str) -> None:
        self.profile = quality.get(name)
        self.scene.profile = self.profile
        self._state_timer.setInterval(self.profile.state_ms)
        self._telemetry_timer.setInterval(self.profile.telemetry_ms)
        if self.second is not None:
            self.second.on_profile(self.profile)

    # ================================================================ relógio
    def _tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now
        self.scene.step(dt)
        self._tick_times.append(dt)
        hub1 = self.window.isVisible() and not self.window.isMinimized()
        orb = self.orb.isVisible()
        if not (hub1 or orb):
            wanted = self.profile.hidden_interval_ms      # nada visível: a cena segue coerente, sem desenho
            self.target_fps = 0
        else:
            fps = quality.effective_fps(self.profile, self._hud_fps(), active=self.scene.in_motion())
            if self.view.paint_count != self._painted and self.view.frame_times:   # custo real da pintura
                self._painted = self.view.paint_count
                last = self.view.frame_times[-1]
                self._paint_ema = last if not self._paint_ema else self._paint_ema * 0.85 + last * 0.15
            cpu = (self.state_cache.get("telemetry") or {}).get("cpu")
            budget = PAINT_BUDGET_LOADED if isinstance(cpu, (int, float)) and cpu > 85 else PAINT_BUDGET
            if self._paint_ema > 0:
                fps = min(fps, max(self.profile.idle_fps, int(budget / self._paint_ema)))
            self.target_fps = fps
            wanted = max(7, int(1000 / fps))
            if hub1:
                self.view.update()
            if orb:
                self.orb.update()
        if self._frame.interval() != wanted:
            self._frame.setInterval(wanted)
        if len(self._tick_times) >= 30:
            self.frame_rate = len(self._tick_times) / max(1e-6, sum(self._tick_times))

    def _heartbeat(self) -> None:
        """Atraso do laço de eventos da interface: o quanto um temporizador de 200 ms atrasou."""
        now = time.perf_counter()
        lag = max(0.0, now - self._last_beat - 0.2)
        self._last_beat = now
        metrics = getattr(self.core, "metrics", None)
        if metrics is None:
            return
        metrics.record("ui.lag", lag)
        frames = list(self.view.frame_times)[-30:]
        for value in frames[-min(len(frames), max(1, int(self.target_fps * 0.2) or 1)):]:
            metrics.record("ui.frame", value)
        metrics.gauge("ui.fps", round(self.frame_rate, 1))
        metrics.gauge("ui.target_fps", self.target_fps)
        metrics.gauge("ui.profile", self.profile.name)
        metrics.gauge("ui.events_dropped", self.dropped_events)
        metrics.gauge("ui.inbox", len(self._inbox))
        metrics.gauge("ui.hub2_open", bool(self.second is not None and self.second.isVisible()))

    def health(self) -> dict:
        visible = self.window.isVisible() or self.orb.isVisible()
        if not self.frame_rate:
            return {"status": "OK", "detail": "medindo taxa de quadros"}
        paint = self._paint_ema * 1000
        detail = f"{self.frame_rate:.0f} quadros/s (alvo {self.target_fps}) · pintura {paint:.1f} ms · " \
                 f"perfil {self.profile.name}"
        lag = getattr(self.core, "metrics", None)
        lag_stats = lag.stats("ui.lag") if lag is not None else {}
        slow = lag_stats.get("n", 0) >= 10 and lag_stats.get("p95", 0) > 0.25
        return {"status": "WARN" if slow and visible else "OK", "detail": detail + ("" if visible else " · oculto")}

    # ================================================================ janelas
    def show(self, *, minimized: bool = False) -> None:
        if minimized:
            self.collapse()
        else:
            self.window.show()
            self.window.raise_()
            self.window.focus_input()

    def expand(self) -> None:
        self.orb.hide()
        self.window.showNormal() if self.window.isMinimized() else self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.window.focus_input()

    def collapse(self) -> None:
        self.window.hide()
        if not self.orb.isVisible():
            if self.orb.pos() == QtCore.QPoint(0, 0):
                self.orb.place_default()
            self.orb.show()

    def open_second_brain(self, section: str | None = None) -> None:
        if self.second is None:
            from .second_hub import SecondBrainWindow
            self.second = SecondBrainWindow(self.core, state=self.state_cache, profile=self.profile)
            self.second.authorization_decided.connect(lambda ok: self.core.authorizations.resolve(ok, by="hub2"))
        self.second.show_section(section)
        self.second.showNormal() if self.second.isMinimized() else self.second.show()
        self.second.raise_()
        self.second.activateWindow()

    def _closed_to_tray(self) -> None:
        if self.tray is None:
            self.quit()
        elif not self.orb.isVisible():
            self.orb.show()

    def _toggle_mic(self, enabled: bool) -> None:
        if self.core.enable_voice:
            self.core.voice.toggle_mic(enabled)

    def _toggle_voice(self, enabled: bool) -> None:
        self.core.speaker.muted = not enabled
        if not enabled:
            self.core.speaker.interrupt()

    # ================================================================ notificações
    def _notify(self, payload: dict) -> None:
        """Notificação nativa (bandeja do Windows) para um lembrete real; respeita silêncio."""
        if payload.get("silent"):
            return
        title = {"lead": "JARVIS · Lembrete antecipado", "missed": "JARVIS · Lembrete perdido"}.get(
            payload.get("kind"), "JARVIS · Lembrete")
        body = str(payload.get("title", ""))[:160]
        if payload.get("when_text"):
            body += f"\n{payload['when_text']}"
        self._show_message(title, body)

    def _show_message(self, title: str, body: str) -> None:
        """Usa a notificação nativa do sistema (no Windows 10/11, o centro de notificações) quando há
        bandeja; sem bandeja, o aviso fica na central de notificações do HUB 2 e na fala."""
        self.notifications_shown += 1
        if self.tray is None or not self.tray.isVisible():
            return
        self.tray.showMessage(title[:80], body[:240], app_icon(), 9000)

    # ================================================================ bandeja e menu
    def _make_tray(self) -> QtWidgets.QSystemTrayIcon | None:
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QtWidgets.QSystemTrayIcon(app_icon(), self)
        tray.setToolTip("JARVIS")
        tray.setContextMenu(self._menu())
        tray.activated.connect(lambda reason: self.expand()
                               if reason == QtWidgets.QSystemTrayIcon.Trigger else None)
        tray.messageClicked.connect(lambda: self.open_second_brain("notifications"))
        tray.show()
        return tray

    def _menu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu()
        menu.addAction("Abrir o HUB", self.expand)
        menu.addAction("Second Brain", lambda: self.open_second_brain())
        menu.addAction("Orbe compacto", self.collapse)
        menu.addSeparator()
        mic = menu.addAction("Microfone")
        mic.setCheckable(True)
        mic.setChecked(self.core.voice.mic_enabled if self.core.enable_voice else False)
        mic.toggled.connect(lambda on: self.window.input.mic.setChecked(on))
        voice = menu.addAction("Voz do JARVIS")
        voice.setCheckable(True)
        voice.setChecked(not self.core.speaker.muted)
        voice.toggled.connect(lambda on: self.window.input.voice.setChecked(on))
        profiles = menu.addMenu("Perfil de desempenho")
        group = QtGui.QActionGroup(profiles)
        for name, label in (("performance", "Performance (fluidez)"), ("balanced", "Balanced (equilíbrio)"),
                            ("cinematic", "Cinematic (efeitos)")):
            action = profiles.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.profile.name == name)
            action.setActionGroup(group)
            action.triggered.connect(lambda _=False, n=name: self.core.settings_manager.update(performance_profile=n))
        menu.addAction("Diagnóstico", self.show_diagnostics)
        menu.addSeparator()
        menu.addAction("Sair", self.quit)
        return menu

    def show_diagnostics(self) -> None:
        report = self.core.health.last or {}
        text = format_report(report) if report else "Verificação de saúde ainda não concluída."
        plugins = ", ".join(f"{p['name']} ({p['status']})" for p in self.core.plugins.list()) or "nenhum"
        box = QtWidgets.QMessageBox(self.window)
        box.setWindowTitle("JARVIS — diagnóstico")
        box.setIcon(QtWidgets.QMessageBox.NoIcon)
        box.setText(f"<pre>{text}\n\nPlugins: {plugins}</pre>")
        box.exec()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.window.hide_to_tray = False
        for timer in (self._frame, self._state_timer, self._telemetry_timer, self._heartbeat_timer):
            timer.stop()
        if self.second is not None:
            self.second.shutdown()
        if self.tray is not None:
            self.tray.hide()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.quit()


def run_hud(core, *, minimized: bool = False, boot: bool = True) -> int:
    """Cria a interface, inicia o Core em segundo plano e roda o laço do Qt."""
    from . import theme

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setApplicationName("JARVIS")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(app_icon())
    controller = HudController(core)
    controller.show(minimized=minimized)
    if boot:
        threading.Thread(target=core.boot, name="ultron-boot", daemon=True).start()
    app.aboutToQuit.connect(core.shutdown)
    QtGui.QGuiApplication.setQuitOnLastWindowClosed(False)
    return app.exec()
