"""Plugin opcional: provedor de modelo externo compatível com a API de chat da OpenAI.

DESATIVADO POR PADRÃO. O ULTRON é local-first: este provedor só é considerado quando
TODAS as condições abaixo valem ao mesmo tempo:

1. o plugin foi ativado explicitamente (``plugins_enabled = ["external_model_provider"]``);
2. ``privacy_mode = "standard"`` e ``allow_external_models = true``;
3. o modelo local está indisponível (o roteador sempre prefere o Ollama local);
4. as variáveis de ambiente estão definidas:
   ``ULTRON_EXTERNAL_BASE_URL`` (ex.: https://api.exemplo.com/v1), ``ULTRON_EXTERNAL_MODEL``
   e ``ULTRON_EXTERNAL_API_KEY``.

A chave fica apenas no ambiente (nunca em arquivo de configuração). Cada chamada passa
pela política de privacidade e é registrada como conexão externa.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from ultron.models.ollama_client import ChatResult
from ultron.plugins import Plugin


class ExternalChatProvider:
    tasks = ("text",)

    def __init__(self):
        self.endpoint = os.environ.get("ULTRON_EXTERNAL_BASE_URL", "").rstrip("/")
        self.model = os.environ.get("ULTRON_EXTERNAL_MODEL", "")

    def available(self) -> bool:
        return bool(self.endpoint.startswith("https://") and self.model and os.environ.get("ULTRON_EXTERNAL_API_KEY"))

    def chat(self, messages: list[dict], *, timeout: float | None = None, cancel=None, **_ignored) -> ChatResult:
        if cancel is not None and getattr(cancel, "cancelled", False):
            raise RuntimeError("cancelado")
        payload = json.dumps({"model": self.model, "messages": [
            {"role": m.get("role", "user"), "content": m.get("content", "")} for m in messages]}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}/chat/completions", data=payload, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {os.environ.get('ULTRON_EXTERNAL_API_KEY', '')}"})
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=timeout or 60.0) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        return ChatResult(content=str(content), model=self.model, seconds=time.perf_counter() - started)


class ExternalModelPlugin(Plugin):
    name = "external_model_provider"
    version = "1.0.0"
    description = "Provedor externo opcional (desativado por padrão; bloqueado no modo local)."
    capabilities = ("model_provider",)
    default_enabled = False

    def initialize(self, ctx):
        ctx.register_model_provider("external", ExternalChatProvider())


PLUGIN = ExternalModelPlugin()
