"""J.A.R.V.I.S. // MISSION MANAGER (Fases 27-28)
Fila e ciclo de vida de missões. Não executa ferramentas.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
import threading, time, uuid

@dataclass
class Mission:
    id: str
    objective: str
    priority: int = 50
    status: str = "QUEUED"
    source: str = "user"
    created: float = field(default_factory=time.time)
    started: float = 0.0
    finished: float = 0.0
    result: str = ""
    error: str = ""
    metadata: dict = field(default_factory=dict)
    def to_dict(self): return asdict(self)

_LOCK=threading.RLock(); _QUEUE=[]; _CURRENT=None; _HISTORY=[]; _MAX_HISTORY=100

def enqueue(objective, *, priority=50, source="user", metadata=None):
    global _CURRENT
    m=Mission(uuid.uuid4().hex[:10], str(objective).strip(), int(priority), "QUEUED", source, metadata=dict(metadata or {}))
    with _LOCK:
        _QUEUE.append(m); _QUEUE.sort(key=lambda x:(-x.priority, x.created))
    return m.to_dict()

def next_mission():
    with _LOCK:
        for m in _QUEUE:
            if m.status=="QUEUED":
                m.status="RUNNING"; m.started=time.time()
                return m.to_dict()
    return None

def update(mission_id, **changes):
    with _LOCK:
        target=None
        if _CURRENT and _CURRENT.id==mission_id: target=_CURRENT
        if target is None:
            target=next((m for m in _QUEUE if m.id==mission_id), None)
        if not target: return None
        for k,v in changes.items():
            if hasattr(target,k): setattr(target,k,v)
        if target.status in {"DONE","FAILED","CANCELLED"}:
            target.finished=time.time(); _HISTORY.append(target.to_dict()); del _QUEUE[_QUEUE.index(target)]
        return target.to_dict()

def start_next():
    global _CURRENT
    with _LOCK:
        for m in _QUEUE:
            if m.status=="QUEUED":
                m.status="RUNNING"; m.started=time.time(); _CURRENT=m; return m.to_dict()
    return None

def current():
    with _LOCK: return _CURRENT.to_dict() if _CURRENT else None

def finish(mission_id, result="", status="DONE", error=""):
    global _CURRENT
    with _LOCK:
        m=_CURRENT if _CURRENT and _CURRENT.id==mission_id else next((x for x in _QUEUE if x.id==mission_id),None)
        if not m: return None
        m.status=status; m.result=str(result or ""); m.error=str(error or ""); m.finished=time.time()
        _HISTORY.append(m.to_dict())
        if m in _QUEUE: _QUEUE.remove(m)
        if _CURRENT and _CURRENT.id==mission_id: _CURRENT=None
        del _HISTORY[:-_MAX_HISTORY]
        return m.to_dict()

def cancel(mission_id): return finish(mission_id, status="CANCELLED")
def pending():
    with _LOCK: return [m.to_dict() for m in sorted(_QUEUE,key=lambda x:(-x.priority,x.created))]
def history(limit=20):
    with _LOCK: return list(_HISTORY[-max(1,int(limit)):])

def snapshot(): return {"current":current(),"pending":pending(),"history":history(20)}
