"""Agente da MATRIZ-MÃE — liga o JARVIS deste computador à JARVIS WEB ORB, por uma conexão de SAÍDA.

* Conecta-se ao gateway (``remote_gateway_url``) por WSS com um token obtido na inscrição (guardado no cofre do
  sistema, nunca em arquivo de configuração). Nenhuma porta é aberta neste computador ou no roteador.
* É o MESMO NeuralCore: o que chega da ORBE vira ``core.submit(..., source="remoto")`` — mesma memória, mesmas
  ferramentas, mesmo executor, mesmas permissões e o mesmo histórico de atividades. Não existe um segundo cérebro.
* Envia à ORBE só o que é REAL: o estado resolvido do núcleo, a persona (JARVIS/ULTRON), a autorização pendente,
  as linhas da conversa e, se o dispositivo pedir, a voz (a MESMA identidade vocal, sintetizada aqui).
* Autorizações: o dispositivo pode responder pedidos comuns; ações sensíveis (categorias sensíveis, apagar dados,
  risco alto) só se confirmam no computador principal.
* Pareamento: o computador pede um código ao gateway, mostra QR/código, e quem decide é o usuário AQUI.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import threading
import time
import urllib.error
import urllib.request
import wave
from typing import Any, Callable

import numpy as np

from ..core.events import EventType

log = logging.getLogger("ultron.remote")

TOKEN_NAME = "remote_agent_token"
STATE_MAP = {
    "IDLE": "aguardando", "DREAMING": "aguardando", "BOOTING": "inicializando", "LISTENING": "escutando",
    "PERCEIVING": "pensando", "CONTEXT": "pensando", "DECIDING": "pensando", "THINKING": "pensando",
    "PLANNING": "pensando", "IMAGINING": "pensando", "SIMULATING": "pensando", "NETWORK": "pensando",
    "SPEAKING": "falando", "EXECUTING": "executando", "VERIFYING": "executando", "RECOVERY": "executando",
    "AWAITING_AUTHORIZATION": "confirmacao", "ERROR": "erro", "REMINDING": "alerta", "SHUTDOWN": "aguardando",
}
LABELS = {"aguardando": "EM ESPERA", "inicializando": "INICIALIZANDO", "escutando": "ESCUTANDO", "pensando": "PENSANDO",
          "falando": "FALANDO", "executando": "EXECUTANDO", "confirmacao": "AGUARDANDO AUTORIZAÇÃO", "erro": "ERRO",
          "alerta": "ALERTA", "privacidade": "PRIVACIDADE"}
COLORS = {"aguardando": (0, 217, 255), "inicializando": (0, 217, 255), "escutando": (103, 243, 255),
          "pensando": (22, 139, 255), "falando": (103, 243, 255), "executando": (22, 139, 255),
          "confirmacao": (255, 181, 71), "erro": (255, 93, 115), "alerta": (255, 181, 71), "privacidade": (61, 88, 115)}
WATCH = (EventType.STATE_CHANGED, EventType.RESPONSE_READY, EventType.USER_INPUT, EventType.AUTHORIZATION_REQUIRED,
         EventType.AUTHORIZATION_RESOLVED, EventType.PERSONA_CHANGED)


def remote_ok(request) -> bool:
    """O dispositivo remoto pode responder a este pedido? Sensível, apagar dados e risco alto: só no computador."""
    if request is None:
        return False
    return (not getattr(request, "category", "") and getattr(request, "permission", "") != "apagar_dados"
            and str(getattr(request, "risk", "")).lower() not in ("high", "critical", "alto", "crítico"))


def wav_bytes(samples: np.ndarray, rate: int) -> bytes:
    data = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(int(rate)); w.writeframes(data)
    return buffer.getvalue()


def read_wav_16k(raw: bytes) -> np.ndarray:
    """WAV PCM 16 bits (do navegador) → mono float32 a 16 kHz."""
    with wave.open(io.BytesIO(raw), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("áudio precisa ser PCM de 16 bits")
        rate, channels = w.getframerate(), w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32767.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != 16000 and len(data):
        positions = np.arange(0, len(data), rate / 16000.0)
        data = np.interp(positions, np.arange(len(data)), data).astype(np.float32)
    return data


class RemoteAgent:
    name = "remote_agent"

    def __init__(self, core, *, settings_getter: Callable[[], Any], token_getter: Callable[[], str] | None = None,
                 token_setter: Callable[[str], Any] | None = None, opener=None):
        from ..platform import credentials
        self.core = core
        self._settings = settings_getter
        self._get_token = token_getter or (lambda: credentials.get_secret(TOKEN_NAME))
        self._set_token = token_setter or (lambda value: credentials.set_secret(TOKEN_NAME, value))
        self._open = opener or urllib.request.urlopen
        self.loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ws = None
        self._stop = threading.Event()
        self._subs: list = []
        self._waiters: dict[str, list] = {}
        self.audio_pref: dict[str, bool] = {}
        self.devices_online: dict[str, str] = {}
        self.devices: list[dict] = []
        self.connected = False
        self.error = ""
        self.last_state: dict = {}
        self._last_device = ""
        self._stt = None
        self.on_pair_claim: Callable[[dict], None] | None = None      # a interface pergunta ao usuário
        self.on_change: Callable[[], None] | None = None              # status/dispositivos mudaram

    # ------------------------------------------------------------ configuração e inscrição
    @property
    def url(self) -> str:
        return str(getattr(self._settings(), "remote_gateway_url", "") or "").rstrip("/")

    def configured(self) -> bool:
        return bool(self.url and self._get_token())

    def enabled(self) -> bool:
        return bool(getattr(self._settings(), "remote_enabled", False)) and self.configured()

    def enroll(self, url: str, secret: str, name: str = "JARVIS") -> tuple[bool, str]:
        """Troca o segredo de inscrição (digitado UMA vez) por um token guardado no cofre do sistema."""
        url = str(url or "").strip().rstrip("/")
        if not url.startswith("https://") and not url.startswith(("http://127.0.0.1", "http://localhost")):
            return False, "o endereço do gateway precisa ser HTTPS"
        request = urllib.request.Request(f"{url}/api/agent/enroll", method="POST",
                                         data=json.dumps({"secret": secret, "name": name}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"})
        try:
            with self._open(request, timeout=20) as response:
                token = json.loads(response.read().decode("utf-8")).get("token", "")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:160] if hasattr(exc, "read") else ""
            return False, f"o gateway recusou ({exc.code}): {detail}"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            return False, f"gateway inacessível: {getattr(exc, 'reason', exc)}"
        if not token:
            return False, "resposta inválida do gateway"
        self._set_token(token)
        return True, "matriz-mãe inscrita no gateway"

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return True
        if not self.enabled():
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="ultron-remote", daemon=True)
        self._thread.start()
        bus = getattr(self.core, "bus", None)
        if bus is not None and not self._subs:
            self._subs = [bus.subscribe(list(WATCH), self._on_event, name="remote.agent")]
        return True

    def stop(self) -> None:
        self._stop.set()
        for sub in self._subs:
            sub.unsubscribe()
        self._subs = []
        loop = self.loop
        if loop is not None and self._ws is not None:
            asyncio.run_coroutine_threadsafe(self._ws.close(), loop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._thread = None
        self.connected = False

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def status(self) -> dict:
        return {"enabled": bool(getattr(self._settings(), "remote_enabled", False)), "configured": self.configured(),
                "connected": self.connected, "gateway": self.url, "error": self.error,
                "online_devices": len(self.devices_online), "devices": len(self.devices)}

    def _run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main())
        finally:
            self.loop.close()
            self.loop = None

    async def _main(self) -> None:
        import websockets
        delay = 1.0
        while not self._stop.is_set():
            url = self.url.replace("https://", "wss://").replace("http://", "ws://") + "/ws/agent"
            try:
                async with websockets.connect(url, additional_headers={"Authorization": f"Bearer {self._get_token()}"},
                                              max_size=4 * 1024 * 1024, open_timeout=15, ping_interval=25) as ws:
                    self._ws, self.connected, self.error, delay = ws, True, "", 1.0
                    self._publish_status()
                    await ws.send(json.dumps({"type": "hello", "name": "JARVIS"}))
                    await ws.send(json.dumps(self.snapshot()))
                    await ws.send(json.dumps({"type": "devices"}))
                    async for raw in ws:
                        await self._handle(json.loads(raw))
            except Exception as exc:                       # rede, recusa, gateway reiniciando: tenta de novo
                status = getattr(getattr(exc, "response", None), "status_code", None)
                self.error = "token recusado pelo gateway (inscreva de novo)" if status == 401 else str(exc)[:200]
                log.info("conexão com o gateway: %s", self.error)
            finally:
                self._ws, self.connected = None, False
                self.devices_online.clear()
                self._publish_status()
            if self._stop.wait(delay):
                break
            delay = min(60.0, delay * 2)

    def _publish_status(self) -> None:
        state = getattr(self.core, "state", None)
        if state is not None:
            try:
                state.update(_source="remote", remote=self.status())
            except Exception:
                pass
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                log.debug("on_change falhou", exc_info=True)

    def _send(self, message: dict) -> bool:
        loop, ws = self.loop, self._ws
        if loop is None or ws is None:
            return False
        asyncio.run_coroutine_threadsafe(ws.send(json.dumps(message, ensure_ascii=False)), loop)
        return True

    def _request(self, message: dict, reply_type: str, timeout: float = 10.0) -> dict | None:
        """Pedido ao gateway com resposta (código de pareamento, lista de dispositivos)."""
        waiter = {"event": threading.Event(), "value": None}
        self._waiters.setdefault(reply_type, []).append(waiter)
        if not self._send(message):
            self._waiters[reply_type].remove(waiter)
            return None
        waiter["event"].wait(timeout)
        return waiter["value"]

    # ------------------------------------------------------------ pareamento e dispositivos (a interface chama)
    def request_pairing(self) -> dict | None:
        return self._request({"type": "pair_request"}, "pair_code")

    def decide_pairing(self, pairing_id: str, approve: bool) -> bool:
        return self._send({"type": "pair_decision", "id": pairing_id, "approve": bool(approve)})

    def refresh_devices(self) -> list[dict]:
        result = self._request({"type": "devices"}, "devices")
        return list((result or {}).get("list") or self.devices)

    def revoke(self, device_id: str) -> bool:
        return self._send({"type": "revoke", "device": device_id})

    # ------------------------------------------------------------ do gateway
    async def _handle(self, data: dict) -> None:
        kind = data.get("type")
        for waiter in self._waiters.pop(kind, []):
            waiter["value"] = data
            waiter["event"].set()
        if kind == "devices":
            self.devices = list(data.get("list") or [])
            self._publish_status()
        elif kind == "pair_claim" and self.on_pair_claim:
            self.on_pair_claim(dict(data))
        elif kind == "device_online":
            self.devices_online[str(data.get("device"))] = str(data.get("name") or "")
            self._publish_status()
            await self._ws.send(json.dumps(self.snapshot()))
        elif kind == "device_offline":
            self.devices_online.pop(str(data.get("device")), None)
            self._publish_status()
        elif kind == "say":
            self._last_device = str(data.get("device") or "")
            name = str(data.get("name") or "remoto")
            accepted = self.core.submit(str(data.get("text") or "")[:2000], source="remoto", meta={"device": name})
            if not accepted:
                await self._ws.send(json.dumps({"type": "notice", "device": self._last_device,
                                                "text": "A matriz-mãe não aceitou o pedido agora (ocupada ou desligando)."}))
        elif kind == "cancel":
            self.core.cancel("interrompido pelo dispositivo remoto")
        elif kind == "authorize":
            await self._authorize(data)
        elif kind == "audio":
            self._last_device = str(data.get("device") or "")
            asyncio.get_running_loop().run_in_executor(None, self._transcribe, data)
        elif kind == "audio_pref":
            self.audio_pref[str(data.get("device"))] = bool(data.get("on"))

    async def _authorize(self, data: dict) -> None:
        pending = self.core.authorizations.pending()
        device = str(data.get("device") or "")
        if pending is None or str(pending.id) != str(data.get("id")):
            await self._ws.send(json.dumps({"type": "notice", "device": device, "text": "Esse pedido já foi resolvido."}))
            return
        if not remote_ok(pending):
            await self._ws.send(json.dumps({"type": "notice", "device": device,
                                            "text": "Ação sensível: confirme no computador principal."}))
            return
        self.core.authorizations.resolve(bool(data.get("approve")), by=f"remoto: {data.get('name') or device}",
                                         request_id=pending.id)

    def _transcribe(self, data: dict) -> None:
        """Voz do navegador → o MESMO reconhecedor (Vosk) da matriz-mãe → o mesmo caminho de um pedido."""
        device = str(data.get("device") or "")
        try:
            samples = read_wav_16k(base64.b64decode(str(data.get("wav_b64") or ""), validate=True))
            if self._stt is None:
                from ..config import paths
                from ..voice.stt import LARGE, SMALL, VoskSTT
                model = next((paths.stt_models_dir() / m for m in (SMALL, LARGE)
                              if (paths.stt_models_dir() / m / "final.mdl").is_file()), None)
                if model is None:
                    raise RuntimeError("modelo de reconhecimento de fala ausente na matriz-mãe")
                self._stt = VoskSTT(model)
            self._stt.reset()
            pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()
            for i in range(0, len(pcm), 8000):
                self._stt.accept(pcm[i:i + 8000])
            text = self._stt.finish()
        except Exception as exc:
            self._send({"type": "notice", "device": device, "text": f"Voz não reconhecida: {exc}"[:200]})
            return
        if not text:
            self._send({"type": "notice", "device": device, "text": "Não entendi o áudio. Tente de novo."})
            return
        self.core.submit(text, source="remoto (voz)", meta={"device": str(data.get("name") or "remoto")})

    # ------------------------------------------------------------ do núcleo para a ORBE
    def snapshot(self) -> dict:
        state = getattr(self.core, "state", None)
        runtime = str(getattr(state, "runtime_state", "IDLE") or "IDLE")
        key = STATE_MAP.get(runtime, "aguardando")
        if getattr(self.core, "privacy_shield", False):
            key = "privacidade"
        pending = self.core.authorizations.pending() if hasattr(self.core, "authorizations") else None
        auth = None
        if pending is not None:
            key = "confirmacao"
            auth = {"id": pending.id, "description": str(pending.description)[:300], "remote_ok": remote_ok(pending)}
        persona = dict(state.get("persona") or {}) if state is not None else {}
        reason = str(state.get("runtime_reason") or "")[:120] if state is not None else ""
        color = COLORS.get(key, COLORS["aguardando"])
        return {"type": "state", "state": key, "label": LABELS.get(key, key.upper()), "detail": reason,
                "rgb": list(color), "iris": list(color), "persona": persona or {"name": "jarvis"},
                "authorization": auth}

    def _on_event(self, event) -> None:
        if not self.connected:
            return
        kind = event.type
        payload = event.payload or {}
        if kind == EventType.USER_INPUT:
            self._send({"type": "line", "role": "user", "text": str(payload.get("text") or "")[:2000],
                        "source": str(payload.get("source") or ""), "at": time.time()})
            return
        if kind == EventType.RESPONSE_READY:
            if payload.get("partial"):
                return
            from ..cognition.provenance import line
            text = str(payload.get("text") or "")[:4000]
            self._send({"type": "line", "role": "jarvis", "text": text,
                        "provenance": line(payload.get("provenance") or {}), "at": time.time()})
            source = str(payload.get("source") or "")
            device = self._last_device
            if source.startswith("remoto") and device and self.audio_pref.get(device, True) and \
                    bool(getattr(self._settings(), "remote_audio", True)):
                spoken = str(payload.get("spoken") or text)
                threading.Thread(target=self._speak_remote, args=(spoken, device), daemon=True).start()
        if kind == EventType.STATE_CHANGED and "runtime_state" not in (payload.get("changed") or ()) and \
                "persona" not in (payload.get("changed") or ()):
            return
        snap = self.snapshot()
        if snap != self.last_state:
            self.last_state = snap
            self._send(snap)

    def _speak_remote(self, text: str, device: str) -> None:
        """A MESMA identidade vocal (perfil e prosódia da persona ativa), sintetizada aqui e enviada só ao
        dispositivo que pediu. Sem voz neural disponível, avisa em vez de inventar áudio."""
        try:
            from ..personality import persona
            from ..voice import dsp, prosody
            from ..voice.profile import effective_profile
            synth = getattr(getattr(self.core, "speaker", None), "synth", None)
            if synth is None or not hasattr(synth, "synthesize_plan"):
                self._send({"type": "notice", "device": device, "text": "Voz neural indisponível na matriz-mãe."})
                return
            profile = effective_profile(self._settings())
            style = prosody.ULTRON_STYLE if persona.current().ultron else prosody.JARVIS_STYLE
            samples, rate, _ = synth.synthesize_plan(prosody.plan(text, style) or [prosody.Phrase(text)],
                                                     length_scale=dsp.length_scale_for(profile))
            samples = dsp.process(samples, rate, profile)
            payload = base64.b64encode(wav_bytes(samples, rate)).decode("ascii")
            self._send({"type": "reply_audio", "device": device, "wav_b64": payload, "text": text[:200]})
        except Exception as exc:
            log.warning("voz remota falhou: %s", exc)
