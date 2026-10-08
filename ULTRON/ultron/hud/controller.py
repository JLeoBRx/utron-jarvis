"""Controlador do HUB: liga o Neural Core à interface sem misturar as responsabilidades.

* Event Bus → Qt: eventos chegam em qualquer thread e são entregues à thread da interface
  por sinal (conexão enfileirada). ``STATE_CHANGED`` não é repassado um a um: marca o
  estado como alterado e a interface lê um único instantâneo por ciclo (sem enxurrada).
* Interface → Core: texto, microfone, voz, autorização e sugestões viram chamadas ao Core,
  que nunca bloqueiam a interface.
* Relógio da animação: avança a cena e redesenha só o que está visível; parado quando
  nada está visível.
"""
from __future__ import annotations

import logging
import time

from PySide6 import QtCore, QtGui, QtWidgets

from ..core.events import EventType
from ..health.monitor import format_report
from .brain_view import BrainView
from .orb import OrbWindow
from .scene import NeuralScene
from .window import HudWindow, app_icon

log = logging.getLogger("ultron.hud")

FORWARD = {t for t in EventType} - {EventType.STATE_CHANGED, EventType.LOG}
AUTO_EXPAND = {EventType.WAKE_WORD, EventType.AUTHORIZATION_REQUIRED}


class HudController(QtCore.QObject):
    _event = QtCore.Signal(str, object)

    def __init__(self, core, *, scene: NeuralScene | None = None, cache_dir=None):
        super().__init__()
        self.core = core
        self.scene = scene or NeuralScene()
        self.view = BrainView(self.scene, cache_dir=cache_dir)
        self.window = HudWindow(self.view)
        self.orb = OrbWindow(self.scene)
        self.tray = self._make_tray()
        self._state_dirty = True
        self._last_tick = time.perf_counter()
        self._tick_times: list[float] = []
        self.frame_rate = 0.0
        self._quitting = False
        self._event.connect(self._on_event)
        core.bus.subscribe(None, self._from_bus, name="hud.bridge")
        core.hud_health = self.health
        self._wire()
        self.scene.load_graph(core.memory.graph.snapshot(max_nodes=800))
        fps = int(getattr(core.settings(), "hud_fps", 60))
        self._frame = QtCore.QTimer(self)
        self._frame.setTimerType(QtCore.Qt.PreciseTimer)
        self._frame.timeout.connect(self._tick)
        self._frame.start(max(7, int(1000 / fps)))
        self._state_timer = QtCore.QTimer(self)
        self._state_timer.timeout.connect(self._pull_state)
        self._state_timer.start(110)
        self._telemetry_timer = QtCore.QTimer(self)
        self._telemetry_timer.timeout.connect(self._pull_telemetry)
        self._telemetry_timer.start(70)

    # ================================================================ ligação com o Core
    def _wire(self) -> None:
        w = self.window
        w.input.submitted.connect(lambda text: self.core.submit(text, source="text"))
        w.input.mic_toggled.connect(self._toggle_mic)
        w.input.voice_toggled.connect(self._toggle_voice)
        w.authorization.decided.connect(lambda ok: self.core.authorizations.resolve(ok, by="hud"))
        w.suggestion.decided.connect(lambda ok: self.core.accept_suggestion(ok, by="hud"))
        w.collapse_requested.connect(self.collapse)
        w.closing.connect(self._closed_to_tray)
        self.orb.expand_requested.connect(self.expand)
        self.orb.menu_requested.connect(lambda pos: self._menu().exec(pos))

    def _from_bus(self, event) -> None:
        """Chamado na thread de quem publicou: só marca/encaminha, nunca desenha."""
        if event.type == EventType.STATE_CHANGED:
            self._state_dirty = True
            return
        if event.type in FORWARD:
            self._event.emit(event.type.value, dict(event.payload))

    @QtCore.Slot(str, object)
    def _on_event(self, kind: str, payload: dict) -> None:
        self.scene.on_event(kind, payload)
        if kind == EventType.SYSTEM_READY.value:
            self.scene.load_graph(self.core.memory.graph.snapshot(max_nodes=800))
        if kind in {k.value for k in AUTO_EXPAND} and not self.window.isVisible() \
                and getattr(self.core.settings(), "hud_auto_expand", True):
            self.expand()

    def _pull_state(self) -> None:
        if not self._state_dirty:
            return
        self._state_dirty = False
        state = self.core.state.as_dict()
        self.scene.on_state(state)
        pending = state.get("pending_authorization")
        self.window.authorization.present(
            f"Ação sensível: {pending.get('description', '')}" if pending and pending.get("status") == "pending"
            else None)
        self.window.refresh_layout()

    def _pull_telemetry(self) -> None:
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

    # ================================================================ relógio
    def _tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now
        self.scene.step(dt)
        visible = False
        if self.window.isVisible() and not self.window.isMinimized():
            self.view.update()
            visible = True
        if self.orb.isVisible():
            self.orb.update()
            visible = True
        self._tick_times.append(dt)
        if len(self._tick_times) >= 60:
            self.frame_rate = len(self._tick_times) / max(1e-6, sum(self._tick_times))
            self._tick_times.clear()
        # nada visível: o relógio desacelera (a cena continua coerente, sem custo de desenho)
        interval = self._frame.interval()
        wanted = max(7, int(1000 / int(getattr(self.core.settings(), "hud_fps", 60)))) if visible else 250
        if interval != wanted:
            self._frame.setInterval(wanted)

    def health(self) -> dict:
        visible = self.window.isVisible() or self.orb.isVisible()
        if not self.frame_rate:
            return {"status": "OK", "detail": "medindo taxa de quadros"}
        paint = self.view.fps
        detail = f"{self.frame_rate:.0f} quadros/s · pintura {1000 / paint:.1f} ms" if paint else f"{self.frame_rate:.0f} quadros/s"
        status = "OK" if not visible or self.frame_rate >= 30 or not self.window.isVisible() else "WARN"
        return {"status": status, "detail": detail + ("" if visible else " · oculto")}

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

    # ================================================================ bandeja e menu
    def _make_tray(self) -> QtWidgets.QSystemTrayIcon | None:
        if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = QtWidgets.QSystemTrayIcon(app_icon(), self)
        tray.setToolTip("ULTRON")
        tray.setContextMenu(self._menu())
        tray.activated.connect(lambda reason: self.expand()
                               if reason == QtWidgets.QSystemTrayIcon.Trigger else None)
        tray.show()
        return tray

    def _menu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu()
        menu.addAction("Abrir o HUB", self.expand)
        menu.addAction("Orbe compacto", self.collapse)
        menu.addSeparator()
        mic = menu.addAction("Microfone")
        mic.setCheckable(True)
        mic.setChecked(self.core.voice.mic_enabled if self.core.enable_voice else False)
        mic.toggled.connect(lambda on: self.window.input.mic.setChecked(on))
        voice = menu.addAction("Voz do ULTRON")
        voice.setCheckable(True)
        voice.setChecked(not self.core.speaker.muted)
        voice.toggled.connect(lambda on: self.window.input.voice.setChecked(on))
        menu.addAction("Diagnóstico", self.show_diagnostics)
        menu.addSeparator()
        menu.addAction("Sair", self.quit)
        return menu

    def show_diagnostics(self) -> None:
        report = self.core.health.last or {}
        text = format_report(report) if report else "Verificação de saúde ainda não concluída."
        plugins = ", ".join(f"{p['name']} ({p['status']})" for p in self.core.plugins.list()) or "nenhum"
        box = QtWidgets.QMessageBox(self.window)
        box.setWindowTitle("ULTRON — diagnóstico")
        box.setIcon(QtWidgets.QMessageBox.NoIcon)
        box.setText(f"<pre>{text}\n\nPlugins: {plugins}</pre>")
        box.exec()

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.window.hide_to_tray = False
        self._frame.stop()
        if self.tray is not None:
            self.tray.hide()
        QtWidgets.QApplication.instance().quit()


def run_hud(core, *, minimized: bool = False, boot: bool = True) -> int:
    """Cria a interface, inicia o Core em segundo plano e roda o laço do Qt."""
    import threading

    from ..config import paths
    from . import theme

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setApplicationName("ULTRON")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(app_icon())
    controller = HudController(core, cache_dir=paths.data_dir())
    controller.show(minimized=minimized)
    if boot:
        threading.Thread(target=core.boot, name="ultron-boot", daemon=True).start()
    app.aboutToQuit.connect(core.shutdown)
    QtGui.QGuiApplication.setQuitOnLastWindowClosed(False)
    return app.exec()
