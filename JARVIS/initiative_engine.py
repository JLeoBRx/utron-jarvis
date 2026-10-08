"""J.A.R.V.I.S. // motor de iniciativa proativa.

Transforma percepções em decisões explícitas: ignorar, oferecer, executar uma
ação de baixo risco ou escalar. Não executa ferramentas diretamente e nunca
altera a política de permissões.
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import defaultdict, deque

import config
import permission_engine

IGNORE = "IGNORE"
OFFER = "OFFER"
AUTO_LOW_RISK = "AUTO_LOW_RISK"
ESCALATE = "ESCALATE"
DECISIONS = (IGNORE, OFFER, AUTO_LOW_RISK, ESCALATE)

DEFAULTS = {
    "enabled": True,
    "mode": "balanced",          # quiet | balanced | assertive
    "cooldown": 120.0,
    "offer_cooldown": 60.0,
    "max_events_hour": 18,
}
MODES = ("quiet", "balanced", "assertive")

LOW_RISK = {
    "open_app", "search_web", "search_files", "control_volume", "control_media"
}
NEVER_PROACTIVE = {
    "open_url", "take_screenshot", "run_automation", "close_app", "move_path",
    "delete_path", "power", "control_radio", "delete_automation", "forget_fact"
}

_lock = threading.RLock()
_events = deque(maxlen=300)
_last_signature = {}
_hour_events = deque()
_settings = dict(DEFAULTS)


def _path():
    return os.path.join(config.data_dir(), "initiative.json")


def _load():
    global _settings
    try:
        with open(_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            _settings["enabled"] = bool(data.get("enabled", DEFAULTS["enabled"]))
            if data.get("mode") in MODES:
                _settings["mode"] = data["mode"]
            for key in ("cooldown", "offer_cooldown"):
                try:
                    _settings[key] = max(15.0, min(3600.0, float(data.get(key, DEFAULTS[key]))))
                except (TypeError, ValueError):
                    pass
            try:
                _settings["max_events_hour"] = max(1, min(100, int(data.get("max_events_hour", DEFAULTS["max_events_hour"]))))
            except (TypeError, ValueError):
                pass
    except (OSError, ValueError, TypeError):
        pass


def _save():
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_settings, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, _path())
    except OSError:
        pass


_load()


def _clean(value, limit=280):
    return " ".join(str(value or "").split())[:limit]


def _signature(candidate):
    return "|".join([
        _clean(candidate.get("type"), 40).lower(),
        _clean(candidate.get("context_key"), 100).lower(),
        _clean(candidate.get("summary"), 180).lower(),
        _clean(candidate.get("suggested_action", {}).get("tool") if isinstance(candidate.get("suggested_action"), dict) else "", 40).lower(),
    ])


def _prune(now=None):
    now = now or time.time()
    while _hour_events and now - _hour_events[0] > 3600:
        _hour_events.popleft()


def _risk(candidate):
    action = candidate.get("suggested_action") or {}
    tool = action.get("tool") if isinstance(action, dict) else None
    if not tool:
        return "none"
    return permission_engine.risk(tool)


def _action_allowed(candidate):
    action = candidate.get("suggested_action") or {}
    if not isinstance(action, dict):
        return False
    tool = str(action.get("tool") or "")
    if tool in NEVER_PROACTIVE or tool not in LOW_RISK:
        return False
    try:
        args = action.get("args") or {}
        if type(args) is not dict:
            return False
        decision = permission_engine.decide(tool)
        return decision == "allow"
    except Exception:
        return False


def consider(candidate):
    """Retorna um registro de decisão sem executar nada."""
    candidate = dict(candidate or {})
    now = time.time()
    try:
        confidence = float(candidate.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    candidate["confidence"] = max(0.0, min(1.0, confidence))
    candidate["risk"] = _risk(candidate)
    signature = _signature(candidate)
    candidate["signature"] = signature

    with _lock:
        _prune(now)
        if not _settings["enabled"]:
            decision = IGNORE
            reason = "iniciativa desativada"
        elif len(_hour_events) >= _settings["max_events_hour"]:
            decision = IGNORE
            reason = "limite horário atingido"
        elif candidate["confidence"] < 0.55:
            decision = IGNORE
            reason = "confiança insuficiente"
        elif now - _last_signature.get(signature, 0.0) < _settings["cooldown"]:
            decision = IGNORE
            reason = "cooldown do mesmo contexto"
        else:
            typ = str(candidate.get("type") or "observation")
            urgent = float(candidate.get("urgency", 0.0) or 0.0) >= 0.85
            has_action = bool(candidate.get("suggested_action"))
            risk = candidate["risk"]
            if has_action and _action_allowed(candidate) and candidate["confidence"] >= 0.78:
                decision = AUTO_LOW_RISK
                reason = "ação explícita, allowlist de baixo risco e permissão liberada"
            elif urgent and candidate["confidence"] >= 0.78:
                decision = ESCALATE
                reason = "situação urgente exige atenção do senhor"
            elif typ in {"error", "problem", "blocked", "repetitive_task"} or has_action:
                decision = OFFER
                reason = "há oportunidade de ajuda, mas não há autorização para agir sozinho"
            elif _settings["mode"] == "assertive" and candidate["confidence"] >= 0.82:
                decision = OFFER
                reason = "modo proativo assertivo"
            else:
                decision = IGNORE
                reason = "nenhuma iniciativa suficientemente útil"

        if decision != IGNORE:
            _last_signature[signature] = now
            _hour_events.append(now)
            record = {
                "timestamp": now,
                "decision": decision,
                "reason": reason,
                "candidate": candidate,
            }
            _events.append(record)
            return record
        return {"timestamp": now, "decision": IGNORE, "reason": reason, "candidate": candidate}


def set_enabled(enabled):
    with _lock:
        _settings["enabled"] = bool(enabled)
        _save()
    return _settings["enabled"]


def set_mode(mode):
    mode = str(mode).strip().lower()
    if mode not in MODES:
        raise ValueError("Modo de iniciativa inválido.")
    with _lock:
        _settings["mode"] = mode
        _save()
    return mode


def set_cooldown(seconds):
    seconds = max(15.0, min(3600.0, float(seconds)))
    with _lock:
        _settings["cooldown"] = seconds
        _save()
    return seconds


def reset_cooldowns():
    with _lock:
        _last_signature.clear()


def status():
    with _lock:
        _prune()
        return {
            **_settings,
            "events_last_hour": len(_hour_events),
            "recent": list(_events)[-8:],
        }
