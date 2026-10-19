"""VOICE PROCESSOR — microfone → reconhecimento → palavra de ativação → comando.

Fluxo por bloco de áudio (250 ms):

1. nível de entrada (para a HUD) e reconhecimento contínuo (Vosk, offline);
2. **fora de uma conversa**, só frases que começam com "Jarvis" (ou uma variante
   medida/calibrada) viram comando; o resto é descartado sem registro;
3. depois de uma resposta, uma **janela de continuação** aceita a próxima frase sem a
   palavra de ativação;
4. **enquanto o JARVIS fala** (sem cancelamento de eco por hardware), o que o microfone
   capta é comparado com o texto sendo falado: eco é ignorado; "pare", "Jarvis" ou
   "pausa" ditos pelo usuário interrompem/pausam a fala na hora (*barge-in*).

Diagnóstico: contadores por etapa (blocos lidos, silêncio absoluto, parciais, finais,
ativações, entregas ao núcleo) e uma "escuta de diagnóstico" opcional que mostra o texto
reconhecido SOMENTE durante um teste pedido pelo usuário.

A captura roda em thread própria com supervisor: se o microfone falha ou é desconectado,
o pipeline tenta reabrir com espera exponencial (2 s → 60 s) e informa o motivo.
``on_command`` é chamado na thread de captura e deve apenas enfileirar o trabalho.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from ..core.events import EventType
from ..perception.microphone import pcm_level
from .audio import AudioBackendMissing
from .stt import VoskSTT, choose_model
from .wake_word import (DEFAULT_NAME_VARIANTS, DEFAULT_STRONG_VARIANTS, DEFAULT_WEAK_VARIANTS, WakeResult,
                        WakeWordDetector, _norm)

log = logging.getLogger("ultron.voice")

RATE = 16000
CHUNK = 4000                      # 250 ms a 16 kHz

CANCEL_WORDS = {"pare", "para", "parar", "chega", "silencio", "cancela", "cancelar", "cancele", "basta",
                "interrompa", "aborta", "abortar", "stop"}
PAUSE_WORDS = {"pausa", "pause", "espera", "espere", "aguarde", "aguarda"}
RESUME_WORDS = {"continua", "continue", "prossiga", "prossegue", "retome", "retoma"}
# Frases de duas palavras: medidas como bem mais confiáveis no reconhecimento do que palavras soltas.
CANCEL_PHRASES = {"pode parar", "pode cancelar", "pare agora", "para agora", "chega disso", "fique quieto",
                  "fica quieto", "cala boca"}
PAUSE_PHRASES = {"pode pausar", "pode pausa", "espera um", "espere um", "um momento", "um instante"}
RESUME_PHRASES = {"pode continuar", "pode seguir", "pode prosseguir", "continue falando"}
NOISE_WORDS = {"a", "e", "o", "hum", "ah", "uh", "eh", "ha", "hm", "the", "um", "ai"}

ECHO_TAIL_SECONDS = 0.9           # reverberação da própria fala após o fim da reprodução
SILENT_CHUNKS_WARNING = 20        # 5 s de zeros exatos: microfone bloqueado (privacidade) ou mudo por hardware
SILENCE_REASON = ("o microfone entrega silêncio absoluto — verifique Configurações do Windows > Privacidade > "
                  "Microfone (permitir que aplicativos da área de trabalho acessem) ou se ele está mudo")
LISTEN_TIMEOUT = 8.0              # escuta sem fala → volta ao repouso
WAKE_ONLY_WINDOW = 8.0            # "Jarvis" sozinho: espera o comando por este tempo
AWAIT_RESPONSE_SECONDS = 180.0    # limite de espera pela resposta antes de encerrar a conversa


def _words(text: str) -> list[str]:
    return _norm(text).split()


def echo_ratio(heard: str, spoken: str) -> float:
    """Fração das palavras ouvidas que estão no texto que o JARVIS está falando."""
    heard_words = [w for w in _words(heard) if len(w) >= 2]
    if not heard_words:
        return 0.0
    spoken_words = set(_words(spoken))
    return sum(1 for w in heard_words if w in spoken_words) / len(heard_words)


def classify_short_command(text: str) -> str | None:
    """'cancel' | 'pause' | 'resume' para frases curtas de controle da fala."""
    words = [w for w in _words(text) if w != "a"]
    if not words or len(words) > 3:
        return None
    pair = " ".join(words[:2])
    if pair in CANCEL_PHRASES or words[0] in CANCEL_WORDS:
        return "cancel"
    if pair in PAUSE_PHRASES or words[0] in PAUSE_WORDS:
        return "pause"
    if pair in RESUME_PHRASES or words[0] in RESUME_WORDS:
        return "resume"
    return None


def find_barge_in(heard: str, spoken: str, wake_fn: Callable[[str], Any]) -> tuple[str, str] | None:
    """Procura, no que o microfone captou durante a fala, a intervenção do usuário.

    Frases de controle de duas palavras ("pode parar", "pode continuar") valem em qualquer
    posição, se não forem eco. Fora isso, palavras do texto falado (eco) e ruídos são puladas
    e o trecho restante precisa começar com "Jarvis …" ou um controle curto ("pare", "pausa").
    Uma ativação cujas palavras (e o comando que a segue) estão no próprio texto falado é eco.
    Devolve (tipo, comando) com tipo em wake | cancel | pause | resume.
    """
    words = _words(heard)
    spoken_words = set(_words(spoken))
    # frases de controle de duas palavras são específicas: valem em qualquer posição
    for index in range(len(words) - 1):
        pair = (words[index], words[index + 1])
        if pair[0] in spoken_words and pair[1] in spoken_words:
            continue
        phrase = " ".join(pair)
        for kind, phrases in (("cancel", CANCEL_PHRASES), ("pause", PAUSE_PHRASES), ("resume", RESUME_PHRASES)):
            if phrase in phrases:
                return kind, phrase
    for index, word in enumerate(words):
        tail = " ".join(words[index:])
        wake = wake_fn(tail)
        if wake is not None:
            echo_form = all(w in spoken_words for w in wake.matched.split())
            if not echo_form or (wake.command and echo_ratio(wake.command, spoken) < 0.5):
                return "wake", wake.command
        if word in spoken_words or word in NOISE_WORDS:
            continue
        kind = classify_short_command(tail)
        if kind is not None:
            return kind, tail
        return None
    return None


class VoicePipeline:
    name = "voice"

    def __init__(self, *, bus=None, state=None, settings_getter: Callable[[], Any] | None = None,
                 speaker=None, on_command: Callable[[str, dict], None] | None = None,
                 stt_factory: Callable[[], tuple] | None = None,
                 mic_opener: Callable[[], tuple] | None = None,
                 command_check: Callable[[str], bool] | None = None):
        self._bus = bus
        self._state = state
        self._settings = settings_getter or (lambda: None)
        self.speaker = speaker
        self._on_command = on_command
        self._stt_factory = stt_factory
        self._mic_opener = mic_opener
        self._command_check = command_check          # formas fracas só valem com comando reconhecido
        self.stt = None
        self.stt_reason = ""
        s = self._settings()
        self.detector = WakeWordDetector(tuple(getattr(s, "wake_words", ("jarvis",))),
                                         tuple(getattr(s, "wake_variants", DEFAULT_STRONG_VARIANTS)),
                                         weak=tuple(getattr(s, "wake_weak_variants", DEFAULT_WEAK_VARIANTS)),
                                         names=tuple(getattr(s, "wake_names", DEFAULT_NAME_VARIANTS)),
                                         followup_seconds=float(getattr(s, "followup_seconds", 12.0)))
        self._thread: threading.Thread | None = None
        self._running = False
        self._mic_enabled = True
        self._wakeup = threading.Event()
        self._restart = threading.Event()
        self._reload_stt = False
        self._subs: list = []
        # estado da captura
        self.capturing = False
        self.device = ""
        self.reason = ""
        self.level = 0.0
        self.failures = 0
        self.retry_at = 0.0
        # estado da conversa
        self.listening = False
        self._listen_mode = ""
        self._listening_since = 0.0
        self._last_speech_at = 0.0
        self.conversation = False
        self._awaiting_since = 0.0                 # comando entregue, resposta ainda não veio
        self._overlapped_speech = False
        self._barged = False
        self._barge_cut = False                    # fala cortada pelo usuário: sem cauda de eco
        # contadores (sem conteúdo: falas não endereçadas ao JARVIS não são guardadas)
        self.commands = 0
        self.ignored = 0
        self.echoes = 0
        self.last_command = ""
        self.last_confidence = 0.0
        self.stats = {"chunks": 0, "zero_chunks": 0, "partials": 0, "finals": 0, "wakes": 0, "delivered": 0}
        self.last_chunk_at = 0.0
        self.peak_level = 0.0
        self.silence_warning = ""
        self._silent_run = 0
        self.diagnostic_tap: Callable[[str, dict], None] | None = None   # só durante um teste pedido

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        s = self._settings()
        self._mic_enabled = bool(getattr(s, "voice_enabled", True))
        self._running = True
        if self._bus is not None:
            self._subs = [
                self._bus.subscribe(EventType.VOICE_FINISHED, self._on_voice_finished, name="voice.followup"),
                self._bus.subscribe(EventType.RESPONSE_READY, self._on_response, name="voice.response"),
            ]
        self._thread = threading.Thread(target=self._supervise, name="ultron-microphone", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._wakeup.set()
        for sub in self._subs:
            sub.unsubscribe()
        self._subs = []
        if self._thread is not None:
            self._thread.join(2.0)               # a leitura bloqueia no máximo um bloco (250 ms)
            if self._thread.is_alive():
                log.warning("captura de áudio não encerrou em 2 s; segue como daemon")
        self._thread = None
        self.capturing = False

    def health(self) -> dict:
        if not self._mic_enabled:
            return {"status": "WARN", "detail": "microfone desativado pelo usuário"}
        if self.stt is None and self.stt_reason:
            return {"status": "UNAVAILABLE", "detail": f"reconhecimento de fala: {self.stt_reason}"}
        if self.capturing and self.silence_warning:
            return {"status": "WARN", "detail": f"{self.device}: {self.silence_warning}"}
        if self.capturing:
            return {"status": "OK", "detail": f"{self.device} · {getattr(self.stt, 'label', '?')}"}
        return {"status": "UNAVAILABLE" if self.reason else "UNKNOWN", "detail": self.reason or "iniciando"}

    # ------------------------------------------------------------ controle externo
    def toggle_mic(self, enabled: bool | None = None) -> bool:
        self._mic_enabled = (not self._mic_enabled) if enabled is None else bool(enabled)
        if not self._mic_enabled:
            self._stop_listening()
            self.detector.close_followup()
            self.conversation = False
        self._wakeup.set()
        self._publish_state()
        return self._mic_enabled

    @property
    def mic_enabled(self) -> bool:
        return self._mic_enabled

    def restart(self, *, reload_stt: bool = False) -> None:
        """Reabre o microfone (e recarrega o modelo de fala, se pedido)."""
        self._reload_stt = self._reload_stt or reload_stt
        self.failures = 0
        self._restart.set()
        self._wakeup.set()

    def apply_settings(self, changed: list[str] | tuple[str, ...]) -> None:
        s = self._settings()
        if {"wake_words", "wake_variants", "wake_weak_variants", "wake_names"} & set(changed):
            self.detector.set_variants(tuple(s.wake_words), tuple(s.wake_variants), tuple(s.wake_weak_variants),
                                       tuple(getattr(s, "wake_names", DEFAULT_NAME_VARIANTS)))
        if "followup_seconds" in changed:
            self.detector.followup_seconds = float(s.followup_seconds)
        if "voice_enabled" in changed:
            self.toggle_mic(bool(s.voice_enabled))
        if {"mic_name", "mic_index", "mic_backend"} & set(changed):
            self.restart()
        if "stt_engine" in changed:
            self.restart(reload_stt=True)

    def open_followup(self, seconds: float | None = None) -> None:
        if self._mic_enabled and (seconds if seconds is not None else self.detector.followup_seconds) > 0:
            self.detector.open_followup(seconds)
            self._publish_state()

    def mic_probe(self) -> dict:
        """Leitura para o sensor de microfone e a telemetria da HUD."""
        return {
            "capturing": self.capturing, "enabled": self._mic_enabled, "device": self.device,
            "level": round(self.level, 3), "listening": self.listening, "conversation": self.conversation,
            "followup": round(self.detector.followup_remaining(), 1), "stt": getattr(self.stt, "label", None),
            "reason": self.reason or self.stt_reason or self.silence_warning, "commands": self.commands,
        }

    def counters(self) -> dict:
        """Contadores por etapa (diagnóstico). Nenhum conteúdo de fala é guardado."""
        age = time.monotonic() - self.last_chunk_at if self.last_chunk_at else None
        return {**self.stats, "commands": self.commands, "ignored": self.ignored, "echoes": self.echoes,
                "last_chunk_age": round(age, 2) if age is not None else None, "peak_level": round(self.peak_level, 3),
                "silence_warning": self.silence_warning, "failures": self.failures,
                "wake_forms": self.detector.forms, "weak_forms": self.detector.weak_forms}

    # ------------------------------------------------------------ dispositivos
    @staticmethod
    def list_devices() -> dict:
        from .audio import list_input_devices
        return list_input_devices()

    def select_device(self, name: str = "", index: int = -1, *, settings_manager=None) -> None:
        """Troca o microfone (nome exato ou índice) e reabre a captura. Persistido nas configurações."""
        if settings_manager is not None:
            settings_manager.update(mic_name=name or "", mic_index=int(index))   # dispara restart via apply_settings
        else:
            self.restart()

    # ------------------------------------------------------------ supervisor
    def _sleep(self, seconds: float) -> None:
        self._wakeup.wait(max(0.0, seconds))
        self._wakeup.clear()

    def _load_stt(self) -> None:
        self._set_state(stt_loading=True)
        try:
            if self._stt_factory is not None:
                self.stt, self.stt_reason = self._stt_factory()
            else:
                path, reason = choose_model(getattr(self._settings(), "stt_engine", "auto"))
                if path is None:
                    self.stt, self.stt_reason = None, reason
                else:
                    started = time.perf_counter()
                    self.stt, self.stt_reason = VoskSTT(path, RATE), ""
                    log.info("reconhecimento de fala: %s (%.1fs)", self.stt.label, time.perf_counter() - started)
        except ImportError:
            self.stt, self.stt_reason = None, "Vosk não instalado"
        except Exception as exc:
            self.stt, self.stt_reason = None, f"falha ao carregar o modelo de fala: {exc}"
        self._set_state(stt_loading=False, stt=getattr(self.stt, "label", None), stt_reason=self.stt_reason)

    def _open_mic(self) -> tuple:
        if self._mic_opener is not None:
            return self._mic_opener()
        from .audio import open_microphone
        s = self._settings()
        return open_microphone(rate=RATE, chunk=CHUNK, name_hint=getattr(s, "mic_name", ""),
                               index=int(getattr(s, "mic_index", -1)), log_fn=log.info,
                               backend=str(getattr(s, "mic_backend", "auto") or "auto"))

    def _supervise(self) -> None:
        while self._running:
            if not self._mic_enabled:
                self._set_capture(False, "microfone desativado")
                self._sleep(5.0)
                continue
            if self.stt is None or self._reload_stt:
                self._reload_stt = False
                self._load_stt()
                if self.stt is None:
                    self._set_capture(False, self.stt_reason)
                    self._sleep(60.0)                      # sem modelo de fala: nova tentativa rara
                    continue
            self._restart.clear()
            try:
                handle, stream, device = self._open_mic()
            except (AudioBackendMissing, ImportError):
                self._set_capture(False, "nenhuma biblioteca de áudio instalada (PyAudio ou sounddevice): "
                                         "microfone indisponível — execute INSTALL_JARVIS.bat")
                self._sleep(300.0)                          # dependência ausente não se resolve sozinha
                continue
            except Exception as exc:
                self.failures += 1
                delay = min(60.0, 2.0 ** min(self.failures, 6))
                self.retry_at = time.time() + delay
                self._set_capture(False, f"microfone indisponível: {exc}")
                if self.failures in (1, 4) or self.failures % 10 == 0:
                    log.warning("microfone indisponível (%s); nova tentativa em %.0fs", exc, delay)
                self._sleep(delay)
                continue
            self.failures, self.retry_at, self.device = 0, 0.0, device
            self._silent_run, self.silence_warning = 0, ""
            self._set_capture(True, "")
            try:
                while self._running and self._mic_enabled and not self._restart.is_set():
                    data = stream.read(CHUNK, exception_on_overflow=False)
                    if not data:
                        raise OSError("fluxo de áudio encerrado")
                    self.process_chunk(data)
            except Exception as exc:
                self.failures += 1
                log.warning("captura de áudio interrompida: %s", exc)
                self._set_capture(False, f"captura interrompida: {exc}")
                self._sleep(min(30.0, 1.0 * self.failures))
            finally:
                for closer in (getattr(stream, "stop_stream", None), getattr(stream, "close", None),
                               getattr(handle, "terminate", None)):
                    try:
                        if closer:
                            closer()
                    except Exception:
                        pass
                self.capturing = False
                self._stop_listening()

    # ------------------------------------------------------------ processamento
    def _speech_active(self) -> bool:
        sp = self.speaker
        if sp is None:
            return False
        if sp.speaking:
            self._barge_cut = False
            return True
        if self._barge_cut:
            return False
        return time.time() - float(getattr(sp, "last_spoken_at", 0.0)) < ECHO_TAIL_SECONDS

    def _spoken_text(self) -> str:
        sp = self.speaker
        if sp is None:
            return ""
        recent = getattr(sp, "recent_text", None)
        return recent() if callable(recent) else str(getattr(sp, "current_text", "") or "")

    def wake(self, text: str) -> WakeResult | None:
        """Política de ativação: forma forte sempre; forma fraca só seguida de comando reconhecido."""
        result = self.detector.detect(text)
        if not result.detected:
            return None
        if result.strength == "weak":
            if not result.command or self._command_check is None:
                return None
            try:
                if not self._command_check(result.command):
                    return None
            except Exception:
                return None
        return result

    def process_chunk(self, data: bytes) -> None:
        """Processa um bloco PCM 16 bits mono a 16 kHz (mesmo caminho para microfone e testes)."""
        now = time.monotonic()
        self.stats["chunks"] += 1
        self.last_chunk_at = now
        if not data.strip(b"\x00"):                       # zeros exatos: nenhum som chega do dispositivo
            self.stats["zero_chunks"] += 1
            self._silent_run += 1
            if self._silent_run == SILENT_CHUNKS_WARNING:
                self.silence_warning = SILENCE_REASON
                log.warning("microfone %s: silêncio absoluto por 5 s", self.device or "?")
                self._publish_state()
        elif self._silent_run:
            self._silent_run = 0
            if self.silence_warning:
                self.silence_warning = ""
                self._publish_state()
        self.level = pcm_level(data)
        self.peak_level = max(self.level, self.peak_level * 0.97)
        if self._speech_active():
            self._overlapped_speech = True
        final, partial = self.stt.accept(data)
        if partial:
            self.stats["partials"] += 1
            self._tap("partial", text=partial)
            self._on_partial(partial)
        if final:
            self.stats["finals"] += 1
            confidence = float(getattr(self.stt, "last_confidence", 0.0))
            self._tap("final", text=final, confidence=confidence)
            self._on_final(final, confidence)
        self._tick(now)

    def _tap(self, kind: str, **data: Any) -> None:
        tap = self.diagnostic_tap
        if tap is not None:
            try:
                tap(kind, data)
            except Exception:
                pass

    def flush(self) -> None:
        """Fecha a frase em andamento (fim de arquivo nos testes, ou ao parar a captura)."""
        if self.stt is not None:
            text = self.stt.finish()
            if text:
                self._on_final(text, float(getattr(self.stt, "last_confidence", 0.0)))

    def _interrupt_speech(self) -> None:
        self._barge_cut = True
        if self.speaker is not None:
            self.speaker.interrupt()

    def _on_partial(self, text: str) -> None:
        self._last_speech_at = time.monotonic()
        if self._overlapped_speech:
            if self._barged:
                return
            barge = find_barge_in(text, self._spoken_text(), self.wake)
            if barge is not None and barge[0] in ("wake", "cancel"):
                self._barged = True
                self._interrupt_speech()                       # barge-in: corta a fala imediatamente
                self._start_listening("barge-in")
            return
        if not self.listening:
            if self.detector.detect(text).strength == "strong":
                self._start_listening("wake")
            elif self.detector.in_followup():
                self._start_listening("followup")

    def _on_final(self, text: str, confidence: float) -> None:
        overlapped, barged = self._overlapped_speech, self._barged
        self._barged = False
        self._overlapped_speech = self._speech_active()
        words = _words(text)
        if not words or all(w in NOISE_WORDS for w in words):
            return
        if overlapped or barged:
            self._on_final_during_speech(text, confidence, barged)
            return
        wake = self.wake(text)
        in_followup = self.detector.in_followup()
        if wake is None and not in_followup:
            self.ignored += 1                                   # não endereçado ao JARVIS: descartado
            self._stop_listening()
            return
        command = wake.command if wake is not None else text.strip()
        if wake is not None:
            self.stats["wakes"] += 1
            self._tap("wake", matched=wake.matched, strength=wake.strength, command=command)
            self._publish(EventType.WAKE_WORD, matched=wake.matched, strength=wake.strength, command=command[:200],
                          confidence=round(confidence, 3))
            if not command:
                self._await_command()
                return
        self._dispatch(command, {"wake": wake is not None, "followup": wake is None, "barge_in": False,
                                 "confidence": round(confidence, 3), "control": classify_short_command(command)})

    def _on_final_during_speech(self, text: str, confidence: float, barged: bool) -> None:
        """Enquanto o JARVIS fala, só passam "Jarvis …" e controles curtos ditos pelo usuário."""
        barge = find_barge_in(text, self._spoken_text(), self.wake)
        if barge is None:
            if self._listen_mode == "wake" and self.listening and echo_ratio(text, self._spoken_text()) < 0.5:
                # o usuário foi convidado a falar ("Jarvis." → confirmação): a frase é o comando
                self._dispatch(text.strip(), {"wake": True, "followup": False, "barge_in": False,
                                              "confidence": round(confidence, 3),
                                              "control": classify_short_command(text)})
                return
            self.echoes += 1                                    # eco da própria voz ou fala não endereçada
            if barged:
                self._stop_listening()
            return
        kind, command = barge
        if kind in ("pause", "resume"):
            applied = self.speaker.pause() if kind == "pause" else self.speaker.resume()
            self._publish(EventType.VOICE_RECEIVED, text=command, control=kind, applied=bool(applied))
            return
        if not barged:
            self._interrupt_speech()
        if kind == "wake":
            self.stats["wakes"] += 1
            self._tap("wake", matched="barge-in", strength="strong", command=command)
            self._publish(EventType.WAKE_WORD, matched="barge-in", command=command[:200],
                          confidence=round(confidence, 3))
            if not command:
                self._await_command()
                return
        self._dispatch(command, {"wake": kind == "wake", "followup": False, "barge_in": True,
                                 "confidence": round(confidence, 3),
                                 "control": "cancel" if kind == "cancel" else classify_short_command(command)})

    def inject_text(self, text: str, *, diagnostic: bool = False) -> None:
        """Entrega um texto como se tivesse sido reconhecido: o MESMO caminho de um comando falado
        (VOICE_RECEIVED → on_command → Neural Core). Usado pelo diagnóstico de voz."""
        self._dispatch(" ".join(str(text or "").split()), {
            "wake": True, "followup": False, "barge_in": False, "confidence": 1.0,
            "control": classify_short_command(text), "diagnostic": diagnostic})

    def _await_command(self) -> None:
        """Só a palavra de ativação: abre a escuta para o comando que vem a seguir."""
        self.conversation = True
        self.detector.open_followup(max(WAKE_ONLY_WINDOW, self.detector.followup_seconds))
        self._start_listening("wake")

    def _dispatch(self, command: str, meta: dict) -> None:
        self.commands += 1
        self.last_command, self.last_confidence = command, meta.get("confidence", 0.0)
        self.conversation = True
        self._awaiting_since = time.monotonic()
        self.detector.close_followup()                         # reaberta após a resposta
        self._stop_listening()
        self._publish(EventType.VOICE_RECEIVED, text=command, **meta)
        if self._on_command is not None:
            try:
                self._on_command(command, dict(meta, source="voice"))
                self.stats["delivered"] += 1
                self._tap("delivered", text=command)
            except Exception:
                log.exception("falha ao entregar comando de voz")

    def _tick(self, now: float) -> None:
        if self.listening and now - max(self._listening_since, self._last_speech_at) > LISTEN_TIMEOUT \
                and not self.detector.in_followup():
            self._stop_listening()
        if self.conversation and not self.detector.in_followup() and not self._speech_active():
            if self._awaiting_since and now - self._awaiting_since < AWAIT_RESPONSE_SECONDS:
                return                                          # a resposta ainda está a caminho
            runtime = self._state.runtime_state if self._state is not None else "IDLE"
            if runtime in ("IDLE", "LISTENING"):
                self.conversation = False                      # silêncio após a resposta: fim da conversa
                self._awaiting_since = 0.0
                self._publish_state()

    # ------------------------------------------------------------ eventos da resposta
    def _response_delivered(self) -> None:
        self._awaiting_since = 0.0
        self.open_followup()

    def _on_voice_finished(self, event) -> None:
        if not self.conversation or event.get("interrupted") or event.get("pending"):
            return
        runtime = self._state.runtime_state if self._state is not None else "IDLE"
        if runtime in ("IDLE", "LISTENING", "SPEAKING"):        # fala de progresso no meio de uma tarefa não abre
            self._response_delivered()

    def _on_response(self, event) -> None:
        speaker_ok = self.speaker is not None and getattr(self.speaker, "available", False) \
            and not getattr(self.speaker, "muted", False)
        if self.conversation and not event.get("partial") and (not speaker_ok or not event.get("voice", True)):
            self._response_delivered()

    # ------------------------------------------------------------ estado e eventos
    def _start_listening(self, mode: str) -> None:
        now = time.monotonic()
        self._listening_since = now
        self._listen_mode = mode if mode == "wake" or not self.listening else self._listen_mode
        if self.listening:
            return
        self.listening = True
        self._publish(EventType.LISTENING_STARTED, mode=mode)
        if self._state is not None and self._state.runtime_state in ("IDLE", "SPEAKING", "DREAMING"):
            self._state.set_runtime_state("LISTENING", mode, source="voice")
        self._publish_state()

    def _stop_listening(self) -> None:
        if not self.listening:
            return
        self.listening = False
        self._listen_mode = ""
        self._publish(EventType.LISTENING_STOPPED)
        if self._state is not None and self._state.runtime_state == "LISTENING":
            self._state.set_runtime_state("IDLE", "", source="voice")
        self._publish_state()

    def _set_capture(self, capturing: bool, reason: str) -> None:
        changed = capturing != self.capturing or reason != self.reason
        self.capturing, self.reason = capturing, reason
        if changed:
            self._publish_state()

    def _set_state(self, **values: Any) -> None:
        if self._state is not None:
            self._state.merge("voice_state", values, _source="voice")

    def _publish_state(self) -> None:
        probe = self.mic_probe()
        probe.pop("level", None)                               # o nível é lido por consulta, não por evento
        self._set_state(**{f"mic_{k}" if k in ("enabled", "device", "reason") else k: v for k, v in probe.items()})

    def _publish(self, kind: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(kind, payload, source="voice")
