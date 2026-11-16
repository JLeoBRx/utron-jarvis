"""Contrato único de provedor de IA, provedores locais e remotos, roteamento por política, fallback, prazo, cancelamento e consumo.
"""

# Situação declarada pelo próprio módulo e mostrada no console (rota /api/v1/system/status).
STATUS = {"situacao": "planejado", "fase": 5, "resumo": "não há gateway: o Assistant não gera respostas; só lista os provedores cadastrados"}
