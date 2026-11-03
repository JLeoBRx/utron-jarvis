"""Controlador da interface: liga o Neural Core à PLATAFORMA JARVIS ULTIMATE sem misturar responsabilidades.

Uma janela (``PlatformWindow``) com cinco módulos — JARVIS · TARDIS · ATIVIDADES ·
CONFIGURAÇÕES · DIAGNÓSTICOS — e o orbe compacto. As páginas pesadas (TARDIS, Diagnósticos,
Atividades, Configurações) nascem na primeira visita e nunca são destruídas: trocar de página
preserva câmera, região, filtros e textos.

* **JARVIS** (``BrainView`` + conversa): percepção, decisão, planejamento, execução, verificação, voz.
* **TARDIS** (``TardisPage``): a SALA DE CONTROLE (console 3D, rotor ligado ao motor da TARDIS e os
  painéis de análise) e o ARQUIVO (``TardisWindow``, a memória pessoal como espaço navegável).
* **DIAGNÓSTICOS** (o Painel de Sistemas embutido + eventos, log, serviços e GPU).

Todas as páginas leem o MESMO estado central (JARVIS_STATE) e os MESMOS eventos:

* Event Bus → interface: eventos chegam em qualquer thread e entram numa fila limitada; a
  thread da interface drena em lotes (uma única chamada enfileirada por rajada). Em
  sobrecarga extrema, os eventos visuais mais antigos são descartados e contados — nunca há
  bloqueio de quem publica.
* Estado: ``STATE_CHANGED`` informa os campos alterados; a interface copia só esses campos
  (leitura incremental) num cache compartilhado por todas as páginas.
* Relógio: ritmo de quadros adaptativo. No teto do perfil só enquanto há movimento real; em
  repouso, a cadência econômica; vista fora da tela (outra página na frente), nenhum desenho; e
  nunca acima da carga que a pintura pode ocupar da thread da interface (o desenho do PySide6 não
  libera o GIL: pintar demais atrasa o núcleo inteiro).
* Trabalho pesado (snapshot do grafo, consultas do Second Brain, listas) roda fora da thread da
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
from . import quality, theme
from .brain_view import BrainView
from .orb import OrbWindow
from .platform import NAV_KEYS, PlatformWindow
from .scene import NeuralScene
from .window import app_icon

log = logging.getLogger("ultron.hud")

FORWARD = {t for t in EventType} - {EventType.STATE_CHANGED, EventType.LOG}
AUTO_EXPAND = {EventType.WAKE_WORD.value, EventType.AUTHORIZATION_REQUIRED.value}
PAINT_BUDGET = 0.45            # fração máxima da thread da interface ocupada pela pintura
PAINT_BUDGET_LOADED = 0.30     # com a CPU do sistema acima de 85%
SHUTDOWN_DELAY_MS = 1500       # "Encerrando, senhor." é dito antes de fechar


class _ScenePlaceholder(QtWidgets.QWidget):
    """Fundo da página JARVIS enquanto a cena 3D está emprestada à sala da TARDIS (uma cena, um motor)."""

    paint_count = 0
    bottom_reserved = 16

    def __init__(self):
        super().__init__()
        self.frame_times: deque = deque(maxlen=2)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: #020611;")

    def in_motion(self) -> bool:
        return False


class HudController(QtCore.QObject):
    _wake = QtCore.Signal()
    _settings_changed = QtCore.Signal(object)
    _graph_ready = QtCore.Signal(object)

    INBOX_LIMIT = 4000
    DRAIN_BATCH = 400

    def __init__(self, core, *, scene: NeuralScene | None = None):
        super().__init__()
        self.core = core
        # Cache do estado central, compartilhado por TODAS as páginas e atualizado no lugar (_pull_state).
        # Criado antes de qualquer peça da interface: a bandeja monta o menu (e o submenu do Observador,
        # que lê este cache) já na construção, quando o sistema tem bandeja.
        self.state_cache: dict = core.state.as_dict()
        settings = core.settings()
        self.profile = quality.get(getattr(settings, "performance_profile", quality.DEFAULT))
        self.scene = scene or NeuralScene(profile=self.profile)
        self.scene.profile = self.profile
        self.view = BrainView(self.scene)                       # núcleo neural (vista alternativa)
        self.avatar_reason = ""
        self.scene3d = None                         # central 3D (Three.js no QtWebEngine), quando disponível
        self.scene3d_reason = ""                    # por que a central 3D não está em uso (vazio = em uso)
        self.tardis_page = None                     # página TARDIS: sala de controle + ARQUIVO
        self.avatar = self._make_avatar(getattr(settings, "render_backend", "cpu"))
        face = getattr(settings, "avatar_mode", "face") == "face"
        self.window = PlatformWindow(self.avatar if face else self.view, core=core, effects=self._effects_enabled)
        (self.view if face else self.avatar).setParent(self.window.jarvis_page)
        (self.view if face else self.avatar).hide()
        self.orb = OrbWindow(self.scene)
        self.second = None                          # ARQUIVO da TARDIS: memória espacial (sob demanda)
        self._placeholder = _ScenePlaceholder()     # ocupa a página JARVIS enquanto a cena 3D está na TARDIS
        self.window.page_changed.connect(self._page_changed)
        self.systems = None                         # Diagnósticos / Painel de Sistemas (idem)
        self.activity_page = None
        self.settings_page = None
        self.window.set_factory("tardis", self._make_tardis)
        self.window.set_factory("diagnosticos", self._make_diagnostics)
        self.window.set_factory("atividades", self._make_activity)
        self.window.set_factory("configuracoes", self._make_settings)
        self.tray = self._make_tray()
        self._inbox: deque = deque()
        self._inbox_lock = threading.Lock()
        self._wake_pending = False
        self._dirty: set[str] = set()
        self._dirty_lock = threading.Lock()
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
        core.hud_probe = lambda: bool(self.window.covering)   # lido em outra thread: só um booleano
        core.settings_manager.on_change(lambda changed, s: self._settings_changed.emit(list(changed)))
        self._wire()
        self.scene.on_state(self.state_cache)
        self.window.on_state(self.state_cache)
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
        # Protocolo ULTRON: evento VISUAL (nenhuma ação real); sorteio ocasional e fim automático
        from ..config import paths
        from .ultron_protocol import UltronProtocol
        self.ultron = UltronProtocol(settings=core.settings, history_path=paths.data_file("protocolo_ultron.json"))
        self._ultron_saved: dict | None = None          # aparência de antes do evento, restaurada exatamente
        self._ultron_timer = QtCore.QTimer(self)
        self._ultron_timer.timeout.connect(self._ultron_tick)
        self._ultron_timer.start(5000)
        # tecla de emergência (configurável): vale em qualquer janela do JARVIS, inclusive o ORBE recolhido
        self.emergency_shortcut = QtGui.QShortcut(
            QtGui.QKeySequence(str(getattr(core.settings(), "ultron_emergency_key", "") or "Ctrl+Shift+U")),
            self.window, context=QtCore.Qt.ApplicationShortcut, activated=self.ultron_emergency)

    def _hud_fps(self) -> int:
        return int(getattr(self.core.settings(), "hud_fps", 60))

    # ================================================================ avatar
    def _make_avatar(self, backend: str):
        """A vista do JARVIS: a central 3D quando possível; senão o rosto 2D (GPU ou CPU) — e diz por quê."""
        view = self._make_scene3d()
        if view is None:
            view = self._make_avatar_2d(backend)
        view.face_clicked.connect(lambda: self.window.input.mic.toggle())
        view.set_profile(self.profile.name, effects=self._effects_enabled())
        view.captions_enabled = bool(getattr(self.core.settings(), "captions", True))
        view.on_state(self.core.state.as_dict())
        return view

    def _make_scene3d(self):
        """Central 3D (holograma de corpo inteiro, ORBE, cabine e sala da TARDIS) — ou None com o motivo."""
        from . import scene3d
        ok, reason = scene3d.availability(self.core.settings(), platform_name=QtGui.QGuiApplication.platformName())
        if ok:
            try:
                from .scene3d.view import Scene3DView
                speaker = self.core.speaker
                view = Scene3DView(profile_name=self.profile.name, effects=self._effects_enabled(),
                                   mouth=speaker.mouth, caption=speaker.caption, audible=speaker.audible)
                view.unavailable.connect(self._scene3d_failed)
                view.action_requested.connect(self._scene3d_request)
                view.became_ready.connect(self._scene3d_ready)
                self.scene3d, self.scene3d_reason = view, ""
                self.avatar_reason = "cena 3D (abrindo)"
                return view
            except Exception as exc:                          # nunca impede a interface de abrir
                log.exception("cena 3D: falha ao criar a vista")
                reason = f"falha ao criar a vista 3D: {exc}"
                scene3d.mark_failed(reason)
        self.scene3d, self.scene3d_reason = None, reason
        log.info("cena 3D não usada: %s", reason)
        return None

    def _scene3d_ready(self, info: dict) -> None:
        self.avatar_reason = f"cena 3D — WebGL 2 ({info.get('renderer', '?')})"

    def _scene3d_failed(self, reason: str) -> None:
        """A cena 3D caiu (sem WebGL, contexto perdido, processo encerrado...): volta para 2D sem perder nada."""
        view = self.scene3d
        if view is None:
            return
        self.scene3d, self.scene3d_reason = None, reason
        room = self.tardis_page.room if self.tardis_page is not None else None
        if room is not None and room.scene3d is view:
            room.detach_scene3d()
        if self.orb.scene_view is view:
            self.orb.detach_scene()                     # o orbe volta ao desenho 2D
        self.avatar_reason = ""                         # era "cena 3D (abrindo)": agora vale o desenho 2D
        self.avatar = self._make_avatar_2d(getattr(self.core.settings(), "render_backend", "cpu"))
        self.avatar.face_clicked.connect(lambda: self.window.input.mic.toggle())
        self.avatar.set_profile(self.profile.name, effects=self._effects_enabled())
        self.avatar.captions_enabled = bool(getattr(self.core.settings(), "captions", True))
        self.avatar.on_state(self.state_cache)
        page = self.window.jarvis_page
        if page.central in (view, self._placeholder):
            face = getattr(self.core.settings(), "avatar_mode", "face") == "face"
            page.set_central(self.avatar if face else self.view)
        view.dispose()
        view.hide()
        view.setParent(None)
        view.deleteLater()
        self._show_message("JARVIS · vista 3D indisponível", f"{reason}. A interface continua na vista 2D.")

    def _scene3d_request(self, action: str) -> None:
        """Pedidos da página 3D (cliques do usuário): os mesmos caminhos dos botões da interface."""
        if action == "restore":
            self.ultron_stop("botão")
        elif action == "tardis":
            self.open_tardis()
        elif action == "jarvis":
            self.open_page("jarvis")

    def _page_changed(self, key: str) -> None:
        """Uma só cena 3D: no JARVIS ela é o convés; na TARDIS, a sala de controle (passa pela porta)."""
        self._tardis_sounds(key)
        view = self.scene3d
        if view is None:
            return
        room = self.tardis_page.room if self.tardis_page is not None else None
        page = self.window.jarvis_page
        animate = self._effects_enabled()
        if key == "tardis" and room is not None:
            if room.scene3d is not view:
                if page.central is view:
                    page.set_central(self._placeholder)
                room.attach_scene3d(view)
            view.set_mode("tardis", animate=animate)
        elif key == "jarvis" and (room is None or room.scene3d is view or page.central is self._placeholder):
            if room is not None and room.scene3d is view:
                room.detach_scene3d()
            face = getattr(self.core.settings(), "avatar_mode", "face") == "face"
            page.set_central(view if face else self.view)
            view.set_mode("jarvis", animate=animate)

    def _tardis_sounds(self, key: str) -> None:
        """Portas ao entrar e sair da sala; ambiente da sala só com a página TARDIS à frente."""
        audio = getattr(self.core, "neural_audio", None)
        if audio is None or not hasattr(audio, "door"):
            return
        inside = key == "tardis"
        was_inside = getattr(self, "_in_tardis", False)
        self._in_tardis = inside
        if inside != was_inside:
            audio.door(True)
            QtCore.QTimer.singleShot(1100, lambda: audio.door(False))
        audio.set_room(inside)

    def _make_avatar_2d(self, backend: str):
        """Rosto holográfico 2D: GPU (OpenGL) quando pedido e disponível; senão CPU — e diz por quê."""
        from .avatar.view import AvatarView, create_gl_view
        speaker = self.core.speaker
        sources = {"mouth": speaker.mouth, "caption": speaker.caption, "audible": speaker.audible}
        view = None
        if backend == "gpu":
            try:
                view = create_gl_view(**sources)
                self.avatar_reason = "GPU (OpenGL)"
            except Exception as exc:                          # sem OpenGL: a CPU desenha o mesmo rosto
                self.avatar_reason = f"CPU — OpenGL indisponível: {exc}"
                log.warning("avatar: %s", self.avatar_reason)
        if view is None:
            view = AvatarView(**sources)
            self.avatar_reason = self.avatar_reason or "CPU"
        return view

    def central(self):
        """A vista em uso na página JARVIS (rosto ou núcleo neural)."""
        return self.window.jarvis_page.central

    def _apply_avatar_settings(self, changed: list) -> None:
        settings = self.core.settings()
        if "scene3d" in changed:
            from . import scene3d
            if getattr(settings, "scene3d", "auto") == "auto":
                scene3d.clear_marker()                  # nova tentativa pedida pelo usuário
        if {"render_backend", "scene3d"} & set(changed) and not (self.scene3d is not None and
                                                              getattr(settings, "scene3d", "auto") == "auto"):
            old = self.avatar
            self.avatar_reason = ""
            self.avatar = self._make_avatar(getattr(settings, "render_backend", "cpu"))
            self.avatar.on_state(self.state_cache)
            page = self.window.jarvis_page
            if page.central in (old, self._placeholder):
                page.set_central(self.avatar)
                if self.window.current_key == "tardis":
                    self._page_changed("tardis")
            room = self.tardis_page.room if self.tardis_page is not None else None
            if room is not None and room.scene3d is old:
                room.detach_scene3d()
            if old is not self.avatar:
                if hasattr(old, "dispose"):
                    old.dispose()
                if old is self.scene3d:
                    self.scene3d = None
                old.setParent(None)
                old.deleteLater()
        if "avatar_mode" in changed:
            face = getattr(settings, "avatar_mode", "face") == "face"
            self.window.jarvis_page.set_central(self.avatar if face else self.view)
        if {"performance_profile", "heavy_effects"} & set(changed):
            self.avatar.set_profile(self.profile.name, effects=self._effects_enabled())
            if self.tardis_page is not None:
                self.tardis_page.on_profile(self.profile)
        if "captions" in changed:
            self.avatar.captions_enabled = bool(getattr(settings, "captions", True))

    def _effects_enabled(self) -> bool:
        """Transições holográficas e animações da barra: só com "efeitos pesados" e fora do perfil econômico."""
        return bool(getattr(self.core.settings(), "heavy_effects", True)) and self.profile.name != "economy"

    # ================================================================ páginas (criadas sob demanda)
    def _make_tardis(self):
        from .tardis_room.page import TardisPage
        self.tardis_page = TardisPage(self.core, archive_factory=self._make_archive, profile=self.profile,
                                      effects=self._effects_enabled)
        self.tardis_page.mode_changed.connect(lambda _mode: self.window.refresh_layout())
        self.tardis_page.escape_unhandled.connect(self.escape)
        self.tardis_page.room.escape_first = lambda: self.ultron_stop("Esc")
        return self.tardis_page

    def _make_archive(self):
        """O ARQUIVO da TARDIS (memória espacial), criado na primeira visita."""
        from .tardis import TardisWindow
        self.second = TardisWindow(self.core, state=self.state_cache, profile=self.profile)
        self.second.authorization_decided.connect(lambda ok: self.core.authorizations.resolve(ok, by="tardis"))
        self.second.authorization_always.connect(lambda: self._authorize_always("tardis"))
        self.second.return_requested.connect(lambda: self.tardis_page.show_room())
        self.second.back_button.setText("← SALA DE CONTROLE")
        self.second.back_button.setToolTip("Voltar à sala de controle da TARDIS (o arquivo fica como está)")
        return self.second

    def _make_diagnostics(self):
        from .diagnostics_page import DiagnosticsPanel
        self.systems = DiagnosticsPanel(self.core, state=self.state_cache, profile=self.profile,
                                        events=self.window.event_log)
        self.systems.authorization_decided.connect(lambda ok: self.core.authorizations.resolve(ok, by="sistemas"))
        self.systems.authorization_always.connect(lambda: self._authorize_always("sistemas"))
        return self.systems

    def _make_activity(self):
        from .activity_page import ActivityPage
        self.activity_page = ActivityPage(self.core)
        return self.activity_page

    def _make_settings(self):
        from .settings_page import SettingsPage
        self.settings_page = SettingsPage(self.core)
        self.settings_page.ultron_history = lambda: list(self.ultron.history)
        self.settings_page.ultron_demo.connect(lambda: self.ultron_start("demonstracao"))
        self.settings_page.refresh()
        return self.settings_page

    # ================================================================ ligação com o Core
    def _wire(self) -> None:
        w = self.window
        w.input.submitted.connect(lambda text: self.core.submit(text, source="text"))
        w.input.mic_toggled.connect(self._toggle_mic)
        w.input.voice_toggled.connect(self._toggle_voice)
        w.input.second_brain.connect(lambda: self.open_archive())
        w.input.systems.connect(lambda: self.open_systems())
        w.authorization.decided.connect(lambda ok: self.core.authorizations.resolve(ok, by="hud"))
        w.authorization.always.connect(lambda: self._authorize_always("hud"))
        w.suggestion.decided.connect(lambda ok: self.core.accept_suggestion(ok, by="hud"))
        w.collapse_requested.connect(self.collapse)
        w.second_brain_requested.connect(lambda: self.open_archive())
        w.systems_requested.connect(lambda: self.open_systems())
        w.closing.connect(self._closed_to_tray)
        w.interrupt_requested.connect(self.escape)
        w.stop_requested.connect(self.stop)
        w.conversation_command.connect(lambda text: self.core.submit(text, source="text"))
        w.chip_clicked.connect(self._chip_clicked)
        self.orb.expand_requested.connect(self.expand)
        self.orb.menu_requested.connect(lambda pos: self._menu().exec(pos))
        self.orb.moved.connect(self._orb_moved)

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
                self.avatar.on_event(kind, payload)
                self.window.on_event(kind, payload, stamp)
                for hub in (self.second, self.systems):
                    if hub is not None:
                        hub.on_event(kind, payload)
            except Exception:                               # um evento malformado nunca derruba a interface
                log.exception("falha ao tratar %s na interface", kind)
            if kind == EventType.SYSTEM_READY.value:
                self._load_graph_async()
            elif kind == EventType.REMINDER_DUE.value:
                self._notify(payload)
            elif kind == EventType.NOTIFICATION.value and payload.get("popup") and not payload.get("silent"):
                self._show_message(f"JARVIS · {payload.get('title', '')}", str(payload.get("body", "")))
            elif kind == EventType.SHUTDOWN_REQUESTED.value:
                QtCore.QTimer.singleShot(SHUTDOWN_DELAY_MS, self.quit)    # já confirmado pelo executor
            elif kind == EventType.UI_REQUEST.value:
                self._ui_request(payload)
            elif kind == "TARDIS_STATE" and self.scene3d is not None:
                room = self.tardis_page.room if self.tardis_page is not None else None
                if room is None or room.scene3d is not self.scene3d:      # na sala, a própria sala envia tudo
                    self.scene3d.push_room({"mode": str(payload.get("mode") or "repouso"),
                                            "fault": bool(payload.get("fault")), "available": True})
            if kind in AUTO_EXPAND and not self.window.isVisible() \
                    and getattr(self.core.settings(), "hud_auto_expand", True):
                self.expand()
        if more:
            QtCore.QTimer.singleShot(0, self._drain)

    def _ui_request(self, payload: dict) -> None:
        if payload.get("ultron"):
            action = str(payload["ultron"])
            if action == "stop":
                self.ultron_stop("comando")
            else:
                self.ultron_start("demonstracao" if action == "demo" else "manual")
            return
        view = payload.get("view")
        section = payload.get("section") or None
        if view == "second_brain":
            self.open_archive(section)
        elif view == "tardis":
            self.open_tardis(section)
        elif view in ("systems", "voice", "network", "autonomy", "diagnosticos", "diagnostics"):
            self.open_systems(section or (view if view in ("voice", "network", "autonomy") else None))
        elif view in NAV_KEYS:
            self.open_page(view, section)
        elif view in ("settings", "activity"):
            self.open_page({"settings": "configuracoes", "activity": "atividades"}[view], section)

    def _pull_state(self) -> None:
        with self._dirty_lock:
            names, self._dirty = self._dirty, set()
        if not names:
            return
        self.state_cache.update(self.core.state.subset(names))
        self.scene.on_state(self.state_cache)
        self.avatar.on_state(self.state_cache)
        self.window.on_state(self.state_cache, names)
        for hub in (self.second, self.systems):
            if hub is not None:
                hub.on_state(self.state_cache, names)
        if "pending_authorization" in names:
            pending = self.state_cache.get("pending_authorization")
            active = bool(pending and pending.get("status") == "pending")
            scope = f" [{pending['category_label']}]" if active and pending.get("category_label") else ""
            self.window.authorization.present(
                f"Ação sensível{scope}: {pending.get('description', '')}" if active else None,
                allow_always=bool(pending and pending.get("standing_allowed")))
            self.window.refresh_layout()

    def _pull_telemetry(self) -> None:
        if not (self.window.isVisible() or self.orb.isVisible()):
            return                                        # só a página JARVIS e o orbe mostram níveis de áudio
        telemetry = self.core.telemetry()
        mic = self.core.voice.mic_probe() if self.core.enable_voice else {}
        if self.core.privacy_shield:
            telemetry["mic_state"] = "PRIVACIDADE"
        elif not mic.get("enabled", True):
            telemetry["mic_state"] = "MIC OFF"
        elif mic.get("capturing"):
            telemetry["mic_state"] = "MIC ON"
        else:
            telemetry["mic_state"] = "MIC —"
        telemetry["recognizing"] = bool(mic.get("recognizing"))
        self.scene.on_telemetry(telemetry)
        self.avatar.on_telemetry(telemetry)
        self.window.on_telemetry(telemetry)
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
        self._apply_avatar_settings(changed)
        if "ultron_emergency_key" in changed:
            key = str(getattr(self.core.settings(), "ultron_emergency_key", "") or "Ctrl+Shift+U")
            self.emergency_shortcut.setKey(QtGui.QKeySequence(key))
        if self.settings_page is not None:
            self.settings_page.on_settings_changed(changed)
        self.window.refresh_chips()

    def set_profile(self, name: str) -> None:
        self.profile = quality.get(name)
        self.scene.profile = self.profile
        self._state_timer.setInterval(self.profile.state_ms)
        self._telemetry_timer.setInterval(self.profile.telemetry_ms)
        for hub in (self.second, self.systems, self.tardis_page):
            if hub is not None:
                hub.on_profile(self.profile)

    # ================================================================ relógio
    def _tick(self) -> None:
        now = time.perf_counter()
        dt = now - self._last_tick
        self._last_tick = now
        self.scene.step(dt)
        self._tick_times.append(dt)
        central = self.central()
        hub1 = self.window.isVisible() and not self.window.isMinimized() and central.isVisible()
        shown = self.avatar.isVisible() and ((self.window.isVisible() and not self.window.isMinimized())
                                             or self.orb.scene_view is self.avatar)   # também no ORBE 3D
        if shown:                                         # rosto 2D na página JARVIS, ou a cena 3D (JARVIS ou TARDIS)
            self.avatar.step(dt)
        else:
            self.avatar.update_state()                    # o estado vale mesmo com outra página à frente
        from .avatar.states import SHORT
        resolved = self.avatar.resolved
        if getattr(self, "ultron", None) is not None and self.ultron.active:
            # o estado REAL continua visível (o ULTRON pode estar executando ou aguardando autorização)
            self.window.top.state_chip.set_display(f"ULTRON · {SHORT.get(resolved.key, resolved.label)}",
                                                   (255, 31, 61))
        else:
            self.window.top.state_chip.set_display(SHORT.get(resolved.key, resolved.label), resolved.style.rgb)
        orb = self.orb.isVisible()
        if not (hub1 or orb):
            wanted = self.profile.hidden_interval_ms      # nada visível: a cena segue coerente, sem desenho
            self.target_fps = 0
        else:
            moving = self.avatar.in_motion() if central is self.avatar else self.scene.in_motion()
            fps = quality.effective_fps(self.profile, self._hud_fps(), active=moving,
                                        background=self._tardis_in_front())
            if getattr(central, "paint_count", 0) != self._painted and getattr(central, "frame_times", None):
                self._painted = central.paint_count
                last = central.frame_times[-1]
                self._paint_ema = last if not self._paint_ema else self._paint_ema * 0.85 + last * 0.15
            cpu = (self.state_cache.get("telemetry") or {}).get("cpu")
            budget = PAINT_BUDGET_LOADED if isinstance(cpu, (int, float)) and cpu > 85 else PAINT_BUDGET
            if self._paint_ema > 0:
                fps = min(fps, max(self.profile.idle_fps, int(budget / self._paint_ema)))
            self.target_fps = fps
            wanted = max(7, int(1000 / fps))
            if hub1:
                central.update()
            if orb:
                self.orb.update()
        if self._frame.interval() != wanted:
            self._frame.setInterval(wanted)
        if len(self._tick_times) >= 30:
            self.frame_rate = len(self._tick_times) / max(1e-6, sum(self._tick_times))

    def _tardis_in_front(self) -> bool:
        """O TARDIS ficou numa janela separada e em foco (não acontece com a plataforma, onde ele é uma
        página: com o TARDIS à frente a vista do JARVIS nem é desenhada)."""
        second = self.second
        return bool(second is not None and second.isWindow() and second.isVisible() and second.isActiveWindow()
                    and not self.window.isActiveWindow())

    def _heartbeat(self) -> None:
        """Atraso do laço de eventos da interface: o quanto um temporizador de 200 ms atrasou."""
        now = time.perf_counter()
        lag = max(0.0, now - self._last_beat - 0.2)
        self._last_beat = now
        metrics = getattr(self.core, "metrics", None)
        if metrics is None:
            return
        metrics.record("ui.lag", lag)
        frames = list(getattr(self.central(), "frame_times", ()))[-30:]
        for value in frames[-min(len(frames), max(1, int(self.target_fps * 0.2) or 1)):]:
            metrics.record("ui.frame", value)
        metrics.gauge("ui.fps", round(self.frame_rate, 1))
        metrics.gauge("ui.target_fps", self.target_fps)
        metrics.gauge("ui.profile", self.profile.name)
        metrics.gauge("ui.events_dropped", self.dropped_events)
        metrics.gauge("ui.inbox", len(self._inbox))
        metrics.gauge("ui.page", self.window.current_key)
        tardis_open = bool(self.second is not None and self.second.isVisible())
        metrics.gauge("ui.tardis_open", tardis_open)
        if tardis_open:
            metrics.gauge("ui.tardis_fps", self.second.target_fps)
            for value in list(self.second.view.frame_times)[-5:]:
                metrics.record("ui.tardis_frame", value)
        room = self.tardis_page.room if self.tardis_page is not None else None
        room_open = bool(room is not None and room.isVisible())
        metrics.gauge("ui.tardis_room_open", room_open)
        if room_open:
            metrics.gauge("ui.tardis_room_fps", room.target_fps)
            for value in list(room.view.frame_times)[-5:]:
                metrics.record("ui.tardis_room_frame", value)

    def health(self) -> dict:
        visible = self.window.isVisible() or self.orb.isVisible()
        if not self.frame_rate:
            return {"status": "OK", "detail": "medindo taxa de quadros"}
        paint = self._paint_ema * 1000
        view = ("cena 3D" if self.scene3d is not None else "rosto holográfico") if self.central() in (
            self.avatar, self._placeholder) else "núcleo neural"
        detail = f"{self.frame_rate:.0f} quadros/s (alvo {self.target_fps}) · pintura {paint:.1f} ms · " \
                 f"perfil {self.profile.name} · página {self.window.current_key} · {view} ({self.avatar_reason})"
        scene = self.scene3d
        if scene is not None and scene.stats.get("fps"):        # quadros medidos pela própria página 3D
            detail += f" · cena 3D {scene.stats['fps']} q/s (alvo {scene.stats.get('target')}, " \
                      f"redução {scene.stats.get('level', 0)})"
        elif self.scene3d_reason:
            detail += f" · cena 3D não usada: {self.scene3d_reason}"
        lag = getattr(self.core, "metrics", None)
        lag_stats = lag.stats("ui.lag") if lag is not None else {}
        slow = lag_stats.get("n", 0) >= 10 and lag_stats.get("p95", 0) > 0.25
        return {"status": "WARN" if slow and visible else "OK", "detail": detail + ("" if visible else " · oculto")}

    # ================================================================ janela e páginas
    def show(self, *, minimized: bool = False) -> None:
        start = getattr(self.core.settings(), "start_page", "jarvis")
        if start in NAV_KEYS and start != self.window.current_key:
            self.window.navigate(start, animate=False)
        if minimized:
            self.collapse()
        else:
            self.window.show()
            self.window.raise_()
            self.window.focus_input()

    def expand(self) -> None:
        self.orb.hide()
        self._return_scene_from_orb()
        self.window.showNormal() if self.window.isMinimized() else self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        self.window.focus_input()

    def collapse(self) -> None:
        self.window.hide()
        if not self.orb.isVisible():
            self._lend_scene_to_orb()
            if self.orb.pos() == QtCore.QPoint(0, 0):
                self._place_orb()
            self.orb.show()

    def _lend_scene_to_orb(self) -> None:
        """ORBE 3D minimizado: a MESMA cena (um motor) vai para a janela flutuante, em modo compacto. Sem cena
        pronta, o orbe 2D de sempre."""
        view = self.scene3d
        if view is None or not view.is_ready or self.orb.scene_view is view:
            return
        room = self.tardis_page.room if self.tardis_page is not None else None
        if room is not None and room.scene3d is view:
            room.detach_scene3d()
        page = self.window.jarvis_page
        if page.central is view:
            page.set_central(self._placeholder)
        self.orb.attach_scene(view)
        view.set_compact(True)

    def _return_scene_from_orb(self) -> None:
        view = self.orb.detach_scene() if self.orb.scene_view is not None else None
        if view is None:
            return
        view.set_compact(False)
        room = self.tardis_page.room if self.tardis_page is not None else None
        if self.window.current_key == "tardis" and room is not None:
            room.attach_scene3d(view)
        else:
            face = getattr(self.core.settings(), "avatar_mode", "face") == "face"
            self.window.jarvis_page.set_central(view if face else self.view)

    def _place_orb(self) -> None:
        """Onde o usuário deixou o orbe da última vez (se ainda estiver numa tela), senão no canto."""
        saved = tuple(getattr(self.core.settings(), "orb_position", ()) or ())
        if len(saved) == 2:
            point = QtCore.QPoint(int(saved[0]), int(saved[1]))
            if any(screen.availableGeometry().contains(point) for screen in QtGui.QGuiApplication.screens()):
                self.orb.move(point)
                return
        self.orb.place_default()

    def _orb_moved(self, point: QtCore.QPoint) -> None:
        try:
            self.core.settings_manager.update(orb_position=[point.x(), point.y()])
        except Exception:
            log.debug("posição do orbe não gravada", exc_info=True)

    def open_page(self, key: str, section: str | None = None):
        """Mostra a janela e navega até o módulo (a página é criada na primeira visita)."""
        if not self.window.isVisible() or self.window.isMinimized():
            self.expand()
        page = self.window.navigate(key)
        if page is not None and not page.isVisible() and self.window.isVisible():
            page.show()                                  # alguém escondeu a página dentro da janela
        if section and page is not None and hasattr(page, "show_section"):
            page.show_section(section)
        return page

    def open_tardis(self, section: str | None = None):
        """Abre a TARDIS como estava (sala ou ARQUIVO); com seção, vai ao painel da sala ou à região do
        ARQUIVO. Voltar ao JARVIS só troca de página: câmera, painel, região e filtros ficam."""
        return self.open_page("tardis", section)

    def open_archive(self, section: str | None = None):
        """O ARQUIVO da TARDIS: a memória pessoal como espaço navegável (o antigo HUB 2)."""
        page = self.open_page("tardis")
        if page is not None and hasattr(page, "show_archive"):
            page.show_archive(section)
        return self.second

    open_second_brain = open_archive                # nome antigo (compatibilidade)

    def return_to_core(self) -> None:
        self.window.navigate("jarvis")
        self.expand()

    def open_systems(self, section: str | None = None) -> None:
        """DIAGNÓSTICOS: voz, rede local, autonomia, desempenho e saúde, eventos, log, serviços e GPU."""
        self.open_page("diagnosticos")
        if self.systems is not None:
            self.systems.show_section(section)

    def _closed_to_tray(self) -> None:
        if self.tray is None:
            self.quit()
        elif not self.orb.isVisible():
            if self.orb.pos() == QtCore.QPoint(0, 0):
                self._place_orb()
            self.orb.show()

    def _authorize_always(self, by: str) -> None:
        """SEMPRE: aprova e cria a autorização permanente escopada (24 h) — o núcleo recusa a parte
        permanente se o pedido não for elegível e aprova só esta vez."""
        from ..agent.autonomy import STANDING_DEFAULT
        self.core.authorizations.resolve(True, by=by, remember=STANDING_DEFAULT)

    def _toggle_mic(self, enabled: bool) -> None:
        if not self.core.enable_voice:
            return
        if enabled and self.core.privacy_shield:
            self.window.input.mic.blockSignals(True)
            self.window.input.mic.setChecked(False)          # o modo privacidade manda: microfone fechado
            self.window.input.mic.blockSignals(False)
            self.window.conversation.add_system("modo privacidade ativo: saia dele para ligar o microfone",
                                                alert=True)
            return
        self.core.voice.toggle_mic(enabled)

    def _toggle_voice(self, enabled: bool) -> None:
        self.core.speaker.muted = not enabled
        if not enabled:
            self.core.speaker.interrupt()

    # ================================================================ Esc, PARAR e indicadores
    def escape(self) -> str:
        """Esc como no original: interrompe a fala; senão cancela o pedido em andamento (ou a autorização
        pendente); senão sai da tela cheia. Nunca minimiza. Devolve o que foi feito. Com o Protocolo ULTRON
        ativo, Esc primeiro restaura o JARVIS."""
        if self.ultron.active:
            self.ultron_stop("Esc")
            return "ultron"
        if self.core.speaker.speaking:
            self.core.speaker.interrupt()
            return "speech"
        if self.core.busy or self.core.authorizations.pending() is not None:
            self.core.cancel("cancelado pelo usuário (Esc)")
            self.window.conversation.add_system("cancelado (Esc)")
            return "cancel"
        if self.window.isFullScreen():
            self.window.showNormal()
            return "fullscreen"
        return ""

    def stop(self) -> None:
        """PARAR (conversa): cancela pedido, fala e autorização pendente."""
        cancelled = self.core.cancel("cancelado pelo usuário (PARAR)")
        self.window.conversation.add_system("cancelado" if cancelled else "não havia nada em andamento")

    # ================================================================ Protocolo ULTRON (evento visual)
    def _ultron_guard(self):
        from .ultron_protocol import Guard
        state = self.state_cache
        return Guard(runtime_state=str(state.get("runtime_state") or "IDLE"),
                     authorization_pending=self.core.authorizations.pending() is not None,
                     action_running=bool(state.get("current_action")),
                     privacy=bool(getattr(self.core, "privacy_shield", False)),
                     idle_seconds=time.time() - float(getattr(self.core, "_last_interaction", time.time())))

    def _ultron_operator_for(self, source: str) -> bool:
        s = self.core.settings()
        if source == "manual":
            return bool(getattr(s, "ultron_operator", True))
        if source == "ocasional":
            return bool(getattr(s, "ultron_operator_occasional", False))
        return False                                   # demonstração: só identidade

    def ultron_start(self, source: str = "manual") -> bool:
        ok, reason = self.ultron.start(source, self._ultron_guard())
        if not ok:
            self.window.conversation.add_system(f"Protocolo ULTRON não iniciado: {reason}.")
            return False
        self._ultron_apply(True, source)
        return True

    def ultron_stop(self, by: str) -> bool:
        if not self.ultron.stop(by):
            return False
        self._ultron_apply(False, by)
        return True

    def ultron_emergency(self) -> None:
        """Tecla de emergência: restaura o JARVIS e interrompe o que estiver em curso (tarefa, autorização, fala)."""
        if self.ultron.active:
            self.ultron_stop("tecla de emergência")
        self.core.cancel("tecla de emergência do Protocolo ULTRON")

    def _ultron_tick(self) -> None:
        if self.ultron.active:
            if self.ultron.expired():
                self.ultron_stop("tempo")
        elif self.ultron.maybe_trigger(self._ultron_guard()):
            self._ultron_apply(True, "ocasional")

    def _ultron_apply(self, on: bool, source: str) -> None:
        """Identidade completa: persona no núcleo (voz, tom, perfil ULTRON_OPERATOR), cores, marca, título, orbe,
        cena 3D, uma linha na conversa e no histórico. Ao sair, tudo volta como estava."""
        from .ultron_protocol import LABEL, LABEL_OPERATOR, MESSAGES, OPERATOR_MESSAGES
        app = QtWidgets.QApplication.instance()
        brand = self.window.top.brand
        operator = on and self._ultron_operator_for(source)
        label = LABEL_OPERATOR if operator else LABEL
        messages = OPERATOR_MESSAGES if operator else MESSAGES
        if hasattr(self.core, "set_persona"):            # o fim por tempo não corta uma tarefa no meio
            self.core.set_persona("ultron" if on else "jarvis", operator=operator, source=source,
                                  interrupt=source not in ("tempo", "encerramento"))
        if on:
            self._ultron_saved = {"style": app.styleSheet() if app is not None else None,
                                  "identity": self.window.identity,
                                  "brand": (brand.title, brand.subtitle, QtGui.QColor(brand.color)),
                                  "panels": [(w, w.styleSheet()) for w in self.window.findChildren(QtWidgets.QWidget)
                                             if w.styleSheet()]}
            if app is not None:
                app.setStyleSheet(theme.ultron_stylesheet(self._ultron_saved["style"]))
            for widget, style in self._ultron_saved["panels"]:      # os painéis também "mudam de dono"
                widget.setStyleSheet(theme.ultron_stylesheet(style))
            self.window.identity = "U.L.T.R.O.N."
            self.window.refresh_title()
            self.window.set_escape_override(True)       # Esc restaura o JARVIS em qualquer página
            brand.title, brand.subtitle, brand.color = "U.L.T.R.O.N.", \
                ("PERFIL ULTRON_OPERATOR" if operator else "PROTOCOLO ULTRON"), QtGui.QColor(theme.ERROR)
            text = f"PROTOCOLO ULTRON INICIADO — {label}."
        else:
            saved, self._ultron_saved = self._ultron_saved, None
            if saved is not None:
                if app is not None and saved["style"] is not None:
                    app.setStyleSheet(saved["style"])
                self.window.identity = saved["identity"]
                self.window.refresh_title()
                for widget, style in saved["panels"]:
                    try:
                        widget.setStyleSheet(style)
                    except RuntimeError:                   # painel fechado durante o evento
                        pass
                brand.title, brand.subtitle, brand.color = saved["brand"]
            self.window.set_escape_override(False)
            text = f"JARVIS restaurado ({source})."
            page = getattr(self, "settings_page", None)
            if page is not None:
                page.refresh()                         # histórico de ocorrências atualizado
        brand.update()
        self.orb.ultron = on
        self.orb.update()
        if self.scene3d is not None:
            self.scene3d.set_ultron(on, source=source, messages=messages, label=label)
        self.window.conversation.add_system(text)
        activity = getattr(self.core, "activity", None)
        if activity is not None:
            activity.record("sistema", ("Protocolo ULTRON iniciado" + (" — perfil ULTRON_OPERATOR" if operator
                                                                        else " — só identidade")) if on
                            else "Protocolo ULTRON encerrado — JARVIS restaurado", origin="hud", result=source)

    def _chip_clicked(self, key: str) -> None:
        if key == "mic":
            if self.core.privacy_shield:
                self._privacy_menu().exec(QtGui.QCursor.pos())
            else:
                self.window.input.mic.toggle()
        elif key == "tts":
            self.window.input.voice.toggle()
        elif key == "ai":
            self.open_page("configuracoes", "ia")
        elif key == "net":
            self.open_systems("network")
        elif key == "obs":
            self._observer_menu().exec(QtGui.QCursor.pos())
        elif key == "session":
            self.open_page("configuracoes", "privacidade")

    def _observer_menu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self.window)
        self._fill_observer_menu(menu)
        return menu

    def _fill_observer_menu(self, menu: QtWidgets.QMenu) -> QtWidgets.QMenu:
        """Modos do Observador e pausa (barra de automação do original), relidos do estado real."""
        menu.clear()
        observer = self.state_cache.get("observer")
        if not isinstance(observer, dict):
            observer = {}            # antes do boot o núcleo ainda não publicou o Observador: vale a configuração
        mode = observer.get("mode") or getattr(self.core.settings(), "observer_mode", "off")
        group = QtGui.QActionGroup(menu)
        for value, label in (("off", "Desligado"), ("assistant", "Assistente (sugere na tela)"),
                             ("observer", "Observador (sugere e fala)")):
            action = menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(mode == value)
            action.setActionGroup(group)
            action.triggered.connect(lambda _=False, v=value: self._observer(v))
        menu.addSeparator()
        if observer.get("paused"):
            menu.addAction("Retomar o Observador", lambda: self._observer("resume"))
        else:
            pause = menu.addAction("Pausar o Observador", lambda: self._observer("pause"))
            pause.setEnabled(mode != "off")
        return menu

    def _privacy_menu(self) -> QtWidgets.QMenu:
        menu = QtWidgets.QMenu(self.window)
        if self.core.privacy_shield:
            menu.addAction("Sair do modo privacidade (liberar o microfone)", lambda: self._privacy(False))
        else:
            menu.addAction("Entrar no modo privacidade (fechar o microfone)", lambda: self._privacy(True))
        return menu

    def _observer(self, action: str) -> None:
        response = self.core.set_observer(action)
        self.window.conversation.add_system(response.text)
        self.window.refresh_chips()

    def _privacy(self, active: bool) -> None:
        response = self.core.set_privacy_shield(active, by="interface")
        self.window.conversation.add_system(response.text, alert=active)
        if self.core.enable_voice:
            self.window.input.mic.blockSignals(True)
            self.window.input.mic.setChecked(self.core.voice.mic_enabled)
            self.window.input.mic.blockSignals(False)
        self.window.refresh_chips()

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
        bandeja; sem bandeja, o aviso fica na central de notificações do TARDIS e na fala."""
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
        menu = self._menu()
        tray.setContextMenu(menu)
        self._tray_menu = menu
        tray.activated.connect(lambda reason: self.expand()
                               if reason in (QtWidgets.QSystemTrayIcon.Trigger,
                                             QtWidgets.QSystemTrayIcon.DoubleClick) else None)
        tray.messageClicked.connect(lambda: self.open_tardis("notifications"))
        tray.show()
        return tray

    def _menu(self) -> QtWidgets.QMenu:
        """Menu da bandeja e do orbe. As marcações são relidas a cada abertura (estado real)."""
        menu = QtWidgets.QMenu()
        header = menu.addAction("J.A.R.V.I.S.")
        header.setEnabled(False)
        menu.addAction("Abrir o JARVIS", lambda: self.open_page("jarvis"))
        for key, label in (("tardis", "TARDIS — segundo cérebro"),
                           ("atividades", "Atividades"), ("configuracoes", "Configurações"),
                           ("diagnosticos", "Diagnósticos")):
            menu.addAction(label, lambda k=key: self.open_page(k))
        menu.addAction("Diagnóstico de voz", lambda: self.open_systems("voice"))
        menu.addAction("Orbe compacto", self.collapse)
        menu.addSeparator()
        mic = menu.addAction("Microfone")
        mic.setCheckable(True)
        mic.toggled.connect(lambda on: self.window.input.mic.setChecked(on))
        voice = menu.addAction("Voz do JARVIS")
        voice.setCheckable(True)
        voice.toggled.connect(lambda on: self.window.input.voice.setChecked(on))
        restart = menu.addAction("Reiniciar voz", self._restart_voice)
        privacy = menu.addAction("Modo privacidade (microfone fechado)")
        privacy.setCheckable(True)
        privacy.triggered.connect(lambda on: self._privacy(bool(on)))
        observer_menu = menu.addMenu("Observador")
        startup = menu.addAction("Iniciar com o Windows")
        startup.setCheckable(True)
        startup.triggered.connect(self._toggle_startup)
        profiles = menu.addMenu("Qualidade visual")
        group = QtGui.QActionGroup(profiles)
        profile_actions = {}
        for name in quality.NAMES:
            action = profiles.addAction(quality.LABELS[name])
            action.setCheckable(True)
            action.setActionGroup(group)
            action.triggered.connect(lambda _=False, n=name: self.core.settings_manager.update(performance_profile=n))
            profile_actions[name] = action
        menu.addAction("Diagnóstico", self.show_diagnostics)
        menu.addSeparator()
        menu.addAction("Sair", self.quit)

        def sync() -> None:                           # estado real a cada abertura do menu
            from ..platform import autostart
            for action, value in ((mic, self.core.voice.mic_enabled if self.core.enable_voice else False),
                                  (voice, not self.core.speaker.muted), (privacy, bool(self.core.privacy_shield))):
                action.blockSignals(True)
                action.setChecked(bool(value))
                action.blockSignals(False)
            mic.setEnabled(self.core.enable_voice and not self.core.privacy_shield)
            restart.setEnabled(self.core.enable_voice and not self.core.privacy_shield)
            startup.blockSignals(True)
            startup.setChecked(autostart.is_enabled())
            startup.blockSignals(False)
            startup.setEnabled(autostart.supported())
            startup.setToolTip("" if autostart.supported() else "disponível apenas no Windows")
            for name, action in profile_actions.items():
                action.setChecked(self.profile.name == name)
            self._fill_observer_menu(observer_menu)

        menu.aboutToShow.connect(sync)
        sync()
        return menu

    def _restart_voice(self) -> None:
        if not self.core.enable_voice or self.core.privacy_shield:
            return
        threading.Thread(target=self.core.voice.restart, name="ultron-voice-restart", daemon=True).start()
        self.window.conversation.add_system("reiniciando a voz (captura e reconhecimento)")

    def _toggle_startup(self, on: bool) -> None:
        """Pedido explícito do usuário (clique). Se o Registro recusar, a marcação volta (como no original)."""
        from ..platform import autostart
        try:
            (autostart.enable if on else autostart.disable)()
            self.core.settings_manager.update(startup=bool(on))
            self._show_message("JARVIS", autostart.check()["text"])
        except OSError as exc:
            self._show_message("JARVIS · início automático", f"Não foi possível alterar: {exc}")

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
        if self.ultron.active:
            self.ultron.stop("encerramento")
        if self.scene3d is not None:
            self.scene3d.dispose()                      # sem relatórios tardios; o marcador de abertura sai
        self.window.shutdown()                          # para relógios e leitores de todas as páginas
        self.window.hide()
        self.orb.hide()
        if self.tray is not None:
            self.tray.hide()
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.quit()


_QT_LEVELS = {QtCore.QtMsgType.QtDebugMsg: logging.DEBUG, QtCore.QtMsgType.QtInfoMsg: logging.DEBUG,
              QtCore.QtMsgType.QtWarningMsg: logging.INFO, QtCore.QtMsgType.QtCriticalMsg: logging.ERROR,
              QtCore.QtMsgType.QtFatalMsg: logging.CRITICAL}


def log_qt_messages() -> None:
    """Mensagens do Qt vão para o registro do JARVIS. Sem console (pythonw) elas se perderiam — inclusive a
    fatal (plataforma gráfica que não carrega), que o Qt emite pouco antes de encerrar o processo."""
    qt_log = logging.getLogger("ultron.qt")

    def handler(kind, _context, message) -> None:
        qt_log.log(_QT_LEVELS.get(kind, logging.INFO), "%s", message)

    QtCore.qInstallMessageHandler(handler)


def run_hud(core, *, minimized: bool = False, boot: bool = True) -> int:
    """Cria a interface, inicia o Core em segundo plano e roda o laço do Qt."""
    from . import theme

    log_qt_messages()
    from .scene3d import prepare_qt
    prepare_qt()                                           # antes da QApplication: exigência do QtWebEngine
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setApplicationName("JARVIS")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(app_icon())
    log.info("interface: Qt %s, plataforma %s, bandeja do sistema %s", QtCore.qVersion(), app.platformName(),
             "disponível" if QtWidgets.QSystemTrayIcon.isSystemTrayAvailable() else "indisponível")
    controller = HudController(core)
    controller.show(minimized=minimized)
    log.info("interface aberta%s", " (recolhida no orbe)" if minimized else "")
    from ..platform import control
    # Pedidos antigos já foram descartados no registro do processo (control.register). Um --stop ou um
    # "mostrar" que chegue ENQUANTO a janela monta vale: apagá-lo aqui fazia o --stop se perder.
    control.set_mode("janela")

    def watch_requests() -> None:                          # pedidos de outra abertura ou da linha de comando
        if control.stop_requested():                       # --stop: saída normal
            control.clear_stop_request()
            controller.quit()
        elif control.show_requested():                     # START_JARVIS.bat de novo: a janela aparece
            control.clear_show_request()
            controller.expand()

    stop_watch = QtCore.QTimer(controller)
    stop_watch.timeout.connect(watch_requests)
    stop_watch.start(1000)
    if boot:
        threading.Thread(target=core.boot, name="ultron-boot", daemon=True).start()
    app.aboutToQuit.connect(core.shutdown)
    QtGui.QGuiApplication.setQuitOnLastWindowClosed(False)
    return app.exec()
