"""Monitoramento do Assistant: métricas com percentis, histórico de atividades e diagnóstico.

Camada 2. O registro de saúde vem de `safra_foundation`.
"""

# Situação declarada pelo próprio módulo e mostrada no console (rota /api/v1/system/status).
STATUS = {"situacao": "parcial", "fase": 3, "resumo": "saúde, uso de recursos e histórico de atividades; percentis e diagnóstico na Fase 4"}
