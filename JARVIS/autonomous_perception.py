"""J.A.R.V.I.S. // AUTONOMOUS PERCEPTION LOOP
Mantém uma percepção temporal do desktop sem transformar cada captura em uma chamada
caríssima ao modelo. Detecta mudanças, estabilidade, troca de aplicação e saliência.
Não executa ações e não trata conteúdo da tela como instrução.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from collections import deque
import hashlib, time
import threading

@dataclass
class PerceptionEvent:
    timestamp: float
    kind: str
    significance: float
    changed: bool
    focus_changed: bool
    stable: bool
    reason: str
    context_key: str
    sequence: int
    def to_dict(self): return asdict(self)

_LOCK=threading.RLock(); _HISTORY=deque(maxlen=80)
_LAST_HASH=""; _LAST_FOCUS=None; _STABLE_SINCE=None; _SEQUENCE=0


def _digest(thumb):
    if thumb is None: return ""
    try:
        if hasattr(thumb, "tobytes"): raw=thumb.tobytes()
        else: raw=bytes(thumb)
        return hashlib.blake2b(raw, digest_size=12).hexdigest()
    except Exception: return hashlib.blake2b(str(thumb).encode(), digest_size=12).hexdigest()


def reset():
    global _LAST_HASH,_LAST_FOCUS,_STABLE_SINCE,_SEQUENCE
    with _LOCK:
        _LAST_HASH=""; _LAST_FOCUS=None; _STABLE_SINCE=None; _SEQUENCE=0; _HISTORY.clear()


def observe(thumb, foreground, *, visual_analyzed=False, changed_threshold=False, settled=True):
    """Registra uma batida de percepção e devolve somente evidência temporal."""
    global _LAST_HASH,_LAST_FOCUS,_STABLE_SINCE,_SEQUENCE
    fg=dict(foreground or {}); focus=(str(fg.get("process") or "").lower(), str(fg.get("title") or "").lower())
    digest=_digest(thumb)
    with _LOCK:
        now=time.time(); _SEQUENCE+=1
        focus_changed=_LAST_FOCUS is not None and focus != _LAST_FOCUS
        visual_changed=bool(_LAST_HASH and digest and digest != _LAST_HASH)
        first=not bool(_LAST_HASH)
        changed=first or focus_changed or bool(changed_threshold)
        if not changed:
            if _STABLE_SINCE is None: _STABLE_SINCE=now
        else: _STABLE_SINCE=now
        stable=bool(settled and _STABLE_SINCE is not None and now-_STABLE_SINCE >= 2.0)
        significance=1.0 if focus_changed else (0.82 if changed_threshold else (0.58 if visual_changed else 0.08))
        if first: reason="primeira percepção do contexto"
        elif focus_changed: reason="janela ou processo em foco mudou"
        elif changed_threshold: reason="mudança visual relevante detectada"
        elif visual_changed: reason="imagem mudou desde a última percepção"
        else: reason="contexto permaneceu estável"
        context_key=f"{focus[0]}|{focus[1][:100]}"
        event=PerceptionEvent(now,"change" if changed else "heartbeat",significance,changed,focus_changed,stable,reason,context_key,_SEQUENCE)
        _HISTORY.append(event.to_dict()); _LAST_HASH=digest; _LAST_FOCUS=focus
        return event.to_dict()


def recent(limit=10):
    with _LOCK: return list(_HISTORY)[-max(1,min(int(limit),80)):]


def snapshot():
    with _LOCK:
        return {"last_focus":_LAST_FOCUS,"stable_since":_STABLE_SINCE,"sequence":_SEQUENCE,"recent":recent(10)}
