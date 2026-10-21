"""Estilo de resposta do JARVIS.

Pós-processamento aplicado a qualquer texto antes de ser exibido ou falado. Garante a
personalidade mesmo quando o modelo local ignora parte das instruções:

* remove emojis e entusiasmo de atendente ("Perfeito!", "Fico feliz em ajudar", ...);
* corrige autorreferências a identidades antigas;
* para voz: remove marcação, encurta URLs e limita o número de frases.
"""
from __future__ import annotations

import re

from . import identity

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"   # símbolos e pictogramas
    "\U00002600-\U000027BF"   # diversos
    "\U0001F000-\U0001F2FF"
    "\U0000FE0F\U0000200D"
    "]+",
    flags=re.UNICODE,
)

# Interjeições de atendente no início de uma frase — só quando são interjeição (seguidas de pontuação):
# "Excelente escolha." não é tocado. Como no JARVIS original (agent._jarvis_tone): "Claro, senhor." →
# "Entendido, senhor."; "Ótimo!" → "Certo."; "Ótimo, vou abrir" → "Vou abrir".
_OPENER = re.compile(
    r"(^|(?<=[.!?]\s))(claro|perfeito|ótimo|otimo|excelente|maravilha|beleza|que bom|sem problemas|olá|ola|oi)"
    r"(\s*,\s*senhor)?\s*([!.,]+)\s*",
    re.IGNORECASE,
)
_ACK = {"claro": "Entendido", "perfeito": "Entendido", "ótimo": "Certo", "otimo": "Certo", "excelente": "Certo",
        "maravilha": "Certo", "beleza": "Certo", "sem problemas": "Entendido", "que bom": "Certo"}
_FICO_FELIZ = re.compile(r"(^|(?<=[.!?]\s))fico feliz(?: em ajudar| em poder ajudar)?[^.!?]*[.!?]?\s*", re.IGNORECASE)


def _opener(match: re.Match) -> str:
    lead, word, senhor, punct = match.group(1), match.group(2).lower(), match.group(3), match.group(4)
    if word in ("olá", "ola", "oi"):
        return lead
    if "," in punct and not senhor:
        return lead                                   # "Ótimo, vou abrir" → "vou abrir"
    ack = _ACK.get(word, "Entendido")
    return f"{lead}{ack}{', senhor' if senhor else ''}. "
_FRIENDLY_TAILS = re.compile(
    r"\s*(?:espero ter ajudado|qualquer coisa,? (?:é só|estou à disposição)|estou à disposição|"
    r"posso ajudar em mais alguma coisa)[^.!?]*[.!?]?\s*$",
    re.IGNORECASE,
)
_MULTI_EXCLAMATION = re.compile(r"!+")
_MARKDOWN = re.compile(r"(\*\*|__|`{1,3}|^#{1,6}\s*|^\s*[-*]\s+)", re.MULTILINE)
_URL = re.compile(r"https?://([^/\s]+)\S*")


def _replace_identity(text: str) -> str:
    for old in identity.FORBIDDEN_IDENTITIES:
        text = re.sub(rf"\b{re.escape(old)}\b", identity.NAME, text) if old[-1].isalnum() else \
            text.replace(old, identity.NAME)
    text = re.sub(r"\bJust A Rather Very Intelligent System\b", identity.NAME, text, flags=re.I)
    return text


def stylize(text: str, *, channel: str = "text", max_sentences: int | None = None) -> str:
    """Aplica a personalidade ao texto. ``channel`` é ``text`` (HUD) ou ``voice`` (fala)."""
    out = str(text or "")
    out = _EMOJI_RE.sub("", out)
    out = _replace_identity(out)
    out = _FICO_FELIZ.sub(lambda m: m.group(1), out)
    previous = None
    while previous != out:            # aberturas encadeadas ("Claro! Perfeito, senhor.")
        previous = out
        out = _OPENER.sub(_opener, out).lstrip()
    out = re.sub(r"^(Entendido|Certo)(, senhor)?\.\s+(Entendido|Certo)(, senhor)?\.", r"\1\2.", out)
    # depois de tirar uma interjeição, a frase seguinte começa com maiúscula
    out = re.sub(r"^((?:Entendido|Certo)(?:, senhor)?\.\s+)([a-zà-ú])", lambda m: m.group(1) + m.group(2).upper(), out)
    out = _FRIENDLY_TAILS.sub("", out)
    out = _MULTI_EXCLAMATION.sub(".", out)
    out = re.sub(r"\.\s*\.", ".", out)
    if channel == "voice":
        out = _MARKDOWN.sub("", out)
        out = _URL.sub(lambda m: m.group(1), out)
        out = re.sub(r"\s*\n+\s*", ". ", out)
        out = re.sub(r"\.\s*\.", ".", out)
        limit = max_sentences if max_sentences is not None else 4
        sentences = re.split(r"(?<=[.!?])\s+", out.strip())
        if len(sentences) > limit:
            out = " ".join(sentences[:limit])
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"[ \t]+([.,;:!?])", r"\1", out).strip()
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    return out


def short_for_voice(text: str, max_chars: int = 320) -> str:
    """Versão falada: no máximo ``max_chars``; o texto completo permanece na HUD."""
    spoken = stylize(text, channel="voice")
    if len(spoken) <= max_chars:
        return spoken
    cut = spoken[:max_chars]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("; "))
    if end > max_chars * 0.4:
        cut = cut[:end + 1]
    return cut.rstrip(",; ") + " Detalhes na interface."
