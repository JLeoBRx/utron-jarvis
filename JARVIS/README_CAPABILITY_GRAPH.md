# J.A.R.V.I.S. // FASE 17 — TOOL REGISTRY + CAPABILITY GRAPH

A Fase 17 cria um registro unificado e um grafo de capacidades.

## Modelo

`ferramenta -> capacidade -> evidência`

O grafo também preserva risco e disponibilidade. Ele serve para planejamento e seleção, mas **não autoriza execução**.

## Separação de responsabilidades

- `capability_model.py`: catálogo declarativo de capacidades.
- `capability_discovery.py`: descobre capacidades das ferramentas registradas.
- `capability_graph.py`: relaciona ferramentas, capacidades e evidências.
- `tool_registry.py`: ponto único de consulta do catálogo.
- `tools.py`: continua sendo a autoridade final/allowlist para execução.

## Resultado

Uma ferramenta nova pode ser registrada e descoberta sem alterar o Neural Core. O Action Selector usa o grafo como evidência adicional para priorização.
