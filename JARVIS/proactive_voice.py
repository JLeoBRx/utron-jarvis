"""J.A.R.V.I.S. // Fase 40 — Proactive Voice Policy"""
from __future__ import annotations
import time
_LOCK={}

def allow(key, cooldown=180.0):
    now=time.time(); last=_LOCK.get(str(key),0.0)
    if now-last < float(cooldown): return False
    _LOCK[str(key)]=now; return True

def message(reason, *, prefix="Senhor"):
    text=str(reason).strip().rstrip('.')
    return f"{prefix}, detectei algo que pode exigir sua atenção: {text}."
