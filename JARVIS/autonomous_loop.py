"""J.A.R.V.I.S. // PERSISTENT AUTONOMOUS LOOP (Fase 24)
Observa continuamente e só promove uma observação a missão quando a política permitir.
"""
from __future__ import annotations
import threading, time
import config

_LOCK=threading.RLock(); _STOP=threading.Event(); _THREAD=None
_STATE={"running":False,"cycles":0,"last_cycle":0.0,"last_decision":None,"last_error":""}

def snapshot():
    with _LOCK: return dict(_STATE)

def _capture():
    import windows_state_adapter
    windows=windows_state_adapter.snapshot(include_windows=True)
    fg=windows.get("active_window") or {}
    observation={"foreground":fg,"evidencia_tela":{"context_change":False,"summary":"estado estrutural capturado"}}
    try:
        import perception_engine
        observation.update(perception_engine.build_core_context({}, fg, enrich_screen=True))
    except Exception as exc:
        observation["perception_warning"]=str(exc)[:180]
    return observation, fg, windows

def run_once(*, on_event=None, allow_autonomous_actions=None):
    on_event=on_event or (lambda *a,**k:None)
    observation, fg, windows=_capture()
    import proactive_assistance
    decision=proactive_assistance.evaluate(observation, fg, {"current": observation})
    with _LOCK:
        _STATE["cycles"]+=1; _STATE["last_cycle"]=time.time(); _STATE["last_decision"]=decision.to_dict()
    on_event("perception", observation=observation, windows=windows)
    on_event("proactive", decision=decision.to_dict())
    # Por padrão, a autonomia passiva apenas sugere. A promoção para execução requer flag explícita
    # e uma missão objetiva fornecida pela percepção.
    allow = bool(getattr(config,"AUTONOMOUS_ACTIONS_ENABLED",False) if allow_autonomous_actions is None else allow_autonomous_actions)
    if allow and decision.action=="SUGGEST" and decision.objective:
        import human_in_loop
        auth=human_in_loop.classify(decision.objective)
        if auth.mode=="AUTO":
            import mission_manager
            mission=mission_manager.enqueue(decision.objective, source="proactive", priority=40, metadata={"decision":decision.to_dict()})
            on_event("mission_created", mission=mission)
            return {"decision":decision.to_dict(),"mission":mission,"observation":observation}
    return {"decision":decision.to_dict(),"observation":observation}

def _worker(interval):
    with _LOCK: _STATE["running"]=True
    try:
        while not _STOP.is_set():
            try: run_once()
            except Exception as exc:
                with _LOCK: _STATE["last_error"]=str(exc)[:300]
            _STOP.wait(max(0.5,float(interval)))
    finally:
        with _LOCK: _STATE["running"]=False

def start(interval=None):
    global _THREAD
    with _LOCK:
        if _STATE["running"]: return False
        _STOP.clear(); interval=float(interval or getattr(config,"AUTONOMOUS_LOOP_INTERVAL",3.0))
        _STATE["running"] = True
        _THREAD=threading.Thread(target=_worker,args=(interval,),daemon=True,name="JARVIS-AutonomousLoop"); _THREAD.start(); return True

def stop(timeout=3):
    _STOP.set(); t=_THREAD
    if t and t.is_alive(): t.join(max(0.1,float(timeout)))
    return not snapshot()["running"]
