# J.A.R.V.I.S. — FASE 10: AUTONOMOUS PERCEPTION LOOP

A percepção agora é temporal e contínua.

## O que mudou

Antes, o Observador fazia essencialmente:

`captura -> detectar mudança -> chamar visão -> analisar`

Agora existe uma camada intermediária:

`captura -> percepção temporal -> comparar estado -> classificar mudança -> contexto -> visão somente quando necessário`

A camada `autonomous_perception.py` registra:

- troca de janela/processo;
- mudança visual relevante;
- mudança visual simples;
- estabilidade do contexto;
- sequência temporal;
- saliência da mudança;
- histórico curto de percepções.

Ela **não executa ferramentas** e **não transforma texto da tela em comando**.

## Por que isso aproxima o comportamento do JARVIS

O sistema deixa de tratar cada captura como um evento isolado. Ele passa a ter uma noção operacional de:

- "o usuário continua no mesmo contexto";
- "a janela mudou";
- "algo relevante mudou na tela";
- "a tela ainda está mudando, então é cedo para interpretar";
- "o contexto está estável e pode ser analisado".

Isso permite que o Neural Core receba contexto temporal em vez de somente fotografias independentes.

## Limite importante

Esta fase não cria consciência nem autonomia irrestrita. A percepção apenas observa e classifica mudanças. A decisão de agir continua passando por Decision Engine, Goal Manager, Planner, Execution Loop e Verification/Recovery.
