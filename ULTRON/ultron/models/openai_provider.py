"""Provedor OpenAI (Responses API) — restauração da integração do JARVIS original (README_OPENAI.md).

Como no original:

* ``JARVIS_AI_PROVIDER=openai`` escolhe a OpenAI como cérebro; ``JARVIS_OPENAI_MODEL`` o modelo;
  ``JARVIS_OPENAI_WEB_SEARCH`` (padrão 1) liga a pesquisa web da própria OpenAI; a chave vem de
  ``OPENAI_API_KEY`` ou do cofre do sistema (nunca de arquivo de configuração);
* as ferramentas continuam sendo executadas LOCALMENTE pelo JARVIS: a OpenAI só escolhe uma
  ferramenta estruturada (nunca recebe shell);
* se a API estiver indisponível, o roteador volta ao Ollama local.

Diferença deliberada (privacidade): com o LOCAL MODE ativo nenhuma chamada sai do computador; usar a
OpenAI exige ``privacy_mode=standard`` e ``allow_external_models=true`` (a tela de configurações faz
isso com um aviso explícito). Cada chamada é registrada pela política de privacidade.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

from ..platform import credentials
from .ollama_client import ChatResult

log = logging.getLogger("ultron.openai")


class ProviderError(RuntimeError):
    """Falha do provedor externo. ``kind``: AUTH, MODEL, QUOTA, NETWORK, BAD_RESPONSE, BLOCKED, CANCELLED."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _tool_name(name: str) -> str:
    """A API aceita só [a-zA-Z0-9_-] em nomes de função: 'app.open' → 'app__open'."""
    return str(name).replace(".", "__")


def _skill_name(name: str) -> str:
    return str(name).replace("__", ".")


def _image_url(b64: str) -> str:
    mime = "image/png" if str(b64).startswith("iVBOR") else "image/jpeg"
    return f"data:{mime};base64,{b64}"


def to_responses_input(messages: list[dict]) -> tuple[str, list[dict]]:
    """Mensagens no formato do JARVIS/Ollama → (instructions, input) da Responses API.

    As respostas de ferramenta (``role: tool``) não têm id no formato local: são pareadas, na ordem,
    com as chamadas da mensagem do assistente imediatamente anterior."""
    instructions: list[str] = []
    items: list[dict] = []
    pending_ids: list[str] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = str(msg.get("content") or "")
        if role == "system":
            instructions.append(content)
            continue
        if role == "tool":
            call_id = pending_ids.pop(0) if pending_ids else f"call_{len(items)}"
            items.append({"type": "function_call_output", "call_id": call_id, "output": content})
            continue
        if role == "assistant":
            if content:
                items.append({"role": "assistant", "content": content})
            pending_ids = []
            for index, call in enumerate(msg.get("tool_calls") or []):
                function = call.get("function") or {}
                call_id = str(call.get("id") or f"call_{len(items)}_{index}")
                args = function.get("arguments", {})
                items.append({"type": "function_call", "call_id": call_id,
                              "name": _tool_name(function.get("name", "")),
                              "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)})
                pending_ids.append(call_id)
            continue
        images = msg.get("images") or []
        if images:
            parts: list[dict] = [{"type": "input_text", "text": content}] if content else []
            parts += [{"type": "input_image", "image_url": _image_url(b64)} for b64 in images]
            items.append({"role": "user", "content": parts})
        else:
            items.append({"role": "user", "content": content})
    return "\n\n".join(i for i in instructions if i), items


def to_responses_tools(tools: list | None, *, web_search: bool) -> list[dict]:
    out = []
    for tool in tools or []:
        function = tool.get("function") or tool
        if not function.get("name"):
            continue
        out.append({"type": "function", "name": _tool_name(function["name"]),
                    "description": str(function.get("description", ""))[:1000],
                    "parameters": function.get("parameters") or {"type": "object", "properties": {}}})
    if web_search:
        out.append({"type": "web_search"})
    return out


def parse_response(body: dict, model: str, seconds: float) -> ChatResult:
    texts: list[str] = []
    calls: list[dict] = []
    for item in body.get("output") or []:
        kind = item.get("type")
        if kind == "message":
            for part in item.get("content") or []:
                if part.get("type") in ("output_text", "text") and part.get("text"):
                    texts.append(str(part["text"]))
        elif kind == "function_call":
            raw = item.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except ValueError:
                args = {}
            calls.append({"id": item.get("call_id") or item.get("id"),
                          "function": {"name": _skill_name(item.get("name", "")), "arguments": args}})
    if not texts and body.get("output_text"):
        texts.append(str(body["output_text"]))
    usage = body.get("usage") or {}
    return ChatResult("".join(texts).strip(), calls, f"openai:{body.get('model') or model}", seconds,
                      int(usage.get("output_tokens") or 0))


class OpenAIProvider:
    """Provedor registrado no roteador de modelos com o nome ``openai``."""

    tasks = ("text", "vision")
    provider_name = "openai"

    def __init__(self, settings_getter: Callable[[], Any], *, privacy=None,
                 key_getter: Callable[[], str] | None = None, opener=None):
        self._settings = settings_getter
        self._privacy = privacy
        self._key = key_getter or (lambda: credentials.get_secret("openai_api_key"))
        self._open = opener or urllib.request.urlopen
        self.last_error: dict | None = None
        self.calls = 0

    # ------------------------------------------------------------ estado
    @property
    def model(self) -> str:
        return str(getattr(self._settings(), "openai_model", "") or "")

    @property
    def base_url(self) -> str:
        return str(getattr(self._settings(), "openai_base_url", "https://api.openai.com/v1")).rstrip("/")

    def chosen(self) -> bool:
        return getattr(self._settings(), "ai_provider", "ollama") == "openai"

    def blocked_reason(self) -> str:
        """Por que a OpenAI não pode ser usada agora ("" = pode)."""
        s = self._settings()
        if not self.chosen():
            return "provedor escolhido: Ollama local"
        if not self._key():
            return "chave da OpenAI ausente (OPENAI_API_KEY ou CONFIGURAÇÕES > INTELIGÊNCIA)"
        if not self.model:
            return "modelo da OpenAI não definido (JARVIS_OPENAI_MODEL)"
        if getattr(s, "privacy_mode", "local") == "local":
            return "LOCAL MODE ativo: nenhuma chamada sai do computador"
        if not getattr(s, "allow_external_models", False):
            return "modelos externos não permitidos (allow_external_models)"
        return ""

    def available(self) -> bool:
        return not self.blocked_reason()

    def status(self) -> dict:
        return {"chosen": self.chosen(), "available": self.available(), "blocked": self.blocked_reason(),
                "model": self.model, "key": credentials.source("openai_api_key") or "ausente",
                "web_search": bool(getattr(self._settings(), "openai_web_search", True)),
                "calls": self.calls, "last_error": self.last_error}

    # ------------------------------------------------------------ chamada
    def chat(self, messages: list[dict], *, tools: list | None = None, fmt: str | dict | None = None,
             options: dict | None = None, timeout: float | None = None, cancel=None, on_token=None,
             **_ignored) -> ChatResult:
        blocked = self.blocked_reason()
        if blocked:
            raise ProviderError("BLOCKED", blocked)
        if cancel is not None and getattr(cancel, "cancelled", False):
            raise ProviderError("CANCELLED", "cancelado")
        host = urllib.parse.urlsplit(self.base_url).hostname or ""
        if self._privacy is not None:
            decision = self._privacy.allow_external("modelo de IA escolhido pelo usuário (OpenAI)", host,
                                                    explicit=True)
            if not decision.allowed:
                raise ProviderError("BLOCKED", decision.reason)
        instructions, items = to_responses_input(messages)
        has_images = any(isinstance(i.get("content"), list) for i in items)
        payload: dict[str, Any] = {"model": self.model, "input": items, "store": False}
        if instructions:
            payload["instructions"] = instructions
        web = bool(getattr(self._settings(), "openai_web_search", True)) and not has_images and fmt is None
        tool_list = to_responses_tools(tools, web_search=web)
        if tool_list:
            payload["tools"] = tool_list
        if fmt == "json" or isinstance(fmt, dict):
            payload["text"] = {"format": {"type": "json_object"}}
        request = urllib.request.Request(
            f"{self.base_url}/responses", data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._key()}"})
        started = time.perf_counter()
        self.calls += 1
        try:
            with self._open(request, timeout=timeout or 90.0) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", {}).get("message", "")
            except Exception:
                pass
            kind = {401: "AUTH", 403: "AUTH", 404: "MODEL", 429: "QUOTA"}.get(exc.code, "NETWORK")
            text = {"AUTH": "chave da OpenAI recusada", "MODEL": f"modelo {self.model} não encontrado na sua conta",
                    "QUOTA": "limite de uso ou saldo da OpenAI atingido"}.get(kind, f"erro HTTP {exc.code}")
            self.last_error = {"kind": kind, "text": text, "at": time.time()}
            raise ProviderError(kind, f"{text}{(': ' + detail[:160]) if detail else ''}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.last_error = {"kind": "NETWORK", "text": "OpenAI inacessível", "at": time.time()}
            raise ProviderError("NETWORK", f"OpenAI inacessível: {getattr(exc, 'reason', exc)}") from exc
        except ValueError as exc:
            self.last_error = {"kind": "BAD_RESPONSE", "text": "resposta inválida", "at": time.time()}
            raise ProviderError("BAD_RESPONSE", "resposta inválida da OpenAI") from exc
        if body.get("error"):
            raise ProviderError("BAD_RESPONSE", str(body["error"])[:200])
        self.last_error = None
        result = parse_response(body, self.model, time.perf_counter() - started)
        if on_token and result.content:
            on_token(result.content)
        return result
