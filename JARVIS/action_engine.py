"""J.A.R.V.I.S. // Action Engine

Camada de execução orientada a alvo para Windows.
Prioridade: UI Automation -> OCR -> coordenadas.
Nunca executa shell, PowerShell ou comandos arbitrários.
"""
from __future__ import annotations

import re
import time

import config
import context_state
import vision


def _norm(value):
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _foreground_signature():
    try:
        import commands
        fg = commands.foreground_info()
        return {
            "title": str(fg.get("title") or ""),
            "process": str(fg.get("process") or ""),
            "pid": fg.get("pid"),
        }
    except Exception:
        return {"title": "", "process": "", "pid": None}


def locate_target(description):
    """Localiza um alvo e devolve apenas um alvo se houver correspondência inequívoca."""
    result = vision.locate(description)
    matches = result.get("matches") or []
    if len(matches) != 1:
        return {
            "ok": False,
            "reason": "ambiguous" if len(matches) > 1 else "not_found",
            "message": "Encontrei múltiplos alvos." if len(matches) > 1 else "Não encontrei um alvo único.",
            "matches": matches[:8],
            "engine": result.get("engine", ""),
        }
    target = dict(matches[0])
    target["description"] = str(description)[:200]
    target["foreground"] = _foreground_signature()
    return {"ok": True, "target": target, "engine": result.get("engine", "")}


def _target_center(target):
    left = int(target.get("left", 0))
    top = int(target.get("top", 0))
    width = int(target.get("width", max(1, int(target.get("right", left + 1)) - left)))
    height = int(target.get("height", max(1, int(target.get("bottom", top + 1)) - top)))
    return left + max(1, width // 2), top + max(1, height // 2)


def click(description, *, require_confirmation=True):
    """Localiza, valida janela e clica em um único alvo."""
    found = locate_target(description)
    if not found["ok"]:
        return False, found["message"], {"verified": False, "reason": found["reason"]}

    target = found["target"]
    before = target.get("foreground") or {}
    current = _foreground_signature()
    if before.get("pid") and current.get("pid") and before["pid"] != current["pid"]:
        return False, "A janela mudou durante a preparação da ação. Não executei o clique.", {
            "verified": False, "reason": "foreground_changed"
        }

    risk = "medium"
    if _norm(target.get("control_type")) in {"button", "hyperlink", "menuitem"}:
        risk = "medium"

    if require_confirmation:
        return False, "Ação localizada e pronta para confirmação.", {
            "verified": False,
            "confirmation_required": True,
            "risk": risk,
            "target": target,
        }

    try:
        import commands
        x, y = _target_center(target)
        commands.pyautogui.moveTo(x, y, duration=0.08)
        commands.pyautogui.click()
        time.sleep(0.15)
        context_state.add_event("action", f"Clique executado em {target.get('name') or description}.")
        return True, f"Clique executado em {target.get('name') or description}.", {
            "verified": True,
            "risk": risk,
            "target": target,
            "evidence": f"Alvo único localizado por {found.get('engine', 'visão estruturada')}.",
        }
    except Exception as exc:
        return False, f"Não consegui executar o clique: {exc}", {"verified": False, "reason": str(exc)}


def safe_action_policy():
    """Política efetiva; mantém execução automática desligada por padrão."""
    return {
        "automatic_clicks": bool(getattr(config, "ALLOW_AUTONOMOUS_UI_CLICKS", False)),
        "requires_unique_target": True,
        "requires_same_foreground": True,
        "fallback_order": ["uia", "ocr", "coordinates"],
    }
