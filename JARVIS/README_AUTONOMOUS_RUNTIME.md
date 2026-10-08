# J.A.R.V.I.S. // FASE 21 — AUTONOMOUS AGENT RUNTIME

A Fase 21 cria um coordenador central para o ciclo operacional de uma missão.

```text
PERCEBER → WORLD MODEL → ROUTING → PLANEJAR → EXECUTAR → OBSERVAR → VERIFICAR
                                      ↑                         │
                                      └──── RECOVERY/REPLAN ───┘
```

## Responsabilidades

- capturar estado inicial antes da missão;
- selecionar a rota de inteligência;
- delegar planejamento/execução ao `execution_loop`;
- atualizar o estado do Runtime durante a missão;
- capturar estado novamente ao final;
- manter `tools.py`/allowlist como autoridade de execução;
- não executar shell arbitrário.

O Runtime é um **orquestrador**, não uma nova camada de permissões.

## Limitação de validação

A compilação e os testes determinísticos podem ser feitos neste ambiente Linux. A execução real de mouse/teclado, APIs Win32, PySide6 e dispositivos do Windows precisa ser validada na máquina Windows do usuário.
