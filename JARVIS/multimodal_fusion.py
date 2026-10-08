"""J.A.R.V.I.S. // MULTIMODAL FUSION (Fase 31)
Consolida evidências de tela, Windows, OCR, UI, voz/texto e memória em um
pacote de contexto. Não executa ações.
"""
from __future__ import annotations
import time


def _text(value, limit=900):
    return str(value or "").strip()[:limit]


def build(*, observation=None, foreground=None, windows_state=None,
          conversation=None, goal=None, memory_context=None):
    observation = observation or {}
    foreground = foreground or {}
    windows_state = windows_state or {}
    conversation = conversation or []
    recent = conversation[-4:] if isinstance(conversation, list) else []
    evidence = observation.get("evidencia_tela") or {}
    ui = evidence.get("ui") or {}
    ocr = evidence.get("ocr") or {}
    return {
        "timestamp": time.time(),
        "goal": _text(goal, 700),
        "foreground": {
            "process": _text(foreground.get("process"), 180),
            "title": _text(foreground.get("title"), 300),
        },
        "windows": {
            "active": windows_state.get("active") or {},
            "count": len(windows_state.get("windows") or []),
        },
        "visual": {
            "summary": _text(evidence.get("summary"), 900),
            "context_change": bool(evidence.get("context_change")),
            "ocr_blocks": len(ocr.get("blocks") or []),
            "ui_elements": len(ui.get("elements") or []),
        },
        "error": {
            "visible": bool(observation.get("erro_visivel")),
            "text": _text(observation.get("erro_texto"), 700),
        },
        "conversation": recent,
        "memory": _text(memory_context, 1000),
        "source": "multimodal_fusion",
    }
