"""SAFRA Portal — site público e painel administrativo (CMS).

Serviço separado do SAFRA Core: roda em servidor, com banco próprio, e não conhece conversas, memórias nem
ferramentas. Só pode importar a camada de base (`safra.core`, `safra.storage`, `safra.security`,
`safra.monitoring`, `safra.api.foundation`); a regra é conferida por tests/test_architecture.py.

Situação: PLANEJADO (Fases 8 e 9). Este pacote ainda não tem implementação.
"""
