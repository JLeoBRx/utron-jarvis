"""DIAGNÓSTICO DE VOZ — as oito etapas do caminho microfone → cérebro → fala, com evidência.

1. microfone detectado          (lista real de dispositivos de entrada)
2. dispositivo selecionado      (qual será/está aberto, pela regra nome → índice → padrão)
3. captura funcionando          (blocos chegando, nível, silêncio absoluto = privacidade/mudo)
4. mecanismo STT disponível     (Vosk importável e modelos presentes)
5. modelo de português carregado
6. palavra de ativação detectada (só no teste com fala: o usuário diz "Jarvis…")
7. texto entregue ao cérebro    (USER_INPUT com origem voz chega ao Neural Core)
8. resposta produzida e reproduzida (RESPONSE_READY + VOICE_FINISHED com fala real)

Nada é presumido: uma etapa sem evidência fica FAIL, WARN ou SKIPPED com o motivo. O teste
roda numa thread de trabalho (nunca na da interface) e cada leitura tem prazo.
Privacidade: o texto ouvido só é mostrado durante o teste pedido pelo usuário.
"""
from __future__ import annotations

import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..core.events import EventType

STEPS = (
    ("mic_detected", "Microfone detectado"),
    ("device_selected", "Dispositivo selecionado"),
    ("capture", "Captura de áudio"),
    ("stt_engine", "Mecanismo de reconhecimento (STT)"),
    ("pt_model", "Modelo de português carregado"),
    ("wake", "Palavra de ativação \"Jarvis\""),
    ("delivery", "Texto entregue ao cérebro"),
    ("response", "Resposta produzida e reproduzida"),
)
PROBE_COMMAND = "que horas são"           # resposta direta, sem efeito colateral


@dataclass
class Step:
    key: str
    title: str
    status: str = "PENDING"               # OK | WARN | FAIL | SKIPPED | PENDING
    detail: str = ""
    hint: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class VoiceDiagnostics:
    def __init__(self, core, *, on_step: Callable[[Step], None] | None = None, cancel=None):
        self.core = core
        self.on_step = on_step
        self.cancel = cancel
        self.steps = {key: Step(key, title) for key, title in STEPS}
        self.heard: list[str] = []

    # ------------------------------------------------------------ utilidades
    def _set(self, key: str, status: str, detail: str, hint: str = "", **data: Any) -> Step:
        step = self.steps[key]
        step.status, step.detail, step.hint = status, detail, hint
        step.data.update(data)
        if self.on_step is not None:
            try:
                self.on_step(step)
            except Exception:
                pass
        return step

    def _cancelled(self) -> bool:
        return bool(self.cancel is not None and getattr(self.cancel, "cancelled", False))

    @property
    def pipeline(self):
        return getattr(self.core, "voice", None) if getattr(self.core, "enable_voice", True) else None

    # ------------------------------------------------------------ execução
    def run(self, *, interactive: bool = False, listen_seconds: float = 10.0,
            prompt: Callable[[str], None] | None = None, probe_response: bool = True) -> dict:
        started = time.time()
        devices = self.check_devices()
        self.check_capture(devices)
        self.check_stt()
        if interactive and not self._cancelled():
            self.check_wake_interactive(listen_seconds, prompt)
        else:
            self._set("wake", "SKIPPED", "teste sem fala: diga \"Jarvis\" no teste com fala para verificar",
                      wakes=(self.pipeline.stats.get("wakes", 0) if self.pipeline is not None else 0))
            if probe_response and not self._cancelled():
                self.check_delivery_and_response()
            else:
                self._set("delivery", "SKIPPED", "não solicitado")
                self._set("response", "SKIPPED", "não solicitado")
        statuses = [s.status for s in self.steps.values()]
        overall = "FAIL" if "FAIL" in statuses else ("WARN" if "WARN" in statuses else "OK")
        return {"overall": overall, "steps": [s.to_dict() for s in self.steps.values()], "heard": list(self.heard),
                "devices": devices.get("devices", []), "backend": devices.get("backend"),
                "counters": self.pipeline.counters() if self.pipeline is not None else {},
                "seconds": round(time.time() - started, 1), "at": started}

    # ------------------------------------------------------------ 1 e 2
    def check_devices(self) -> dict:
        from .audio import _candidates, list_input_devices
        settings = self.core.settings()
        backend = str(getattr(settings, "mic_backend", "auto") or "auto")
        listing = list_input_devices(backend)
        devices = listing.get("devices", [])
        if listing.get("backend") is None:
            self._set("mic_detected", "FAIL", "nenhuma biblioteca de áudio utilizável: " + "; ".join(listing["errors"]),
                      "Instale as dependências com INSTALL_JARVIS.bat (PyAudio ou sounddevice).")
            self._set("device_selected", "SKIPPED", "sem biblioteca de áudio")
            return listing
        if not devices:
            self._set("mic_detected", "FAIL", f"nenhum dispositivo de entrada visível ({listing['backend']})",
                      "Conecte um microfone e confira em Configurações > Sistema > Som > Entrada.")
            self._set("device_selected", "SKIPPED", "nenhum dispositivo")
            return listing
        self._set("mic_detected", "OK", f"{len(devices)} dispositivo(s) de entrada via {listing['backend']}",
                  devices=[f"{d['index']}: {d['name']} ({d['host_api']})" for d in devices])
        name_hint, index = str(getattr(settings, "mic_name", "") or ""), int(getattr(settings, "mic_index", -1))
        candidates = _candidates(devices, listing.get("default"), name_hint, index)
        pipeline = self.pipeline
        if pipeline is not None and pipeline.capturing:
            self._set("device_selected", "OK", f"em uso: {pipeline.device}",
                      configured=name_hint or (index if index >= 0 else "padrão do sistema"))
        elif candidates:
            note = "" if pipeline is None else f" (captura parada: {pipeline.reason or 'iniciando'})"
            status = "WARN" if note else "OK"
            self._set("device_selected", status, f"seria aberto: {candidates[0]['name']}{note}",
                      "Escolha outro microfone na lista se este não for o correto." if note else "")
        else:
            self._set("device_selected", "FAIL",
                      f"o microfone configurado ({name_hint or index}) não foi encontrado e não há padrão do sistema",
                      "Escolha um dispositivo da lista (HUB > Voz > Microfone ou --mic).")
        return listing

    # ------------------------------------------------------------ 3
    def check_capture(self, listing: dict, seconds: float = 1.5) -> None:
        pipeline = self.pipeline
        if pipeline is None:
            self._set("capture", "SKIPPED", "voz desativada nesta execução (--no-voice)")
            return
        if not pipeline.mic_enabled:
            self._set("capture", "WARN", "microfone desligado pelo usuário (botão MIC)", "Ligue o MIC para testar.")
            return
        if pipeline.capturing:
            before = dict(pipeline.stats)
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and not self._cancelled():
                time.sleep(0.05)
            chunks = pipeline.stats["chunks"] - before["chunks"]
            zeros = pipeline.stats["zero_chunks"] - before["zero_chunks"]
            self._capture_verdict(chunks, zeros, pipeline.peak_level, source="captura do JARVIS")
            return
        if listing.get("backend") is None or not listing.get("devices"):
            self._set("capture", "FAIL", f"captura parada: {pipeline.reason or 'sem dispositivo'}")
            return
        self._probe_open(seconds)

    def _probe_open(self, seconds: float) -> None:
        """Captura parada: abre um fluxo temporário só para medir (fechado em seguida)."""
        from ..perception.microphone import pcm_level
        from .audio import open_microphone
        settings = self.core.settings()
        try:
            handle, stream, name = open_microphone(rate=16000, chunk=4000, name_hint=getattr(settings, "mic_name", ""),
                                                   index=int(getattr(settings, "mic_index", -1)),
                                                   backend=str(getattr(settings, "mic_backend", "auto") or "auto"))
        except Exception as exc:
            self._set("capture", "FAIL", f"não foi possível abrir o microfone: {exc}",
                      "Feche outros programas que usam o microfone ou escolha outro dispositivo.")
            return
        chunks = zeros = 0
        peak = 0.0
        try:
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline and not self._cancelled():
                data = stream.read(4000, exception_on_overflow=False)
                chunks += 1
                if not data.strip(b"\x00"):
                    zeros += 1
                peak = max(peak, pcm_level(data))
        except Exception as exc:
            self._set("capture", "FAIL", f"leitura falhou em {name}: {exc}")
            return
        finally:
            for closer in (getattr(stream, "stop_stream", None), getattr(stream, "close", None),
                           getattr(handle, "terminate", None)):
                try:
                    if closer:
                        closer()
                except Exception:
                    pass
        self._capture_verdict(chunks, zeros, peak, source=f"teste temporário em {name}")

    def _capture_verdict(self, chunks: int, zeros: int, peak: float, *, source: str) -> None:
        if chunks <= 0:
            self._set("capture", "FAIL", f"nenhum bloco de áudio recebido ({source})",
                      "O dispositivo travou; reinicie a voz ou escolha outro microfone.")
        elif zeros >= chunks:
            self._set("capture", "WARN", f"{chunks} blocos recebidos, todos em silêncio absoluto ({source})",
                      "Windows: Configurações > Privacidade e segurança > Microfone > permitir que aplicativos da "
                      "área de trabalho acessem o microfone; confira também se o microfone não está mudo.",
                      chunks=chunks, zeros=zeros)
        else:
            self._set("capture", "OK", f"{chunks} blocos recebidos; pico de nível {peak:.0%} ({source})",
                      "" if peak > 0.05 else "Nível muito baixo: aproxime-se ou aumente o ganho do microfone.",
                      chunks=chunks, zeros=zeros, peak=round(peak, 3))

    # ------------------------------------------------------------ 4 e 5
    def check_stt(self) -> None:
        import importlib.util

        from .stt import choose_model
        if importlib.util.find_spec("vosk") is None:
            self._set("stt_engine", "FAIL", "Vosk não instalado", "Execute INSTALL_JARVIS.bat.")
            self._set("pt_model", "SKIPPED", "sem mecanismo de reconhecimento")
            return
        engine = str(getattr(self.core.settings(), "stt_engine", "auto") or "auto")
        path, reason = choose_model(engine)
        if path is None:
            self._set("stt_engine", "OK", f"Vosk disponível (modo {engine})")
            self._set("pt_model", "FAIL", reason,
                      "Coloque os modelos Vosk em português em assets/stt (veja VOICE_DIAGNOSTICS.md).")
            return
        self._set("stt_engine", "OK", f"Vosk disponível (modo {engine}); modelo escolhido: {path.name}")
        pipeline = self.pipeline
        stt = getattr(pipeline, "stt", None) if pipeline is not None else None
        if stt is not None:
            self._set("pt_model", "OK", f"carregado: {getattr(stt, 'label', path.name)}")
            return
        if pipeline is not None and pipeline.stt_reason:
            self._set("pt_model", "FAIL", pipeline.stt_reason)
            return
        started = time.perf_counter()
        try:
            from .stt import VoskSTT
            VoskSTT(path, 16000)
        except Exception as exc:
            self._set("pt_model", "FAIL", f"falha ao carregar {path.name}: {exc}")
            return
        self._set("pt_model", "OK", f"{path.name} carrega em {time.perf_counter() - started:.1f} s "
                                    "(a captura ainda não o usava)")

    # ------------------------------------------------------------ 6, 7 e 8 com fala real
    def check_wake_interactive(self, seconds: float, prompt: Callable[[str], None] | None) -> None:
        pipeline = self.pipeline
        if pipeline is None or not pipeline.capturing or pipeline.stt is None:
            for key in ("wake", "delivery", "response"):
                self._set(key, "SKIPPED", "captura ou reconhecimento indisponível (veja as etapas acima)")
            return
        events: queue.Queue = queue.Queue()
        pipeline.diagnostic_tap = lambda kind, data: events.put((kind, data))
        subs = [self.core.bus.subscribe(EventType.USER_INPUT, lambda e: events.put(("input", e.payload)),
                                        name="voice.diag.input"),
                self.core.bus.subscribe(EventType.RESPONSE_READY, lambda e: events.put(("response", e.payload)),
                                        name="voice.diag.response"),
                self.core.bus.subscribe(EventType.VOICE_FINISHED, lambda e: events.put(("spoken", e.payload)),
                                        name="voice.diag.spoken")]
        if prompt is not None:
            prompt(f"Diga agora: \"Jarvis, {PROBE_COMMAND}?\" (até {seconds:.0f} s)")
        woke = delivered = responded = spoke = None
        deadline = time.monotonic() + seconds
        try:
            while time.monotonic() < deadline and not self._cancelled():
                try:
                    kind, data = events.get(timeout=0.2)
                except queue.Empty:
                    continue
                if kind == "final":
                    self.heard.append(data.get("text", ""))
                elif kind == "wake" and woke is None:
                    woke = data
                    deadline = max(deadline, time.monotonic() + 12.0)
                elif kind == "input" and data.get("source") == "voice" and delivered is None:
                    delivered = data
                elif kind == "response" and delivered is not None and not data.get("partial") and responded is None:
                    responded = data
                    if not data.get("voice"):
                        break                      # sem fala nesta resposta: nada mais a esperar
                elif kind == "spoken" and responded is not None:
                    spoke = data
                    break
        finally:
            pipeline.diagnostic_tap = None
            for sub in subs:
                sub.unsubscribe()
        heard = "; ".join(f"“{h}”" for h in self.heard[-4:]) or "nada"
        if woke is not None:
            self._set("wake", "OK", f"ativado por “{woke.get('matched')}” ({woke.get('strength')}); ouvido: {heard}")
        else:
            self._set("wake", "FAIL" if not self.heard else "WARN", f"palavra de ativação não reconhecida; ouvido: {heard}",
                      "Rode a calibração (HUB > Voz > Calibrar ou python -m ultron.voice.calibrate) para o JARVIS "
                      "aprender como o reconhecedor ouve a sua pronúncia.")
        if delivered is not None:
            self._set("delivery", "OK", f"o Neural Core recebeu: “{delivered.get('text', '')}”")
        else:
            self._set("delivery", "FAIL" if woke is not None else "SKIPPED",
                      "nenhum comando de voz chegou ao núcleo" if woke is not None else "sem ativação")
        self._response_verdict(responded, spoke, delivered is not None)

    def check_delivery_and_response(self, timeout: float = 15.0) -> None:
        """Sem fala: injeta um texto reconhecido pelo MESMO caminho da voz e acompanha até a fala."""
        pipeline = self.pipeline
        if pipeline is None:
            self._set("delivery", "SKIPPED", "voz desativada nesta execução")
            self._set("response", "SKIPPED", "voz desativada nesta execução")
            return
        events: queue.Queue = queue.Queue()
        subs = [self.core.bus.subscribe(EventType.USER_INPUT, lambda e: events.put(("input", e.payload)),
                                        name="voice.diag.input"),
                self.core.bus.subscribe(EventType.RESPONSE_READY, lambda e: events.put(("response", e.payload)),
                                        name="voice.diag.response"),
                self.core.bus.subscribe(EventType.VOICE_FINISHED, lambda e: events.put(("spoken", e.payload)),
                                        name="voice.diag.spoken")]
        delivered = responded = spoke = None
        try:
            pipeline.inject_text(PROBE_COMMAND, diagnostic=True)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and not self._cancelled():
                try:
                    kind, data = events.get(timeout=0.2)
                except queue.Empty:
                    continue
                if kind == "input" and data.get("source") == "voice" and delivered is None:
                    delivered = data
                elif kind == "response" and delivered is not None and not data.get("partial") and responded is None:
                    responded = data
                    if not data.get("voice"):
                        break
                elif kind == "spoken" and responded is not None:
                    spoke = data
                    break
        finally:
            for sub in subs:
                sub.unsubscribe()
        if delivered is not None:
            self._set("delivery", "OK", f"texto de teste “{PROBE_COMMAND}” chegou ao núcleo pela rota da voz")
        else:
            self._set("delivery", "FAIL", "o texto de teste não chegou ao núcleo em 15 s")
        self._response_verdict(responded, spoke, delivered is not None)

    def _response_verdict(self, responded: dict | None, spoke: dict | None, delivered: bool) -> None:
        speaker = getattr(self.core, "speaker", None)
        output = getattr(self.core, "audio_out", None)
        if responded is None:
            self._set("response", "FAIL" if delivered else "SKIPPED",
                      "nenhuma resposta produzida" if delivered else "nada foi entregue ao núcleo")
            return
        text = str(responded.get("text", ""))[:120]
        if spoke is not None and spoke.get("spoken"):
            self._set("response", "OK", f"resposta “{text}” falada ({getattr(output, 'backend', '?')})")
        elif speaker is not None and getattr(speaker, "muted", False):
            self._set("response", "WARN", f"resposta “{text}” produzida; voz desligada pelo usuário (botão VOZ)")
        elif spoke is not None:
            self._set("response", "FAIL", f"resposta “{text}” produzida, mas não reproduzida: {spoke.get('reason', '')}",
                      "Confira a saída de áudio padrão do Windows e a voz instalada (assets/voices).")
        else:
            reason = getattr(speaker, "reason", "") or getattr(output, "reason", "") or "sem confirmação de reprodução"
            self._set("response", "WARN" if responded.get("voice") else "FAIL",
                      f"resposta “{text}” produzida; reprodução não confirmada ({reason})")


def format_report(report: dict) -> str:
    marks = {"OK": "OK  ", "WARN": "AVISO", "FAIL": "FALHA", "SKIPPED": "—   ", "PENDING": "…   "}
    lines = [f"DIAGNÓSTICO DE VOZ: {report['overall']} ({report['seconds']} s)"]
    for i, step in enumerate(report["steps"], 1):
        lines.append(f" {i}. [{marks.get(step['status'], step['status'])}] {step['title']}: {step['detail']}")
        if step.get("hint") and step["status"] != "OK":
            lines.append(f"      → {step['hint']}")
    if report.get("devices"):
        lines.append("Microfones: " + "; ".join(f"{d['index']}: {d['name']}" for d in report["devices"][:10]))
    return "\n".join(lines)


def run_in_background(core, *, interactive: bool = False, on_step=None, on_done=None, cancel=None) -> threading.Thread:
    """Executa o diagnóstico numa thread própria (a interface nunca espera)."""
    def work() -> None:
        try:
            report = VoiceDiagnostics(core, on_step=on_step, cancel=cancel).run(interactive=interactive)
        except Exception as exc:                       # o diagnóstico nunca derruba a interface
            report = {"overall": "FAIL", "steps": [], "error": f"{type(exc).__name__}: {exc}", "seconds": 0,
                      "devices": []}
        if on_done is not None:
            on_done(report)

    thread = threading.Thread(target=work, name="jarvis-voice-diagnostics", daemon=True)
    thread.start()
    return thread
