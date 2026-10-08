"""J.A.R.V.I.S. // Fases 36-40 — Neural HUD State Engine
A camada visual não executa ações. Ela traduz eventos reais do Neural Core em
estado visual: módulos ativos, rota, objetivo, voz e energia.
"""
from __future__ import annotations
import threading, time

LOCK = threading.RLock()

MODULES = {
    "VISION": {"label":"VISÃO", "group":"perception"},
    "MEMORY": {"label":"MEMÓRIA", "group":"intelligence"},
    "VOICE": {"label":"VOZ", "group":"interface"},
    "OLLAMA": {"label":"OLLAMA", "group":"intelligence"},
    "GPT": {"label":"GPT", "group":"intelligence"},
    "AGENT": {"label":"AGENTE", "group":"execution"},
    "WEB": {"label":"WEB", "group":"tools"},
    "WINDOWS": {"label":"WINDOWS", "group":"execution"},
    "FILES": {"label":"ARQUIVOS", "group":"tools"},
    "SKILLS": {"label":"SKILLS", "group":"intelligence"},
    "WORLD": {"label":"WORLD MODEL", "group":"context"},
}

_STATE_MODULES = {
    "PERCEIVING": {"VISION", "WORLD"},
    "CONTEXT": {"VISION", "WINDOWS", "WORLD", "MEMORY"},
    "DECIDING": {"WORLD", "MEMORY", "SKILLS"},
    "ROUTING": {"OLLAMA", "GPT"},
    "PLANNING": {"AGENT", "MEMORY", "SKILLS"},
    "EXECUTING": {"AGENT", "WINDOWS", "FILES", "WEB"},
    "VERIFYING": {"VISION", "WINDOWS", "WORLD", "AGENT"},
    "RECOVERY": {"AGENT", "MEMORY", "WORLD"},
    "WAITING": {"VOICE", "AGENT"},
    "SPEAKING": {"VOICE"},
    "LISTENING": {"VOICE"},
}

_state = {
    "state":"IDLE", "route":"OLLAMA_LOCAL", "goal":"AGUARDANDO OBJETIVO",
    "event":"CORE ONLINE", "active_modules":set(), "last_event":time.time(),
    "voice_active":False, "energy":0.24,
}


def reset():
    with LOCK:
        _state.update(state="IDLE", route="OLLAMA_LOCAL", goal="AGUARDANDO OBJETIVO",
                      event="CORE ONLINE", active_modules=set(), last_event=time.time(),
                      voice_active=False, energy=.24)


def update_event(event: dict):
    """Atualiza estado visual a partir de um evento do Core; nunca executa ferramentas."""
    if not isinstance(event, dict):
        return snapshot()
    kind = str(event.get("type", ""))
    with LOCK:
        if kind == "state":
            st = str(event.get("state", "IDLE"))
            _state["state"] = st
            _state["active_modules"] = set(_STATE_MODULES.get(st, set()))
            _state["energy"] = {"IDLE":.24,"WAITING":.45,"DONE":.35,"ERROR":.55}.get(st, 1.0)
        elif kind == "route":
            _state["route"] = str(event.get("route", "OLLAMA_LOCAL"))
            if _state["route"] == "OPENAI":
                _state["active_modules"].update({"GPT"})
            else:
                _state["active_modules"].add("OLLAMA")
        elif kind == "goal":
            _state["goal"] = str(event.get("goal", ""))[:120] or _state["goal"]
            _state["active_modules"].update({"AGENT", "WORLD"})
        elif kind in {"verification", "recovery", "timeline", "decision", "proactive"}:
            _state["event"] = str(event.get("message") or event.get("reason") or event.get("subject") or kind)[:140]
        elif kind == "result":
            _state["event"] = "VERIFICAÇÃO // OBJETIVO ENCERRADO"
            _state["active_modules"] = set()
        elif kind == "error":
            _state["state"] = "ERROR"
            _state["event"] = str(event.get("message", "falha do núcleo"))[:140]
        elif kind == "skills":
            _state["active_modules"].add("SKILLS")
        elif kind == "memory_recall":
            _state["active_modules"].add("MEMORY")
        elif kind in {"windows_state", "windows_state_warning"}:
            _state["active_modules"].add("WINDOWS")
        elif kind in {"multimodal", "multimodal_warning"}:
            _state["active_modules"].add("VISION")
        elif kind == "voice":
            _state["voice_active"] = bool(event.get("active", True))
            _state["active_modules"].add("VOICE")
        _state["last_event"] = time.time()
        return _snapshot_locked()


def _snapshot_locked():
    return {**_state, "active_modules": sorted(_state["active_modules"])}


def snapshot():
    with LOCK:
        return _snapshot_locked()
