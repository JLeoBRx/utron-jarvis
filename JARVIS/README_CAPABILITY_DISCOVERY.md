# J.A.R.V.I.S. // FASE 16 — CAPABILITY DISCOVERY

Esta fase adiciona um catálogo descoberto das ferramentas realmente registradas em `tools.DEFINITIONS`.

## Princípio

Discovery não executa ferramentas e não concede permissões. A allowlist de `tools.py` continua sendo a autoridade final.

## Fluxo

```text
TOOLS DEFINITIONS
       ↓
CAPABILITY DISCOVERY
       ↓
TOOL → CAPABILITIES → RISK → EVIDENCE
       ↓
ACTION SELECTION
       ↓
ALLOWLIST
       ↓
EXECUTION
```

O catálogo parte das associações explícitas do `capability_model` e possui uma heurística conservadora para reconhecer capacidades de ferramentas novas a partir de nome/descrição. Isso não cria uma ferramenta nova nem libera execução.

## Validação

`capability_discovery.validate()` compara o catálogo descoberto com as definições registradas e identifica ferramentas descobertas sem registro ou sem entrada no catálogo.
