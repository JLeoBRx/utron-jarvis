# J.A.R.V.I.S. — FASE 7: MEMORY & LEARNING ENGINE

Esta fase adiciona memória episódica e aprendizagem local.

## O que mudou

- `learning_engine.py` registra episódios de tarefas e sequências de ferramentas.
- Sucessos anteriores podem ser consultados antes do planejamento.
- O agente recebe pistas de experiências semelhantes, mas é obrigado a verificar o estado atual antes de repetir uma estratégia.
- Há feedback explícito por episódio.
- Há resumo das estratégias aprendidas.
- Dados ficam no SQLite local já usado pelo projeto.
- Não são armazenadas screenshots, credenciais ou texto bruto de tela.
- A aprendizagem não altera permissões e não executa ações automaticamente.

## Fluxo

`Tarefa → planejamento → execução → verificação → resultado → episódio → próxima tarefa`

Exemplo:

1. O JARVIS corrige um erro no VS Code.
2. A sequência de ferramentas e o resultado verificado são registrados.
3. Em uma tarefa futura semelhante, o agente consulta experiências locais.
4. A estratégia aparece como pista, não como ordem.
5. O estado atual é verificado antes de qualquer ação.

## Novas ferramentas

- `recall_experience`
- `learning_summary`
- `record_learning_feedback`

## Limites

Aprender não significa alterar a política de segurança. O JARVIS não aprende a contornar permissões, não cria shell e não executa ferramentas fora da allowlist.
