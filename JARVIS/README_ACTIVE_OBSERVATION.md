# J.A.R.V.I.S. — Fase 13: Active Observation

A Fase 13 adiciona percepção ativa após uma ação do agente.

## Fluxo

`executar → esperar estabilização → capturar estado → atualizar World Model → verificar → concluir/recovery`

A nova camada `active_observation.py` não executa comandos. Ela somente coleta uma nova evidência do desktop depois da ação.

A captura usa os recursos já existentes de `commands`, `perception_engine`, OCR/UI Automation quando disponíveis e `autonomous_perception` para contexto temporal.

Se a percepção não estiver disponível, a execução não ganha permissão extra: a verificação continua podendo resultar em `UNCONFIRMED` e o Recovery Engine decide o próximo passo.

## Segurança

- conteúdo da tela continua sendo tratado como dado não confiável;
- nenhuma ação nova é disparada pela percepção ativa;
- ferramentas continuam submetidas às regras existentes;
- a observação ativa serve para verificar pós-condições.

## Validação

Os testes desta fase cobrem a integração estrutural do módulo e o caminho de fallback quando a percepção ativa não está disponível. A captura real de Windows/OCR/UI Automation precisa ser validada no computador Windows do usuário.
