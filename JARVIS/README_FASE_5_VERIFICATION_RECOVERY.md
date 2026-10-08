# J.A.R.V.I.S. — FASE 5: VERIFICATION & RECOVERY ENGINE

A quinta fase impede que o JARVIS trate "a ferramenta terminou" como sinônimo de "a tarefa funcionou".

Fluxo: **ação → estabilização → comparação antes/depois → pós-condição → recuperação segura → nova verificação**.

### Novos componentes
- `verification_engine.py`: pós-condições e estratégias de recuperação.
- `verify_ui_action`: ferramenta de verificação sem execução.
- `execute_ui_action.expected`: permite declarar a mudança esperada.
- `agent.py`: verificação pós-ação e limite de recuperação.
- `config.py`: `MAX_RECOVERY_ATTEMPTS=3`, `VERIFY_SETTLE_SECONDS=0.7`.

A recuperação continua limitada à allowlist. Não existe shell livre.
