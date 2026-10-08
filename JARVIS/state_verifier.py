"""J.A.R.V.I.S. // STATE VERIFIER
Compara o estado esperado com evidência observada, sem tratar texto do modelo como prova.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import re

@dataclass
class StateCheck:
    status: str
    confidence: float
    expected: str
    observed: str
    reason: str
    retryable: bool = True
    def to_dict(self): return asdict(self)


def expected_from_transition(goal: str, tool_name: str = "", result: str = "", verification: dict | None = None):
    tool = str(tool_name or "").strip().lower()
    result = str(result or "").strip()
    v = verification or {}
    if v.get("verified") is True and v.get("evidence"):
        return {"kind": "tool_postcondition", "text": str(v["evidence"])[:500], "source": "tool_verification"}
    if tool in {"click_by_description", "open_app", "open_path", "open_url", "focus_window"}:
        return {"kind": "ui_transition", "text": f"estado posterior compatível com {tool}", "source": "transition_model"}
    return {"kind": "mission_outcome", "text": str(goal or "objetivo concluído")[:500], "source": "goal"}


def check(expected: dict, *, world: dict | None = None, evidence: str = "", timeline_failed=False):
    expected = expected or {}
    observed = str(evidence or "").strip()
    world = world or {}
    if timeline_failed:
        return StateCheck("FAILED", .94, expected.get("text", ""), observed or "falha de execução", "a execução reportou falha", True)
    if expected.get("source") == "tool_verification" and observed:
        return StateCheck("VERIFIED", .94, expected.get("text", ""), observed, "pós-condição local confirmada pela ferramenta", False)

    entities = world.get("entities") or []
    hay = " ".join(str(e.get("name", "")) for e in entities).lower()
    obs = observed.lower()
    # Evidência estruturada do sistema tem precedência sobre linguagem livre.
    if any(token and token.lower() in hay for token in re.findall(r"[\wÀ-ÿ]{4,}", expected.get("text", ""))[:8]):
        return StateCheck("VERIFIED", .76, expected.get("text", ""), hay[:500], "o World Model contém evidência compatível com o estado esperado", False)
    if obs and any(k in obs for k in ("confirmad", "verificad", "existe", "aberto", "criado", "salvo", "localizado")):
        return StateCheck("VERIFIED", .72, expected.get("text", ""), observed[:500], "há evidência operacional compatível", False)
    return StateCheck("UNCONFIRMED", .38, expected.get("text", ""), observed[:500] or "sem evidência posterior", "o estado final ainda não foi observado de forma suficiente", True)
