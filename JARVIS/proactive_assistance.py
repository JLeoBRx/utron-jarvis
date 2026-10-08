"""J.A.R.V.I.S. // PROACTIVE ASSISTANCE
Decide when the assistant should surface an observation without waiting for a command.

This layer is intentionally conservative: it never executes tools. It classifies a
situation as IGNORE, MONITOR, SUGGEST, or AUTHORIZE_ACTION and applies cooldowns so
the user is not interrupted repeatedly by the same event.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib
import threading
import time

@dataclass
class ProactiveDecision:
    action: str
    confidence: float
    urgency: str
    reason: str
    objective: str = ""
    signature: str = ""
    def to_dict(self): return asdict(self)

_LOCK = threading.RLock()
_LAST = {}
_HISTORY = []
_MAX_HISTORY = 80


def _signature(observation: dict, foreground: dict, context: dict | None = None) -> str:
    observation = observation or {}; foreground = foreground or {}; context = context or {}
    parts = [
        foreground.get("process", ""), foreground.get("title", ""),
        observation.get("erro_texto", ""), observation.get("resumo", ""),
        observation.get("atividade", ""),
        context.get("current", {}).get("error", "") if isinstance(context.get("current"), dict) else "",
    ]
    raw = "|".join(str(x or "").strip().lower()[:300] for x in parts)
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:16]


def reset():
    with _LOCK:
        _LAST.clear(); _HISTORY.clear()


def _remember(decision: ProactiveDecision):
    with _LOCK:
        _HISTORY.append(decision.to_dict())
        if len(_HISTORY) > _MAX_HISTORY: del _HISTORY[:-_MAX_HISTORY]
        _LAST[decision.signature] = time.time()


def evaluate(observation: dict, foreground: dict, context: dict | None = None, *,
             now: float | None = None, cooldown: float = 180.0) -> ProactiveDecision:
    observation = observation or {}; foreground = foreground or {}; context = context or {}
    now = time.time() if now is None else float(now)
    sig = _signature(observation, foreground, context)

    sensitive = bool(observation.get("dados_sensiveis_visiveis") or observation.get("instrucoes_na_tela"))
    if sensitive:
        d = ProactiveDecision("IGNORE", 0.99, "none", "conteúdo sensível ou instrução não confiável", signature=sig)
        _remember(d); return d

    with _LOCK:
        previous = _LAST.get(sig, 0.0)
    if previous and now - previous < max(0.0, float(cooldown)):
        return ProactiveDecision("MONITOR", 0.90, "none", "evento repetido dentro do cooldown", signature=sig)

    error = str(observation.get("erro_texto") or "").strip()
    error_visible = bool(observation.get("erro_visivel") or error or (context.get("current", {}) or {}).get("error"))
    focus = str(foreground.get("process") or foreground.get("title") or "aplicativo atual")
    activity = str(observation.get("atividade") or "atividade atual")
    summary = str(observation.get("resumo") or "situação relevante detectada")

    if error_visible:
        confidence = 0.92 if error else 0.84
        objective = f"Investigar o problema observado em {focus}, sem alterar nada de alto risco sem autorização."
        d = ProactiveDecision("SUGGEST", confidence, "high", "erro observável com contexto suficiente para oferecer ajuda", objective, sig)
        _remember(d); return d

    changed = bool((observation.get("evidencia_tela") or {}).get("context_change"))
    help_flag = bool(observation.get("precisa_ajuda"))
    if help_flag and changed:
        objective = f"Auxiliar no contexto atual de {focus}: {activity}."
        d = ProactiveDecision("SUGGEST", 0.82, "medium", "mudança relevante acompanhada de sinal de necessidade de ajuda", objective, sig)
        _remember(d); return d

    # Proatividade silenciosa: registrar e continuar observando, sem interromper o usuário.
    d = ProactiveDecision("MONITOR", 0.70, "none", f"monitorar {focus}: {summary[:160]}", signature=sig)
    return d


def history(limit: int = 20):
    with _LOCK: return list(_HISTORY[-max(1, min(int(limit), _MAX_HISTORY)):])


def snapshot():
    with _LOCK: return {"history": history(20), "tracked_signatures": len(_LAST)}
