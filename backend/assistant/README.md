# SAFRA Assistant — backend

O assistente. Roda **no computador do usuário**, com banco privado (um arquivo SQLite) e API que só escuta em
`127.0.0.1`. Não conhece o SAFRA Portal e funciona sem ele.

| Módulo | Situação |
|---|---|
| `core` (configuração do processo) | implementado e testado |
| `storage` (migrações do banco privado) | implementado e testado |
| `api` (aplicação, rota de saúde, linha de comando) | implementado e testado |
| `security`, `monitoring`, `platform`, `memory`, `ai_gateway`, `voice`, `communication`, `projects`, `tools`, `intelligence` | planejados: só o pacote e a responsabilidade |

```text
pip install -e ../foundation -e ".[dev]"
pytest                          testes
safra-assistant --check         valida a configuração, migra o banco (com backup) e informa a saúde
safra-assistant                 inicia a API em http://127.0.0.1:47800
```

| Variável | Padrão | Observação |
|---|---|---|
| `SAFRA_ENVIRONMENT` | `development` | `development`, `test`, `staging`, `production` |
| `SAFRA_DATA_DIR` | `%LOCALAPPDATA%\SAFRA` ou `~/.local/share/safra` | pasta nova; a do legado nunca é alterada |
| `SAFRA_DATABASE_URL` | SQLite em `SAFRA_DATA_DIR` | só SQLite local é aceito |
| `SAFRA_API_HOST` | `127.0.0.1` | só endereços deste computador são aceitos |
| `SAFRA_API_PORT` | `47800` | |
| `SAFRA_LOG_LEVEL`, `SAFRA_LOG_TO_FILE`, `SAFRA_MIGRATE_ON_START` | `INFO`, `true`, `true` | |
