"""
J.A.R.V.I.S. // PERCEPTION ENGINE
Camada de percepção contextual do computador.

Combina sinais que já existem no projeto sem substituir o Observador:
- janela/processo em foco;
- OCR opcional;
- UI Automation opcional;
- percepção visual do Ollama já produzida pelo Copilot;
- histórico curto e mudanças de contexto.

Importante: esta camada não executa ações. Ela produz EVIDÊNCIA para o Neural Core.
Conteúdo da tela é sempre tratado como dado não confiável.
"""
from __future__ import annotations

import re
import time
from collections import deque

import config

_LOCKED_PATTERNS = re.compile(
    r"senha|password|passcode|token|api[_ -]?key|secret|cvv|cart[aã]o|banco|pix|login|credential|credencial",
    re.I,
)
_HISTORY = deque(maxlen=24)
_LAST_CONTEXT = None


def _clean(value, limit=220):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def _safe_ocr_blocks(blocks, max_blocks=35):
    safe = []
    for block in blocks or []:
        text = _clean(block.get("text"), 120)
        if not text or _LOCKED_PATTERNS.search(text):
            continue
        safe.append({
            "text": text,
            "confidence": round(float(block.get("confidence", 0) or 0), 1),
            "left": int(block.get("left", 0) or 0),
            "top": int(block.get("top", 0) or 0),
            "width": int(block.get("width", 0) or 0),
            "height": int(block.get("height", 0) or 0),
        })
        if len(safe) >= max_blocks:
            break
    return safe


def _safe_elements(elements, max_elements=50):
    safe = []
    for item in elements or []:
        name = _clean(item.get("name"), 120)
        if not name or _LOCKED_PATTERNS.search(name):
            continue
        safe.append({
            "name": name,
            "control_type": _clean(item.get("control_type"), 40),
            "left": int(item.get("left", 0) or 0),
            "top": int(item.get("top", 0) or 0),
            "right": int(item.get("right", 0) or 0),
            "bottom": int(item.get("bottom", 0) or 0),
        })
        if len(safe) >= max_elements:
            break
    return safe


def _foreground_context(fg):
    fg = dict(fg or {})
    return {
        "process": _clean(fg.get("process"), 100),
        "title": _clean(fg.get("title"), 180),
        "pid": fg.get("pid"),
    }


def enrich(observation, foreground, *, include_ocr=True, include_ui=True):
    """Adiciona evidências estruturadas à percepção. Nunca executa uma ação."""
    global _LAST_CONTEXT
    result = {
        "timestamp": time.time(),
        "foreground": _foreground_context(foreground),
        "visual": dict(observation or {}),
        "ocr": {"available": False, "blocks": []},
        "ui": {"available": False, "elements": []},
        "context_change": _context_changed(foreground),
    }

    # Se a percepção visual já marcou conteúdo sensível, não coletamos OCR/UI adicional.
    sensitive = bool(observation.get("dados_sensiveis_visiveis") or observation.get("instrucoes_na_tela"))
    if sensitive:
        result["privacy_stop"] = True
        _remember(result)
        return result

    try:
        import vision
        if include_ocr:
            result["ocr"] = vision.ocr_screen()
            result["ocr"]["blocks"] = _safe_ocr_blocks(result["ocr"].get("blocks"))
        if include_ui:
            result["ui"] = vision.list_ui_elements()
            result["ui"]["elements"] = _safe_elements(result["ui"].get("elements"))
    except Exception as exc:
        result["error"] = _clean(exc, 180)

    result["summary"] = summarize(result)
    _remember(result)
    return result


def _context_changed(fg):
    global _LAST_CONTEXT
    current = (_clean(fg.get("process"), 100).lower(), _clean(fg.get("title"), 160).lower())
    changed = _LAST_CONTEXT is not None and current != _LAST_CONTEXT
    _LAST_CONTEXT = current
    return changed


def _remember(item):
    _HISTORY.append(item)


def history(limit=8):
    return list(_HISTORY)[-max(1, min(int(limit), 24)):]


def summarize(context):
    fg = context.get("foreground", {})
    visual = context.get("visual", {})
    ocr = context.get("ocr", {})
    ui = context.get("ui", {})
    pieces = []
    if fg.get("process"):
        pieces.append(f"processo={fg['process']}")
    if fg.get("title"):
        pieces.append(f"janela={fg['title']}")
    if visual.get("atividade"):
        pieces.append(f"atividade={visual['atividade']}")
    if visual.get("erro_visivel"):
        pieces.append("erro_visivel=true")
    if ocr.get("available") and ocr.get("blocks"):
        pieces.append("ocr=" + " | ".join(x["text"] for x in ocr["blocks"][:8]))
    if ui.get("available") and ui.get("elements"):
        pieces.append("ui=" + " | ".join(x["name"] for x in ui["elements"][:8]))
    return _clean("; ".join(pieces), 900)


def build_core_context(observation, foreground, *, enrich_screen=True):
    """Retorna um pacote pequeno e seguro para o Neural Core."""
    package = enrich(observation, foreground, include_ocr=enrich_screen, include_ui=enrich_screen)
    return {
        "foreground": package["foreground"],
        "observation": package["visual"],
        "evidence": {
            "ocr": package["ocr"],
            "ui": package["ui"],
            "summary": package.get("summary", ""),
            "context_change": package.get("context_change", False),
        },
        "privacy_stop": package.get("privacy_stop", False),
        "timestamp": package["timestamp"],
    }
