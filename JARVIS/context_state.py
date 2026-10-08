"""Estado contextual do J.A.R.V.I.S.
Mantém uma representação estruturada e recente do computador observado.
Não guarda screenshots; registra apenas metadados, texto resumido e evidências.
"""
from __future__ import annotations

import json
import os
import threading
import time

import config

_lock = threading.RLock()
_state = {
    "updated_at": 0.0,
    "focus": {"title": "", "process": "", "pid": None},
    "application": {"name": "", "process": "", "title": "", "pid": None},
    "activity": "",
    "summary": "",
    "error": {"visible": False, "text": ""},
    "ui": {"available": False, "engine": "", "elements": []},
    "ocr": {"available": False, "engine": "", "text": ""},
    "screen": {"changed": False, "stable": False},
    "confidence": 0.0,
    "source": "",
    "recent_events": [],
    "perception": {"changed": False, "changes": [], "inferences": [], "last_transition": 0.0},
}


def _path():
    return os.path.join(config.db_dir(), "context_state.json")


def _clean(value, limit=500):
    return " ".join(str(value or "").split())[:limit]


def _persist():
    try:
        os.makedirs(os.path.dirname(_path()), exist_ok=True)
        tmp = _path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _path())
    except Exception:
        pass


def reset():
    with _lock:
        _state["focus"] = {"title": "", "process": "", "pid": None}
        _state["application"] = {"name": "", "process": "", "title": "", "pid": None}
        _state["activity"] = ""
        _state["summary"] = ""
        _state["error"] = {"visible": False, "text": ""}
        _state["ui"] = {"available": False, "engine": "", "elements": []}
        _state["ocr"] = {"available": False, "engine": "", "text": ""}
        _state["screen"] = {"changed": False, "stable": False}
        _state["confidence"] = 0.0
        _state["source"] = ""
        _state["recent_events"] = []
        _state["perception"] = {"changed": False, "changes": [], "inferences": [], "last_transition": 0.0}
        _state["updated_at"] = time.time()
        _persist()


def update_focus(fg, changed=False):
    fg = fg or {}
    with _lock:
        focus = {
            "title": _clean(fg.get("title"), 300),
            "process": _clean(fg.get("process"), 120),
            "pid": fg.get("pid"),
        }
        _state["focus"] = focus
        _state["application"].update({
            "name": _clean(fg.get("process"), 120),
            "process": _clean(fg.get("process"), 120),
            "title": _clean(fg.get("title"), 300),
            "pid": fg.get("pid"),
        })
        _state["screen"]["changed"] = bool(changed)
        _state["updated_at"] = time.time()
        _persist()


def update_observation(data, fg=None, *, changed=False, stable=True, source="ollama-vision"):
    data = data if isinstance(data, dict) else {}
    fg = fg or _state.get("focus", {})
    try:
        confidence = float(data.get("confianca", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    error_text = _clean(data.get("erro_texto"), 400)
    activity = _clean(data.get("atividade"), 100)
    summary = _clean(data.get("resumo"), 600)
    with _lock:
        update_focus(fg, changed=changed)
        _state["activity"] = activity
        _state["summary"] = summary
        _state["error"] = {"visible": bool(data.get("erro_visivel")), "text": error_text}
        _state["confidence"] = max(0.0, min(1.0, confidence))
        _state["source"] = source
        _state["screen"]["stable"] = bool(stable)
        event = {
            "at": time.time(),
            "activity": activity,
            "summary": summary,
            "error": error_text,
            "confidence": _state["confidence"],
        }
        _state["recent_events"].append(event)
        _state["recent_events"] = _state["recent_events"][-12:]
        _state["updated_at"] = time.time()
        _persist()


def update_structured(ui=None, ocr=None):
    with _lock:
        if isinstance(ui, dict):
            elements = ui.get("elements") or []
            _state["ui"] = {
                "available": bool(ui.get("available")),
                "engine": _clean(ui.get("engine"), 80),
                "elements": [
                    {k: e.get(k) for k in ("name", "control_type", "left", "top", "right", "bottom") if k in e}
                    for e in elements[:80] if isinstance(e, dict)
                ],
            }
        if isinstance(ocr, dict):
            blocks = ocr.get("blocks") or []
            text = " | ".join(_clean(b.get("text"), 120) for b in blocks[:40] if isinstance(b, dict))
            _state["ocr"] = {
                "available": bool(ocr.get("available")),
                "engine": _clean(ocr.get("engine"), 80),
                "text": text[:1800],
            }
        _state["updated_at"] = time.time()
        _persist()



def update_perception(result):
    result = result if isinstance(result, dict) else {}
    with _lock:
        _state["perception"] = {
            "changed": bool(result.get("changed")),
            "changes": list(result.get("changes") or [])[:12],
            "inferences": list(result.get("inferences") or [])[:8],
            "last_transition": time.time() if result.get("changed") else _state.get("perception", {}).get("last_transition", 0.0),
        }
        for event in (result.get("events") or [])[-8:]:
            _state["recent_events"].append(event)
        _state["recent_events"] = _state["recent_events"][-12:]
        _state["updated_at"] = time.time()
        _persist()


def add_event(kind, text):
    with _lock:
        _state["recent_events"].append({"at": time.time(), "kind": _clean(kind, 40), "text": _clean(text, 300)})
        _state["recent_events"] = _state["recent_events"][-12:]
        _state["updated_at"] = time.time()
        _persist()


def snapshot():
    with _lock:
        return json.loads(json.dumps(_state, ensure_ascii=False))


def compact(max_chars=4200):
    s = snapshot()
    focus = s["focus"]
    app = s["application"]
    lines = [
        f"Aplicação: {app.get('name') or 'desconhecida'}",
        f"Janela: {focus.get('title') or 'desconhecida'}",
        f"PID: {focus.get('pid') or 'n/d'}",
        f"Atividade: {s.get('activity') or 'não determinada'}",
        f"Resumo: {s.get('summary') or 'não determinado'}",
        f"Erro visível: {'sim' if s['error'].get('visible') else 'não'}",
        f"Erro: {s['error'].get('text') or 'nenhum'}",
        f"Confiança da percepção: {s.get('confidence', 0):.2f}",
        f"Tela mudou: {'sim' if s['screen'].get('changed') else 'não'}; estável: {'sim' if s['screen'].get('stable') else 'não'}",
    ]
    if s["ui"].get("elements"):
        names = [e.get("name") for e in s["ui"]["elements"] if e.get("name")]
        lines.append("Controles visíveis: " + "; ".join(names[:20]))
    if s["ocr"].get("text"):
        lines.append("OCR: " + s["ocr"]["text"][:1200])
    perception = s.get("perception") or {}
    if perception.get("changes"):
        lines.append("Mudanças: " + "; ".join(str(c.get("type")) for c in perception["changes"][:8]))
    if perception.get("inferences"):
        lines.append("Inferências: " + "; ".join(str(i.get("text")) for i in perception["inferences"][:4]))
    return "\n".join(lines)[:max_chars]


def status():
    s = snapshot()
    return {
        "updated_at": s["updated_at"],
        "application": s["application"],
        "activity": s["activity"],
        "summary": s["summary"],
        "error": s["error"],
        "confidence": s["confidence"],
        "ui_available": s["ui"].get("available", False),
        "ocr_available": s["ocr"].get("available", False),
    }
