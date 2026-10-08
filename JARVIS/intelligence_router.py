"""J.A.R.V.I.S. // INTELLIGENCE ROUTER
Escolhe a inteligência adequada para cada missão sem transformar o roteamento em
um simples if/else por palavra-chave.

Local é o padrão. OpenAI é opcional e só é usado quando explicitamente habilitado
E existe uma chave no ambiente. A execução das ferramentas continua sob a allowlist
local do JARVIS.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import json
import os
import urllib.request
import urllib.error

import config

@dataclass
class RouteDecision:
    route: str
    model: str
    reason: str
    confidence: float
    fallback: str = "OLLAMA_LOCAL"

    def to_dict(self):
        return asdict(self)


def _openai_ready() -> bool:
    return bool(getattr(config, "OPENAI_ENABLED", False) and os.environ.get("OPENAI_API_KEY"))


def local_available() -> bool:
    # A disponibilidade real do Ollama é verificada no momento da chamada.
    return bool(getattr(config, "OLLAMA_URL", ""))


def _complexity(goal: str) -> float:
    text = str(goal or "").lower()
    score = 0.25
    markers = {
        "investigue": .18, "analise": .15, "depure": .18, "corrija": .15,
        "implemente": .18, "desenvolva": .18, "projeto": .12, "código": .15,
        "erro": .12, "planeje": .14, "compare": .10, "integre": .15,
    }
    for marker, weight in markers.items():
        if marker in text:
            score += weight
    if len(text) > 500: score += .10
    return min(1.0, score)


def decide(goal: str, context: dict | None = None) -> RouteDecision:
    context = context or {}
    complexity = _complexity(goal)
    has_visual = bool(context.get("visual") or context.get("screen") or context.get("ocr"))
    openai = _openai_ready()

    if openai and complexity >= .72:
        return RouteDecision("OPENAI", getattr(config, "OPENAI_MODEL", "gpt-6-luna"),
                             "missão complexa e provedor remoto explicitamente habilitado", .88)
    if openai and has_visual and complexity >= .55:
        return RouteDecision("OPENAI", getattr(config, "OPENAI_MODEL", "gpt-6-luna"),
                             "contexto visual relevante e provedor remoto habilitado", .80)
    return RouteDecision("OLLAMA_LOCAL", getattr(config, "OLLAMA_MODEL", ""),
                         "execução local é suficiente ou OpenAI não está habilitado", .86)


def _ollama(messages, tool_defs=None, model=None):
    payload = {"model": model or config.OLLAMA_MODEL, "messages": messages, "stream": False}
    if tool_defs:
        payload["tools"] = tool_defs
    req = urllib.request.Request(config.OLLAMA_URL, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode())["message"]


def _openai(messages, tool_defs=None, model=None):
    """Adaptador opcional para Chat Completions; não é usado sem chave explícita."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY não configurada")
    payload = {"model": model or config.OPENAI_MODEL, "messages": messages}
    if tool_defs:
        payload["tools"] = tool_defs
        payload["tool_choice"] = "auto"
    req = urllib.request.Request(
        getattr(config, "OPENAI_URL", "https://api.openai.com/v1/chat/completions"),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=120) as response:
        data = json.loads(response.read().decode())
    return data["choices"][0]["message"]


def chat(messages, tool_defs=None, decision: RouteDecision | None = None):
    decision = decision or decide(messages[-1].get("content", "") if messages else "")
    if decision.route == "OPENAI":
        try:
            return _openai(messages, tool_defs, decision.model)
        except Exception:
            # Falha de rede/API nunca deve matar o agente: retorna ao cérebro local.
            return _ollama(messages, tool_defs, config.OLLAMA_MODEL)
    return _ollama(messages, tool_defs, decision.model)
