"""Geração estruturada (JSON) com o modelo local, com fallback procedural declarado."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from ..models.ollama_client import OllamaError
from ..models.router import ModelUnavailable

log = logging.getLogger("ultron.imagination")

CREATIVE_SYSTEM = (
    "Você é o núcleo de imaginação do ULTRON. Crie conteúdo original, coerente e específico em português do Brasil. "
    "Responda SOMENTE com JSON válido no formato pedido, sem comentários."
)


def parse(text: str) -> dict | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except ValueError:
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if match:
            try:
                value = json.loads(match.group(0))
                return value if isinstance(value, dict) else None
            except ValueError:
                return None
    return None


def generate(router, prompt: str, *, fallback: Callable[[], dict], required: tuple[str, ...], cancel=None,
             temperature: float = 0.85, num_predict: int = 900) -> dict:
    """Pede JSON ao modelo local; sem modelo ou com resposta inválida, usa o fallback procedural."""
    if router is not None:
        try:
            result = router.chat("text", [{"role": "system", "content": CREATIVE_SYSTEM},
                                          {"role": "user", "content": prompt}],
                                 fmt="json", options={"temperature": temperature, "num_predict": num_predict},
                                 timeout=180, cancel=cancel)
            data = parse(result.content)
            if data and all(data.get(k) for k in required):
                data["generator"] = f"llm:{result.model}"
                return data
            log.info("resposta criativa incompleta; usando gerador procedural")
        except ModelUnavailable as exc:
            log.info("modelo indisponível para imaginação: %s", exc)
        except OllamaError as exc:
            if exc.kind == "CANCELLED":
                raise
            log.info("falha do modelo na imaginação: %s", exc)
    data = fallback()
    data["generator"] = "procedural"
    return data


def clean_text(value: Any, limit: int = 600) -> str:
    return " ".join(str(value or "").split())[:limit]


def clean_map(value: Any, keys: tuple[str, ...], limit: int = 400) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    lowered = {str(k).upper(): v for k, v in source.items()}
    return {k: clean_text(lowered.get(k), limit) for k in keys if lowered.get(k)}
