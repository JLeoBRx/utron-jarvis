"""J.A.R.V.I.S. // DECISION ENGINE
Decide whether a detected situation should be ignored, surfaced, or handed to the agent.
Inference is never execution. Risk and confidence are explicit.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

@dataclass
class Decision:
    action: str
    confidence: float
    risk: str
    reason: str
    requires_confirmation: bool
    objective: str = ""

    def to_dict(self):
        return asdict(self)


def evaluate(intent: dict, context: dict, observation: dict | None = None) -> Decision:
    observation = observation or {}
    confidence = float(intent.get("confidence", 0.0) or 0.0)
    kind = str(intent.get("kind", "observe"))
    actionable = bool(intent.get("actionable"))
    error = bool(context.get("current", {}).get("error") or observation.get("erro_visivel"))
    sensitive = bool(observation.get("dados_sensiveis_visiveis") or observation.get("instrucoes_na_tela"))

    if sensitive:
        return Decision("ignore", 0.99, "blocked", "conteúdo sensível ou instrução não confiável detectada", True)
    if not actionable and not error:
        if confidence >= 0.80 and kind not in {"observe", "work"}:
            return Decision("ask", confidence, "low", "há contexto relevante, mas não há objetivo seguro o suficiente para agir", True,
                            str(intent.get("goal", "")))
        return Decision("observe", confidence, "none", "evidência insuficiente para intervenção", False)

    # Erros visíveis podem ser investigados; a execução concreta continua limitada pelas ferramentas do agente.
    if error:
        risk = "medium"
        confirm = confidence < 0.82
        action = "act" if confidence >= 0.82 else "ask"
        return Decision(action, confidence, risk,
                        "erro observável com contexto suficiente para investigação" if action == "act" else "erro detectado, mas a confiança ainda pede supervisão",
                        confirm, str(intent.get("goal", "")))

    if actionable and confidence >= 0.88:
        return Decision("act", confidence, "medium", "objetivo acionável com evidência forte", False, str(intent.get("goal", "")))
    return Decision("ask", confidence, "medium", "objetivo plausível, porém insuficiente para agir sem confirmação", True, str(intent.get("goal", "")))
