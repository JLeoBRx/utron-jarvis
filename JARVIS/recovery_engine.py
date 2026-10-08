"""J.A.R.V.I.S. // RECOVERY ENGINE
Escolhe a próxima estratégia após uma verificação negativa, sem ampliar permissões.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass
class RecoveryDecision:
    action: str
    reason: str
    revision: int
    allowed: bool = True
    def to_dict(self): return asdict(self)


def decide(verification: dict, revision: int, max_replans: int) -> RecoveryDecision:
    v = verification or {}
    if v.get("status") == "VERIFIED":
        return RecoveryDecision("finish", "objetivo verificado", revision, True)
    if not v.get("retryable", True):
        return RecoveryDecision("stop", "falha não marcada como recuperável", revision, False)
    if revision >= max_replans:
        return RecoveryDecision("stop", "limite seguro de recuperação atingido", revision, False)
    return RecoveryDecision("replan", "resultado não confirmado ou falha recuperável; buscar estratégia alternativa permitida", revision + 1, True)
