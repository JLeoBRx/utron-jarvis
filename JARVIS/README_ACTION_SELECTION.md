# J.A.R.V.I.S. — FASE 14: ACTION SELECTION / TOOL INTELLIGENCE

A Fase 14 adiciona uma camada explícita de seleção de ferramentas antes da execução.

## Fluxo

```text
OBJETIVO
   ↓
ACTION SELECTOR
   ↓
FERRAMENTAS CANDIDATAS
   ↓
PLANNER / AGENT
   ↓
ALLOWLIST
   ↓
EXECUÇÃO
   ↓
OBSERVAÇÃO
   ↓
VERIFICAÇÃO
```

O `action_selector.py` classifica ferramentas registradas por relevância para o objetivo e para o contexto disponível. A seleção é **orientativa**: ela não concede permissão para executar nada. A allowlist em `tools.py` continua sendo a autoridade final.

A orientação é entregue ao agente junto do objetivo, permitindo que o modelo priorize ferramentas mais adequadas sem remover as alternativas permitidas.

## Segurança

- Não cria shell, CMD, PowerShell ou execução arbitrária.
- Não transforma a recomendação em autorização.
- A confirmação continua obrigatória para ferramentas sensíveis já existentes.
- A execução continua limitada a `tools.DEFINITIONS`.

## Validação

Foi executado `python -m compileall -q .` e o teste `test_fase14.py` passou.

A validação é estática/smoke test. A execução real de Windows, PyAutoGUI, UI Automation, Ollama, microfone e dispositivos precisa ser validada na máquina Windows do projeto.
