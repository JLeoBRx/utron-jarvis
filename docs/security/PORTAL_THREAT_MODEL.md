# Modelo de ameaças do SAFRA Portal

Data: 15/11/2026. Versão do código: Fase 2. Este documento **não afirma que o Portal é seguro**: diz o que foi
considerado, o que foi feito e qual teste confere cada defesa. O que não tem teste ou só pode ser conferido na
publicação está marcado como **risco residual**. O Portal ainda não foi publicado nem passou por avaliação externa.

## 1. Escopo

| Dentro | Fora (outros documentos ou fases) |
|---|---|
| site público, painel administrativo, API do painel, mídia, banco do Portal, backups do Portal, dependências | o SAFRA Assistant (outro serviço, outra máquina, outro banco); hospedagem, TLS e *proxy* (Fase 11) |

**Ativos:** contas e sessões administrativas; conteúdo publicado (reputação); rascunhos ainda não publicados;
arquivos de mídia; banco do Portal e seus backups; configuração do servidor (URL do banco); integridade dos
instaladores (quando houver); disponibilidade do site.

**Atacantes considerados:** visitante anônimo na internet; robô de força bruta; página de terceiros aberta no
navegador de um administrador; administrador de papel menor tentando subir de nível; conta administrativa
comprometida; dependência comprometida.

**Fronteiras de confiança:** navegador ↔ servidor (tudo o que chega do navegador é não confiável, inclusive do
painel); servidor ↔ banco; servidor ↔ disco de mídia; repositório ↔ servidor (segredos não passam pelo Git).

## 2. Ameaças

Probabilidade e impacto: B baixa, M média, A alta — avaliados para um site institucional pequeno na internet.

| # | Ameaça | Ativo | Vetor | P | I | Mitigação implementada | Teste que confere |
|---|---|---|---|:-:|:-:|---|---|
| T1 | **Acesso administrativo indevido** | painel, conteúdo | entrar sem conta; conta padrão; rota administrativa sem sessão | M | A | nenhuma conta existe ao instalar (primeiro administrador por comando no servidor); toda rota de `/admin/api` exige sessão, exceto entrada e recuperação | `test_auth::test_a_fresh_portal_has_no_account_at_all`, `test_authorization::test_a_visitor_reaches_no_admin_route` (51 combinações), E2E "visitante… não entra no painel" |
| T2 | **Roubo de sessão** | sessão | ler o *cookie* por script; interceptar na rede; reaproveitar após sair; fixação de sessão | M | A | *cookie* `HttpOnly`, `SameSite=Strict`, `Secure` quando o site é HTTPS, restrito a `/admin`; *token* novo a cada entrada; banco guarda só o resumo SHA-256; prazo de inatividade (30 min) e absoluto (12 h); sair revoga no servidor; trocar ou recuperar a senha encerra as outras sessões | `test_auth::test_login_sets_a_strict_http_only_cookie_scoped_to_the_admin`, `…test_cookie_is_secure_when_the_site_is_https`, `…test_only_token_digests_are_stored`, `…test_session_expires_by_inactivity_and_by_absolute_time`, `…test_logout_revokes_the_session_on_the_server`, `…test_a_forged_or_garbage_cookie_is_not_a_session` |
| T3 | **CSRF** | ações do painel | página de terceiros fazendo o navegador do administrador enviar um pedido | M | A | `SameSite=Strict`; todo pedido que altera exige `Origin` do próprio site **e** o código anti-CSRF da sessão no cabeçalho; CORS não habilitado | `test_auth::test_changes_need_origin_and_the_csrf_token_of_the_session`, `…test_login_from_another_origin_is_refused` |
| T4 | **XSS** | visitantes, sessões administrativas | texto do CMS com HTML ou *script*; endereço `javascript:`; injeção de modelo | M | A | o painel não envia HTML: só blocos tipados validados no servidor; escape automático nos modelos; marcação mínima convertida **depois** do escape; endereços só `https:`, `mailto:`, `/…` e `#…`; CSP `default-src 'none'`, `script-src 'self'`, sem `unsafe-inline`; site público sem JavaScript | `test_content::test_text_typed_in_the_cms_never_becomes_markup_or_script` (9 cargas), `…test_only_known_blocks_with_known_fields_are_accepted`, `test_public_site::test_security_headers`, E2E "texto com HTML e script vira texto" e "nenhum bloqueio de CSP" |
| T5 | **SQL injection** | banco | parâmetros, busca, *cookie* | B | A | todo acesso pelo SQLAlchemy com parâmetros; nenhum SQL montado com texto vindo de fora; entradas validadas por modelo | `test_auth::test_a_forged_or_garbage_cookie_is_not_a_session` (inclui `' OR 1=1 --`); a busca do painel usa parâmetro; nenhum `text()` com SQL em `safra_portal` (conferido por busca no código) |
| T6 | **Upload malicioso** | servidor, visitantes | executável, HTML, SVG com *script*, PHP, arquivo disfarçado de imagem, arquivo gigante | M | A | tipo decidido pelos primeiros bytes (PNG, JPEG, GIF, WebP); SVG recusado; extensão e tipo informados ignorados; limite de tamanho lido em fluxo; dimensões limitadas; nome no disco gerado pelo servidor; servido com o tipo gravado, `nosniff` e `inline` | `test_media::test_invalid_or_malicious_uploads_are_rejected` (9 tipos), `…test_oversized_upload_is_rejected`, E2E "arquivo que não é imagem é recusado" |
| T7 | **Path traversal** | arquivos do servidor | `../` no nome enviado ou na URL de mídia | M | A | nome original nunca vira caminho; URL de mídia só aceita o formato gerado (`xx/<32 hex>.ext`) **e** registrado no banco | `test_media::test_the_original_name_never_becomes_a_path`, `…test_only_registered_files_are_served` (7 tentativas, inclusive codificadas) |
| T8 | **Exposição de arquivos privados** | banco, logs, configuração | pedir o arquivo do banco ou de log por URL | B | A | só três pontos servem arquivos: `/static` (pasta do pacote), `/admin/` (painel compilado) e `/media` (só registrados); a pasta de dados não é servida | `test_media::test_only_registered_files_are_served` (tenta o `portal.sqlite3`) |
| T9 | **Vazamento de variáveis de ambiente** | URL do banco, configuração | mensagem de erro, página de erro, log, repositório | M | A | erro 500 sem detalhe; erro de configuração cita o campo, nunca o valor; log mascara padrões de segredo; `.env` ignorado pelo Git; regra do repositório procura segredos | `foundation/test_web::test_unhandled_exception_becomes_500_without_leaking_anything`, `test_config::test_error_message_never_echoes_the_database_url`, `foundation/test_errors_logging::test_secrets_are_masked_in_messages_and_fields`, `workspace/test_repository_rules::test_no_secret_is_committed_in_the_new_platform` |
| T10 | **Força bruta** | contas | tentar senhas em sequência; enumerar contas | A | A | limite por endereço (10 em 5 min); bloqueio da conta após 5 falhas, progressivo (15 min dobrando até 24 h); resposta e custo iguais para conta inexistente, inativa ou bloqueada; senha mínima de 12 caracteres; scrypt com o custo recomendado pela OWASP | `test_auth::test_login_is_rate_limited_per_address`, `…test_account_locks_after_repeated_failures_even_with_the_right_password`, `…test_wrong_password_unknown_user_and_inactive_user_look_the_same` |
| T11 | **Abuso de endpoints** | disponibilidade | pedidos grandes, muitos pedidos, cálculo de senha caro em massa | M | M | corpo limitado por modelo; envio de arquivo cortado ao passar do limite; no máximo dois cálculos de senha ao mesmo tempo; limite na recuperação de acesso; páginas públicas com `Cache-Control` de 60 s, o que permite cache no *proxy* | parcial: limites de tamanho testados; **sem teste de carga** (Fase 12) |
| T12 | **Escalada de privilégios** | papéis | editor tentando publicar, gerenciar usuários ou se promover; forjar papel no pedido | M | A | permissão de cada rota conferida no servidor; papel lido do banco a cada pedido; só `users.manage` altera papéis; o último administrador não pode ser rebaixado | `test_authorization::test_each_role_is_refused_exactly_where_the_matrix_says`, `…test_editor_cannot_manage_users_or_publish`, `…test_permissions_come_from_the_database_not_from_the_client`, `test_auth::test_the_last_active_administrator_cannot_be_demoted_or_deactivated` |
| T13 | **Exposição de backups** | banco inteiro, inclusive resumos de senha | baixar backup pela web; backup esquecido | B | A | backups ficam na pasta de dados, fora de qualquer rota; o banco guarda só resumos (senha com scrypt, *tokens* com SHA-256) | `test_media::test_only_registered_files_are_served`; **cifrar backups e guardá-los fora do servidor: risco residual** (Fase 11) |
| T14 | **Publicação indevida** | reputação | rascunho aparecer; publicação por quem não pode; instalador publicado sem análise | M | A | o site lê só a versão publicada, por um único caminho; publicar é permissão separada de editar; edição depois de publicar não vai ao ar sozinha; pré-visualização exige sessão e não é indexável; publicação de instaladores bloqueada **no código** | `test_content::test_draft_is_not_public_and_published_content_is`, `…test_edits_after_publishing_stay_private_until_published_again`, `…test_preview_needs_a_session_and_is_never_indexed_or_cached`, `test_public_site::test_installer_publication_is_blocked_in_code`, E2E "editar depois de publicar" |
| T15 | **Comprometimento de dependências** | todo o sistema | versão maliciosa publicada num repositório de pacotes | M | A | versões do npm e do Rust travadas por arquivo de trava e escolhidas entre as publicadas há pelo menos duas semanas; versões Python testadas registradas em `backend/requirements.lock`; inventário de licenças e dependências; nenhum recurso de CDN em produção | parcial: CI instala do arquivo de trava (`npm ci`, `cargo --locked`); **sem auditoria automática de vulnerabilidades: risco residual** |
| T16 | **Exposição acidental de dados privados** | dados do usuário do Assistant | o Portal consultar ou receber dados do assistente | B | A | dois serviços em máquinas e bancos diferentes; o Portal não importa o Assistant, não tem cliente HTTP de saída, recusa o banco do outro | `tests/isolation/test_service_isolation.py` (15 testes, inclusive subir cada serviço num processo em que o outro não pode ser importado) |
| T17 | Clickjacking | ações do painel | painel dentro de um *iframe* de terceiros | B | M | `X-Frame-Options: DENY` e `frame-ancestors 'none'` | `test_public_site::test_security_headers` |
| T18 | Cabeçalho `Host` forjado / DNS rebinding | links gerados, sessões | pedido com outro `Host` | B | M | lista fechada de `Host` aceitos, recusada antes das rotas | `test_public_site::test_requests_for_another_host_are_refused` |
| T19 | Perda de dados por edição simultânea | conteúdo | duas pessoas gravando o mesmo conteúdo | M | M | número de versão do rascunho; gravação desatualizada recusada com quem alterou | `test_content::test_simultaneous_editing_never_overwrites_silently` |

## 3. Riscos residuais

| Risco | Por que continua | Quando se trata |
|---|---|---|
| Limite de tentativas em memória, por processo | com várias instâncias, cada uma conta separado | Fase 11: limite no *proxy* ou armazenamento comum |
| **Atrás de um *proxy*, todos os pedidos parecem vir do mesmo endereço** | o Portal não confia em `X-Forwarded-For` (de propósito); atrás de um *proxy* o limite por endereço vira um limite único para todos | Fase 11: configurar só o *proxy* conhecido como confiável |
| Bloqueio de conta pode ser usado para impedir a entrada de um administrador | é o custo do bloqueio contra força bruta; o prazo é limitado | avaliar segundo fator na Fase 9 |
| Sem segundo fator de autenticação | fora do escopo desta fase | Fase 9 |
| Recuperação de acesso depende de um administrador entregar o código por fora | o Portal não envia e-mail | Fase 9, se houver envio de e-mail |
| Backups sem cifra e no mesmo servidor | infraestrutura ainda não definida | Fase 11 |
| Sem auditoria automática de vulnerabilidades das dependências | não configurada | Fase 11 (CI) |
| Sem teste de carga | fora do escopo desta fase | Fase 12 |
| Avaliação de segurança só por testes próprios | não houve avaliação externa | antes da produção |

## 4. Como manter este documento

Toda rota nova do painel entra automaticamente nos testes de autorização (o teste lê as rotas do código). Toda
ameaça nova ganha uma linha aqui **com o teste que a confere**, ou entra na lista de riscos residuais.
