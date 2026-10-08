# J.A.R.V.I.S. — FASE 15: CAPABILITY MODEL

A Fase 15 adiciona um mapa declarativo de capacidades ao sistema.

## Princípio

O objetivo não deve ser traduzido diretamente para um nome de ferramenta. Primeiro o sistema infere a capacidade necessária; depois o Action Selector relaciona capacidades a ferramentas candidatas.

```text
OBJETIVO
  ↓
CAPABILITY MODEL
  ↓
CAPACIDADES NECESSÁRIAS
  ↓
ACTION SELECTOR
  ↓
FERRAMENTAS CANDIDATAS
  ↓
ALLOWLIST / EXECUTION
```

O Capability Model não executa ferramentas, não concede permissões e não substitui a allowlist de `tools.py`.

## Capacidades iniciais

- `read_screen`
- `understand_ui`
- `interact_ui`
- `launch_application`
- `navigate_web`
- `find_files`
- `inspect_system`
- `control_media`
- `wait_for_state`
- `remember_information`
- `recall_information`

## Validação

`test_fase15.py` verifica inferência de capacidades e o mapeamento capacidade → ferramenta. A Fase 14 também é executada como regressão.

A validação nesta etapa é estática/smoke test; execução real de Windows e periféricos deve ser feita na máquina-alvo.
