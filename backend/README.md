# SAFRA — backend

Dois pacotes Python numa só base de código (decisão AD-02):

| Pacote | O que é | Situação |
|---|---|---|
| `safra` | **SAFRA Core**: o assistente, com API local | fundação implementada e testada (abaixo) |
| `safra_portal` | **SAFRA Portal**: site público e painel administrativo | planejado (Fases 8 e 9) |

## O que já existe

| Módulo | Implementado | Testes |
|---|---|---|
| `safra.core` | configuração validada (`SAFRA_*`), erros com código estável, logs em JSON com correlação e mascaramento de segredos | `test_config.py`, `test_errors_logging.py` |
| `safra.storage` | motor do banco (SQLite em modo WAL; PostgreSQL pela mesma interface), migrações versionadas com retorno, backup verificado antes de migrar | `test_storage.py` |
| `safra.security` | guarda de senhas com scrypt, *tokens* aleatórios com resumo | `test_security_primitives.py` |
| `safra.monitoring` | registro de saúde com isolamento de falhas | `test_health.py` |
| `safra.api` | aplicação base (formato único de erro, correlação, guarda de `Host`, cabeçalhos de segurança), aplicação do Core com a rota de saúde, linha de comando | `test_api.py` |
| regras de arquitetura | camadas, ciclos, construções proibidas, independência do legado, identidade | `test_architecture.py` |

Os outros oito módulos do Core existem só como pacote com a descrição da responsabilidade.
**Nada foi validado em Windows real.**

## Como usar

```text
python -m venv .venv && .venv/bin/pip install -e ".[dev]"      (Windows: .venv\Scripts\pip)
pytest                                   testes
safra-core --check                       valida a configuração, migra o banco (com backup) e informa a saúde
safra-core                               inicia a API em http://127.0.0.1:47800
```

Para repetir exatamente o ambiente testado: `pip install -r requirements.lock`.

## Configuração

Variáveis de ambiente, todas opcionais:

| Variável | Padrão | Observação |
|---|---|---|
| `SAFRA_ENVIRONMENT` | `development` | `development`, `test`, `staging`, `production` |
| `SAFRA_DATA_DIR` | `%LOCALAPPDATA%\SAFRA` (Windows) ou `~/.local/share/safra` | pasta **nova**: a do legado nunca é alterada |
| `SAFRA_DATABASE_URL` | SQLite em `SAFRA_DATA_DIR` | |
| `SAFRA_API_HOST` | `127.0.0.1` | só endereços deste computador são aceitos |
| `SAFRA_API_PORT` | `47800` | |
| `SAFRA_LOG_LEVEL` | `INFO` | |
| `SAFRA_LOG_TO_FILE` | `true` | `logs/safra.jsonl`, com rotação |
| `SAFRA_MIGRATE_ON_START` | `true` | |

Nenhum segredo é lido de variável nem de arquivo nesta fase.
