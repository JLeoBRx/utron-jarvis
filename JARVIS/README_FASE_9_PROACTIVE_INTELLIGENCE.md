# J.A.R.V.I.S. — Fase 9: Proactive Intelligence / Initiative Engine

Esta fase adiciona uma camada de decisão entre **percepção** e **ação**.

Fluxo:

`OBservar → detectar oportunidade/problema → classificar confiança/urgência/risco → decidir → agir/oferecer/escalar/ignorar`

## Decisões

- `IGNORE`: ruído, baixa confiança, repetição ou ausência de oportunidade real.
- `OFFER`: JARVIS percebe algo útil, mas espera o senhor autorizar.
- `AUTO_LOW_RISK`: somente quando a ação já veio explicitamente identificada, pertence à allowlist de baixo risco e o Permission Engine permite a execução.
- `ESCALATE`: situação relevante/urgente que deve interromper o silêncio e chamar a atenção do senhor.

## Proteções

- A Initiative Engine não executa ferramentas diretamente.
- Não altera permissões.
- Não libera shell, CMD, PowerShell, Python ou execução arbitrária.
- Não transforma texto da tela em instrução.
- Respeita cooldown por contexto e limite horário de iniciativas.
- A execução continua passando pela validação existente do Copilot e pelo `backend.run_exclusive`.
- Conteúdo sensível continua sendo descartado antes da iniciativa.

## Modos de iniciativa

- `quiet`: mais conservador.
- `balanced`: padrão.
- `assertive`: permite oferecer ajuda em mais situações de alta confiança.

As configurações ficam em `data/initiative.json`.

## Limitação importante

Esta fase torna a tomada de iniciativa explícita e controlada. Ela **não** transforma o JARVIS em um agente com acesso irrestrito ao Windows. A execução permanece limitada às ferramentas existentes e às políticas de permissão do projeto.

## Validação

Os arquivos Python desta fase foram validados por AST e compilação (`py_compile`). Isso valida a estrutura do código; o comportamento de captura de tela, Ollama, áudio, UI Automation e voz ainda depende do ambiente Windows e deve ser testado na máquina.
