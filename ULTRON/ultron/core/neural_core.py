"""NEURAL CORE — o JARVIS montado.

Responsabilidades:

* construir cada componente com suas dependências (nenhum módulo cria outro por conta própria);
* registrar tudo no ``LifecycleManager`` (boot em ordem, falha isolada, parada em ordem inversa);
* ser a **entrada única** de pedidos (texto da HUD, voz, console) e a **saída única** de
  respostas (``RESPONSE_READY`` + fala);
* rotear respostas de autorização ("sim"/"não"), sugestões proativas e cancelamento;
* agendar a manutenção: saúde, consolidação da memória, decaimento do grafo, varredura da
  rede local, privacidade e Dream Mode (só em repouso);
* ligar o SECOND BRAIN (registros, lembretes, captura automática e esclarecimentos) ao mesmo
  caminho de execução usado por voz, texto e HUB 2 (``run_skill``).

Toda inferência roda no worker ``ai``; a interface nunca espera por nada daqui.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from .. import __version__
from ..agent.autonomy import AuthorizationManager, AutonomyPolicy, classify_reply
from ..agent.execution import Action, ExecutionEngine
from ..agent.permissions import PermissionPolicy
from ..agent.recovery import RecoveryEngine
from ..agent.verification import VerificationEngine
from .activity import ActivityLog
from ..audio.neural_audio import NeuralAudio
from ..cognition.context_engine import ContextEngine
from ..cognition.decision_engine import DecisionEngine
from ..cognition.goal_manager import GoalManager
from ..cognition.intent_engine import IntentEngine
from ..cognition.planner_engine import PlannerEngine
from ..cognition.reasoning_engine import ReasoningEngine
from ..cognition.types import Command, Intent
from ..config import paths
from ..config import settings as settings_module
from ..health.monitor import HealthMonitor
from ..imagination.imagination_core import ImaginationCore
from ..memory.system import MemorySystem
from ..models.ollama_client import OllamaClient
from ..models.router import ModelRouter
from ..network.world_integration import NetworkIntelligence
from ..perception.engine import PerceptionEngine
from ..personality import dialogue
from ..personality import identity
from ..plugins.base import PluginContext
from ..plugins.manager import PluginManager
from ..privacy.privacy_mode import PrivacyPolicy
from ..proactive.intelligence import ProactiveIntelligence
from ..secondbrain import Capture, CaptureResult, ReminderScheduler, SecondBrainService, confirmation_text
from ..skills.base import SkillContext
from ..skills.registry import SkillRegistry, load_builtin
from ..voice.audio import AudioOutput
from ..voice.processor import VoicePipeline
from ..voice.tts import Speaker
from ..world.world_model import WorldModel
from .event_bus import EventBus
from .events import EventType
from .lifecycle import LifecycleManager
from .metrics import PerformanceMonitor
from .orchestrator import Orchestrator, Response
from .runtime import CancellationToken, CancelledError, WorkerPool
from .state import StateStore

log = logging.getLogger("ultron.core")

SUGGESTION_TTL = 90.0
PENDING_TTL = 120.0              # esclarecimento do Second Brain ("às 3 da manhã ou às 15?") aguardando resposta
TOPIC_TTL = 15 * 60.0            # "anote essa ideia" / "lembre-me disso" olham até 15 min para trás
REMINDING_SECONDS = 8.0
IDLE_STATES = ("IDLE", "LISTENING", "SPEAKING")


class Service:
    """Adaptador de ciclo de vida para partes sem start/stop próprios."""

    def __init__(self, name: str, *, start: Callable[[], None] | None = None, stop: Callable[[], None] | None = None,
                 health: Callable[[], dict] | None = None, critical: bool = False):
        self.name = name
        self._start, self._stop, self._health = start, stop, health
        self.critical = critical

    def start(self) -> None:
        if self._start:
            self._start()

    def stop(self) -> None:
        if self._stop:
            self._stop()

    def health(self) -> dict:
        return self._health() if self._health else {"status": "OK", "detail": ""}


class NeuralCore:
    def __init__(self, settings_manager=None, *, voice: bool = True, perception: bool = True, plugins: bool = True,
                 audio_output: AudioOutput | None = None, ollama_client: OllamaClient | None = None,
                 hud_probe: Callable[[], bool] | None = None, memory_db=None):
        self.settings_manager = settings_manager or settings_module.manager()
        self.settings = lambda: self.settings_manager.settings
        self.enable_voice = voice
        self.enable_perception = perception
        self.enable_plugins = plugins
        self.hud_probe = hud_probe or (lambda: False)
        self.hud_health: Callable[[], dict] | None = None
        self.started_at = 0.0
        self.booted = False
        self._lock = threading.RLock()
        self._token: CancellationToken | None = None
        self._dream_token: CancellationToken | None = None
        self._pending_capture: dict | None = None
        self._topic: tuple[str, float] | None = None
        self._reminding_until = 0.0
        self._suggestion: dict | None = None
        self._last_interaction = time.time()
        self._memory_check = (0.0, {"status": "UNKNOWN", "detail": ""})
        self.observer_paused = False        # Observador pausado (capturas suspensas; análises em voo descartadas)
        self.privacy_shield = False         # modo privacidade: microfone fechado e observação suspensa
        self._shield_since = 0.0
        self._shield_restore_mic = True
        self._build(audio_output, ollama_client, memory_db)

    # ================================================================ montagem
    def _build(self, audio_output, ollama_client, memory_db) -> None:
        s = self.settings
        self.bus = EventBus()
        self.state = StateStore(self.bus)
        self.runtime = WorkerPool(WorkerPool.NAMES + ("health", "actions"))
        self.lifecycle = LifecycleManager(self.bus)
        self.metrics = PerformanceMonitor(bus=self.bus, runtime=self.runtime)
        self.state.update(_source="core", identity={**identity.describe(), "version": __version__})

        self.privacy = PrivacyPolicy(s, bus=self.bus, state=self.state)
        self.memory = MemorySystem(memory_db, bus=self.bus, state=self.state)
        self.world = WorldModel(bus=self.bus, state=self.state)
        self.client = ollama_client or OllamaClient(s().ollama_url, timeout=s().llm_timeout,
                                                    local_only=lambda: self.privacy.local_mode)
        self.client.metrics = self.metrics
        self.router = ModelRouter(self.client, settings_getter=s, bus=self.bus, state=self.state, privacy=self.privacy)
        from ..models.openai_provider import OpenAIProvider
        self.openai = OpenAIProvider(s, privacy=self.privacy)
        self.router.register_provider("openai", self.openai)
        self.network = NetworkIntelligence(db=self.memory.db, settings_getter=s, bus=self.bus, state=self.state,
                                           world=self.world, graph=self.memory.graph, privacy=self.privacy)
        # SECOND BRAIN — memória pessoal, lembretes e captura (HUB 2, voz e texto usam esta mesma camada)
        self.second_brain = SecondBrainService(self.memory.db, bus=self.bus, state=self.state, settings_getter=s,
                                               graph=self.memory.graph)
        self.reminders = ReminderScheduler(self.second_brain, bus=self.bus, state=self.state, settings_getter=s,
                                           announce=self._announce_reminder)
        self.capture = Capture(self.second_brain, settings_getter=s)
        self.registry = load_builtin(SkillRegistry())
        self.authorizations = AuthorizationManager(bus=self.bus, state=self.state,
                                                   timeout_getter=lambda: s().authorization_timeout,
                                                   store_path=paths.data_file("autorizacoes_permanentes.json"))
        self.autonomy = AutonomyPolicy(s)
        self.permissions = PermissionPolicy(s)
        # histórico de atividades (mesmo banco SQLite): pedidos, ações, verificações, lembretes e falhas
        self.activity = ActivityLog(self.memory.db, bus=self.bus, settings_getter=s)
        self.activity.attach()
        self.imagination = ImaginationCore(router=self.router, memory=self.memory, bus=self.bus, state=self.state,
                                           privacy=self.privacy, settings_getter=s)
        # voz
        self.audio_out = audio_output or AudioOutput()
        self.speaker = Speaker(self.audio_out, bus=self.bus, state=self.state, settings_getter=s)
        self.intents = IntentEngine(automations=self.memory.procedural.automation_for,
                                    wake_words=lambda: tuple(s().wake_words), recent_topic=self._recent_topic)
        self.voice = VoicePipeline(bus=self.bus, state=self.state, settings_getter=s, speaker=self.speaker,
                                   on_command=self._on_voice_command, command_check=self._looks_like_command)
        self.voice.privacy_guard = lambda: self.privacy_shield
        self.neural_audio = NeuralAudio(self.audio_out, bus=self.bus, state=self.state, settings_getter=s)
        # percepção
        self.perception = PerceptionEngine(settings_getter=s, runtime=self.runtime, bus=self.bus, state=self.state,
                                           world=self.world, memory=self.memory, router=self.router,
                                           network=self.network, hud_probe=lambda: self.hud_probe(),
                                           mic_probe=self.voice.mic_probe, observation_block=self.observation_block)
        self.perception.metrics = self.metrics
        # agente e cognição
        self.executor = ExecutionEngine(self.registry, autonomy=self.autonomy, authorizations=self.authorizations,
                                        context_factory=self._skill_context, bus=self.bus, state=self.state,
                                        audit=self.memory.db.audit, permissions=self.permissions,
                                        activity=self.activity)
        self.verifier = VerificationEngine(self.registry, bus=self.bus, state=self.state)
        self.recovery = RecoveryEngine(bus=self.bus, state=self.state)
        self.goals = GoalManager(self.memory.db, bus=self.bus, state=self.state)
        self.context = ContextEngine(memory=self.memory, world=self.world, perception=self.perception)
        self.reasoning = ReasoningEngine(self.router, self.context, settings_getter=s, state=self.state)
        self.planner = PlannerEngine(self.registry, reasoning=self.reasoning, memory=self.memory, bus=self.bus,
                                     state=self.state)
        self.decisions = DecisionEngine()
        self.orchestrator = Orchestrator(
            bus=self.bus, state=self.state, memory=self.memory, goals=self.goals, intents=self.intents,
            decisions=self.decisions, context=self.context, reasoning=self.reasoning, planner=self.planner,
            executor=self.executor, verifier=self.verifier, recovery=self.recovery, registry=self.registry,
            router=self.router, control=self._control, imagine=self._imagine, progress=self._progress)
        self.proactive = ProactiveIntelligence(bus=self.bus, state=self.state, decisions=self.decisions,
                                               settings_getter=s)
        self.health = HealthMonitor(bus=self.bus, state=self.state, model_probe=self._running_models)
        self.plugins = PluginManager(context_factory=self._plugin_context, settings_getter=s)
        self._register_health_probes()
        self._register_components()
        self.bus.subscribe(EventType.INSIGHT, self._on_insight, name="core.insight")
        self.bus.subscribe(EventType.WAKE_WORD, self._on_wake, name="core.wake")
        self.settings_manager.on_change(self._on_settings_changed)

    def _register_components(self) -> None:
        L = self.lifecycle
        L.register(self.metrics)
        L.register(self.privacy)
        L.register(self.memory)
        L.register(self.world, depends_on=("memory",))
        L.register(Service("models", start=self._start_models, health=self._models_health), depends_on=("privacy",))
        L.register(self.goals, depends_on=("memory",))
        L.register(self.second_brain, depends_on=("memory",))
        L.register(self.reminders, depends_on=("second_brain",))
        L.register(self.network, depends_on=("memory", "world_model", "privacy"))
        L.register(Service("skills", health=lambda: {"status": "OK", "detail": f"{len(self.registry.available())}"
                                                                            f"/{len(self.registry)} disponíveis"}))
        L.register(Service("agent", health=lambda: {"status": "OK", "detail": f"autonomia {self.autonomy.level}"}),
                   depends_on=("skills", "memory"))
        L.register(self.imagination, depends_on=("memory", "models"))
        if self.enable_voice:
            L.register(Service("voice_output", start=self._start_output, stop=self._stop_output,
                               health=self._output_health))
            L.register(self.neural_audio, depends_on=("voice_output",))
            L.register(self.voice, depends_on=("voice_output",))
        if self.enable_perception:
            L.register(self.perception, depends_on=("world_model", "models", "network"))
        L.register(self.proactive, depends_on=("memory",))
        if self.enable_plugins:
            L.register(self.plugins, depends_on=("skills", "models"))
        L.register(self.health)

    # ================================================================ ciclo de vida
    def boot(self, *, on_progress: Callable[[str, str], None] | None = None) -> dict[str, str]:
        started = time.perf_counter()
        self.started_at = time.time()
        self.state.set_runtime_state("BOOTING", "inicialização", source="core")
        self.bus.publish(EventType.SYSTEM_BOOT, {"version": __version__, "components": self.lifecycle.names()},
                         source="core")
        self.bus.start()
        self.runtime.start()
        done: list[str] = []

        def progress(name: str, status: str) -> None:
            done.append(name)
            self.state.update(_source="core", boot={"component": name, "status": status, "done": len(done),
                                                   "total": len(self.lifecycle.names())})
            if on_progress:
                on_progress(name, status)

        self._apply_start_policy()
        statuses = self.lifecycle.start_all(on_progress=progress)
        self._schedule()
        if getattr(self.settings(), "privacy_shield_on_start", False):
            self.set_privacy_shield(True, by="inicialização")
        seconds = round(time.perf_counter() - started, 2)
        failed = [n for n, st in statuses.items() if st == "FAILED"]
        self.booted = True
        self.state.set_runtime_state("IDLE", "", source="core")
        self.bus.publish(EventType.SYSTEM_READY, {"seconds": seconds, "components": statuses, "failed": failed},
                         source="core")
        log.info("JARVIS online em %.2fs (%d componentes, %d com falha)", seconds, len(statuses), len(failed))
        self.runtime.submit("health", self.health.check_all, name="health:boot")
        self.say(dialogue.say("online"))
        return statuses

    def shutdown(self) -> None:
        if not self.booted:
            return
        self.booted = False
        self.bus.publish(EventType.SYSTEM_SHUTDOWN, {}, source="core")
        self.cancel("encerramento")
        try:
            self.state.set_runtime_state("SHUTDOWN", "encerrando", source="core")
        except Exception:
            pass
        self.lifecycle.stop_all()
        self.runtime.stop()
        self.bus.stop()

    def _schedule(self) -> None:
        s = self.settings()
        sched = self.runtime.scheduler
        sched.every("health", 15.0, self.health.check_all, worker="health", initial_delay=8.0)
        sched.every("metrics", 5.0, self.metrics.sample_process, worker="health", initial_delay=1.0)
        sched.every("models", 60.0, self._refresh_models, worker="network", initial_delay=30.0)
        sched.every("privacy", 60.0, self.privacy.refresh, worker="network", initial_delay=20.0)
        sched.every("consolidation", s.consolidation_interval, self.memory.consolidate, worker="memory",
                    initial_delay=s.consolidation_interval)
        sched.every("graph_decay", 3600.0, self.memory.graph.decay, worker="memory", initial_delay=600.0)
        sched.every("discovery", s.discovery_interval, self._discover_network, worker="network", initial_delay=90.0)
        sched.every("dream", 60.0, self._maybe_dream, worker="imagination", initial_delay=120.0)
        sched.every("suggestion_expiry", 5.0, self._expire_suggestion, worker="perception", initial_delay=5.0)
        sched.every("backup", 3600.0, self._auto_backup, worker="memory", initial_delay=180.0)

    def _auto_backup(self) -> None:
        """Backup diário do banco único (só se o último passou do intervalo configurado)."""
        s = self.settings()
        if not getattr(s, "auto_backup", True):
            return
        from ..memory import backup
        try:
            path = backup.backup_if_due(self.memory.db, interval_hours=float(getattr(s, "backup_interval_hours", 24.0)),
                                        keep=int(getattr(s, "backup_keep", 10)))
        except Exception as exc:                       # registrado; o próximo ciclo tenta de novo
            log.warning("backup automático falhou: %s", exc)
            return
        if path is not None:
            self.memory.db.audit("backup", "auto", path.name, True)

    # ================================================================ modelos
    def _start_models(self) -> None:
        if self.client.is_alive(timeout=1.5):
            self.router.refresh(force=True)
            return
        self.router.refresh(force=True)               # registra a indisponibilidade com o motivo
        if getattr(self.settings(), "ollama_autostart", True) and self.privacy.ollama_is_local():
            threading.Thread(target=self._autostart_ollama, name="ultron-ollama-start", daemon=True).start()

    def _autostart_ollama(self) -> None:
        try:
            if self.client.ensure_server(autostart=True, wait_seconds=25.0):
                self.router.refresh(force=True)
                log.info("Ollama disponível após inicialização automática")
        except Exception as exc:
            log.warning("não foi possível iniciar o Ollama: %s", exc)

    def _refresh_models(self) -> None:
        status = self.router.refresh(force=True)
        if not status.ollama_alive and getattr(self.settings(), "ollama_autostart", True) \
                and self.privacy.ollama_is_local() and time.time() - self.started_at > 60:
            self._autostart_ollama()

    def _models_health(self) -> dict:
        status = self.router.status()
        if not status.ollama_alive:
            return {"status": "FAIL", "detail": f"Ollama indisponível: {status.error or 'sem resposta'}"}
        text = status.selections.get("text")
        if text is None or not text.available:
            return {"status": "FAIL", "detail": f"sem modelo de texto: {getattr(text, 'reason', '')}"}
        missing = f"; ausentes: {', '.join(status.missing)}" if status.missing else ""
        vision = status.selections.get("vision")
        vision_txt = vision.model if vision is not None and vision.available else "sem visão"
        return {"status": "WARN" if status.missing else "OK",
                "detail": f"{text.model} · {vision_txt}{missing}", "value": status.latency_ms}

    def _running_models(self) -> list[dict]:
        return self.client.running_models() if self.router.status().ollama_alive else []

    # ================================================================ voz e áudio
    def _start_output(self) -> None:
        self.audio_out.start()
        self.audio_out.sfx_volume = float(self.settings().sfx_volume)
        self.speaker.start()

    def _stop_output(self) -> None:
        self.speaker.stop()
        self.audio_out.stop()

    def _output_health(self) -> dict:
        if not self.audio_out.available:
            return {"status": "UNAVAILABLE", "detail": self.audio_out.reason or "sem saída de áudio"}
        if self.speaker.synth is None and self.speaker.reason:
            return {"status": "FAIL", "detail": f"síntese de voz: {self.speaker.reason}"}
        return {"status": "OK", "detail": f"{self.audio_out.backend} · {getattr(self.speaker.synth, 'name', '...')}"}

    def say(self, text: str) -> bool:
        if not text or not self.enable_voice or self.speaker.muted:
            return False
        return self.speaker.say(text)

    @property
    def voice_output_ready(self) -> bool:
        return self.enable_voice and not self.speaker.muted and self.audio_out.available

    # ================================================================ entrada
    def _looks_like_command(self, text: str) -> bool:
        try:
            return self.intents.classify(text).kind not in ("unknown", "response")
        except Exception:
            return False

    def _on_voice_command(self, text: str, meta: dict) -> None:
        self.submit(text, source="voice", meta=meta)

    def submit(self, text: str, *, source: str = "text", meta: dict | None = None) -> bool:
        """Entrada única. Devolve True quando o pedido foi aceito para processamento."""
        text = " ".join(str(text or "").split())
        if not text:
            return False
        self._last_interaction = time.time()
        if self._dream_token is not None:
            self._dream_token.cancel("interação do usuário")
        self.bus.publish(EventType.USER_INPUT, {"text": text[:500], "source": source, **(meta or {})}, source="core")
        text_in = text
        intent = self.intents.classify(text)
        if intent.kind == "cancel":
            was_speaking = bool(self.speaker.speaking)
            cancelled = self.cancel("cancelado pelo usuário")
            text = dialogue.say("cancelled") if cancelled or was_speaking else "Não há nada em andamento."
            self.activity.record("pedido", text_in, origin=source, input=text_in,
                                 state="cancelado" if cancelled or was_speaking else "concluido", result=text)
            self._emit_response(Response(text, "info"), source, speak=False)
            return True
        if self.authorizations.pending() is not None:
            reply = self.authorizations.handle_reply(text, by=source)
            if reply == "always":
                grant = self.authorizations.last_standing
                note = (f"Autorizado. Esta mesma ação, com o mesmo recurso, não pedirá confirmação até "
                        f"{time.strftime('%d/%m às %H:%M', time.localtime(grant['expires_at']))}."
                        if grant else "Autorizado só desta vez: autorização permanente não é permitida para "
                                      "ações sensíveis, críticas, irreversíveis ou proativas.")
                self._emit_response(Response(note, "info"), source, speak=False)
            if reply is not None:
                return True
            self.authorizations.resolve(False, by="novo pedido")      # outro assunto: nega e segue
        if self._suggestion is not None:
            reply = classify_reply(text)
            if reply is not None:
                self.accept_suggestion(reply == "yes", by=source)
                return True
        pending, self._pending_capture = self._pending_capture, None
        if pending is not None and time.time() <= pending["expires"]:
            if classify_reply(text) == "no":
                self._emit_response(Response("Certo. Nada foi registrado.", "info"), source)
                return True
            if intent.kind == "unknown":                 # resposta ao esclarecimento ("às 15", "da tarde"...)
                activity = self.activity.begin("pedido", text, origin=source, input=text,
                                               detail={"esclarecimento": True})
                self.runtime.submit("ai", self._answer_pending, pending, text, source, activity,
                                    name="esclarecimento")
                return True
        if intent.kind == "unknown":
            self._topic = (text, time.time())
            if getattr(self.settings(), "auto_capture", True):
                self.runtime.submit("memory", self._auto_capture, text, source, name="captura")
        busy = self._token is not None
        if busy:
            self._emit_response(Response(dialogue.say("busy"), "info"), source, partial=True)
        activity = self.activity.begin("pedido", text, origin=source, input=text)
        self.runtime.submit("ai", self._process, text, source, activity, name=f"pedido:{text[:30]}")
        return True

    def cancel(self, reason: str = "cancelado pelo usuário") -> bool:
        cancelled = False
        with self._lock:
            token = self._token
        if token is not None:
            token.cancel(reason)
            cancelled = True
        if self._dream_token is not None:
            self._dream_token.cancel(reason)
        if self.authorizations.pending() is not None:
            cancelled = True
        self.authorizations.cancel_all()
        self.speaker.interrupt()
        return cancelled

    def _process(self, text: str, source: str, activity: str = "") -> None:
        started = time.perf_counter()
        token = CancellationToken()
        with self._lock:
            self._token = token
        if activity:
            self.activity.update(activity, state="executando")
        try:
            with self.activity.scope(activity):
                response = self.orchestrator.handle(Command(text, source=source), token)
        except CancelledError:
            response = Response(dialogue.say("cancelled"), "info", success=False)
        except Exception as exc:  # o JARVIS nunca cai por causa de um pedido
            log.exception("falha ao processar pedido")
            response = Response(f"Falha interna ao processar o pedido ({type(exc).__name__}). Registrado.", "error",
                                success=False)
        finally:
            with self._lock:
                self._token = None
        if token.cancelled and response.kind not in ("info", "error"):
            response = Response(dialogue.say("cancelled"), "info", success=False)
        self._finish_state()
        clarify = (response.data or {}).get("clarify") or {}
        if clarify.get("skill") == "secondbrain.capture" and clarify.get("pending"):
            self._pending_capture = {"pending": clarify["pending"], "expires": time.time() + PENDING_TTL}
        self.activity.finish_request(activity, response, cancelled=token.cancelled)
        self._emit_response(response, source)
        self.metrics.record("request", time.perf_counter() - started)

    def _finish_state(self) -> None:
        try:
            if self.state.runtime_state not in ("SPEAKING", "LISTENING", "SHUTDOWN"):
                self.state.set_runtime_state("IDLE", "", source="core")
            self.state.set_cognitive_phase("", source="core")
        except Exception:
            pass

    # ================================================================ saída
    def _emit_response(self, response: Response, source: str, *, partial: bool = False, speak: bool = True) -> None:
        voice = bool(speak and self.voice_output_ready and response.spoken)
        payload = {**response.to_dict(), "source": source, "partial": partial, "voice": voice}
        self.bus.publish(EventType.RESPONSE_READY, payload, source="core")
        if voice:
            self.say(response.spoken)

    def _progress(self, text: str) -> None:
        self._emit_response(Response(text, "progress"), "core", partial=True)

    # ================================================================ controle do próprio sistema
    def _control(self, intent: Intent) -> Response:
        if intent.kind == "dream":
            return self._imagine(intent, None)
        args = dict(intent.args or {})
        s = self.settings()
        if "mute_voice" in args:
            self.speaker.muted = bool(args["mute_voice"])
            if self.speaker.muted:
                self.speaker.interrupt()
                return Response("Voz desativada. Respostas apenas em texto.", "info")
            return Response("Voz reativada.", "info")
        if "speech_speed_delta" in args:
            value = round(max(0.6, min(1.4, s.speech_speed + float(args["speech_speed_delta"]))), 2)
            self.settings_manager.update(speech_speed=value)
            return Response(f"Velocidade da fala: {value:.1f}.", "info")
        if "voice_volume_delta" in args:
            value = round(max(0.1, min(1.0, s.volume + float(args["voice_volume_delta"]))), 2)
            self.settings_manager.update(volume=value)
            return Response(f"Volume da voz: {value:.0%}.", "info")
        if "observer" in args:
            return self.set_observer(str(args["observer"]))
        if "screen_observation" in args:
            return self.set_observer("on" if args["screen_observation"] else "off")
        if "privacy_shield" in args:
            return self.set_privacy_shield(bool(args["privacy_shield"]), by="pedido")
        if "privacy_mode" in args:
            self.settings_manager.update(privacy_mode=str(args["privacy_mode"]))
            self.privacy.refresh()
            return Response("LOCAL MODE ativo. Conexões externas automáticas bloqueadas.", "info")
        if "open_view" in args:
            if self.hud_health is None:
                return Response("Interface gráfica indisponível nesta execução.", "error", success=False)
            self.bus.publish(EventType.UI_REQUEST, {"view": args["open_view"], "section": args.get("section", "")},
                             source="core")
            label = {"systems": "o painel de Sistemas", "voice": "o diagnóstico de voz", "network": "a rede local",
                     "autonomy": "o painel de autonomia"}.get(args["open_view"], "o TARDIS")
            return Response(f"Abrindo {label}.", "info")
        return Response("Ajuste não reconhecido.", "error")

    # ================================================================ Observador e modo privacidade
    def _apply_start_policy(self) -> None:
        """Como no JARVIS original, o Observador sempre começa DESLIGADO (a não ser que o usuário peça
        para restaurar o último modo). ``screen_observation`` acompanha o modo (compatibilidade)."""
        try:
            from ..memory.legacy_import import import_copilot_settings
            legacy = paths.legacy_jarvis_database()
            found = import_copilot_settings(self.memory.db, legacy.with_name("copilot.json") if legacy else None)
            if found.get("excluded"):
                merged = tuple(dict.fromkeys(tuple(self.settings().excluded_apps) + tuple(found["excluded"])))
                self.settings_manager.update(excluded_apps=merged)
                log.info("exclusões do Observador original importadas: %d", len(found["excluded"]))
        except Exception as exc:                      # dados legados nunca impedem o boot
            log.warning("exclusões do Observador original não importadas: %s", exc)
        s = self.settings()
        if not getattr(s, "observer_restore_on_start", False):
            self.settings_manager.update(observer_mode="off", screen_observation=False)
        else:
            self.settings_manager.update(screen_observation=s.observer_mode != "off")
        self._publish_observer()

    def observation_block(self) -> str:
        """Motivo pelo qual a tela NÃO deve ser observada agora ("" = pode observar)."""
        if self.privacy_shield:
            return "modo privacidade ativo"
        if getattr(self.settings(), "observer_mode", "off") == "off":
            return "Observador desligado"
        if self.observer_paused:
            return "Observador pausado"
        return ""

    def _publish_observer(self) -> None:
        s = self.settings()
        self.state.update(_source="core",
                          observer={"mode": getattr(s, "observer_mode", "off"), "paused": self.observer_paused,
                                    "block": self.observation_block()},
                          privacy_shield={"active": self.privacy_shield,
                                          "microphone": "fechado" if self.privacy_shield else "livre",
                                          "since": self._shield_since if self.privacy_shield else 0.0})

    def set_observer(self, action: str) -> Response:
        """Observador: on/observer (observa e fala quando útil), assistant (só sugere), off, pause, resume."""
        s = self.settings()
        mode = getattr(s, "observer_mode", "off")
        if action in ("pause", "resume"):
            if mode == "off":
                return Response("O Observador está desligado, senhor.", "info")
            self.observer_paused = action == "pause"
            self._publish_observer()
            return Response("Observador pausado, senhor." if self.observer_paused else "Observador retomado, senhor.",
                            "info")
        new_mode = {"on": "observer", "observer": "observer", "assistant": "assistant", "off": "off"}.get(action)
        if new_mode is None:
            return Response("Modo do Observador não reconhecido.", "error", success=False)
        self.observer_paused = False
        self.settings_manager.update(observer_mode=new_mode, screen_observation=new_mode != "off")
        self._publish_observer()
        if new_mode == "off":
            return Response("Observador desativado, senhor.", "info")
        note = " O modo privacidade está ativo: a observação começa quando ele for desligado." \
            if self.privacy_shield else ""
        if new_mode == "assistant":
            return Response("Observador em modo assistente: sugestões na tela, sem falar." + note, "info")
        return Response("Observador ativado, senhor. Vou acompanhar o contexto e só intervir quando houver algo "
                        "realmente útil." + note, "info")

    def set_privacy_shield(self, active: bool, *, by: str = "") -> Response:
        """Modo privacidade: FECHA o microfone (o dispositivo é liberado), suspende a observação da tela e
        mostra o estado. Por voz só é possível entrar; sair exige teclado/mouse (o microfone está fechado)."""
        if active == self.privacy_shield:
            return Response("O modo privacidade já está " + ("ativo." if active else "desligado."), "info")
        if self.enable_voice and active:
            self._shield_restore_mic = self.voice.mic_enabled
        self.privacy_shield = active
        self._shield_since = time.time() if active else 0.0
        if self.enable_voice:
            if active:
                self.voice.toggle_mic(False)
            elif self._shield_restore_mic and getattr(self.settings(), "voice_enabled", True):
                self.voice.toggle_mic(True)
        self._publish_observer()
        self.activity.record("sistema", "Modo privacidade " + ("ativado" if active else "desligado"),
                             origin=by or "user", result="microfone " + ("fechado" if active else "liberado"))
        self.bus.publish(EventType.PRIVACY_UPDATED, {"shield": active, "by": by,
                                                     "microphone": "fechado" if active else "liberado"},
                         source="core")
        if active:
            return Response("Modo privacidade ativo. Microfone fechado e observação da tela suspensa. Para sair, "
                            "use o botão PRIVACIDADE ou digite: sair do modo privacidade.", "info")
        return Response("Modo privacidade desligado. Microfone liberado.", "info")

    def _imagine(self, intent: Intent, cancel) -> Response:
        result = self.imagination.handle(intent, cancel)
        return Response(result.get("text", ""), "answer", data=result.get("data") or {})

    # ================================================================ proatividade
    def _on_insight(self, event) -> None:
        insight = event.payload
        if insight.get("suggestion"):
            self._suggestion = {**insight, "expires": time.time() + SUGGESTION_TTL}
        self._emit_response(Response(insight.get("text", ""), "insight", data={"insight": insight}), "proactive",
                            partial=True, speak=self.state.runtime_state in ("IDLE", "DREAMING"))

    def accept_suggestion(self, accept: bool, *, by: str = "user") -> bool:
        suggestion, self._suggestion = self._suggestion, None
        if suggestion is None:
            return False
        if not accept:
            self._emit_response(Response("Entendido. Nada foi feito.", "info"), by)
            return True
        action = suggestion["suggestion"]
        if "command" in action:
            activity = self.activity.begin("pedido", action["command"], origin=by, input=action["command"],
                                           detail={"sugestao_aceita": True})
            self.runtime.submit("ai", self._process, action["command"], by, activity, name="sugestão")
            return True
        skill, args = action.get("skill"), dict(action.get("args") or {})
        if suggestion.get("action") == "authorize":
            # o texto aceito descrevia exatamente esta ação e suas consequências
            self.authorizations.pre_approve(skill, args, ttl=60.0, by=by)
        intent = Intent("command", suggestion.get("text", skill), skill=skill, args=args, confidence=0.9)
        activity = self.activity.begin("pedido", f"Sugestão aceita: {intent.text}", origin=by,
                                       detail={"sugestao_aceita": True, "skill": skill})
        self.runtime.submit("ai", self._run_suggested, intent, by, activity, name="sugestão")
        return True

    def _run_suggested(self, intent: Intent, source: str, activity: str = "") -> None:
        token = CancellationToken()
        with self._lock:
            self._token = token
        try:
            with self.activity.scope(activity):
                response = self.orchestrator.run_goal(intent, token, source="user")
        except Exception as exc:
            log.exception("sugestão falhou")
            response = Response(f"A ação sugerida falhou ({type(exc).__name__}).", "error", success=False)
        finally:
            with self._lock:
                self._token = None
        self._finish_state()
        self.activity.finish_request(activity, response, cancelled=token.cancelled)
        self._emit_response(response, source)

    def _expire_suggestion(self) -> None:
        if self._suggestion is not None and time.time() > self._suggestion["expires"]:
            self._suggestion = None
        pending = self._pending_capture
        if pending is not None and time.time() > pending["expires"]:
            self._pending_capture = None
        if self.state.runtime_state == "REMINDING" and time.monotonic() > self._reminding_until \
                and not self.speaker.speaking:
            self.state.set_runtime_state("IDLE", "", source="reminders")

    # ================================================================ second brain
    def _recent_topic(self) -> dict | None:
        """Assunto de "anote essa ideia"/"lembre-me disso": a última fala livre do usuário ou o último
        registro criado/editado no Second Brain — o mais recente dos dois, até 15 minutos atrás."""
        now = time.time()
        topic = self._topic if self._topic and now - self._topic[1] <= TOPIC_TTL else None
        record = None
        try:
            rows = self.second_brain.store.select(["deleted_at IS NULL", "updated_at >= ?"], [now - TOPIC_TTL],
                                                  limit=1)
            record = rows[0] if rows else None
        except Exception:
            record = None
        if record is not None and (topic is None or record.updated_at >= topic[1]):
            return {"text": record.title, "record_id": record.id}
        return {"text": topic[0], "record_id": None} if topic else None

    def _auto_capture(self, text: str, source: str) -> None:
        """Captura automática (evidência clara de compromisso): registro INFERIDO, revisável e reversível."""
        if self._pending_capture is not None:
            return
        try:
            result = self.capture.auto(text, origin="auto")
        except Exception as exc:
            log.info("captura automática ignorada: %s", exc)
            return
        if result.question and result.pending:
            self._pending_capture = {"pending": result.pending, "expires": time.time() + PENDING_TTL}
            self._emit_response(Response(result.question, "question", data={"clarify": {
                "skill": "secondbrain.capture", "pending": result.pending}}), "second_brain", partial=True)
            return
        if result.records and result.inferred:
            record = result.records[0]
            try:
                self.memory.db.audit("second_brain", "auto_capture", f"{record.kind}: {record.title}"[:300], None)
            except Exception:
                pass
            text = confirmation_text(result, now=self.second_brain.now_wall())
            self._emit_response(Response(text, "info", data={"record": record.to_dict(), "inferred": True}),
                                "second_brain", partial=True, speak=False)

    def _answer_pending(self, pending: dict, text: str, source: str, activity: str = "") -> None:
        with self.activity.scope(activity):
            response = self._pending_response(pending, text)
        self.activity.finish_request(activity, response)
        self._emit_response(response, source)

    def _pending_response(self, pending: dict, text: str) -> Response:
        try:
            answer = self.capture.answer(pending["pending"], text)
        except Exception as exc:
            return Response(f"Nada foi registrado: {exc}", "error", success=False)
        if isinstance(answer, CaptureResult):
            self._pending_capture = {"pending": answer.pending, "expires": time.time() + PENDING_TTL}
            return Response(answer.question, "question")
        outcome = self.run_skill("secondbrain.capture", answer, origin="user")
        if outcome["success"] and outcome["data"].get("clarify"):
            self._pending_capture = {"pending": outcome["data"].get("pending") or {},
                                     "expires": time.time() + PENDING_TTL}
            return Response(outcome["text"], "question")
        return self._outcome_response(outcome)

    def _outcome_response(self, outcome: dict) -> Response:
        """Resposta honesta para uma execução direta: sucesso só com verificação."""
        if outcome["success"] and outcome["verified"]:
            return Response(outcome["text"] or dialogue.say("done"), "result", success=True, verified=True)
        if outcome["success"]:
            return Response(f"{outcome['text']} Sem confirmação independente.".strip(), "result", success=True,
                            verified=False)
        reason = outcome["error"] or outcome["status"]
        return Response(f"{dialogue.say('failed')} {reason[:1].upper() + reason[1:]}", "error", success=False)

    def run_skill(self, skill: str, args: dict | None = None, *, origin: str = "user", cancel=None) -> dict:
        """Executa UMA skill pelo caminho central (autonomia, autorização específica, auditoria e
        verificação). Usado pelo HUB 2 e pelas respostas de esclarecimento — nunca na thread da interface."""
        action = Action(skill, dict(args or {}), origin=origin)
        record = self.executor.execute(action, cancel=cancel, on_authorization=lambda d: self._progress(
            dialogue.say("auth_request", action=d)))
        verification = self.verifier.verify(record, self.executor.context(cancel))
        if self._token is None:
            self._finish_state()
        return {"status": record.status, "success": record.executed, "verified": verification.verified,
                "text": record.result.result, "error": record.result.error, "error_kind": record.result.error_kind,
                "data": record.result.data, "verification": verification.to_dict(),
                "authorization": record.authorization}

    def _announce_reminder(self, payload: dict) -> None:
        """O agendador disparou um lembrete (fora do modo silencioso): estado REMINDING e fala curta."""
        if not self.booted:
            return
        notice = str(payload.get("notice") or payload.get("title") or "Lembrete.")
        if self.state.runtime_state in ("IDLE", "DREAMING", "REMINDING"):
            if self._dream_token is not None:
                self._dream_token.cancel("lembrete")
            self._reminding_until = time.monotonic() + REMINDING_SECONDS
            self.state.set_runtime_state("REMINDING", notice[:80], source="reminders")
        self._emit_response(Response(notice + (f" — {payload['when_text']}." if payload.get("when_text") else "."),
                                     "reminder", data={"reminder": payload}), "reminders", partial=True,
                            speak=self._token is None)

    def _second_brain_health(self) -> dict:
        rank = {"OK": 0, "UNKNOWN": 1, "UNAVAILABLE": 1, "WARN": 2, "FAIL": 3}
        try:
            service, reminders = self.second_brain.health(), self.reminders.health()
        except Exception as exc:
            return {"status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"[:200]}
        worst = max((service, reminders), key=lambda r: rank.get(r["status"], 1))
        return {"status": worst["status"], "detail": f"{service['detail']}; lembretes: {reminders['detail']}"}

    def _on_wake(self, event) -> None:
        if event.get("command"):
            return
        # só "Jarvis.": o pulso neural confirma; sem mixagem de efeitos, a confirmação é falada
        if not getattr(self.audio_out, "mixes_effects", False):
            self.say(dialogue.say("wake"))

    # ================================================================ manutenção
    def _discover_network(self) -> None:
        if getattr(self.settings(), "network_discovery", True):
            self.network.scan()

    def _maybe_dream(self) -> None:
        if self.state.runtime_state != "IDLE" or self._token is not None:
            return
        idle = time.time() - self._last_interaction
        if not self.imagination.dream.due(idle):
            return
        token = CancellationToken()
        self._dream_token = token
        try:
            self.state.set_runtime_state("DREAMING", "repouso", source="core")
            self.imagination.dream.dream(cancel=token)
        except Exception as exc:
            log.info("sonho interrompido: %s", exc)
        finally:
            self._dream_token = None
            if self.state.runtime_state == "DREAMING":
                self.state.set_runtime_state("IDLE", "", source="core")

    def _on_settings_changed(self, changed: list[str], settings) -> None:
        if not changed:
            return
        voice_keys = {"wake_words", "wake_variants", "wake_weak_variants", "wake_names", "followup_seconds",
                      "voice_enabled", "mic_name", "mic_index", "mic_backend", "stt_engine"}
        if voice_keys & set(changed):
            self.voice.apply_settings(changed)
        if {"window_interval", "process_interval", "system_interval", "vision_interval", "filesystem_interval",
                "network_interval", "device_interval"} & set(changed):
            self.perception.apply_settings(settings)
        if "ollama_url" in changed:
            self.client.base_url = settings.ollama_url.rstrip("/")
        if {"ollama_url", "model", "vision_model", "privacy_mode", "allow_external_models"} & set(changed):
            self.runtime.submit("network", self.router.refresh, force=True, name="router:refresh")
        if {"privacy_mode", "allow_external_models"} & set(changed):
            self.runtime.submit("network", self.privacy.refresh, name="privacy:refresh")
        if "sfx_volume" in changed:
            self.audio_out.sfx_volume = float(settings.sfx_volume)
        if "consolidation_interval" in changed:
            self.runtime.scheduler.set_interval("consolidation", settings.consolidation_interval)
        if "discovery_interval" in changed:
            self.runtime.scheduler.set_interval("discovery", settings.discovery_interval)
        if "startup" in changed:
            from ..platform import autostart
            if autostart.supported():
                (autostart.enable if settings.startup else autostart.disable)()

    # ================================================================ contexto das skills e plugins
    def _skill_context(self, cancel) -> SkillContext:
        return SkillContext(world=self.world, memory=self.memory, perception=self.perception, network=self.network,
                            router=self.router, settings=self.settings(), privacy=self.privacy,
                            imagination=self.imagination, voice=self.voice, cancel=cancel,
                            emit=lambda kind, **payload: self.bus.publish(kind, payload, source="skill"),
                            extras={"registry": self.registry, "goals": self.goals, "core": self,
                                    "second_brain": self.second_brain, "capture": self.capture})

    def _plugin_context(self, plugin) -> PluginContext:
        return PluginContext(plugin=plugin, bus=self.bus, state=self.state, settings=self.settings,
                             registry=self.registry, health_monitor=self.health, router=self.router,
                             privacy=self.privacy, data_dir=paths.data_dir() / "plugins" / plugin.name,
                             log=logging.getLogger(f"ultron.plugin.{plugin.name}"))

    # ================================================================ saúde
    def _register_health_probes(self) -> None:
        h = self.health
        h.register("OLLAMA", self._models_health)
        h.register("VOICE", self._voice_health)
        h.register("VISION", self._vision_health)
        h.register("NETWORK", self.network.health)
        h.register("MEMORY", self._memory_health)
        h.register("SECOND_BRAIN", self._second_brain_health)
        h.register("HUD", lambda: self.hud_health() if self.hud_health else
                   {"status": "UNAVAILABLE", "detail": "modo sem interface gráfica"})

    def _voice_health(self) -> dict:
        if not self.enable_voice:
            return {"status": "UNAVAILABLE", "detail": "voz desativada nesta execução"}
        output, mic = self._output_health(), self.voice.health()
        worst = max((output, mic), key=lambda r: {"OK": 0, "UNKNOWN": 1, "UNAVAILABLE": 1, "WARN": 2,
                                                  "FAIL": 3}.get(r["status"], 1))
        return {"status": worst["status"], "detail": f"saída: {output['detail']}; microfone: {mic['detail']}"}

    def _vision_health(self) -> dict:
        selection = self.router.status().selections.get("vision")
        blocked = self.observation_block()
        if blocked:
            return {"status": "OK", "detail": f"observação da tela inativa: {blocked}"}
        if selection is None or not selection.available:
            return {"status": "UNAVAILABLE", "detail": getattr(selection, "reason", "modelo de visão não verificado")}
        sensor = getattr(self.perception, "vision_sensor", None)
        detail = f"{selection.model}" + (f" · {sensor.status}" if sensor is not None else "")
        return {"status": "OK", "detail": detail}

    def _memory_health(self) -> dict:
        checked_at, cached = self._memory_check
        if time.time() - checked_at > 600:                   # quick_check no máximo a cada 10 min
            ok = self.memory.db.integrity_ok()
            stats = self.memory.graph.stats()
            cached = {"status": "OK" if ok else "FAIL",
                      "detail": ("integridade verificada" if ok else "falha de integridade do banco")
                                + f"; grafo {stats.get('nodes', 0)} nós / {stats.get('edges', 0)} conexões"}
            self._memory_check = (time.time(), cached)
        return cached

    # ================================================================ leitura para a interface
    def telemetry(self) -> dict[str, Any]:
        """Leitura barata e frequente (níveis de áudio, filas, uptime)."""
        return {
            "mic_level": self.voice.level if self.enable_voice else 0.0,
            "out_level": getattr(self.audio_out, "level", 0.0),
            "speaking": bool(self.speaker.speaking),
            "listening": bool(self.voice.listening),
            "workers": {k: v["pending"] for k, v in self.runtime.status().items()},
            "uptime": time.time() - self.started_at if self.started_at else 0.0,
            "suggestion": (self._suggestion or {}).get("text") if self._suggestion else None,
        }

    def diagnose(self) -> dict[str, Any]:
        return {"version": __version__, "components": self.lifecycle.statuses(),
                "health": self.health.check_all(), "plugins": self.plugins.list(),
                "skills": {"total": len(self.registry), "available": len(self.registry.available())},
                "models": self.router.status().to_dict(), "privacy": self.privacy.status(),
                "voice": self.voice.mic_probe(), "workers": self.runtime.status()}
