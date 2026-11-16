"""Ferramentas, registro, executor único, verificação do efeito e recuperação. Toda execução consulta as políticas de `security`.
"""

# Situação declarada pelo próprio módulo e mostrada no console (rota /api/v1/system/status).
STATUS = {"situacao": "planejado", "fase": 7, "resumo": "não há executor: nenhuma ferramenta pode ser executada; só lista as cadastradas"}
