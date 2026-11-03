"""JARVIS WEB ORB: gateway + agente da matriz-mãe + "navegador" — de ponta a ponta, em 127.0.0.1.

O gateway roda de verdade (aiohttp), o agente é o de produção ligado a um NeuralCore REAL (com o servidor que imita
o Ollama) e o navegador é um cliente HTTP/WebSocket com cookies. Nada sai do computador; nenhuma URL pública é
afirmada. Cobre: inscrição, pareamento confirmado NO computador, sessão por cookie, conversa pelo MESMO núcleo,
autorização remota (comum × sensível), identidade ULTRON vinda da matriz-mãe, revogação, matriz-mãe desconectada,
origem, CSRF, limites de tentativas, cabeçalhos de segurança e ausência de segredos no site.
"""
import asyncio
import json
import socket
import sys
import threading
import time
import unittest
from pathlib import Path

import helpers

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "gateway"))
HAVE_DEPS = helpers.module_available("aiohttp") and helpers.module_available("websockets")
SECRET = "segredo-de-teste-0123456789"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return bool(cond())


class Gateway:
    """O gateway real numa thread com o próprio laço asyncio."""

    def __init__(self):
        from aiohttp import web
        from jarvis_gateway.app import create_app
        from jarvis_gateway.config import Config
        from jarvis_gateway.security import hash_secret
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.cfg = Config(public_url=self.url, enroll_secret_hash=hash_secret(SECRET),
                          db_path=str(helpers.temp_dir("gw-") / "gateway.sqlite3"), dev_insecure=True,
                          port=self.port)
        self.cfg.validate()
        self.app = create_app(self.cfg)
        self.loop = asyncio.new_event_loop()
        self.runner = web.AppRunner(self.app)
        ready = threading.Event()

        def run():
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.runner.setup())
            self.loop.run_until_complete(web.TCPSite(self.runner, "127.0.0.1", self.port).start())
            ready.set()
            self.loop.run_forever()
            self.loop.run_until_complete(self.runner.cleanup())
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(10)

    @property
    def hub(self):
        return self.app["hub"]

    @property
    def store(self):
        return self.app["store"]

    def stop(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)


class Browser:
    """Um navegador: cookies, cabeçalho Origin do próprio site e WebSocket da ORBE."""

    def __init__(self, url):
        self.url = url
        self.loop = asyncio.new_event_loop()
        self.session = None
        self.ws = None
        self.messages = []
        self._reader = None

    def run(self, coro, timeout=30):
        return self.loop.run_until_complete(asyncio.wait_for(coro, timeout))

    async def _session(self):
        import aiohttp
        if self.session is None:
            self.session = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True))
        return self.session

    def get(self, path, **kw):
        async def go():
            s = await self._session()
            async with s.get(self.url + path, **kw) as r:
                return r.status, await r.text(), dict(r.headers)
        return self.run(go())

    def post(self, path, body, *, origin=True, csrf=True):
        async def go():
            s = await self._session()
            headers = {"Content-Type": "application/json"}
            if origin:
                headers["Origin"] = self.url if origin is True else origin
            if csrf:
                token = next((c.value for c in s.cookie_jar if c.key == "jarvis_csrf"), "")
                headers["X-CSRF-Token"] = token
            async with s.post(self.url + path, data=json.dumps(body), headers=headers) as r:
                return r.status, await r.text()
        return self.run(go())

    def connect(self, origin=None):
        async def go():
            s = await self._session()
            self.ws = await s.ws_connect(self.url.replace("http", "ws") + "/ws/orb",
                                         headers={"Origin": origin or self.url})
            self._reader = asyncio.ensure_future(self._read())
        return self.run(go())

    async def _read(self):
        async for msg in self.ws:
            if msg.type.name == "TEXT":
                self.messages.append(json.loads(msg.data))
        self.messages.append({"type": "_closed", "code": self.ws.close_code})

    def send(self, obj):
        return self.run(self.ws.send_json(obj))

    def wait_for(self, predicate, timeout=15.0):
        end = time.time() + timeout
        while time.time() < end:
            for m in self.messages:
                if predicate(m):
                    return m
            self.loop.run_until_complete(asyncio.sleep(0.05))
        return None

    def close(self):
        async def go():
            if self.ws is not None and not self.ws.closed:
                await self.ws.close()
            if self.session is not None:
                await self.session.close()
        self.run(go())
        self.loop.close()


@unittest.skipUnless(HAVE_DEPS, "aiohttp e websockets necessários (requirements do gateway)")
class SecurityUnitTest(unittest.TestCase):
    def test_hashing_tokens_limits_and_csrf(self):
        from jarvis_gateway.security import (RateLimiter, csrf_ok, hash_secret, normalize_code, pairing_code,
                                             token_hash, verify_secret)
        stored = hash_secret("um-segredo-forte-123")
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertTrue(verify_secret("um-segredo-forte-123", stored))
        self.assertFalse(verify_secret("outro", stored))
        self.assertFalse(verify_secret("x", "lixo"))
        self.assertNotEqual(token_hash("a"), token_hash("b"))
        code = pairing_code()
        self.assertEqual(len(code), 8)
        self.assertEqual(normalize_code(code.lower() + " -"), code)
        clock = [0.0]
        limiter = RateLimiter(2, 60, clock=lambda: clock[0])
        self.assertTrue(limiter.allow("ip")); self.assertTrue(limiter.allow("ip")); self.assertFalse(limiter.allow("ip"))
        clock[0] = 61
        self.assertTrue(limiter.allow("ip"))
        self.assertTrue(csrf_ok("abc", "abc")); self.assertFalse(csrf_ok("abc", "abd")); self.assertFalse(csrf_ok("", ""))

    def test_config_refuses_insecure_public_setups(self):
        from jarvis_gateway.config import Config
        with self.assertRaises(ValueError):
            Config(public_url="http://orb.exemplo.com").validate()
        with self.assertRaises(ValueError):
            Config(public_url="https://orb.exemplo.com", dev_insecure=True).validate()
        Config(public_url="https://orb.exemplo.com").validate()
        self.assertTrue(Config(public_url="https://orb.exemplo.com").secure_cookies)


@unittest.skipUnless(HAVE_DEPS, "aiohttp e websockets necessários (requirements do gateway)")
class WebOrbEndToEndTest(unittest.TestCase):
    def setUp(self):
        from fake_ollama import FakeOllama
        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.remote import RemoteAgent
        self.gw = Gateway()
        self.fake = FakeOllama(["qwen2.5:3b"], responder=lambda payload: "Resposta da matriz-mãe.")
        self.fake.__enter__()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.apply({"ollama_url": self.fake.url, "network_discovery": False, "auto_backup": False,
                                "remote_enabled": True, "remote_gateway_url": self.gw.url, "voice_enabled": False})
        self.manager = manager
        self.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                               memory_db=helpers.make_memory().db)
        self.core.boot()
        self.token = {"value": ""}
        self.claims = []
        self.agent = RemoteAgent(self.core, settings_getter=lambda: manager.settings,
                                 token_getter=lambda: self.token["value"],
                                 token_setter=lambda v: self.token.__setitem__("value", v))
        self.agent.on_pair_claim = self.claims.append
        self.core.remote = self.agent
        self.browser = Browser(self.gw.url)

    def tearDown(self):
        self.browser.close()
        self.agent.stop()
        self.core.shutdown()
        self.core.memory.db.close()
        self.fake.__exit__(None, None, None)
        self.gw.stop()

    def _pair(self):
        ok, why = self.agent.enroll(self.gw.url, SECRET)
        self.assertTrue(ok, why)
        self.assertTrue(self.agent.start())
        self.assertTrue(_wait(lambda: self.agent.connected), self.agent.error)
        self.assertEqual(self.browser.get("/api/session")[0], 200)
        pairing = self.agent.request_pairing()
        self.assertTrue(pairing and pairing["code"] and pairing["url"].startswith(self.gw.url + "/p/"))
        status, body = self.browser.post("/api/pair/claim", {"code": pairing["code"], "device_name": "Celular de teste"})
        self.assertEqual(status, 200, body)
        claim = json.loads(body)["claim"]
        self.assertTrue(_wait(lambda: self.claims), "o computador principal recebe o pedido de pareamento")
        self.assertEqual(self.claims[-1]["device_name"], "Celular de teste")
        self.agent.decide_pairing(self.claims[-1]["id"], True)
        status, body, _ = self.browser.get(f"/api/pair/wait?claim={claim}")
        self.assertEqual(json.loads(body)["state"], "aprovado")
        self.browser.connect()
        hello = self.browser.wait_for(lambda m: m["type"] == "hello")
        self.assertTrue(hello and hello["matriz"], "ORBE conectada à matriz-mãe")
        return pairing

    def test_full_flow_through_the_same_core(self):
        self._pair()
        # a conversa vai para o MESMO NeuralCore e volta para a ORBE
        self.browser.send({"type": "audio_pref", "on": False})
        self.browser.send({"type": "say", "text": "Explique em uma frase o que é um holograma."})
        user = self.browser.wait_for(lambda m: m["type"] == "line" and m["role"] == "user")
        self.assertEqual(user["source"], "remoto")
        reply = self.browser.wait_for(lambda m: m["type"] == "line" and m["role"] == "jarvis", timeout=30)
        self.assertIsNotNone(reply, "a resposta da matriz-mãe chega à ORBE")
        self.assertIn("matriz-mãe", reply["text"])
        self.assertIn("fonte:", reply["provenance"])
        # autorização comum: pode ser respondida do celular; o MESMO AuthorizationManager decide
        req = self.core.authorizations.request("Anotar contexto da sessão", skill="memory.session_note", risk="low",
                                               timeout=30)
        state = self.browser.wait_for(lambda m: m["type"] == "state" and (m.get("authorization") or {}).get("id") == req.id)
        self.assertTrue(state["authorization"]["remote_ok"])
        self.browser.send({"type": "authorize", "id": req.id, "approve": True})
        self.assertTrue(_wait(lambda: req.status == "approved"))
        self.assertIn("remoto", req.resolved_by)
        # sensível (apagar dados): só no computador principal
        sensitive = self.core.authorizations.request("Apagar arquivo", skill="fs.delete", risk="high",
                                                     permission="apagar_dados", timeout=30)
        state = self.browser.wait_for(lambda m: m["type"] == "state" and (m.get("authorization") or {}).get("id") == sensitive.id)
        self.assertFalse(state["authorization"]["remote_ok"])
        self.browser.send({"type": "authorize", "id": sensitive.id, "approve": True})
        self.assertIsNotNone(self.browser.wait_for(lambda m: m["type"] == "notice" and "computador principal" in m["text"]))
        self.assertEqual(sensitive.status, "pending", "o celular não aprova ação sensível")
        self.core.authorizations.resolve(False, by="teste")
        # a identidade ULTRON vem da matriz-mãe (o site não decide)
        self.core.set_persona("ultron", operator=True, source="teste")
        ultron = self.browser.wait_for(lambda m: m["type"] == "state" and (m.get("persona") or {}).get("name") == "ultron")
        self.assertIsNotNone(ultron)
        self.core.set_persona("jarvis", source="teste")
        self.assertIsNotNone(self.browser.wait_for(
            lambda m: m["type"] == "state" and (m.get("persona") or {}).get("name") == "jarvis" and m is not ultron))
        # auditoria do gateway: sem conteúdo de conversa
        kinds = [a["kind"] for a in self.gw.store.audit_log()]
        for k in ("inscricao", "pareamento_aprovado", "dispositivo_conectado", "remoto_mensagem", "remoto_autorizacao"):
            self.assertIn(k, kinds)
        details = " ".join(a["detail"] for a in self.gw.store.audit_log())
        self.assertNotIn("holograma", details, "o gateway não grava o texto das conversas")

    def test_matriz_offline_revocation_and_reconnection(self):
        self._pair()
        self.agent.stop()
        offline = self.browser.wait_for(lambda m: m["type"] == "matriz" and m["online"] is False)
        self.assertIsNotNone(offline, "a ORBE diz MATRIZ-MÃE DESCONECTADA — nunca finge estar online")
        self.browser.send({"type": "say", "text": "oi"})
        self.assertIsNotNone(self.browser.wait_for(lambda m: m["type"] == "notice" and "DESCONECTADA" in m["text"]))
        self.assertTrue(self.agent.start())
        self.assertIsNotNone(self.browser.wait_for(lambda m: m["type"] == "matriz" and m["online"] is True))
        devices = self.agent.refresh_devices()
        self.assertEqual(len(devices), 1)
        self.agent.revoke(devices[0]["id"])
        closed = self.browser.wait_for(lambda m: m["type"] == "_closed")
        self.assertEqual(closed["code"], 4001, "revogado no computador principal: a sessão cai na hora")
        self.assertFalse(json.loads(self.browser.get("/api/session")[1])["paired"])

    def test_refusals_limits_and_headers(self):
        ok, why = self.agent.enroll(self.gw.url, "segredo-errado")
        self.assertFalse(ok)
        self.assertIn("403", why)
        self.assertTrue(self.agent.enroll(self.gw.url, SECRET)[0])
        self.assertTrue(self.agent.start())
        self.assertTrue(_wait(lambda: self.agent.connected))
        self.browser.get("/api/session")
        pairing = self.agent.request_pairing()
        status, _ = self.browser.post("/api/pair/claim", {"code": pairing["code"]}, origin="https://outro-site.example")
        self.assertEqual(status, 403, "origem estranha recusada")
        for _ in range(5):
            self.assertEqual(self.browser.post("/api/pair/claim", {"code": "ZZZZZZZZ"})[0], 404)
        self.assertEqual(self.browser.post("/api/pair/claim", {"code": pairing["code"]})[0], 404,
                         "após 5 erros o código fica bloqueado")
        statuses = [self.browser.post("/api/pair/claim", {"code": "AAAAAAAA"})[0] for _ in range(6)]
        self.assertIn(429, statuses, "limite de tentativas por IP")
        with self.assertRaises(Exception):
            self.browser.connect()                                      # sem cookie de dispositivo
        status, html, headers = self.browser.get("/")
        self.assertEqual(status, 200)
        csp = headers.get("Content-Security-Policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertEqual(headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(self.browser.get("/scene/js/orb.js")[0], 200)
        self.assertEqual(self.browser.get("/scene/../ultron/config/settings.py")[0], 404)
        self.assertEqual(self.browser.get("/scene/js/../../../../README_JARVIS.md")[0], 404)
        self.assertEqual(self.browser.post("/api/logout", {}, csrf=False)[0], 403, "CSRF exigido")
        health = json.loads(self.browser.get("/healthz")[1])
        self.assertEqual(set(health), {"ok", "matriz", "version"}, "a saúde não expõe nada além disso")

    def test_site_has_no_secrets_and_no_ai_keys(self):
        static = ROOT / "gateway" / "jarvis_gateway" / "static"
        text = " ".join(p.read_text(encoding="utf-8") for p in static.glob("*") if p.is_file())
        for forbidden in ("sk-", "OPENAI", "api_key", "apiKey", "Authorization: Bearer", "ollama", "11434", "sqlite"):
            self.assertNotIn(forbidden, text, forbidden)


@unittest.skipUnless(HAVE_DEPS and helpers.qt_available() and helpers.module_available("segno"),
                     "PySide6, segno e websockets necessários")
class DesktopPairingUiTest(unittest.TestCase):
    """O lado do computador: QR Code do pareamento, a confirmação AQUI, a lista de dispositivos e a revogação."""

    def test_qr_confirmation_list_and_revoke(self):
        from PySide6 import QtWidgets
        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.hud.settings_page import PairingDialog, SettingsPage, qr_image
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.apply({"network_discovery": False, "auto_backup": False})
        core = NeuralCore(manager, voice=False, perception=False, plugins=False, memory_db=helpers.make_memory().db)
        try:
            asked = []
            page = SettingsPage(core, ask=lambda title, text: asked.append(text) or True)
            decided, revoked = [], []
            core.remote.decide_pairing = lambda pid, ok: decided.append((pid, ok))
            core.remote.revoke = revoked.append
            page._confirm_pairing({"id": "p1", "device_name": "Celular", "user_agent": "UA", "ip": "203.0.113.7"})
            self.assertEqual(decided, [("p1", True)], "quem decide o pareamento é o usuário NESTE computador")
            self.assertIn("Celular", asked[0])
            self.assertIn("confirmação AQUI", asked[0])
            image = qr_image("https://orb.exemplo.com/p/abcdef0123456789")
            self.assertGreater(image.width(), 150)
            dialog = PairingDialog({"url": "https://orb.exemplo.com/p/abc", "code": "ABCDEFGH",
                                    "expires": time.time() + 300}, parent=page)
            dialog.show(); app.processEvents(); dialog.close()
            page._refresh_remote()
            self.assertIn("não inscrito", page.remote_state.text())
            core.remote.devices = [{"id": "d1", "name": "Celular", "created": time.time(), "expired": False}]
            page._refresh_remote()
            self.assertEqual(page.device_list.count(), 1)
            page.device_list.setCurrentRow(0)
            page._revoke_device()
            self.assertEqual(revoked, ["d1"])
        finally:
            core.memory.db.close()


if __name__ == "__main__":
    unittest.main()
