"""J.A.R.V.I.S. // LONG RUNNING AGENT (Fase 28)
Executor de missões em background. Uma missão por vez; fila gerenciada separadamente.
"""
from __future__ import annotations
import threading
_LOCK=threading.RLock(); _RUNNING=False; _STOP=threading.Event()

def running():
    with _LOCK: return _RUNNING

def stop(): _STOP.set()

def run_next(*, on_timeline=None, on_log=None, conversation=None):
    global _RUNNING
    on_timeline=on_timeline or (lambda *a,**k:None); on_log=on_log or (lambda *a,**k:None)
    import mission_manager
    m=mission_manager.start_next()
    if not m: return None
    with _LOCK: _RUNNING=True
    try:
        import autonomous_agent_runtime
        if _STOP.is_set():
            return mission_manager.finish(m["id"],status="CANCELLED")
        result=autonomous_agent_runtime.run(m["objective"], conversation or [], on_timeline=on_timeline, on_log=on_log)
        return mission_manager.finish(m["id"], result=result, status="DONE")
    except Exception as exc:
        return mission_manager.finish(m["id"], status="FAILED", error=str(exc)[:500])
    finally:
        with _LOCK: _RUNNING=False; _STOP.clear()
