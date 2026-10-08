"""J.A.R.V.I.S. // GOAL MANAGER
Mantém objetivos, evidências, progresso e limites de uma missão do agente.
"""
from __future__ import annotations
import threading, time, uuid
from dataclasses import dataclass, field

@dataclass
class Goal:
    id: str
    objective: str
    source: str
    confidence: float
    risk: str
    status: str = "PROPOSED"
    created: float = field(default_factory=time.time)
    steps: list = field(default_factory=list)
    evidence: list = field(default_factory=list)

    def to_dict(self):
        return {"id":self.id,"objective":self.objective,"source":self.source,"confidence":self.confidence,
                "risk":self.risk,"status":self.status,"created":self.created,"steps":list(self.steps),"evidence":list(self.evidence)}

_LOCK=threading.RLock(); _CURRENT=None; _HISTORY=[]

def create(objective, *, source="user", confidence=1.0, risk="medium"):
    global _CURRENT
    g=Goal(uuid.uuid4().hex[:10], str(objective).strip(), source, float(confidence), risk)
    with _LOCK: _CURRENT=g; _HISTORY.append(g.to_dict())
    return g

def current():
    with _LOCK: return _CURRENT.to_dict() if _CURRENT else None

def update(status=None, step=None, evidence=None):
    with _LOCK:
        if not _CURRENT: return None
        if status: _CURRENT.status=str(status)
        if step: _CURRENT.steps.append(dict(step) if isinstance(step,dict) else str(step))
        if evidence: _CURRENT.evidence.append(dict(evidence) if isinstance(evidence,dict) else str(evidence))
        return _CURRENT.to_dict()

def finish(status="DONE"):
    return update(status=status)

def history(limit=10):
    with _LOCK: return list(_HISTORY[-max(1,int(limit)):])
