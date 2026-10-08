"""J.A.R.V.I.S. // VERIFICATION ENGINE
Separa resultado de ferramenta de sucesso do objetivo.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict

@dataclass
class Verification:
    success: bool
    confidence: float
    status: str
    evidence: str
    reason: str
    retryable: bool = True

    def to_dict(self):
        return asdict(self)


def verify(*, tool_result=None, timeline_failed=False, answer="", goal="", context=None):
    """Avalia evidência disponível sem declarar sucesso apenas porque uma tool terminou."""
    result = tool_result if isinstance(tool_result, dict) else {}
    context = context if isinstance(context, dict) else {}
    explicit = result.get("verified")
    if explicit is True:
        return Verification(True, 0.96, "VERIFIED", str(result.get("evidence") or "resultado explicitamente confirmado")[:500],
                            "há evidência explícita de conclusão", False)
    if explicit is False:
        return Verification(False, 0.96, "FAILED", str(result.get("evidence") or result.get("error") or "resultado explicitamente rejeitado")[:500],
                            "a evidência indica falha", True)
    if timeline_failed:
        return Verification(False, 0.92, "FAILED", str(result.get("error") or "a execução reportou falha")[:500],
                            "a execução apresentou erro observável", True)
    # Não transformar texto do modelo em prova. Resposta vazia ou genérica permanece não confirmada.
    text = str(answer or "").strip().lower()
    generic = {"ok", "feito", "concluído", "concluido", "done", "sucesso", "success"}
    if text in generic:
        return Verification(False, 0.45, "UNCONFIRMED", "a resposta não contém evidência operacional suficiente",
                            "declaração textual isolada não comprova o objetivo", True)
    if result.get("evidence"):
        return Verification(True, 0.78, "VERIFIED", str(result["evidence"])[:500],
                            "há evidência operacional, embora não explícita", False)
    return Verification(False, 0.40, "UNCONFIRMED", "nenhuma evidência objetiva de conclusão disponível",
                        "é necessário observar ou testar o estado final", True)
