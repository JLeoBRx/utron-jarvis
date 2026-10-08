import socket
import threading
import time
import unittest

import helpers

from fake_ollama import FakeOllama
from ultron.core.events import EventType
from ultron.core.runtime import CancellationToken
from ultron.models.ollama_client import OllamaClient, OllamaError
from ultron.models.router import ModelRouter, ModelUnavailable
from ultron.plugins.base import _GuardedProvider
from ultron.privacy.privacy_mode import PrivacyPolicy


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class OllamaClientTest(unittest.TestCase):
    def test_streaming_tokens_and_tool_calls(self):
        calls = [{"function": {"name": "app.open", "arguments": {"name": "chrome"}}}]
        with FakeOllama(["qwen2.5:3b"], responder=lambda p: {"content": "Abrindo o navegador agora.",
                                                             "tool_calls": calls}) as fake:
            client = OllamaClient(fake.url)
            tokens = []
            result = client.chat("qwen2.5:3b", [{"role": "user", "content": "abra o chrome"}],
                                 on_token=tokens.append)
            self.assertEqual(result.content, "Abrindo o navegador agora.")
            self.assertGreater(len(tokens), 1, "resposta chega em partes (streaming)")
            self.assertEqual(result.tool_calls, calls)

    def test_cancel_mid_stream(self):
        with FakeOllama(["qwen2.5:3b"], responder=lambda p: "x" * 600, chunk_delay=0.02) as fake:
            client = OllamaClient(fake.url)
            token = CancellationToken()
            threading.Timer(0.15, token.cancel).start()
            started = time.perf_counter()
            with self.assertRaises(OllamaError) as ctx:
                client.chat("qwen2.5:3b", [{"role": "user", "content": "longo"}], cancel=token)
            self.assertEqual(ctx.exception.kind, "CANCELLED")
            self.assertLess(time.perf_counter() - started, 1.0)

    def test_missing_model_dead_server_and_local_mode(self):
        with FakeOllama(["qwen2.5:3b"]) as fake:
            with self.assertRaises(OllamaError) as ctx:
                OllamaClient(fake.url).chat("llama3.1", [{"role": "user", "content": "oi"}])
            self.assertEqual(ctx.exception.kind, "MODEL_MISSING")
        dead = OllamaClient(f"http://127.0.0.1:{free_port()}", timeout=2)
        self.assertFalse(dead.is_alive())
        remote = OllamaClient("http://192.0.2.50:11434", local_only=lambda: True)
        with self.assertRaises(OllamaError) as ctx:
            remote.list_models()
        self.assertEqual(ctx.exception.kind, "BLOCKED", "modo local: só Ollama nesta máquina")


class RouterTest(unittest.TestCase):
    def _router(self, fake_url, **settings):
        bus, state = helpers.make_bus_state()
        s = helpers.make_settings(ollama_url=fake_url, **settings)
        router = ModelRouter(OllamaClient(fake_url), settings_getter=lambda: s, bus=bus, state=state)
        return router, bus, state

    def test_selects_configured_models_and_reports_missing(self):
        with FakeOllama(["qwen2.5:3b", "llava:7b"], vision_models=("llava:7b",)) as fake:
            router, bus, state = self._router(fake.url)
            events = []
            bus.subscribe([EventType.MODEL_SELECTED, EventType.MODEL_UNAVAILABLE], lambda e: events.append(e))
            status = router.refresh(force=True)
            self.assertTrue(status.ollama_alive)
            self.assertEqual(router.select("text").model, "qwen2.5:3b")
            vision = router.select("vision")
            self.assertEqual(vision.model, "llava:7b", "fallback de visão quando qwen2.5vl não está instalado")
            self.assertIn("qwen2.5vl:3b", status.missing)
            self.assertEqual(state.get("active_model"), "qwen2.5:3b")
            self.assertTrue(any(e.type == EventType.MODEL_SELECTED for e in events))

    def test_no_vision_model_gives_install_hint(self):
        with FakeOllama(["qwen2.5:3b"], vision_models=()) as fake:
            router, _bus, _state = self._router(fake.url)
            router.refresh(force=True)
            vision = router.select("vision")
            self.assertFalse(vision.available)
            self.assertIn("ollama pull qwen2.5vl:3b", vision.install_hint)

    def test_server_down_raises_model_unavailable_with_reason(self):
        router, _bus, _state = self._router(f"http://127.0.0.1:{free_port()}")
        router.refresh(force=True)
        with self.assertRaises(ModelUnavailable) as ctx:
            router.chat("text", [{"role": "user", "content": "oi"}])
        self.assertIn("Ollama indisponível", str(ctx.exception))

    def test_running_models_reports_gpu_share(self):
        with FakeOllama(["qwen2.5:3b"]) as fake:
            fake.loaded = ["qwen2.5:3b"]
            running = OllamaClient(fake.url).running_models()
            self.assertEqual(running[0]["name"], "qwen2.5:3b")
            self.assertEqual(running[0]["gpu_fraction"], 1.0)


class ExternalProviderTest(unittest.TestCase):
    class Provider:
        tasks = ("text",)
        model = "externo-1"
        endpoint = "https://api.exemplo.org"

        def available(self):
            return True

        def chat(self, messages, **kwargs):
            return "resposta externa"

    def test_external_models_are_blocked_in_local_mode(self):
        settings = helpers.make_settings(privacy_mode="local", allow_external_models=True)
        privacy = PrivacyPolicy(lambda: settings)
        guarded = _GuardedProvider("externo", self.Provider(), privacy)
        with self.assertRaises(PermissionError):
            guarded.chat([{"role": "user", "content": "oi"}])
        router = ModelRouter(OllamaClient(f"http://127.0.0.1:{free_port()}"), settings_getter=lambda: settings,
                             privacy=privacy)
        router.register_provider("externo", guarded)
        router.refresh(force=True)
        self.assertFalse(router.select("text").available, "modo local nunca cai para um modelo externo")
        settings.apply({"privacy_mode": "standard"})
        self.assertEqual(router.select("text").provider, "externo", "só com permissão explícita do usuário")


if __name__ == "__main__":
    unittest.main()
