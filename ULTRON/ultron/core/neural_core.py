"""NEURAL CORE — o ULTRON montado.

Responsabilidades:

* construir cada componente com suas dependências (nenhum módulo cria outro por conta própria);
* registrar tudo no ``LifecycleManager`` (boot em ordem, falha isolada, parada em ordem inversa);
* ser a **entrada única** de pedidos (texto da HUD, voz, console) e a **saída única** de
  respostas (``RESPONSE_READY`` + fala);
* rotear respostas de autorização ("sim"/"não"), sugestões proativas e cancelamento;
* agendar a manutenção: saúde, consolidação da memória, decaimento do grafo, varredura da
  rede local, privacidade e Dream Mode (só em repouso).

Toda inferência roda no worker ``ai``; a interface nunca espera por nada daqui.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from .. import __version__
from ..agent.autonomy import AuthorizationManager, AutonomyPolicy, classify_reply
from ..agent.execution import ExecutionEngine
from ..agent.recovery import RecoveryEngine
from ..agent.verification import VerificationEngine
from ..audio.neural_audio import NeuralAudio
from ..cognition.context_engine import ContextEngine
from ..cognition.decision_engine import DecisionEngine
from ..cognition.goal_manager import GoalManager
from ..cognition.intent_engine import IntentEngine
from ..cognition.planner_engine import PlannerEngine
from ..cognition.reasoning_engine import ReasoningEngine
from ..cognition.types import Command, Intent
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
        self._suggestion: dict | None = None
        self._last_interaction = time.time()
        self._memory_check = (0.0, {"status": "UNKNOWN", "detail": ""})
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
        self.network = NetworkIntelligence(db=self.memory.db, settings_getter=s, bus=self.bus, state=self.state,
                                           world=self.world, graph=self.memory.graph, privacy=self.privacy)
        self.registry = load_builtin(SkillRegistry())
        self.authorizations = AuthorizationManager(bus=self.bus, state=self.state,
                                                   timeout_getter=lambda: s().authorization_timeout)
        self.autonomy = AutonomyPolicy(s)
        self.imagination = ImaginationCore(router=self.router, memory=self.memory, bus=self.bus, state=self.state,
                                           privacy=self.privacy, settings_getter=s)
        # voz
        self.audio_out = audio_output or AudioOutput()
        self.speaker = Speaker(self.audio_out, bus=self.bus, state=self.state, settings_getter=s)
        self.intents = IntentEngine(automations=self.memory.procedural.automation_for,
                                    wake_words=lambda: tuple(s().wake_words))
        self.voice = VoicePipeline(bus=self.bus, state=self.state, settings_getter=s, speaker=self.speaker,
                                   on_command=self._on_voice_command, command_check=self._looks_like_command)
        self.neural_audio = NeuralAudio(self.audio_out, bus=self.bus, state=self.state, settings_getter=s)
        # percepção
        self.perception = PerceptionEngine(settings_getter=s, runtime=self.runtime, bus=self.bus, state=self.state,
                                           world=self.world, memory=self.memory, router=self.router,
                                           network=self.network, hud_probe=self.hud_probe,
                                           mic_probe=self.voice.mic_probe)
        self.perception.metrics = self.metrics
        # agente e cognição
        self.executor = ExecutionEngine(self.registry, autonomy=self.autonomy, authorizations=self.authorizations,
                                        context_factory=self._skill_context, bus=self.bus, state=self.state,
                                        audit=self.memory.db.audit)
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

        statuses = self.lifecycle.start_all(on_progress=progress)
        self._schedule()
        seconds = round(time.perf_counter() - started, 2)
        failed = [n for n, st in statuses.items() if st == "FAILED"]
        self.booted = True
        self.state.set_runtime_state("IDLE", "", source="core")
        self.bus.publish(EventType.SYSTEM_READY, {"seconds": seconds, "components": statuses, "failed": failed},
                         source="core")
        log.info("ULTRON online em %.2fs (%d componentes, %d com falha)", seconds, len(statuses), len(failed))
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
        intent = self.intents.classify(text)
        if intent.kind == "cancel":
            was_speaking = bool(self.speaker.speaking)
            cancelled = self.cancel("cancelado pelo usuário")
            text = dialogue.say("cancelled") if cancelled or was_speaking else "Não há nada em andamento."
            self._emit_response(Response(text, "info"), source, speak=False)
            return True
        if self.authorizations.pending() is not None:
            reply = self.authorizations.handle_reply(text, by=source)
            if reply is not None:
                return True
            self.authorizations.resolve(False, by="novo pedido")      # outro assunto: nega e segue
        if self._suggestion is not None:
            reply = classify_reply(text)
            if reply is not None:
                self.accept_suggestion(reply == "yes", by=source)
                return True
        busy = self._token is not None
        if busy:
            self._emit_response(Response(dialogue.say("busy"), "info"), source, partial=True)
        self.runtime.submit("ai", self._process, text, source, name=f"pedido:{text[:30]}")
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

    def _process(self, text: str, source: str) -> None:
        started = time.perf_counter()
        token = CancellationToken()
        with self._lock:
            self._token = token
        try:
            response = self.orchestrator.handle(Command(text, source=source), token)
        except CancelledError:
            response = Response(dialogue.say("cancelled"), "info", success=False)
        except Exception as exc:  # o ULTRON nunca cai por causa de um pedido
            log.exception("falha ao processar pedido")
            response = Response(f"Falha interna ao processar o pedido ({type(exc).__name__}). Registrado.", "error",
                                success=False)
        finally:
            with self._lock:
                self._token = None
        if token.cancelled and response.kind not in ("info", "error"):
            response = Response(dialogue.say("cancelled"), "info", success=False)
        self._finish_state()
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
        if "screen_observation" in args:
            self.settings_manager.update(screen_observation=bool(args["screen_observation"]))
            return Response("Observação da tela " + ("ativada." if args["screen_observation"] else "desativada."),
                            "info")
        if "privacy_mode" in args:
            self.settings_manager.update(privacy_mode=str(args["privacy_mode"]))
            self.privacy.refresh()
            return Response("LOCAL MODE ativo. Conexões externas automáticas bloqueadas.", "info")
        return Response("Ajuste não reconhecido.", "error")

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
            self.runtime.submit("ai", self._process, action["command"], by, name="sugestão")
            return True
        skill, args = action.get("skill"), dict(action.get("args") or {})
        if suggestion.get("action") == "authorize":
            # o texto aceito descrevia exatamente esta ação e suas consequências
            self.authorizations.pre_approve(skill, args, ttl=60.0, by=by)
        intent = Intent("command", suggestion.get("text", skill), skill=skill, args=args, confidence=0.9)
        self.runtime.submit("ai", self._run_suggested, intent, by, name="sugestão")
        return True

    def _run_suggested(self, intent: Intent, source: str) -> None:
        token = CancellationToken()
        with self._lock:
            self._token = token
        try:
            response = self.orchestrator.run_goal(intent, token, source="user")
        except Exception as exc:
            log.exception("sugestão falhou")
            response = Response(f"A ação sugerida falhou ({type(exc).__name__}).", "error", success=False)
        finally:
            with self._lock:
                self._token = None
        self._finish_state()
        self._emit_response(response, source)

    def _expire_suggestion(self) -> None:
        if self._suggestion is not None and time.time() > self._suggestion["expires"]:
            self._suggestion = None

    def _on_wake(self, event) -> None:
        if event.get("command"):
            return
        # só "Ultron.": o pulso neural confirma; sem mixagem de efeitos, a confirmação é falada
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
        voice_keys = {"wake_words", "wake_variants", "wake_weak_variants", "followup_seconds", "voice_enabled",
                      "mic_name", "mic_index", "stt_engine"}
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
                            extras={"registry": self.registry, "goals": self.goals, "core": self})

    def _plugin_context(self, plugin) -> PluginContext:
        from ..config import paths
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
        if not getattr(self.settings(), "screen_observation", True):
            return {"status": "WARN", "detail": "observação da tela desativada"}
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
