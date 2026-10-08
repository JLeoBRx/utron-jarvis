# J.A.R.V.I.S. — Fase 12: Expected State + State Verification

A Fase 12 adiciona uma camada de verificação de transição de estado.

## Princípio

Uma ferramenta terminar não significa que o mundo mudou como esperado.
O sistema agora compara:

**estado esperado → evidência posterior → World Model → decisão**

Possíveis estados:

- `VERIFIED`: há evidência suficiente;
- `UNCONFIRMED`: a execução terminou, mas o estado final não foi observado de forma suficiente;
- `FAILED`: a execução reportou falha.

A camada não executa comandos e não amplia permissões. Ela apenas verifica.

## Fluxo

```text
OBJETIVO
  ↓
PLANNER
  ↓
EXECUÇÃO
  ↓
EXPECTED STATE
  ↓
OBSERVAÇÃO
  ↓
WORLD MODEL
  ↓
STATE VERIFIER
  ├── VERIFIED → DONE
  └── UNCONFIRMED/FAILED → RECOVERY → REPLAN
```

## Validação

A versão foi validada por compilação estática e testes unitários locais da camada de verificação. A execução real de Windows/Ollama/UI Automation continua dependendo da máquina do usuário.
