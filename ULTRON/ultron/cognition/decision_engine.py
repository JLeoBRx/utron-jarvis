"""DECISION ENGINE — decide o caminho de cada intenção e a reação a percepções.

* Pedidos: responder, executar uma skill, planejar, imaginar, perguntar (ambiguidade real),
  recusar (proibido) ou ajustar o próprio sistema.
* Percepções (proatividade): ignorar, informar, sugerir ou pedir autorização. A
  proatividade nunca executa algo sensível por conta própria.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .types import Intent


@dataclass
class Decision:
    route: str               # respond | execute | plan | agentic | imagine | control | cancel | ask | refuse
    reason: str
    question: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InsightDecision:
    action: str              # ignore | inform | suggest | authorize
    reason: str
    priority: str = "normal"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionEngine:
    def decide(self, intent: Intent) -> Decision:
        kind = intent.kind
        if kind == "response":
            return Decision("respond", intent.reason or "resposta direta", confidence=intent.confidence)
        if kind == "cancel":
            return Decision("cancel", "pedido de cancelamento", confidence=1.0)
        if kind in ("control", "dream"):
            return Decision("control", "ajuste do próprio sistema", confidence=intent.confidence)
        if intent.ambiguity:
            return Decision("ask", "ambiguidade real", question=intent.ambiguity, confidence=intent.confidence)
        if kind in ("imagination", "world", "scenario", "explore", "image"):
            return Decision("imagine", "capacidade criativa", confidence=intent.confidence)
        if kind == "goal":
            return Decision("plan", "objetivo com várias etapas", confidence=intent.confidence)
        if intent.skill:
            return Decision("execute", "comando direto", confidence=intent.confidence)
        return Decision("agentic", "o modelo local decide entre responder e agir", confidence=intent.confidence)

    def decide_insight(self, hypothesis: dict, *, sensitive_action: bool = False) -> InsightDecision:
        confidence = float(hypothesis.get("confidence", 0.0))
        kind = hypothesis.get("kind", "")
        sources = hypothesis.get("sources") or []
        if confidence < 0.55 or len(sources) < 1:
            return InsightDecision("ignore", "evidência insuficiente")
        if kind == "development":
            return InsightDecision("ignore", "contexto normal de trabalho")
        if kind in ("application_hung", "dependency_error", "visible_error", "network_problem"):
            if sensitive_action:
                return InsightDecision("authorize", "a correção exige uma ação sensível", "high")
            if confidence >= 0.8 and len(sources) >= 2:
                return InsightDecision("suggest", "problema confirmado por múltiplas fontes", "high")
            return InsightDecision("inform", "possível problema detectado", "normal")
        return InsightDecision("ignore", "sem relevância")
