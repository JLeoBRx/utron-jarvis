# J.A.R.V.I.S. — Fase 1: Núcleo de Orquestração

Esta versão começa a transformação do JARVIS de um conjunto de comandos para um agente com **estado operacional explícito**.

## Fluxo

`percepção → objetivo → planejamento → execução → verificação → recuperação → conclusão`

## O que foi acrescentado

- `orchestrator.py`: mantém o estado da tarefa atual.
- Estados: `UNDERSTANDING`, `PLANNING`, `EXECUTING`, `VERIFYING`, `RECOVERING`, `WAITING_CONFIRMATION`, `COMPLETED`, `BLOCKED`, `FAILED` e `CANCELLED`.
- Objetivo e contexto ficam associados à tarefa.
- Cada ferramenta executada passa a ser registrada no estado da tarefa.
- Falhas de verificação entram explicitamente em `RECOVERING`.
- Confirmações de segurança entram em `WAITING_CONFIRMATION`.
- O estado é salvo localmente em `data/orchestrator_state.json`.
- O Observador entrega contexto real ao orquestrador.
- A HUD mostra o estado da tarefa ativa no indicador da automação.

## Segurança

O orquestrador **não adiciona shell, PowerShell ou CMD**. Ele continua usando exclusivamente as ferramentas allowlisted já existentes.

Esta etapa não declara consciência, intenção própria ou autonomia irrestrita. Ela cria a fundação técnica para um agente persistente e verificável.

## Próxima fase

A próxima etapa deve substituir o contexto visual resumido por um **Context State** estruturado: aplicação ativa, janela, OCR, elementos de UI, terminal, arquivos/projeto detectados e mudanças recentes. Isso permitirá que o planejador tome decisões com evidências mais fortes e menos dependência de uma única descrição do modelo visual.
