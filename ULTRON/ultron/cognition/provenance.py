"""Procedência das respostas — de onde veio cada resposta, dito sem enfeite.

Tipos (podem se combinar):

* ``sistema``      — dado do próprio JARVIS (relógio, estado, configurações, ajuda);
* ``memoria``      — memória pessoal lida do banco (Second Brain, memória, TARDIS);
* ``acao``         — uma ação executada (com ou sem verificação confirmada);
* ``internet``     — o provedor consultou a internet (pesquisa web da OpenAI);
* ``inferencia``   — texto gerado por um modelo (local ou na nuvem, com o nome);
* ``hipotese``     — a resposta do modelo se apresenta como hipótese ("provavelmente", "hipótese");
* ``indisponivel`` — nenhuma fonte respondeu (sem modelo, sem dado).

Nada aqui chama modelo ou rede: só lê o que o orquestrador e o roteador registraram.
"""
from __future__ import annotations

import re

KIND_LABELS = {"sistema": "sistema", "memoria": "memória pessoal", "acao": "ação", "internet": "internet",
               "inferencia": "inferência", "hipotese": "hipótese", "indisponivel": "indisponível"}
MEMORY_PREFIXES = ("secondbrain.", "memory.", "tardis.")
_HYPOTHESIS = re.compile(r"\b(hip[oó]tese|provavelmente|possivelmente|talvez|suponho|imagino que)\b", re.IGNORECASE)


def describe(*, response_kind: str, text: str, success, verified, skills: list[str], route: dict) -> dict:
    kinds: list[str] = []
    parts: list[str] = []
    memory = [s for s in skills if s.startswith(MEMORY_PREFIXES)]
    actions = [s for s in skills if not s.startswith(MEMORY_PREFIXES)]
    if memory:
        kinds.append("memoria")
        parts.append("memória pessoal")
    if actions:
        kinds.append("acao")
        parts.append("ação verificada" if verified else
                     "ação sem verificação confirmada" if success else "ação que não foi concluída")
    if route:
        if route.get("web"):
            kinds.append("internet")
            parts.append("internet (pesquisa da OpenAI)")
        kinds.append("inferencia")
        where = "nuvem" if route.get("provider") == "openai" else "modelo local"
        model = str(route.get("model") or "").replace("openai:", "")
        parts.append(f"inferência — {where}{' ' + model if model else ''}")
        if _HYPOTHESIS.search(text or ""):
            kinds.append("hipotese")
            parts.append("contém hipótese")
    if not kinds:
        if response_kind == "error":
            kinds.append("indisponivel")
            parts.append("indisponível — nenhuma fonte respondeu")
        else:
            kinds.append("sistema")
            parts.append("dados do próprio JARVIS")
    return {"kinds": kinds, "label": " · ".join(parts), "notes": list((route or {}).get("notes") or []),
            "profile": (route or {}).get("profile", ""), "reason": (route or {}).get("reason", "")}


def line(provenance: dict) -> str:
    """Uma linha para a conversa e o console: "fonte: … (aviso)"."""
    if not provenance or not provenance.get("label"):
        return ""
    notes = "; ".join(provenance.get("notes") or [])
    return f"fonte: {provenance['label']}" + (f" — {notes}" if notes else "")
