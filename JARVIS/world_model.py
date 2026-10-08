"""J.A.R.V.I.S. // WORLD MODEL
Representação compacta e temporal do estado conhecido do computador.
Não executa ações. Mantém entidades observadas, relações, objetivo e confiança.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import deque
import threading, time

@dataclass
class Entity:
    key: str
    kind: str
    name: str
    state: str = "observed"
    confidence: float = 0.0
    last_seen: float = 0.0
    metadata: dict | None = None
    def to_dict(self): return asdict(self)

_LOCK=threading.RLock(); _ENTITIES={}; _RELATIONS=deque(maxlen=120); _EVENTS=deque(maxlen=80)
_CURRENT_GOAL=None; _MISSION=None

def reset():
    global _CURRENT_GOAL,_MISSION
    with _LOCK:
        _ENTITIES.clear(); _RELATIONS.clear(); _EVENTS.clear(); _CURRENT_GOAL=None; _MISSION=None

def _upsert(key, kind, name, confidence=0.5, state="observed", metadata=None):
    now=time.time(); old=_ENTITIES.get(key)
    if old:
        old.name=name or old.name; old.state=state; old.confidence=max(float(old.confidence),float(confidence)); old.last_seen=now
        if metadata: old.metadata={**(old.metadata or {}), **metadata}
        return old
    e=Entity(key,kind,name,state,float(confidence),now,metadata or {})
    _ENTITIES[key]=e; return e

def update(package, *, goal=None, decision=None):
    global _CURRENT_GOAL, _MISSION
    """Atualiza o modelo apenas com evidência estruturada já produzida pelo sistema."""
    fg=dict(package.get("foreground") or {}); obs=dict(package.get("observation") or {})
    evidence=dict(package.get("evidence") or {})
    confidence=float(obs.get("confianca",0.5) or 0.5)
    process=str(fg.get("process") or "").strip(); title=str(fg.get("title") or "").strip()
    with _LOCK:
        now=time.time(); changes=[]
        if process or title:
            app_name=title or process
            app=_upsert("app:"+process.lower(),"application",app_name,confidence,metadata={"process":process,"title":title})
            changes.append(app.key)
            _upsert("window:"+title.lower()[:160],"window",title or process,confidence,metadata={"process":process}) if title else None
            if process and title: _RELATIONS.append({"from":app.key,"type":"owns_window","to":"window:"+title.lower()[:160],"ts":now})
        activity=str(obs.get("atividade") or "").strip()
        if activity:
            e=_upsert("activity:"+activity.lower()[:160],"activity",activity,confidence)
            changes.append(e.key)
        if obs.get("erro_visivel") or obs.get("erro_texto"):
            err=str(obs.get("erro_texto") or obs.get("resumo") or "erro observado").strip()[:500]
            e=_upsert("error:"+err.lower()[:180],"error",err,confidence,"active")
            changes.append(e.key)
        if goal:
            _CURRENT_GOAL=dict(goal) if isinstance(goal,dict) else {"text":str(goal)}
            _MISSION={"status":"active","updated":now,"goal":_CURRENT_GOAL}
        elif _MISSION:
            _MISSION["updated"]=now
        event={"ts":now,"type":"update","changed_entities":changes,"goal":_CURRENT_GOAL,"decision":decision or {}}
        _EVENTS.append(event)
        return snapshot()

def set_goal(goal, status="active"):
    global _CURRENT_GOAL,_MISSION
    with _LOCK:
        _CURRENT_GOAL=dict(goal) if isinstance(goal,dict) else {"text":str(goal)}
        _MISSION={"status":status,"updated":time.time(),"goal":_CURRENT_GOAL}
        return snapshot()

def set_mission_status(status):
    with _LOCK:
        if _MISSION: _MISSION["status"]=str(status); _MISSION["updated"]=time.time()
        return snapshot()

def snapshot():
    with _LOCK:
        return {"timestamp":time.time(),"entities":[e.to_dict() for e in _ENTITIES.values()],
                "relations":list(_RELATIONS)[-40:],"events":list(_EVENTS)[-20:],
                "goal":dict(_CURRENT_GOAL) if _CURRENT_GOAL else None,"mission":dict(_MISSION) if _MISSION else None}

def relevant(limit=20):
    s=snapshot(); s["entities"]=sorted(s["entities"],key=lambda x:x.get("last_seen",0),reverse=True)[:max(1,int(limit))]
    return s


def update_windows_state(state: dict):
    """Incorpora estado estrutural do Windows como evidência somente-leitura."""
    if not isinstance(state, dict):
        return snapshot()
    with _LOCK:
        now = time.time()
        active = dict(state.get("active_window") or {})
        if active.get("available"):
            pid = active.get("pid")
            process = str(active.get("process") or "").strip()
            title = str(active.get("title") or "").strip()
            key = "windows:active"
            _upsert(key, "active_window", title or process or "Janela ativa", 0.98, metadata={
                "hwnd": active.get("hwnd"), "pid": pid, "process": process,
                "title": title, "rect": active.get("rect"),
            })
            if process:
                app = _upsert("app:" + process.lower(), "application", process, 0.98, metadata={"pid": pid})
                _RELATIONS.append({"from": app.key, "type": "active", "to": key, "ts": now})
            if title:
                win_key = "window:" + title.lower()[:160]
                _upsert(win_key, "window", title, 0.98, metadata={"pid": pid, "process": process, "rect": active.get("rect")})
                _RELATIONS.append({"from": key, "type": "references", "to": win_key, "ts": now})
        _EVENTS.append({"ts": now, "type": "windows_state", "available": bool(state.get("available")),
                        "window_count": len(state.get("windows") or []),
                        "active": active.get("title") or active.get("process") or ""})
        return snapshot()
