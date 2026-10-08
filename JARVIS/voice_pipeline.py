"""J.A.R.V.I.S. // Fase 37 — Voice Pipeline
Orquestra voz sem substituir o backend existente. O backend continua sendo a
fonte de verdade para TTS/STT; este módulo fornece estado, interrupção e
políticas para fala proativa.
"""
from __future__ import annotations
import threading, time

_LOCK = threading.RLock()
_STOP = threading.Event()
_state = {"listening":False, "speaking":False, "last_text":"", "interrupted":False, "last_at":0.0}


def snapshot():
    with _LOCK: return dict(_state)


def set_listening(active=True):
    with _LOCK: _state["listening"] = bool(active)
    try:
        import neural_hud_engine
        neural_hud_engine.update_event({"type":"voice","active":bool(active)})
    except Exception: pass


def begin_speaking(text):
    with _LOCK:
        _state.update(speaking=True, last_text=str(text)[:300], interrupted=False, last_at=time.time())
    try:
        import neural_hud_engine
        neural_hud_engine.update_event({"type":"voice","active":True})
    except Exception: pass


def end_speaking():
    with _LOCK: _state["speaking"] = False


def interrupt():
    _STOP.set()
    with _LOCK: _state.update(interrupted=True, speaking=False)
    return True


def clear_interrupt(): _STOP.clear()


def should_interrupt(): return _STOP.is_set()


def speak_proactive(text, speak=None):
    """Fala uma sugestão uma única vez; respeita interrupção e não executa ações."""
    if not str(text).strip() or speak is None: return False
    with _LOCK:
        if _state["speaking"]: return False
    begin_speaking(text)
    try:
        if should_interrupt(): return False
        speak(str(text).strip())
        return True
    finally:
        end_speaking()
