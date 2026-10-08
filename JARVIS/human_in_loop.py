"""J.A.R.V.I.S. // HUMAN-IN-THE-LOOP POLICY
Centraliza a classificação de risco e a política de autonomia.
Não executa ferramentas e não substitui as confirmações da camada Windows.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import re

@dataclass(frozen=True)
class Authorization:
    level: str
    mode: str
    confidence: float
    reason: str
    reversible: bool = True
    def to_dict(self): return asdict(self)

_BLOCKED = re.compile(r"\b(senha|password|token|chave privada|private key|seed phrase|frase de recupera)\b", re.I)
_HIGH = re.compile(r"\b(apagar|excluir|formatar|desinstalar|desligar|reiniciar|encerrar|fechar|enviar|publicar|comprar|pagar|transferir|mover arquivo|alterar registro|registrar|instalar)\b", re.I)
_MEDIUM = re.compile(r"\b(editar|alterar|modificar|digitar|clicar|preencher|salvar|abrir|executar|corrigir)\b", re.I)
_SAFE = re.compile(r"\b(consultar|ler|verificar|analisar|observar|listar|pesquisar|buscar|capturar|monitorar)\b", re.I)


def classify(objective: str, *, tool: str = "", irreversible: bool = False) -> Authorization:
    text = f"{objective or ''} {tool or ''}".strip()
    if _BLOCKED.search(text):
        return Authorization("BLOCKED", "BLOCK", 0.99, "conteúdo potencialmente secreto ou credencial detectado", False)
    if irreversible or _HIGH.search(text):
        return Authorization("HIGH", "CONFIRM", 0.95, "ação potencialmente destrutiva, externa ou difícil de reverter", not irreversible)
    if _MEDIUM.search(text):
        return Authorization("MEDIUM", "SUPERVISE", 0.78, "ação altera estado do computador e merece supervisão contextual", True)
    if _SAFE.search(text):
        return Authorization("LOW", "AUTO", 0.90, "ação predominantemente observacional ou reversível", True)
    return Authorization("LOW", "AUTO", 0.60, "não há indicador suficiente para exigir confirmação", True)


def policy_for_tool(tool_name: str, objective: str = "") -> Authorization:
    destructive = {"delete_path", "move_path", "power_control", "close_app"}
    external = {"send_message", "send_email", "publish", "purchase", "payment"}
    irreversible = tool_name in destructive or tool_name in external
    return classify(objective, tool=tool_name, irreversible=irreversible)
