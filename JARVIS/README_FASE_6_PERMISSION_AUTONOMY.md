# J.A.R.V.I.S. — Fase 6: Permission & Autonomy Engine

Esta fase cria um ponto central de decisão para autonomia. Antes de executar uma ferramenta, o JARVIS consulta a política local.

## Modos

- `supervised`: baixo risco automático; médio/alto risco pedem confirmação.
- `autonomous`: baixo e médio risco automáticos; alto risco continua exigindo confirmação.
- `locked`: somente leitura/baixo risco.

## Princípio

A autonomia não significa acesso irrestrito. Shell, CMD, PowerShell, execução arbitrária de código e ferramentas fora da allowlist continuam proibidos.

Ações críticas como excluir/mover arquivos, fechar aplicações, controlar rádios, desligar/reiniciar o computador e apagar memórias continuam exigindo confirmação mesmo no modo AUTÔNOMO.

A política é persistida em `data/permissions.json`.

## Novas ferramentas

- `get_permission_policy`
- `set_permission_mode`
- `set_tool_permission`

A elevação para AUTÔNOMO exige confirmação falada. Uma permissão permanente `allow` para uma ferramenta específica também exige confirmação.
