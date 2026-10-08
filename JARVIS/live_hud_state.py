"""J.A.R.V.I.S. // Fase 38 — Live State
Snapshot pequeno e thread-safe para a HUD. Não executa nada.
"""
from __future__ import annotations
import threading, time
_LOCK=threading.RLock()
_state={"windows":{},"world":{},"voice":{},"runtime":{},"updated":0.0}

def update(**kwargs):
    with _LOCK:
        _state.update(kwargs); _state["updated"] = time.time()
        return snapshot()

def snapshot():
    with _LOCK:
        return {k:(dict(v) if isinstance(v,dict) else v) for k,v in _state.items()}
