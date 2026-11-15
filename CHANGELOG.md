# Registro de mudanças — SAFRA, nova geração

O registro do legado (até a versão 3.0.0) continua em `ULTRON/CHANGELOG_JARVIS.md`.

## 4.0.0.dev0 — em desenvolvimento

### 15/11/2026 — Fase 2: arquitetura, workspace, Portal e Assistant

Relatório completo: `docs/engineering/PHASE_2_REPORT.md`.

**Arquitetura**
- AD-02 e AD-06 confirmadas pelo autor: dois serviços independentes (SAFRA Assistant e SAFRA Portal) e site
  público gerado no servidor. Decisões AD-20 a AD-24 registradas.
- Backend dividido em três pacotes: `safra_foundation` (biblioteca sem domínio), `safra` (Assistant, antes
  `safra-core`) e `safra_portal`. Cada banco grava o serviço dono e recusa o do outro.
- 15 testes de isolamento entre os serviços, inclusive subindo cada um num processo que não consegue importar o
  outro.

**SAFRA Assistant**
- Modelo de dados inicial (migração 0002, 11 tabelas), linha de comando `safra-assistant`.

**SAFRA Portal**
- Autenticação com scrypt (parâmetros conferidos na OWASP), sessões no servidor, anti-CSRF, bloqueio por
  tentativas, limite por endereço, recuperação de acesso por código de uso único; nenhuma conta padrão.
- Papéis Administrador, Editor e Publicador, conferidos no servidor em cada rota, com teste que percorre todas as
  rotas com cada papel e sem sessão.
- CMS: páginas e notícias em blocos tipados, rascunho, publicação, despublicação, versões imutáveis e restauração,
  pré-visualização, exclusão lógica, categorias, mídia validada pelo conteúdo do arquivo, página inicial
  configurável, cadastro de versões para download (publicação bloqueada até a decisão de licença), auditoria.
- Site público com 12 páginas, SEO, Open Graph, mapa do site, `robots.txt`, página 404, sem JavaScript.
- Testes também sobre PostgreSQL 16 no CI.

**Painel administrativo** (`apps/admin`)
- React + TypeScript compilado para arquivos estáticos servidos pelo Portal em `/admin/`; testes de unidade e de
  componente; teste de ponta a ponta num navegador real (`scripts/e2e/portal_e2e.py`).

**Workspace e documentação**
- `packages/design-tokens` como fonte única das cores; modelo de dados, matriz de permissões, modelo de ameaças,
  política de autenticação, inventário de licenças (Python, npm e Rust).
- Prova de conceito da casca do desktop em Tauri e casca de comparação em QtWebEngine, medidas no contêiner e no
  Windows do CI; decisão AD-07 continua aberta.

**Legado**
- Nenhum arquivo de `ULTRON/` foi alterado.

### 14/11/2026 — Fase 1 (auditoria do legado) e início da Fase 2 (fundação)

**Documentação** (`docs/`)
- Auditoria do legado, inventário de funcionalidades (108 itens com destino), linha de base de desempenho
  medida, arquitetura alvo, 19 decisões de arquitetura e plano de entregas em 12 fases.
- Instrumento de medição do legado: `scripts/perf/legacy_baseline.py`, com os dados brutos versionados.

**Backend** (`backend/`)
- Pacote `safra` com os 13 módulos do SAFRA Core e pacote `safra_portal`.
- Implementado e testado: configuração validada; erros com código estável; logs em JSON com correlação e
  mascaramento de segredos; motor do banco; migrações versionadas com retorno e backup verificado; guarda de
  senhas com scrypt; *tokens*; registro de saúde; aplicação base da API (formato único de erro, guarda de
  `Host`, cabeçalhos de segurança); rota de saúde; linha de comando `safra-core`.
- Regras de arquitetura conferidas por teste: camadas, ciclos, construções proibidas, independência do legado,
  ausência de nomes de terceiros.
- CI próprio (`.github/workflows/safra-ci.yml`): Linux e Windows, Python 3.11 e 3.13. Primeira execução
  aprovada nos quatro ambientes, no commit `f54f616`.

**Legado**
- Nenhum arquivo de `ULTRON/` foi alterado.
