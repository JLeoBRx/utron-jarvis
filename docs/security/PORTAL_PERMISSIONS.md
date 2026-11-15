# Matriz de permissões do SAFRA Portal

Data: 15/11/2026. Fonte viva: `backend/portal/src/safra_portal/domain/permissions.py`. A migração inicial grava a
mesma matriz no banco (`roles`, `permissions`, `role_permissions`) e um teste confere que as duas coincidem.
As tabelas abaixo foram **geradas a partir do código** (rotas e permissões reais), não escritas à mão.

## 1. Princípios

1. **O servidor decide.** Cada rota do painel declara a permissão exigida com `require(...)`. A interface só
   esconde o que o papel não permite; esconder não é proteger.
2. **O papel é lido do banco a cada pedido.** Mudar o papel ou desativar a conta vale no pedido seguinte; o
   navegador não tem como "dizer" o próprio papel.
3. **Visitante não tem conta.** O site público só lê conteúdo publicado, por um único caminho de leitura.
4. **Nenhuma conta padrão.** O primeiro administrador é criado no servidor por `safra-portal create-admin`.
5. **Menor privilégio.** Quem edita não publica; quem publica não edita; só o administrador gerencia pessoas,
   exclui conteúdo, mexe na página inicial e nos downloads e lê a auditoria.

## 2. Papéis

| Papel | Para quem |
|---|---|
| **Administrador** | responsável pelo site: tudo, inclusive contas, papéis, exclusões, página inicial, downloads e auditoria |
| **Editor** | quem escreve: cria e edita páginas e notícias, salva rascunhos, restaura versões como rascunho, gerencia mídia e categorias. Não publica, não exclui conteúdo, não administra pessoas |
| **Publicador** | quem revisa: lê rascunhos e versões, pré-visualiza, publica e despublica. Não edita, não administra pessoas |
| **Visitante** | qualquer pessoa na internet: só o conteúdo publicado, sem conta |

## 3. Permissões por papel

| Permissão | Descrição | Administrador | Editor | Publicador |
|---|---|:-:|:-:|:-:|
| `admin.access` | Entrar no painel administrativo | ✔ | ✔ | ✔ |
| `dashboard.read` | Ver o resumo do painel | ✔ | ✔ | ✔ |
| `content.read` | Ver páginas e notícias no painel, inclusive rascunhos, versões e pré-visualização | ✔ | ✔ | ✔ |
| `content.edit` | Criar e editar páginas e notícias, salvar rascunhos e restaurar versões como rascunho | ✔ | ✔ | — |
| `content.publish` | Publicar e despublicar páginas e notícias | ✔ | — | ✔ |
| `content.delete` | Excluir páginas e notícias | ✔ | — | — |
| `categories.manage` | Criar, renomear e remover categorias de notícias | ✔ | ✔ | — |
| `media.read` | Ver a biblioteca de mídia | ✔ | ✔ | ✔ |
| `media.upload` | Enviar imagens e editar seus metadados | ✔ | ✔ | — |
| `media.delete` | Remover imagens que não estão em uso | ✔ | ✔ | — |
| `homepage.edit` | Alterar a página inicial e as informações públicas do site | ✔ | — | — |
| `releases.manage` | Cadastrar e editar versões do software para download | ✔ | — | — |
| `users.manage` | Gerenciar usuários, papéis e recuperação de acesso | ✔ | — | — |
| `audit.read` | Consultar a auditoria administrativa | ✔ | — | — |

## 4. Rotas do painel e a permissão de cada uma

Todas sob `/admin/api`. Além da permissão, toda rota que altera algo exige o cabeçalho `Origin` do próprio site
e o código anti-CSRF da sessão (`X-CSRF-Token`).

| Rota | Método | Exige |
|---|---|---|
| `/auth/login` | POST | (sem sessão; Origin conferido; limite por endereço) |
| `/auth/recover` | POST | (sem sessão; Origin conferido; limite por endereço) |
| `/auth/session` | GET | (qualquer sessão válida) |
| `/auth/logout` | POST | (qualquer sessão válida) |
| `/auth/password` | POST | `admin.access` |
| `/sessions` | GET | `admin.access` |
| `/sessions/{session_id}` | DELETE | `admin.access` |
| `/dashboard` | GET | `dashboard.read` |
| `/pages` | GET | `content.read` |
| `/pages` | POST | `content.edit` |
| `/pages/{item_id}` | GET | `content.read` |
| `/pages/{item_id}` | PUT | `content.edit` |
| `/pages/{item_id}/publish` | POST | `content.publish` |
| `/pages/{item_id}/unpublish` | POST | `content.publish` |
| `/pages/{item_id}/versions` | GET | `content.read` |
| `/pages/{item_id}/versions/{version_id}` | GET | `content.read` |
| `/pages/{item_id}/versions/{version_id}/restore` | POST | `content.edit` |
| `/pages/{item_id}` | DELETE | `content.delete` |
| `/news` | GET | `content.read` |
| `/news` | POST | `content.edit` |
| `/news/{item_id}` | GET | `content.read` |
| `/news/{item_id}` | PUT | `content.edit` |
| `/news/{item_id}/publish` | POST | `content.publish` |
| `/news/{item_id}/unpublish` | POST | `content.publish` |
| `/news/{item_id}/versions` | GET | `content.read` |
| `/news/{item_id}/versions/{version_id}` | GET | `content.read` |
| `/news/{item_id}/versions/{version_id}/restore` | POST | `content.edit` |
| `/news/{item_id}` | DELETE | `content.delete` |
| `/categories` | GET | `content.read` |
| `/categories` | POST | `categories.manage` |
| `/categories/{category_id}` | PUT | `categories.manage` |
| `/categories/{category_id}` | DELETE | `categories.manage` |
| `/media` | GET | `media.read` |
| `/media` | POST | `media.upload` |
| `/media/{media_id}/usage` | GET | `media.read` |
| `/media/{media_id}` | PATCH | `media.upload` |
| `/media/{media_id}` | DELETE | `media.delete` |
| `/homepage` | GET | `content.read` |
| `/homepage` | PUT | `homepage.edit` |
| `/site` | GET | `content.read` |
| `/site` | PUT | `homepage.edit` |
| `/releases` | GET | `releases.manage` |
| `/releases` | POST | `releases.manage` |
| `/releases/{release_id}` | PUT | `releases.manage` |
| `/releases/{release_id}/publish` | POST | `releases.manage` |
| `/releases/{release_id}` | DELETE | `releases.manage` |
| `/users` | GET | `users.manage` |
| `/users` | POST | `users.manage` |
| `/users/{user_id}` | PATCH | `users.manage` |
| `/users/{user_id}/recovery-token` | POST | `users.manage` |
| `/audit` | GET | `audit.read` |

Fora de `/admin/api`:

| Rota | Exige |
|---|---|
| `/admin/preview/pages/{id}`, `/admin/preview/news/{id}` (pré-visualização do rascunho) | `content.read` |
| `/admin/` (arquivos do painel compilado) | nada: são arquivos estáticos; os dados vêm da API, que exige sessão |
| site público, `/media/…`, `/sitemap.xml`, `/robots.txt`, `/healthz` | nada: só o que foi publicado |

## 5. Como isto é testado

| Teste | O que confere |
|---|---|
| `tests/test_authorization.py::test_every_admin_route_declares_a_permission` | nenhuma rota do painel sem permissão declarada, salvo as de entrada; nenhuma permissão inventada ou sem uso |
| `…::test_a_visitor_reaches_no_admin_route` | todas as 51 combinações de rota e método respondem 401 sem sessão |
| `…::test_each_role_is_refused_exactly_where_the_matrix_says` | cada papel, em cada rota: 403 onde a matriz nega, aceito onde permite |
| `…::test_editor_cannot_manage_users_or_publish`, `…::test_publisher_can_publish_but_not_edit_or_manage` | os casos do enunciado da Fase 2 |
| `…::test_permissions_come_from_the_database_not_from_the_client` | cabeçalhos ou parâmetros forjados não mudam nada |
| `tests/test_auth.py::test_role_change_and_deactivation_take_effect_on_the_next_request` | rebaixar e desativar valem no pedido seguinte |
| `tests/test_models.py::test_seeded_roles_and_permissions_match_the_documented_matrix` | banco e código com a mesma matriz |
| `apps/admin/tests/navigation.test.ts` | a interface esconde o que o papel não permite (conveniência, não proteção) |
