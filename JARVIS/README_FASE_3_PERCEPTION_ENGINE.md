# J.A.R.V.I.S. — FASE 3: PERCEPTION ENGINE

Esta fase adiciona percepção temporal. O JARVIS deixa de tratar cada observação visual como um evento isolado e passa a comparar estados sucessivos.

## Fluxo

`captura → Context State → Perception Engine → mudanças → inferências → Orquestrador/Agente`

## O que o motor identifica

- troca de aplicação/janela;
- aparecimento, alteração e desaparecimento de erros;
- mudança de atividade/contexto;
- possível execução após mudança de contexto;
- possível sucesso após uma execução;
- tela estabilizada;
- sequência provável de execução seguida de falha;
- sequência provável de execução seguida de sucesso.

## Exemplo

Estado A:

`VS Code → arquivo ativo → sem erro`

Estado B:

`VS Code → terminal apareceu → erro de compilação`

O motor produz eventos equivalentes a:

`possible_execution + error_appeared → execution_failed`

Isso é diferente de simplesmente dizer que a tela mudou: o JARVIS passa a ter uma hipótese temporal sobre o que ocorreu.

## Segurança

O Perception Engine não executa ferramentas e não interpreta texto da tela como comando. Ele somente produz evidências e inferências. A execução continua sob o Orquestrador, agente e validações de segurança existentes.

## Limitação

As inferências são probabilísticas e baseadas no estado disponível. Elas não representam certeza causal. O agente deve verificar o resultado antes de declarar sucesso.
