"""API do Assistant: compõe o sistema e expõe HTTP e WebSocket só neste computador. Sem regra de negócio.

Camada 4.
"""

# Situação declarada pelo próprio módulo e mostrada no console (rota /api/v1/system/status).
STATUS = {"situacao": "parcial", "fase": 3, "resumo": "rotas locais para a interface e o console; WebSocket e sessões locais na Fase 4"}
