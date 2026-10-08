# J.A.R.V.I.S. — Fase 8: Memory + Learning

A memória agora possui duas camadas:

- **memória declarativa**: fatos e preferências explicitamente guardados pelo usuário;
- **memória operacional**: estratégias e resultados de tarefas anteriores, usada como evidência auxiliar para planejar novos objetivos.

O JARVIS não transforma uma experiência passada em regra absoluta. Estratégias aprendidas são apenas sinais para o Planner/Agent.

## Proteções

- SQLite local;
- bloqueio de padrões de credenciais/segredos;
- limite de tamanho;
- histórico operacional limitado;
- nenhuma memória é enviada automaticamente para a rede;
- resultados não verificados não são registrados como sucesso.

## Fluxo

`objetivo → consultar memória relevante → planejar → executar → verificar → registrar episódio/estratégia`

A aprendizagem é deliberadamente conservadora: uma tarefa só gera uma estratégia positiva quando o Verification Engine confirmou o resultado.
