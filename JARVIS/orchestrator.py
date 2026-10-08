"""
J.A.R.V.I.S. // estado do orquestrador autônomo.
Mantém um estado operacional explícito para cada tarefa: objetivo, contexto,
etapa atual, ferramenta, verificação, recuperação e resultado.
Não executa ações por conta própria; apenas coordena e registra o estado.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid

import config

STATES = (
    "IDLE", "UNDERSTANDING", "PLANNING", "EXECUTING", "VERIFYING",
    "RECOVERING", "WAITING_CONFIRMATION", "COMPLETED", "BLOCKED", "FAILED", "CANCELLED",
)

_lock = threading.RLock()
_task = None
_history = []
_listener = None


def _path():
    return os.path.join(config.db_dir(), "orchestrator_state.json")


def set_listener(callback):
    global _listener
    _listener = callback


def _emit():
    callback = _listener
    snapshot = status()
    if callback:
        try:
            callback(snapshot)
        except Exception:
            pass


def _safe(text, limit=600):
    text = str(text or "").strip()
    return text[:limit]


def _new_task(goal, source="user", context=None):
    now = time.time()
    return {
        "id": uuid.uuid4().hex[:12],
        "created_at": now,
        "updated_at": now,
        "source": _safe(source, 40),
        "goal": _safe(goal, 900),
        "context": _safe(context, 1400),
        "state": "UNDERSTANDING",
        "step": 0,
        "tool_calls": 0,
        "current_tool": "",
        "last_event": "Tarefa recebida.",
        "last_evidence": "",
        "last_error": "",
        "recovery_attempts": 0,
        "confirmation_required": False,
        "result": "",
    }


def _persist():
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        payload = {"active": _task, "history": _history[-20:]}
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, _path())
    except Exception:
        pass


def start(goal, source="user", context=None):
    global _task
    with _lock:
        _task = _new_task(goal, source, context)
        _history.append({**_task})
        _persist()
    _emit()
    return _task["id"]


def active():
    with _lock:
        return _task is not None and _task["state"] not in {
            "COMPLETED", "BLOCKED", "FAILED", "CANCELLED", "IDLE"
        }


def update(state=None, event=None, step=None, tool=None, evidence=None,
           error=None, recovery_attempts=None, confirmation=None, result=None):
    global _task
    with _lock:
        if _task is None:
            return None
        if state is not None and state not in STATES:
            raise ValueError(f"Estado de tarefa inválido: {state}")
        if state is not None:
            _task["state"] = state
        if event is not None:
            _task["last_event"] = _safe(event, 500)
        if step is not None:
            _task["step"] = max(0, int(step))
        if tool is not None:
            _task["current_tool"] = _safe(tool, 100)
            _task["tool_calls"] += 1
        if evidence is not None:
            _task["last_evidence"] = _safe(evidence, 500)
        if error is not None:
            _task["last_error"] = _safe(error, 500)
        if recovery_attempts is not None:
            _task["recovery_attempts"] = max(0, int(recovery_attempts))
        if confirmation is not None:
            _task["confirmation_required"] = bool(confirmation)
        if result is not None:
            _task["result"] = _safe(result, 900)
        _task["updated_at"] = time.time()
        _persist()
        snapshot = dict(_task)
    _emit()
    return snapshot


def complete(result):
    return update(state="COMPLETED", event="Tarefa concluída.", result=result,
                  confirmation=False, error="")


def fail(message, blocked=False):
    return update(state="BLOCKED" if blocked else "FAILED",
                  event="Execução interrompida.", error=message,
                  result=message, confirmation=False)


def cancel(message="Tarefa cancelada, senhor."):
    return update(state="CANCELLED", event="Tarefa cancelada.", result=message,
                  confirmation=False)


def clear():
    global _task
    with _lock:
        _task = None
        _persist()
    _emit()


def status():
    with _lock:
        return dict(_task) if _task else {
            "id": "", "state": "IDLE", "goal": "", "context": "", "step": 0,
            "tool_calls": 0, "current_tool": "", "last_event": "Nenhuma tarefa ativa.",
            "last_evidence": "", "last_error": "", "recovery_attempts": 0,
            "confirmation_required": False, "result": "", "source": "",
        }


def summary():
    data = status()
    if data["state"] == "IDLE":
        return "Nenhuma tarefa ativa."
    goal = _safe(data.get("goal"), 100)
    tool = _safe(data.get("current_tool"), 50)
    state = data.get("state", "IDLE")
    step = data.get("step", 0)
    if tool:
        return f"{state} | passo {step} | {tool} | {goal}"
    return f"{state} | passo {step} | {goal}"


def history():
    with _lock:
        return [dict(item) for item in _history[-20:]]
