"""J.A.R.V.I.S. // INTENT ENGINE 2 (Fase 31/32)
Inferência contextual com múltiplos sinais. Sem execução e sem raciocínio exposto.
"""
from __future__ import annotations


def infer(context: dict) -> dict:
    obs = context.get("observation") or context
    error = bool((context.get("error") or {}).get("visible") or obs.get("erro_visivel"))
    process = str((context.get("foreground") or {}).get("process", "")).lower()
    title = str((context.get("foreground") or {}).get("title", "")).lower()
    visual = context.get("visual") or {}
    goal = str(context.get("goal", "")).strip()
    if error:
        return {"kind":"troubleshoot", "confidence":0.91, "actionable":True,
                "goal": goal or f"investigar erro visível em {process or 'aplicativo atual'}",
                "signals":["error","visual"]}
    if goal:
        return {"kind":"task", "confidence":0.86, "actionable":True,
                "goal":goal, "signals":["explicit_goal","context"]}
    if visual.get("context_change") and (process or title):
        return {"kind":"observe", "confidence":0.72, "actionable":False,
                "goal":"", "signals":["context_change"]}
    if process:
        return {"kind":"work", "confidence":0.62, "actionable":False,
                "goal":"", "signals":["foreground_app"]}
    return {"kind":"observe", "confidence":0.35, "actionable":False,
            "goal":"", "signals":[]}
