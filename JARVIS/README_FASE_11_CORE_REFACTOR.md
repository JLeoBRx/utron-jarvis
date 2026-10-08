# J.A.R.V.I.S. — Fase 11: Core Architecture Refactor

Esta fase reorganiza o projeto sem quebrar os módulos legados que já funcionam.

## Nova arquitetura

```text
core/
  brain.py          fachada cognitiva
  contracts.py      contratos de estado/eventos
  runtime.py        inicialização do aplicativo

perception/
  context.py
  screen.py
  engine.py

actions/
  ui.py
  windows.py
  verification.py

intelligence/
  planner.py
  initiative.py
  goals.py
  recovery.py
  learning.py

voice/
  recognition.py
  conversation.py
  speech.py

interface/
  hud.py
  theme.py
```

Os módulos originais continuam na raiz como camada de compatibilidade. Isso evita uma migração destrutiva e permite que a HUD, backend, agente e ferramentas existentes continuem usando os nomes atuais.

## Brain

`core.brain.JarvisBrain` passa a ser a fachada para:

- Context State
- Orchestrator
- Goal Manager
- Initiative Engine
- Permission Engine
- Learning Engine

Ele não executa shell, PowerShell, CMD ou código arbitrário. A execução continua nas ferramentas estruturadas existentes.

## Novo ponto de entrada

```text
python main.py
```

`Jarvis.py` continua aceito por compatibilidade e encaminha para o mesmo runtime.

## O que esta fase não faz

Não libera autonomia irrestrita. A refatoração melhora a arquitetura; as permissões, allowlists, confirmações e verificações das fases anteriores permanecem válidas.

## Validação

Foram executadas validações sintáticas/compilação em todos os arquivos Python do pacote e testes unitários do Brain com dependências reais do projeto quando disponíveis.
