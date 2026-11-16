# SAFRA Portal — backend

Site público e painel administrativo (CMS). Serviço **independente** do SAFRA Assistant: servidor próprio, banco
próprio, sem nenhuma rota, sessão ou credencial em comum.

| Parte | Pasta | Situação |
|---|---|---|
| Domínio: modelos, matriz de permissões, blocos de conteúdo | `domain/` | implementado e testado |
| Banco, migrações, conteúdo inicial, limite de frequência | `infrastructure/` | implementado e testado |
| Autenticação, sessões, anti-CSRF, bloqueio, recuperação | `auth/` | implementado e testado |
| Conteúdo com versões, página inicial, downloads (publicação bloqueada), auditoria | `cms/` | implementado e testado |
| Mídia com validação pelo conteúdo do arquivo | `media/` | implementado e testado |
| Rotas do painel, montagem, linha de comando | `api/` | implementado e testado |
| Site público gerado no servidor | `public_site/`, `templates/`, `static/` | implementado e testado |

Nada foi publicado na internet nem validado fora do CI.

## Executar em desenvolvimento

```text
pip install -e ../foundation -e ".[dev]"
safra-portal check                                     valida a configuração e migra o banco
safra-portal create-admin --email voce@exemplo.com --name "Seu Nome"     pede a senha no terminal
safra-portal                                           http://127.0.0.1:47900  (painel em /admin/)
pytest
```

Não existe conta padrão: sem `create-admin`, ninguém entra no painel. O painel (`apps/admin`) precisa ser
compilado para aparecer em `/admin/`; sem isso, a API funciona e a página avisa.

## Configuração (`SAFRA_PORTAL_*`)

| Variável | Padrão | Observação |
|---|---|---|
| `ENVIRONMENT` | `development` | em `production`: PostgreSQL e HTTPS obrigatórios |
| `DATA_DIR` | pasta de dados do usuário | banco SQLite de desenvolvimento, mídia, logs, backups |
| `DATABASE_URL` | SQLite em `DATA_DIR` | produção: `postgresql+psycopg://…` (instale o extra `postgres`) |
| `MEDIA_DIR` | `DATA_DIR/media` | |
| `HOST`, `PORT` | `127.0.0.1`, `47900` | |
| `PUBLIC_BASE_URL` | `http://127.0.0.1:47900` | endereço público; define `Host` e `Origin` aceitos, canônico e sitemap |
| `EXTRA_ALLOWED_HOSTS` | vazio | nomes adicionais aceitos em `Host` |
| `SESSION_IDLE_MINUTES`, `SESSION_ABSOLUTE_HOURS` | 30, 12 | prazos da sessão administrativa |
| `LOGIN_ATTEMPTS_PER_IP`, `LOCKOUT_THRESHOLD`, `LOCKOUT_MINUTES` | 10, 5, 15 | força bruta |
| `RECOVERY_TOKEN_MINUTES` | 30 | validade do código de recuperação |
| `MAX_UPLOAD_BYTES` | 5 MiB | limite por imagem |
| `MIGRATE_ON_START`, `SEED_ON_START` | `true`, `true` | |

A URL do banco de produção contém credencial: ela vem **só** do ambiente do servidor, nunca do repositório.
