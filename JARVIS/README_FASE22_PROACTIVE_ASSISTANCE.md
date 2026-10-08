# J.A.R.V.I.S. — Fase 22: Proactive Assistance

A camada Proactive Assistance permite que o sistema avalie se uma percepção merece ser apresentada ao usuário sem depender de uma solicitação explícita.

## Decisões

- `IGNORE`: conteúdo sensível ou instrução não confiável.
- `MONITOR`: situação sem motivo suficiente para interromper o usuário.
- `SUGGEST`: há evidência suficiente para oferecer ajuda.
- `AUTHORIZE_ACTION`: reservado para evolução futura; esta fase não executa ações proativas.

## Segurança

Esta camada não possui executor de ferramentas. Ela apenas classifica e emite eventos. A execução continua subordinada ao Neural Core, Decision Engine, Agent e allowlist de ferramentas.

Também existe cooldown por assinatura de evento para evitar repetição da mesma intervenção.
