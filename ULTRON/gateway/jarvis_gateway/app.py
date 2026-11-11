"""Servidor do gateway (aiohttp): site da ORBE, pareamento, sessões e o relé em tempo real.

Rotas:

* ``GET /`` e ``GET /p/{link}``       — o site da ORBE (o link vem do QR Code mostrado pela matriz-mãe);
* ``GET /static/*``, ``GET /scene/*`` — arquivos do site e os módulos 3D do próprio SAFRA (lista fechada);
* ``GET /healthz``                    — saúde (e se a matriz-mãe está conectada; nada além disso);
* ``GET /api/session``                — este navegador está pareado? (cria o cookie anti-CSRF);
* ``POST /api/pair/claim``            — o navegador apresenta o código/link de pareamento;
* ``GET /api/pair/wait``              — aguarda a confirmação NO COMPUTADOR principal (entrega a sessão uma vez);
* ``POST /api/logout``                — o dispositivo encerra a própria sessão;
* ``POST /api/agent/enroll``          — inscrição da matriz-mãe com o segredo de inscrição (troca por um token);
* ``WS /ws/agent``                    — conexão de SAÍDA do agente da matriz-mãe (token);
* ``WS /ws/orb``                      — a ORBE (cookie do dispositivo; origem conferida).

O gateway só retransmite: o texto das conversas não é gravado aqui (a auditoria guarda tipo, dispositivo, IP e
tamanho). Execução, memória e autorização ficam na matriz-mãe.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
import time
import uuid

from aiohttp import WSMsgType, web

from . import __version__
from .config import PACKAGE_DIR, Config
from .security import (RateLimiter, csrf_ok, new_token, normalize_code, pairing_code, verify_secret)
from .store import Store

log = logging.getLogger("jarvis_gateway")

DEVICE_COOKIE, CSRF_COOKIE = "jarvis_device", "jarvis_csrf"
MAX_TEXT = 2000
MAX_AUDIO_B64 = 1_600_000                     # ~30 s de fala a 16 kHz (WAV, base64)
MAX_PAIR_ATTEMPTS = 5
SCENE_ALLOWED = re.compile(r"^(js/[a-z0-9_]+\.js|css/tokens\.css|vendor/three/[A-Za-z0-9_./-]+\.js)$")
DEVICE_MESSAGES = {"say", "cancel", "authorize", "audio", "audio_pref", "ping"}


def _client_ip(request: web.Request, cfg: Config) -> str:
    if cfg.trust_proxy:
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    peer = request.transport.get_extra_info("peername") if request.transport else None
    return str(peer[0]) if peer else "?"


class Hub:
    """Conexões vivas (só em memória): o agente, os navegadores, os pareamentos aguardando e o último estado."""

    def __init__(self):
        self.agent: web.WebSocketResponse | None = None
        self.agent_name = ""
        self.devices: dict[str, set] = {}
        self.waiting: dict[str, dict] = {}          # claim → {pid, event, token, state, expires}
        self.last_state: dict = {}
        self.history: list[dict] = []

    @property
    def online(self) -> bool:
        return self.agent is not None and not self.agent.closed

    async def to_agent(self, message: dict) -> bool:
        if not self.online:
            return False
        try:
            await self.agent.send_json(message)
            return True
        except (ConnectionError, RuntimeError):
            return False

    async def to_devices(self, message: dict, device: str = "") -> None:
        targets = [ws for did, sockets in self.devices.items() if not device or did == device for ws in sockets]
        for ws in targets:
            if not ws.closed:
                try:
                    await ws.send_json(message)
                except (ConnectionError, RuntimeError):
                    pass


def _csp(index_html: str) -> str:
    """CSP estrita: só arquivos do próprio site + o importmap embutido (por hash), conexões só com a própria origem."""
    hashes = []
    for script in re.findall(r"<script type=\"importmap\">(.*?)</script>", index_html, re.S):
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
        hashes.append(f"'sha256-{digest}'")
    return ("default-src 'self'; script-src 'self' " + " ".join(hashes) + "; style-src 'self'; img-src 'self' data: blob:; "
            "media-src 'self' blob: data:; connect-src 'self'; worker-src 'self' blob:; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'; object-src 'none'")


def create_app(cfg: Config | None = None, *, store: Store | None = None) -> web.Application:
    cfg = cfg or Config.from_env()
    store = store or Store(cfg.db_path)
    hub = Hub()
    limits = {"enroll": RateLimiter(5, 900), "claim": RateLimiter(10, 600), "say": RateLimiter(20, 60),
              "audio": RateLimiter(6, 60), "wait": RateLimiter(60, 60)}
    static_dir = PACKAGE_DIR / "static"
    index_html = (static_dir / "index.html").read_text(encoding="utf-8")
    csp = _csp(index_html)

    @web.middleware
    async def security_headers(request: web.Request, handler):
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "microphone=(self), camera=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if cfg.public_url.startswith("https://"):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if isinstance(response, web.HTTPException) and response.status >= 400:
            raise response
        return response

    app = web.Application(middlewares=[security_headers], client_max_size=2 * 1024 * 1024)
    app["cfg"], app["store"], app["hub"] = cfg, store, hub

    def cookie(response: web.StreamResponse, name: str, value: str, *, http_only: bool, max_age: int) -> None:
        response.set_cookie(name, value, max_age=max_age, path="/", httponly=http_only, secure=cfg.secure_cookies,
                            samesite="Strict")

    def same_origin(request: web.Request) -> bool:
        origin = request.headers.get("Origin", "")
        return origin == cfg.origin

    def device_of(request: web.Request):
        return store.device_for(request.cookies.get(DEVICE_COOKIE, ""))

    # ------------------------------------------------------------ site
    async def index(request: web.Request) -> web.Response:
        response = web.Response(text=index_html, content_type="text/html", charset="utf-8")
        response.headers["Content-Security-Policy"] = csp
        response.headers["Cache-Control"] = "no-store"
        return response

    async def scene_file(request: web.Request) -> web.StreamResponse:
        rel = request.match_info["path"]
        if not SCENE_ALLOWED.match(rel) or ".." in rel:
            raise web.HTTPNotFound()
        path = (cfg.scene_dir / rel).resolve()
        if not str(path).startswith(str(cfg.scene_dir.resolve())) or not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Cache-Control": "public, max-age=3600"})

    async def healthz(request: web.Request) -> web.Response:
        return web.json_response({"ok": True, "matriz": hub.online, "version": __version__})

    async def session(request: web.Request) -> web.Response:
        device = device_of(request)
        response = web.json_response({"paired": device is not None, "device": device["name"] if device else "",
                                      "matriz": hub.online})
        if not request.cookies.get(CSRF_COOKIE):
            cookie(response, CSRF_COOKIE, new_token(18), http_only=False, max_age=86400 * 30)
        response.headers["Cache-Control"] = "no-store"
        return response

    # ------------------------------------------------------------ pareamento (confirmado NO computador principal)
    async def pair_claim(request: web.Request) -> web.Response:
        ip = _client_ip(request, cfg)
        if not same_origin(request):
            store.audit("origem_recusada", ip=ip, detail="pair_claim")
            raise web.HTTPForbidden(text="origem não permitida")
        if not limits["claim"].allow(ip):
            store.audit("limite", ip=ip, detail="pair_claim")
            raise web.HTTPTooManyRequests(text="muitas tentativas; aguarde alguns minutos")
        try:
            body = await request.json()
        except (ValueError, json.JSONDecodeError):
            raise web.HTTPBadRequest(text="pedido inválido")
        name = re.sub(r"[^\w .\-áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ]", "", str(body.get("device_name") or "Navegador"))[:40] or "Navegador"
        link, code = str(body.get("link") or "")[:120], normalize_code(body.get("code") or "")
        row = store.find_pairing(link=link) if link else (store.open_pairing() if code else None)
        now = time.time()
        if row is None or row["state"] != "aberto" or row["expires"] <= now:
            store.audit("pareamento_invalido", ip=ip)
            raise web.HTTPNotFound(text="código de pareamento inválido ou expirado — gere outro no computador")
        if not link and code != row["code"]:
            store.wrong_attempt(row["id"], MAX_PAIR_ATTEMPTS)
            store.audit("pareamento_codigo_errado", ip=ip)
            raise web.HTTPNotFound(text="código de pareamento incorreto")
        if not hub.online:
            raise web.HTTPServiceUnavailable(text="MATRIZ-MÃE DESCONECTADA")
        claim = uuid.uuid4().hex
        ua = request.headers.get("User-Agent", "")[:200]
        store.claim_pairing(row["id"], claim, name, ua, ip)
        hub.waiting[claim] = {"pid": row["id"], "event": asyncio.Event(), "token": "", "state": "aguardando",
                              "expires": row["expires"] + 120, "name": name, "ua": ua, "ip": ip}
        store.audit("pareamento_reivindicado", ip=ip, detail=name)
        await hub.to_agent({"type": "pair_claim", "id": row["id"], "device_name": name, "user_agent": ua, "ip": ip})
        return web.json_response({"claim": claim, "state": "aguardando"})

    async def pair_wait(request: web.Request) -> web.Response:
        claim = request.query.get("claim", "")
        ip = _client_ip(request, cfg)
        if not limits["wait"].allow(ip):
            raise web.HTTPTooManyRequests()
        waiting = hub.waiting.get(claim)
        if waiting is None:
            raise web.HTTPNotFound(text="pareamento desconhecido")
        if waiting["state"] == "aguardando":
            try:
                await asyncio.wait_for(waiting["event"].wait(), timeout=25)
            except asyncio.TimeoutError:
                pass
        if time.time() > waiting["expires"] and waiting["state"] == "aguardando":
            waiting["state"] = "expirado"
        state = waiting["state"]
        response = web.json_response({"state": state})
        response.headers["Cache-Control"] = "no-store"
        if state == "aprovado" and waiting["token"]:
            token, waiting["token"] = waiting["token"], ""           # entregue UMA vez, só a quem reivindicou
            cookie(response, DEVICE_COOKIE, token, http_only=True, max_age=int(cfg.device_days * 86400))
            hub.waiting.pop(claim, None)
        elif state in ("negado", "expirado"):
            hub.waiting.pop(claim, None)
        return response

    async def logout(request: web.Request) -> web.Response:
        if not same_origin(request) or not csrf_ok(request.cookies.get(CSRF_COOKIE), request.headers.get("X-CSRF-Token")):
            raise web.HTTPForbidden(text="pedido recusado (CSRF)")
        device = device_of(request)
        response = web.json_response({"ok": True})
        if device is not None:
            store.revoke_device(device["id"])
            store.audit("dispositivo_saiu", device=device["id"], ip=_client_ip(request, cfg))
            for ws in list(hub.devices.pop(device["id"], set())):
                await ws.close(code=4001, message=b"sessao encerrada")
            await hub.to_agent({"type": "devices", "list": store.devices()})
        response.del_cookie(DEVICE_COOKIE, path="/")
        return response

    # ------------------------------------------------------------ matriz-mãe
    async def enroll(request: web.Request) -> web.Response:
        ip = _client_ip(request, cfg)
        if not limits["enroll"].allow(ip):
            store.audit("limite", ip=ip, detail="enroll")
            raise web.HTTPTooManyRequests(text="muitas tentativas")
        if not cfg.enroll_secret_hash:
            raise web.HTTPServiceUnavailable(text="inscrição desativada: defina JARVIS_ENROLL_SECRET_HASH no servidor")
        try:
            body = await request.json()
        except (ValueError, json.JSONDecodeError):
            raise web.HTTPBadRequest()
        if not verify_secret(str(body.get("secret") or ""), cfg.enroll_secret_hash):
            store.audit("inscricao_recusada", ip=ip)
            raise web.HTTPForbidden(text="segredo de inscrição incorreto")
        token = new_token(32)
        store.set_agent(token, str(body.get("name") or "SAFRA")[:80])
        store.audit("inscricao", ip=ip, detail=str(body.get("name") or "")[:80])
        if hub.online:                                   # a inscrição nova derruba a conexão antiga
            await hub.agent.close(code=4002, message=b"nova inscricao")
        return web.json_response({"token": token})

    async def agent_ws(request: web.Request) -> web.WebSocketResponse:
        ip = _client_ip(request, cfg)
        auth = request.headers.get("Authorization", "")
        token = auth[7:] if auth.startswith("Bearer ") else ""
        if not token or not store.agent_ok(token):
            store.audit("agente_recusado", ip=ip)
            raise web.HTTPUnauthorized(text="token do agente inválido")
        ws = web.WebSocketResponse(heartbeat=25, max_msg_size=8 * 1024 * 1024)
        await ws.prepare(request)
        if hub.online:
            await hub.agent.close(code=4003, message=b"substituido")
        hub.agent = ws
        store.audit("matriz_conectada", ip=ip)
        await hub.to_devices({"type": "matriz", "online": True})
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                await _from_agent(data, ws)
        finally:
            if hub.agent is ws:
                hub.agent = None
                store.audit("matriz_desconectada", ip=ip)
                await hub.to_devices({"type": "matriz", "online": False})
        return ws

    async def _from_agent(data: dict, ws) -> None:
        kind = data.get("type")
        if kind == "hello":
            hub.agent_name = str(data.get("name") or "SAFRA")[:60]
        elif kind == "state":
            hub.last_state = {k: v for k, v in data.items() if k != "type"}
            await hub.to_devices({"type": "state", **hub.last_state})
        elif kind == "line":
            line = {k: data.get(k) for k in ("role", "text", "source", "provenance", "at")}
            hub.history = (hub.history + [line])[-30:]
            await hub.to_devices({"type": "line", **line})
        elif kind == "reply_audio":
            await hub.to_devices({"type": "audio", "wav_b64": data.get("wav_b64", ""),
                                  "text": str(data.get("text", ""))[:200]}, device=str(data.get("device") or ""))
        elif kind == "notice":
            await hub.to_devices({"type": "notice", "text": str(data.get("text", ""))[:300]},
                                 device=str(data.get("device") or ""))
        elif kind == "pair_request":
            code, link = pairing_code(), new_token(24)
            info = store.create_pairing(code, link, cfg.pair_ttl)
            for claim, waiting in list(hub.waiting.items()):           # pareamentos anteriores ficam inválidos
                if waiting["state"] == "aguardando":
                    waiting["state"] = "expirado"; waiting["event"].set()
            store.audit("pareamento_criado")
            await ws.send_json({"type": "pair_code", "id": info["id"], "code": code, "expires": info["expires"],
                                "url": f"{cfg.public_url}/p/{link}"})
        elif kind == "pair_decision":
            pid, approve = str(data.get("id") or ""), bool(data.get("approve"))
            row = store.pairing(pid)
            waiting = next((w for w in hub.waiting.values() if w["pid"] == pid and w["state"] == "aguardando"), None)
            if row is None or waiting is None or row["state"] != "reivindicado":
                await ws.send_json({"type": "pair_result", "id": pid, "ok": False, "reason": "pareamento expirado"})
                return
            if approve:
                token = new_token(32)
                did = store.add_device(waiting["name"], token, cfg.device_days, waiting["ua"], waiting["ip"])
                store.finish_pairing(pid, "aprovado", device_id=did)
                waiting.update(state="aprovado", token=token)
                store.audit("pareamento_aprovado", device=did, ip=waiting["ip"], detail=waiting["name"])
            else:
                store.finish_pairing(pid, "negado")
                waiting["state"] = "negado"
                store.audit("pareamento_negado", ip=waiting["ip"])
            waiting["event"].set()
            await ws.send_json({"type": "pair_result", "id": pid, "ok": True, "approved": approve})
            await ws.send_json({"type": "devices", "list": store.devices()})
        elif kind == "devices":
            await ws.send_json({"type": "devices", "list": store.devices()})
        elif kind == "revoke":
            did = str(data.get("device") or "")
            if store.revoke_device(did):
                store.audit("dispositivo_revogado", device=did)
                for sock in list(hub.devices.pop(did, set())):
                    await sock.close(code=4001, message=b"revogado")
            await ws.send_json({"type": "devices", "list": store.devices()})

    # ------------------------------------------------------------ a ORBE no navegador
    async def orb_ws(request: web.Request) -> web.WebSocketResponse:
        ip = _client_ip(request, cfg)
        if not same_origin(request):
            store.audit("origem_recusada", ip=ip, detail="ws")
            raise web.HTTPForbidden(text="origem não permitida")
        device = device_of(request)
        if device is None:
            raise web.HTTPUnauthorized(text="dispositivo não pareado")
        did = device["id"]
        ws = web.WebSocketResponse(heartbeat=25, max_msg_size=2 * 1024 * 1024)
        await ws.prepare(request)
        hub.devices.setdefault(did, set()).add(ws)
        store.touch_device(did)
        store.audit("dispositivo_conectado", device=did, ip=ip)
        await ws.send_json({"type": "hello", "device": device["name"], "matriz": hub.online, "name": hub.agent_name,
                            "state": hub.last_state, "history": hub.history})
        await hub.to_agent({"type": "device_online", "device": did, "name": device["name"]})
        try:
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    continue
                if store.device_for(request.cookies.get(DEVICE_COOKIE, "")) is None:     # revogado no meio
                    await ws.close(code=4001, message=b"revogado")
                    break
                try:
                    data = json.loads(msg.data)
                except ValueError:
                    continue
                kind = data.get("type")
                if kind not in DEVICE_MESSAGES:
                    continue
                if kind == "ping":
                    await ws.send_json({"type": "pong", "matriz": hub.online})
                    continue
                if not hub.online:
                    await ws.send_json({"type": "notice", "text": "MATRIZ-MÃE DESCONECTADA — nada foi enviado."})
                    continue
                if kind == "say":
                    text = str(data.get("text") or "").strip()[:MAX_TEXT]
                    if not text:
                        continue
                    if not limits["say"].allow(did):
                        store.audit("limite", device=did, ip=ip, detail="say")
                        await ws.send_json({"type": "notice", "text": "Muitas mensagens em pouco tempo; aguarde."})
                        continue
                    store.audit("remoto_mensagem", device=did, ip=ip, detail=f"{len(text)} caracteres")
                    await hub.to_agent({"type": "say", "device": did, "name": device["name"], "text": text})
                elif kind == "cancel":
                    store.audit("remoto_interromper", device=did, ip=ip)
                    await hub.to_agent({"type": "cancel", "device": did})
                elif kind == "authorize":
                    store.audit("remoto_autorizacao", device=did, ip=ip, detail="sim" if data.get("approve") else "não")
                    await hub.to_agent({"type": "authorize", "device": did, "name": device["name"],
                                        "id": data.get("id"), "approve": bool(data.get("approve"))})
                elif kind == "audio":
                    wav = str(data.get("wav_b64") or "")
                    if not wav or len(wav) > MAX_AUDIO_B64 or not limits["audio"].allow(did):
                        await ws.send_json({"type": "notice", "text": "Áudio recusado (tamanho ou frequência)."})
                        continue
                    store.audit("remoto_voz", device=did, ip=ip, detail=f"{len(wav)} bytes")
                    await hub.to_agent({"type": "audio", "device": did, "name": device["name"], "wav_b64": wav})
                elif kind == "audio_pref":
                    await hub.to_agent({"type": "audio_pref", "device": did, "on": bool(data.get("on"))})
        finally:
            sockets = hub.devices.get(did)
            if sockets is not None:
                sockets.discard(ws)
                if not sockets:
                    hub.devices.pop(did, None)
            await hub.to_agent({"type": "device_offline", "device": did})
        return ws

    app.router.add_get("/", index)
    app.router.add_get("/p/{link}", index)
    app.router.add_static("/static/", static_dir, show_index=False, follow_symlinks=False)
    app.router.add_get("/scene/{path:.+}", scene_file)
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/api/session", session)
    app.router.add_post("/api/pair/claim", pair_claim)
    app.router.add_get("/api/pair/wait", pair_wait)
    app.router.add_post("/api/logout", logout)
    app.router.add_post("/api/agent/enroll", enroll)
    app.router.add_get("/ws/agent", agent_ws)
    app.router.add_get("/ws/orb", orb_ws)

    async def on_cleanup(_app):
        store.close()
    app.on_cleanup.append(on_cleanup)
    return app


def run(cfg: Config | None = None) -> None:
    cfg = cfg or Config.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log.info("SAFRA Gateway %s em %s:%s (público: %s)", __version__, cfg.host, cfg.port, cfg.public_url)
    web.run_app(create_app(cfg), host=cfg.host, port=cfg.port, access_log=None)
