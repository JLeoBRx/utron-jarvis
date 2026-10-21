"""Integração OpenAI restaurada do JARVIS original — contra um servidor local que imita a Responses API.

Nenhuma chamada sai do computador: ``FakeOpenAI`` e ``FakeOllama`` rodam em 127.0.0.1.
"""
import logging
import time
import unittest

import helpers

from fake_ollama import FakeOllama
from fake_openai import FakeOpenAI
from ultron.config.settings import SettingsManager
from ultron.core.event_bus import EventBus
from ultron.core.events import EventType
from ultron.models.ollama_client import OllamaClient
from ultron.models.openai_provider import (OpenAIProvider, ProviderError, parse_response, to_responses_input,
                                           to_responses_tools)
from ultron.models.router import ModelRouter
from ultron.privacy.privacy_mode import PrivacyPolicy

KEY = "sk-teste-1234567890"


class ConversionTest(unittest.TestCase):
    def test_messages_tools_and_calls_round_trip(self):
        messages = [
            {"role": "system", "content": "Você é JARVIS."},
            {"role": "user", "content": "abra o bloco de notas"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "function": {"name": "app.open",
                                                                                           "arguments": {"name": "notepad"}}}]},
            {"role": "tool", "content": '{"ok": true}'},
            {"role": "user", "content": "o que há na tela?", "images": ["iVBORw0KGgo="]},
        ]
        instructions, items = to_responses_input(messages)
        self.assertEqual(instructions, "Você é JARVIS.")
        call = next(i for i in items if i.get("type") == "function_call")
        self.assertEqual((call["name"], call["call_id"]), ("app__open", "c1"), "a API não aceita '.' em nomes")
        output = next(i for i in items if i.get("type") == "function_call_output")
        self.assertEqual(output["call_id"], "c1", "resposta da ferramenta pareada com a chamada")
        image = items[-1]["content"][-1]
        self.assertEqual(image["type"], "input_image")
        self.assertTrue(image["image_url"].startswith("data:image/png;base64,"))
        tools = to_responses_tools([{"type": "function", "function": {"name": "web.search", "parameters": {}}}],
                                   web_search=True)
        self.assertEqual([t.get("name", t["type"]) for t in tools], ["web__search", "web_search"])
        result = parse_response({"model": "m", "output": [
            {"type": "function_call", "call_id": "x9", "name": "fs__search", "arguments": '{"name": "relatorio"}'}]},
            "m", 0.1)
        self.assertEqual(result.tool_calls[0]["function"], {"name": "fs.search", "arguments": {"name": "relatorio"}})


class RouterWithOpenAITest(unittest.TestCase):
    def _router(self, openai_url, ollama_url, **settings):
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        values = {"ai_provider": "openai", "openai_model": "gpt-teste", "openai_base_url": openai_url,
                  "privacy_mode": "standard", "allow_external_models": True, "ollama_url": ollama_url}
        values.update(settings)
        manager.settings.apply(values)
        bus = EventBus()
        bus.start()
        self.addCleanup(bus.stop)
        privacy = PrivacyPolicy(lambda: manager.settings)
        router = ModelRouter(OllamaClient(ollama_url), settings_getter=lambda: manager.settings, bus=bus,
                             privacy=privacy)
        provider = OpenAIProvider(lambda: manager.settings, privacy=privacy, key_getter=lambda: KEY)
        router.register_provider("openai", provider)
        return router, provider, bus, manager

    def test_openai_is_the_chosen_brain_and_tools_run_locally(self):
        def responder(payload):
            if not any(i.get("type") == "function_call_output" for i in payload["input"]):
                return {"calls": [{"id": "c1", "name": "app__open", "arguments": {"name": "notepad"}}]}
            return {"text": "Bloco de notas aberto e verificado."}

        with FakeOpenAI(responder, key=KEY) as api, FakeOllama(["qwen2.5:3b"]) as ollama:
            router, provider, _bus, _ = self._router(api.url, ollama.url)
            selection = router.select("text")
            self.assertEqual((selection.provider, selection.model), ("openai", "openai:gpt-teste"))
            messages = [{"role": "system", "content": "Você é JARVIS."}, {"role": "user", "content": "abra o bloco"}]
            tools = [{"type": "function", "function": {"name": "app.open", "description": "Abrir app",
                                                        "parameters": {"type": "object", "properties": {}}}}]
            first = router.chat("text", messages, tools=tools)
            self.assertEqual(first.tool_calls[0]["function"]["name"], "app.open",
                             "a OpenAI só escolhe a ferramenta; o JARVIS executa localmente")
            messages.append(first.message())
            messages.append({"role": "tool", "content": '{"ok": true, "verified": true}'})
            final = router.chat("text", messages, tools=tools)
            self.assertEqual(final.content, "Bloco de notas aberto e verificado.")
            sent = api.requests[0]
            self.assertEqual(sent["auth"], f"Bearer {KEY}")
            self.assertEqual(sent["payload"]["instructions"], "Você é JARVIS.")
            self.assertFalse(sent["payload"]["store"])
            self.assertIn({"type": "web_search"}, sent["payload"]["tools"], "pesquisa web ligada por padrão")
            paired = [i for i in api.requests[1]["payload"]["input"] if i.get("type") == "function_call_output"]
            self.assertEqual(paired[0]["call_id"], "c1")
            self.assertEqual(provider.calls, 2)

    def test_local_mode_keeps_everything_on_the_computer(self):
        with FakeOpenAI(key=KEY) as api, FakeOllama(["qwen2.5:3b"], responder=lambda p: "Resposta local.") as ollama:
            router, provider, _bus, _ = self._router(api.url, ollama.url, privacy_mode="local")
            selection = router.select("text")
            self.assertEqual(selection.provider, "ollama")
            self.assertIn("LOCAL MODE", selection.reason)
            self.assertEqual(router.chat("text", [{"role": "user", "content": "oi"}]).content, "Resposta local.")
            self.assertEqual(api.requests, [], "nenhuma chamada saiu para a OpenAI")
            with self.assertRaises(ProviderError) as ctx:
                provider.chat([{"role": "user", "content": "oi"}])
            self.assertEqual(ctx.exception.kind, "BLOCKED")

    def test_api_failure_falls_back_to_local_ollama(self):
        events = []
        with FakeOpenAI(key=KEY, status=503) as api, FakeOllama(["qwen2.5:3b"], responder=lambda p: "Do Ollama.") as ollama:
            router, provider, bus, _ = self._router(api.url, ollama.url)
            bus.subscribe(EventType.MODEL_UNAVAILABLE, lambda e: events.append(e.payload))
            result = router.chat("text", [{"role": "user", "content": "oi"}])
            self.assertEqual(result.content, "Do Ollama.", "como no original: OpenAI indisponível → Ollama local")
            self.assertEqual(provider.last_error["kind"], "NETWORK")
            deadline = time.time() + 3
            while time.time() < deadline and not events:
                time.sleep(0.02)
            self.assertTrue(any(e.get("fallback") == "ollama" for e in events))

    def test_wrong_key_is_reported_and_key_never_logged(self):
        with FakeOpenAI(key="sk-outra-chave-0000") as api, FakeOllama(["qwen2.5:3b"]) as ollama:
            router, provider, _bus, _ = self._router(api.url, ollama.url)
            with self.assertLogs("ultron", level=logging.DEBUG) as logs:
                logging.getLogger("ultron").debug("início")
                with self.assertRaises(ProviderError) as ctx:
                    provider.chat([{"role": "user", "content": "oi"}])
                router.chat("text", [{"role": "user", "content": "oi"}])      # cai no Ollama
            self.assertEqual(ctx.exception.kind, "AUTH")
            self.assertFalse(any(KEY in line for line in logs.output), "a chave nunca aparece no log")

    def test_missing_key_blocks_with_clear_reason(self):
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.apply({"ai_provider": "openai", "privacy_mode": "standard", "allow_external_models": True})
        provider = OpenAIProvider(lambda: manager.settings, key_getter=lambda: "")
        self.assertIn("chave da OpenAI ausente", provider.blocked_reason())


if __name__ == "__main__":
    unittest.main()
