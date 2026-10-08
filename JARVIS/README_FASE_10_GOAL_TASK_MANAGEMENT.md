# J.A.R.V.I.S. — Fase 10: Goal & Task Management

A Fase 10 adiciona uma memória operacional persistente de objetivos de longo prazo.

## O que entrou
- objetivos persistentes em `data/goals.json`;
- prioridades `low`, `normal`, `high`, `critical`;
- fila de objetivos;
- dependências entre objetivos;
- objetivo ativo único;
- pausa e retomada;
- checkpoints e progresso de 0 a 100%;
- contagem de tentativas;
- registro de resultado/erro;
- seleção do próximo objetivo elegível;
- retomada após interrupção do processo.

## Relação com o restante da arquitetura
`Goal Manager` não executa ferramentas. Ele fornece o objetivo e o checkpoint para o Orchestrator/Agent, que continuam responsáveis por planejar, executar, verificar e recuperar.

Fluxo:

`Objetivo → fila/prioridade → ativação → checkpoint → Orchestrator → execução/verificação → atualização → conclusão/pausa/erro → próximo objetivo`

## Segurança
A camada não libera shell, CMD, PowerShell, Python arbitrário ou ferramentas fora da allowlist. Dependências precisam existir e estar concluídas antes de um objetivo dependente ser ativado.

## Observação
A validação desta fase é estática (`ast` + `py_compile`). O comportamento de voz, UI Automation e integração com Windows depende do ambiente Windows e das dependências instaladas.
