# J.A.R.V.I.S. — Fase 6: Planner + Execution Loop

O objetivo agora é tratado como um plano adaptativo. O Planner mantém etapas, evidências e revisões. O Execution Loop executa o agente em ciclos e, quando uma etapa não é verificada, pode replanejar até `MAX_AGENT_REPLANS` vezes.

Fluxo: objetivo → plano → execução → evidência → verificação → replanejamento (se necessário) → conclusão.

A execução continua limitada às ferramentas estruturadas e à allowlist existente. Não foi adicionado shell irrestrito.
