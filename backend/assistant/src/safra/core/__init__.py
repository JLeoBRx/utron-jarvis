"""Base do Assistant: configuração do processo. Erros, logs e leitura de ambiente vêm de `safra_foundation`.

Camada 0: não importa nenhum outro módulo do Assistant.
"""

# Situação declarada pelo próprio módulo e mostrada no console (rota /api/v1/system/status).
STATUS = {"situacao": "implementado", "fase": 2, "resumo": "configuração do processo, validada antes de tudo"}
