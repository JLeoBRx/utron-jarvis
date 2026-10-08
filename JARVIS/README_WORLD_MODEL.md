# J.A.R.V.I.S. — Fase 11: World Model / State Model

O World Model mantém uma representação temporal e estruturada do que o sistema sabe sobre o computador.

Ele registra, quando houver evidência suficiente:

- aplicativo/processo em foco;
- janela observada;
- atividade contextual;
- erros observados;
- objetivo/missão atual;
- relações simples entre entidades;
- histórico recente de mudanças.

## Princípio

O World Model **não executa ações** e não transforma texto encontrado na tela em comando.
Ele é uma representação de estado para o Neural Core, Planner, Router e HUD.

## Fluxo

`Perception → Context → World Model → Decision → Goal → Planner → Execution → Verification`

A próxima fase pode usar esse estado para comparar **estado esperado × estado observado**, permitindo uma verificação mais objetiva e uma recuperação mais inteligente.
