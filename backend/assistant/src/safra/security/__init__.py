"""Segurança do Assistant: sessões locais, políticas de ferramentas, cofre de credenciais e modo privacidade.

Camada 1. As primitivas (senhas, *tokens*) vêm de `safra_foundation`.
"""

# Situação declarada pelo próprio módulo e mostrada no console (rota /api/v1/system/status).
STATUS = {"situacao": "planejado", "fase": 4, "resumo": "sessões locais, políticas de ferramentas, cofre de credenciais; na Fase 3 a API só recusa origens de fora"}
