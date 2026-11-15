# Relatório de execução — Fase 2: arquitetura, workspace, Portal e Assistant

Data: 15/11/2026. Ramo `claude/adoring-brahmagupta-vcejpt`. Último CI conferido: commit `58571cd`, execução
<https://github.com/JLeoBRx/utron-jarvis/actions/runs/43775067299> — **8 de 8 jobs aprovados**.

**Situação:** os 15 critérios de aceitação do enunciado têm teste automatizado e passam no CI em Linux e Windows.
Os 15 entregáveis existem, com duas ressalvas: a prova de conceito do desktop **não testou áudio nem microfone**,
e nada foi validado no Windows do autor. Por isso a Fase 2 está **entregue, com as pendências da seção 6**; não
está declarada validada.

Legenda usada abaixo: **I** implementado · **T** testado automaticamente · **CI** passa no CI (Linux e Windows,
quando o job existe nos dois) · **V** validado no ambiente real do autor (nenhum item tem V).

## 1. O que foi implementado

| Parte | Situação | Onde |
|---|---|---|
| Workspace: três pacotes Python, painel, tokens de design, provas de conceito, testes da raiz | I T CI | `backend/`, `apps/admin`, `packages/design-tokens`, `desktop/`, `tests/` |
| Isolamento entre os serviços (AD-02) | I T CI | `tests/isolation/` |
| Biblioteca de base (erros, logs, configuração, banco, migrações com backup, restauração, senhas, saúde, base web) | I T CI | `backend/foundation` |
| SAFRA Assistant: configuração, banco privado com 11 tabelas, API mínima (saúde), linha de comando | I T CI | `backend/assistant` |
| SAFRA Portal: autenticação, sessões, CSRF, bloqueio, limite por endereço, recuperação, papéis, auditoria | I T CI | `backend/portal/src/safra_portal/auth`, `domain/permissions.py` |
| CMS: páginas e notícias com versões, restauração, pré-visualização, *slug*, SEO, categorias, imagem de destaque, exclusão com confirmação | I T CI | `backend/portal/src/safra_portal/cms` |
| Mídia: envio validado pelo conteúdo, nome gerado no servidor, texto alternativo, remoção controlada | I T CI | `…/media` |
| Página inicial administrável (título, subtítulo, imagem, botões, seções, ordem, destaques, *links*, rodapé) | I T CI | `…/cms/homepage.py` |
| Downloads: cadastro de versões; publicação de instaladores **bloqueada no código** | I T CI | `…/cms/releases.py` |
| Site público: 12 páginas, SEO, Open Graph, mapa do site, `robots.txt`, 404, sem JavaScript | I T CI | `…/public_site`, `templates/`, `static/` |
| Painel administrativo (`/admin`): resumo, páginas, notícias, categorias, mídia, página inicial, downloads, usuários, auditoria, conta | I T CI | `apps/admin` |
| PostgreSQL 16 para o Portal (migração e fluxo do CMS) | I T CI (só Linux) | `backend/portal/tests/test_postgres.py` |
| Prova de conceito da casca: Tauri e QtWebEngine, mesmo instrumento de medição | I, medida no contêiner e no Windows do CI | `desktop/`, `docs/architecture/DESKTOP_SHELL_POC.md` |
| Inventário de licenças (Python, npm, Rust), avisos de licença no painel compilado | I CI | `docs/engineering/LICENSE_INVENTORY.md`, `scripts/licenses/` |
| Documentação: modelo de dados, permissões, ameaças, autenticação, decisões | feita | `docs/` |

## 2. Arquitetura final desta fase

```
 computador do usuário                                   servidor (ainda não existe)
 ┌───────────────────────────────┐                       ┌──────────────────────────────────────┐
 │ casca (prova de conceito)     │                       │ navegador do visitante  /  /admin    │
 │        │ 127.0.0.1:47800      │   nenhuma ligação     │        │ HTTPS (em produção)          │
 │ SAFRA Assistant (safra)       │ ◄───────── ✕ ───────► │ SAFRA Portal (safra_portal)          │
 │ SQLite privado, dono gravado  │                       │ PostgreSQL (SQLite em dev), mídia    │
 └──────────────┬────────────────┘                       └──────────────────┬───────────────────┘
                └──── ambos dependem só de safra_foundation (biblioteca, sem estado) ────┘
```

- Dois serviços que não se importam, não têm rota, banco, sessão, credencial nem prefixo de configuração em comum;
  cada banco grava o dono e recusa o outro serviço (AD-21).
- Site público em HTML gerado no servidor (Jinja2, escape automático, CSP `default-src 'none'`); painel em React
  + TypeScript compilado para arquivos estáticos servidos pelo próprio Portal; nenhum Node.js em produção (AD-06).
- Conteúdo do CMS em blocos tipados, nunca HTML (AD-22). Detalhes em `docs/architecture/TARGET_ARCHITECTURE.md`
  e `docs/architecture/DATA_MODEL.md`.

## 3. Como executar

```text
pip install -e backend/foundation -e "backend/assistant[dev]" -e "backend/portal[dev]"

# Assistant
safra-assistant --check          valida, migra o banco privado (com backup) e informa a saúde
safra-assistant                  API em http://127.0.0.1:47800

# Painel administrativo (compilado, servido pelo Portal)
cd apps/admin && npm ci && npm run build
npm run dev                      desenvolvimento em http://localhost:5173/admin/ (com o Portal no ar)

# Portal
safra-portal create-admin --email voce@exemplo.com --name "Seu Nome"    a senha é pedida no terminal
safra-portal                     site em http://127.0.0.1:47900, painel em /admin/

# Testes
(cd backend/foundation && pytest); (cd backend/assistant && pytest); (cd backend/portal && pytest); pytest tests
(cd apps/admin && npm test && npx tsc --noEmit -p .)
python scripts/e2e/portal_e2e.py   ponta a ponta no navegador (exige o painel compilado)
```

Esses comandos foram executados nesta sessão, com pastas de dados temporárias: o Assistant respondeu
`{"status":"ok","service":"assistant","version":"4.0.0.dev0"}`, o Portal respondeu 200 em `/` e em `/admin/`,
e respondeu 404 em `/api/v1/health` (a rota do Assistant não existe no Portal).

## 4. Critérios de aceitação

Todos os testes abaixo rodam no CI em Ubuntu e Windows, com Python 3.11 e 3.13, salvo indicação.

| # | Critério | Testes | Resultado |
|---|---|---|---|
| 1 | Portal inicia de forma independente | `tests/isolation`: `test_portal_starts_and_serves_without_the_assistant_installed` (processo em que o Assistant não pode ser importado); passo "Linha de comando dos dois serviços" do CI | passa |
| 2 | Assistant inicia de forma independente | `test_assistant_starts_and_serves_without_the_portal_installed`; `backend/assistant`: `test_assistant_starts_migrates_and_reports_health` | passa |
| 3 | Portal funciona sem o Assistant | `test_portal_starts_and_serves_without_the_assistant_installed`, `test_each_service_keeps_working_while_the_other_is_down`, `test_the_portal_has_no_http_client_to_call_anything` | passa |
| 4 | Assistant funciona sem o Portal | `test_assistant_starts_and_serves_without_the_portal_installed`, `test_each_service_keeps_working_while_the_other_is_down` | passa |
| 5 | Nenhuma rota cruzada | `test_no_route_is_shared_and_no_route_crosses_over`, `test_each_service_answers_404_on_the_other_ones_routes`, `test_neither_service_imports_the_other`, `test_neither_service_mentions_the_other_ones_addresses_or_settings` | passa |
| 6 | Bancos independentes | `test_databases_are_separate_files_with_separate_owners`, `test_each_service_refuses_the_other_ones_database`, `test_default_data_folders_are_different`, `test_the_assistant_never_accepts_a_database_server`; `backend/foundation`: `test_a_database_owned_by_another_service_is_refused` | passa |
| 7 | Usuário público não acessa o CMS | `backend/portal`: `test_a_visitor_reaches_no_admin_route` (todas as rotas do painel, com o método de cada uma, exceto entrar e recuperar acesso); ponta a ponta: "visitante vê o site público e não entra no painel" | passa |
| 8 | Editor não administra usuários | `test_editor_cannot_manage_users_or_publish`, `test_each_role_is_refused_exactly_where_the_matrix_says[editor]` | passa |
| 9 | Publicador consegue publicar | `test_publisher_can_publish_but_not_edit_or_manage`, `test_each_role_is_refused_exactly_where_the_matrix_says[publicador]` | passa |
| 10 | Rascunho não aparece publicamente | `test_draft_is_not_public_and_published_content_is`, `test_edits_after_publishing_stay_private_until_published_again`, `test_navigation_shows_only_what_is_published`; ponta a ponta: "criar página como rascunho" e "editar depois de publicar" | passa |
| 11 | Conteúdo publicado aparece corretamente | `test_draft_is_not_public_and_published_content_is`, `test_homepage_is_driven_by_the_admin`; ponta a ponta: "publicar: a página entra no ar", "texto com HTML e script vira texto no site" | passa |
| 12 | Versões antigas podem ser restauradas | `test_versions_are_kept_and_an_old_one_can_be_restored`; ponta a ponta: "restaurar a versão 1 como rascunho" | passa |
| 13 | Envio inválido é rejeitado | `test_invalid_or_malicious_uploads_are_rejected` (9 conteúdos enviados com nome e tipo de imagem: texto, HTML, SVG, executável, PHP, ZIP, PNG truncado, PNG com dimensões gigantes, vazio), `test_oversized_upload_is_rejected`; ponta a ponta: "envio de arquivo que não é imagem é recusado" | passa |
| 14 | Sessões expiram corretamente | `test_session_expires_by_inactivity_and_by_absolute_time`, `test_logout_revokes_the_session_on_the_server`, `test_recovery_revokes_sessions_and_expired_or_replaced_tokens_fail`; ponta a ponta: "sair encerra a sessão no servidor" | passa |
| 15 | Backups são restauráveis | `backend/portal`: `test_backup_can_be_restored`; `backend/assistant`: `test_private_data_survives_backup_and_restore`; `backend/foundation`: `test_restore_brings_the_data_back_and_keeps_the_replaced_database`, `test_restore_refuses_a_corrupt_backup_and_changes_nothing` | passa |

**Testes adicionais pedidos**

| Tema | Como é conferido |
|---|---|
| Frontend | Vitest: 15 testes (cliente da API, blocos, navegação por papel, tela de entrada); verificação de tipos; compilação sem script embutido |
| Backend e APIs | 62 + 32 + 159 testes nos três pacotes; o teste de autorização percorre cada rota do painel com cada papel e sem sessão |
| Migrações | cada serviço confere que a migração e o modelo descrevem as mesmas tabelas e colunas; ida, volta e backup antes de mexer; PostgreSQL 16 no CI |
| Segurança | autenticação (20 testes), autorização, CSRF e origem, cabeçalhos e CSP, `Host`, envio de arquivos, conteúdo com HTML, segredos fora do repositório (`tests/workspace`) |
| Responsividade | ponta a ponta: a 390 px de largura, sem rolagem lateral no site e no painel |
| Acessibilidade básica | ponta a ponta: o primeiro Tab leva ao atalho para o conteúdo; testes do site conferem `lang`, um único `h1`, `main`, `nav`, `header`, `footer` e o atalho para o conteúdo; o texto alternativo da mídia chega ao HTML público (`test_media.py`); contraste das cores conferido por teste (`tests/workspace/test_design_tokens.py`). Não houve auditoria com leitor de tela |

## 5. Resultados reais

| Suíte | Local (contêiner Linux, Python 3.13, 15/11/2026) | CI, commit `58571cd` |
|---|---|---|
| `backend/foundation` | 62 aprovados | aprovado em Ubuntu e Windows, Python 3.11 e 3.13 |
| `backend/assistant` | 32 aprovados | idem |
| `backend/portal` | 159 aprovados, 2 ignorados (PostgreSQL ausente no contêiner) | idem; os 2 de PostgreSQL rodam e passam no job próprio |
| `tests/` (isolamento e regras do repositório) | 23 aprovados | idem |
| Painel: tipos, Vitest, compilação | sem erros de tipo; 15 aprovados; JS 282,5 kB (83,8 kB comprimido), CSS 13,95 kB | aprovado |
| Ponta a ponta no navegador (Chromium) | 15 de 15 etapas | aprovado |
| Casca: Tauri no Windows | — | compilou em 4 min 19 s; executável de 3 521 536 bytes; abriu e falou com o Assistant nas 3 execuções |
| Casca: QtWebEngine no Windows | — | abriu e falou com o Assistant nas 3 execuções |

Cada suíte Python mostra 1 aviso: o cliente de teste do Starlette pede o pacote `httpx2` no lugar do `httpx`. A
instalação foi bloqueada pela política de permissões desta sessão; o aviso não afeta o resultado.

## 6. Pendências

| Pendência | Por quê / próximo passo |
|---|---|
| Prova de conceito: **áudio e microfone não testados** | o contêiner e o *runner* do CI não têm dispositivo de áudio; por desenho, captura e síntese ficam no Assistant, que ainda não tem o módulo de voz. Testar no Windows do autor quando a voz chegar (Fase 5) |
| Prova de conceito: bandeja e notificações não vistas na tela | as chamadas retornaram sem erro, mas ninguém viu; conferir no Windows do autor |
| Validação no Windows do autor | nada da nova geração foi executado lá |
| Requisitos atualizados (portal, CMS, gateway de IA) | item do plano, não do enunciado; vai para a Fase 3 |
| Composição local com contêineres | item do plano; vai para a Fase 11 |
| Agendamento de publicação, galeria pública, seções de documentação pública | não pedidos nesta fase; Fases 8 e 9 |
| Envio de e-mail na recuperação de acesso | hoje o código de uso único é gerado no painel ou na linha de comando e entregue por outro meio |
| Textos legais (privacidade e termos) | são texto-modelo, marcados como tal no próprio site; precisam da revisão do autor |
| `httpx2` no lugar de `httpx` nos testes | instalar quando a política permitir |

## 7. Problemas encontrados (e o que foi feito)

| Problema | Solução |
|---|---|
| `npm` 10 falhava ao resolver pares opcionais do Vitest | `.npmrc` com `legacy-peer-deps=true` e os pares necessários declarados |
| Erros de tipo nos testes do painel só apareceram depois de um envio | corrigidos; a verificação de tipos agora cobre os testes e roda no CI |
| O painel compilado não trazia o aviso de licença do React | um *plugin* do Vite gera `licencas-de-terceiros.txt`, conferido no CI |
| Registro de saúde duplicado quando a aplicação reiniciava no mesmo processo | o registro passou a ser criado a cada ciclo de vida da aplicação |
| O FastAPI 0.163 esconde as rotas de roteadores incluídos | o teste de autorização enumera as rotas do roteador e confere que são as mesmas servidas |
| A regra de segredos acusou uma senha de teste atribuída junto com o e-mail | a atribuição foi separada; a regra não foi enfraquecida |
| O site da folha de senhas da OWASP estava bloqueado pela rede | os parâmetros foram lidos no repositório oficial da OWASP no GitHub |
| A bandeja do Qt não existe sob Xvfb | registrado; no Windows do CI ela respondeu "ok" |
| O artefato com os dados das cascas no Windows não pôde ser baixado desta sessão | os números foram transcritos do log do job, com a origem indicada |

## 8. Riscos

| Risco | Situação |
|---|---|
| Licença GPL-3.0 da voz atual (Piper) | qualquer instalador distribuído com ela fica sujeito à GPL-3.0; **AD-17 aberta**, publicação de instaladores bloqueada no código |
| Limite de tentativas por endereço atrás de um *proxy* | sem configuração de *proxy* confiável, todos os visitantes parecem vir do mesmo endereço; resolver ao escolher a hospedagem (AD-13) |
| Sem segundo fator de autenticação no painel | previsto para a Fase 9 |
| Backups sem criptografia | aceitável no computador do usuário; no servidor, decidir com a hospedagem |
| Sem auditoria automática de vulnerabilidades das dependências | incluir no CI na próxima fase |
| Dependências só de Windows fora do inventário; licenças dos modelos Vosk e do espeak-ng não conferidas | antes de qualquer instalador |
| Diferença de memória entre as cascas medida só pela RSS somada | medir o conjunto privado no Windows do autor |

O modelo de ameaças completo, com 19 ameaças, a mitigação e o teste de cada uma, está em
`docs/security/PORTAL_THREAT_MODEL.md`. Nada aqui afirma que o Portal é seguro: afirma que cada mitigação listada
tem um teste que passa.

## 9. Decisões ainda abertas

| Decisão | O que falta |
|---|---|
| AD-07 — casca do desktop | medir no Windows do autor e cobrir início com o Windows, tecla de atalho, clique na notificação, áudio e queda da casca |
| AD-13 — hospedagem e publicação | escolha do servidor, domínio e *proxy*; nada foi contratado nem registrado |
| AD-17 — licenciamento | escolher entre licenciar o Assistant como GPL-3.0, trocar a voz, ou não distribuir a voz atual |

## 10. Limites respeitados

Nenhum arquivo de `ULTRON/` foi alterado; nenhum dado antigo foi apagado; nenhum *branch* ou *tag* remoto foi
criado além do ramo de trabalho; nenhum *merge*, publicação, domínio, hospedagem ou instalador; o Assistant só
escuta em `127.0.0.1`; nenhum segredo no repositório (regra conferida por teste).

## 11. Próxima fase recomendada

**Fase 3 — design system e console operacional do Assistant**, começando por: (1) atualizar os requisitos com o
portal, o CMS e o gateway de IA; (2) `packages/contracts` com os tipos da API do Assistant; (3) sessões locais
do Assistant (bilhete da casca e código de uso único no navegador, Fase 4 antecipada no que o console precisa);
(4) auditoria de vulnerabilidades das dependências no CI. Em paralelo, o autor pode rodar as duas cascas no
próprio Windows (`desktop/measure_shell.py`) para fechar a AD-07 e decidir a AD-17.
