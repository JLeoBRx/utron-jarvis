# J.A.R.V.I.S. — Fase 9: Intelligence Routing

O Neural Core agora usa um **Intelligence Router** para escolher a inteligência por missão.

## Rotas

- `OLLAMA_LOCAL`: padrão, sem custo de API e com fallback local.
- `OPENAI`: opcional; só é elegível quando `OPENAI_ENABLED = True` **e** `OPENAI_API_KEY` existe no ambiente.

A decisão considera complexidade, contexto visual e disponibilidade do provedor. Não há troca cega baseada apenas em uma palavra.

## Segurança

A execução de ferramentas continua local e passa pela allowlist de `tools.py`. O provedor de inteligência não recebe permissão para executar shell, PowerShell ou CMD.

Se uma chamada OpenAI falhar, o Router retorna para Ollama local na mesma missão.

A integração remota usa a API de chat da OpenAI de forma opcional. A documentação atual da OpenAI indica a Responses API como a interface recomendada para novas integrações; este adaptador permanece deliberadamente simples e opcional para preservar o funcionamento local. A API é faturada separadamente do ChatGPT.
