# Decisões de arquitetura do SAFRA

Registro vivo. Cada decisão tem contexto, alternativas, o que foi decidido, consequências e situação. Uma
decisão só muda por outra decisão registrada aqui.

Este registro **substitui**, onde houver conflito, o de 14/11/2026 (`ULTRON/docs/especificacao/DECISOES.md`),
escrito antes da missão de reconstrução integral. A última seção diz o que daquele registro continua valendo.

**Situações:** *definida* (diretriz da missão, não se altera sem justificativa técnica registrada) ·
*decidida* (tomada aqui; reversível) · *proposta* (alto impacto: precisa da confirmação do autor) ·
*aberta* (depende de prova de conceito ou de informação que ainda não existe).

| # | Decisão | Situação |
|---|---|---|
| AD-01 | Reconstrução integral em base de código nova; legado preservado | definida |
| AD-02 | Dois serviços com uma base de código: SAFRA Core (local) e SAFRA Portal (hospedado) | proposta |
| AD-03 | Backend em Python com FastAPI e Pydantic | definida |
| AD-04 | Persistência por SQLAlchemy e Alembic; SQLite no Core, PostgreSQL no Portal | decidida |
| AD-05 | Interfaces em React e TypeScript, num espaço de trabalho único | definida |
| AD-06 | Renderização do portal público | proposta |
| AD-07 | Casca do desktop: Tauri como primeira opção, decidida por prova de conceito | aberta |
| AD-08 | Treze módulos do Core e regra de dependência verificada por teste | decidida |
| AD-09 | Gateway de IA híbrido, independente de provedor | definida |
| AD-10 | Autenticação e autorização sempre no servidor | decidida |
| AD-11 | Dados novos em local novo; o legado é lido, nunca alterado | decidida |
| AD-12 | Acesso remoto ao painel operacional desligado por padrão | definida |
| AD-13 | Hospedagem e publicação | aberta |
| AD-14 | Identidade visual e símbolo | definida |
| AD-15 | Testes: pytest, Vitest, Playwright | definida |
| AD-16 | Observabilidade: logs estruturados e percentis | decidida |
| AD-17 | Licenciamento | **aberta — bloqueia a publicação de downloads** |
| AD-18 | Idioma: código em inglês; documentos e interface em português | decidida |
| AD-19 | Versão: a nova geração começa em 4.0.0 | decidida |

---

## AD-01 — Reconstrução integral; legado preservado

**Contexto.** A missão define a estratégia como FULL. O registro anterior previa migração progressiva dentro do
código antigo.
**Decisão.** A nova plataforma nasce na raiz do repositório (`backend/`, `frontend/`, `desktop/`, `infra/`,
`docs/`, `scripts/`). O legado fica em `ULTRON/`, intacto e executável, com o seu CI, até a nova versão ser
validada. Nada do legado é importado como biblioteca pela nova versão.
**O que "integral" não significa.** Não é jogar fora o que foi verificado. A lógica de negócio com testes é
**portada**: reescrita nos novos limites de módulo, com os testes do legado servindo de especificação
(critérios em `docs/architecture/LEGACY_AUDIT.md` §8).
**Consequências.** Duas bases convivem por alguns meses. O risco de regressão silenciosa cai, porque o legado
continua disponível para comparação lado a lado.

## AD-02 — Dois serviços, uma base de código *(proposta)*

**Contexto.** A missão pede um assistente pessoal com dados privados **e** um site público com CMS, com
"backend e contratos compartilhados" e a proibição de misturar dados pessoais com conteúdo institucional.

| Alternativa | Consequência |
|---|---|
| A. Um único serviço atende tudo | o site público rodaria no computador do usuário ou os dados privados iriam para o servidor; contraria a separação exigida |
| **B. Dois serviços que compartilham bibliotecas** | separação física de dados e de processos; contratos, segurança e design system comuns |
| C. Dois repositórios independentes | separação máxima, mas duplica segurança, armazenamento e convenções |

**Proposta: B.**
- **SAFRA Core** (`safra`): o assistente. Roda no computador do usuário, guarda os dados privados em SQLite e
  escuta só em 127.0.0.1. Atende o aplicativo desktop e o painel operacional.
- **SAFRA Portal** (`safra_portal`): site público e CMS. Roda num servidor, com PostgreSQL e armazenamento de
  mídia. Não conhece conversas, memórias nem ferramentas.
- O Portal só pode importar a camada de base do Core (`core`, `storage`, `security`, `monitoring` e a parte
  genérica de `api`). Um teste de arquitetura impede qualquer outra importação.
**Consequências.** A separação exigida pela missão passa a ser estrutural, não uma regra de permissão. Nenhum
caminho de código leva do site público aos dados privados, porque eles estão em máquinas e bancos diferentes.

## AD-03 — Backend em Python, FastAPI e Pydantic

**Decisão (diretriz).** Python 3.11 ou superior, FastAPI, Pydantic 2, uvicorn. Rotas assíncronas; trabalho que
bloqueia (voz, modelos locais, banco) em *threads* controladas, com limite de concorrência.
**Justificativa além da diretriz.** O conhecimento e a lógica verificada do legado estão em Python; o esquema
OpenAPI gerado do código dá os tipos da interface; a validação de entrada vem do próprio modelo.

## AD-04 — Persistência

| Alternativa | Avaliação |
|---|---|
| `sqlite3` direto e migrações próprias (como o legado) | zero dependência; não serve ao PostgreSQL do Portal; migração sem retorno |
| **SQLAlchemy 2 + Alembic** | um só jeito de acessar dados nos dois serviços; migrações versionadas com retorno; SQLite e PostgreSQL |
| ORM assíncrono dedicado | mais uma tecnologia; ganho pequeno num aplicativo de um usuário |

**Decisão.** SQLAlchemy 2 e Alembic nos dois serviços. Core: SQLite em modo WAL, um arquivo, aberto só pelo
processo do Core. Portal: PostgreSQL em homologação e produção; SQLite só em desenvolvimento e teste.
Nenhum SQL fora de `storage` e dos repositórios de cada domínio. Toda migração faz backup verificado antes.
**Consequências.** Duas dependências novas, justificadas pela portabilidade e pelo retorno de migração. A busca
textual do SQLite (FTS5) é criada por SQL explícito nas migrações do Core.

## AD-05 — Interfaces em React e TypeScript

**Decisão (diretriz).** Um espaço de trabalho (`frontend/`) com pacotes compartilhados (`design-system`,
`api-client`) e aplicações separadas: `console` (interface operacional, usada no desktop e no navegador) e
`admin` (CMS). Vite para compilar; tipos gerados do OpenAPI de cada serviço. Node é ferramenta de
desenvolvimento e de CI, nunca requisito de quem usa.

## AD-06 — Renderização do portal público *(proposta)*

**Contexto.** O portal precisa de bom SEO, carregamento rápido, pré-visualização de rascunhos e de mostrar só
o que foi publicado. O conteúdo muda pelo CMS, sem novo *deploy*.

| Alternativa | A favor | Contra |
|---|---|---|
| A. Aplicação React de página única | uma só tecnologia de interface | SEO e primeiro carregamento dependem de JavaScript |
| **B. HTML gerado no servidor pelo próprio Portal** (modelos de página + CSS do design system; React só onde há interação) | SEO e velocidade melhores; um serviço a menos; "só publicado" é um filtro no servidor; pré-visualização é a mesma rota com permissão | os blocos de página existem em HTML além dos componentes React do console e do admin |
| C. *Framework* React com renderização no servidor | React em tudo, com SEO | um servidor Node em produção além do Python: mais custo, mais superfície, mais um *deploy* |

**Proposta: B**, com os *tokens* e o CSS vindos do mesmo design system. Desvia da pilha de referência só nas
páginas públicas; o painel administrativo e o console continuam em React.
**Se preferir React em todo lugar**, a alternativa é a C, com o custo indicado. A decisão é necessária antes
da Fase 8; nada na fundação depende dela.

## AD-07 — Casca do desktop *(aberta: prova de conceito)*

**Contexto.** A missão indica Tauri como primeira opção e exige prova de conceito antes da decisão. O registro
anterior tinha escolhido QtWebEngine por já ser dependência; essa escolha fica **suspensa**.

**Prova de conceito** (compilada no CI do Windows, validada no computador do autor):

| Critério | O que se observa |
|---|---|
| Bandeja | ícone, menu, abrir e recolher a janela |
| Notificações | aviso nativo com clique |
| Inicialização | iniciar com o Windows; instância única |
| Processo do Core | a casca inicia, supervisiona e encerra o serviço Python; o Core sobrevive à queda da casca |
| Áudio | microfone e alto-falante funcionando no Core iniciado pela casca |
| Integração | tecla de atalho global; WebView2 presente no Windows 10 e 11 |
| Consumo | memória em repouso, tempo de abertura, tamanho do instalador — comparados com a casca QtWebEngine |

**Regra de decisão.** Tauri é adotado se cumprir todos os critérios funcionais e não consumir mais do que a
alternativa. Se falhar em algum, a casca é QtWebEngine e o motivo fica registrado aqui.
**Limite.** Este ambiente compila Rust, mas não executa Windows: a parte que importa só se confirma no CI e no
computador do autor.

## AD-08 — Módulos do Core e regra de dependência

**Decisão.** Os treze módulos da missão, em camadas. Um módulo só importa os de camadas abaixo.

| Camada | Módulos |
|---|---|
| 0 | `core` (configuração, erros, logs, eventos; não importa nenhum outro) |
| 1 | `storage`, `security` |
| 2 | `monitoring`, `platform`, `memory`, `ai_gateway`, `voice`, `communication` |
| 3 | `projects`, `tools`, `intelligence` |
| 4 | `api` (compõe o sistema e expõe HTTP e WebSocket) |

Interfaces não importam o backend: falam só pela API. Um teste lê as importações e falha em qualquer violação
ou ciclo; também proíbe `eval`, `exec`, `os.system`, `shell=True`, `pickle` e qualquer importação do legado.

## AD-09 — Gateway de IA híbrido

**Decisão (diretriz).** Um contrato único de provedor (conversa, fluxo de *tokens*, cancelamento, capacidades)
com provedores locais e remotos atrás dele. O roteador escolhe por política: privacidade do conteúdo,
latência, custo, disponibilidade, capacidade e tamanho de contexto. Conteúdo marcado como privado **não sai do
computador** sem política explícita e consentimento registrado. Cada chamada tem prazo, pode ser cancelada e
gera métricas (latência, tempo até o primeiro *token*, *tokens*, erro). A falha de um provedor aciona o
seguinte da cadeia ou devolve "indisponível" — nunca derruba o sistema.
**Origem.** Perfis, limite de gasto e consentimento vêm do legado (`models/`), portados.

## AD-10 — Autenticação e autorização no servidor

**Decisão.**
- **Toda permissão é conferida no backend**, por rota. Esconder botão não é controle.
- **Core**: um dono local. A casca entra por bilhete de uso único; o navegador local, por código de uso único;
  sessão em *cookie* `HttpOnly`/`SameSite=Strict`, anti-CSRF, conferência de `Origin` e `Host` (modelo já
  especificado em `ULTRON/docs/especificacao/CONTRATO_V1.md`).
- **Portal**: usuários administrativos com papéis; sessões no servidor, revogáveis; senha com `scrypt` da
  biblioteca padrão, sem dependência nova, com N=2^17, r=8, p=1 — o mínimo que fontes secundárias atribuem à
  folha de armazenamento de senhas da OWASP, a conferir na fonte oficial no documento de segurança; bloqueio progressivo por
  tentativas; histórico de ações; recuperação de acesso por *token* de uso único.
- **Nenhuma credencial padrão.** O primeiro administrador é criado por comando no servidor.
- Segredos só em variáveis de ambiente do servidor ou no cofre do sistema; nunca no código, no Git ou no
  JavaScript.
**Consequências.** A matriz de permissões do Portal é entregue na Fase 2 (`docs/security/`), antes das rotas.

## AD-11 — Dados novos em local novo

**Decisão.** A nova versão grava em `%LOCALAPPDATA%\SAFRA`, num banco novo. Os dados do legado
(`%LOCALAPPDATA%\ULTRON`) são **importados**: o banco antigo é aberto só para leitura, a importação gera um
relatório (linhas lidas, importadas e recusadas, por tabela) e pode ser repetida. Nada do legado é movido,
alterado ou apagado. As tabelas do módulo de robótica removido não são importadas; o conteúdo vai para um
arquivo JSON conferido.
**Consequências.** Voltar atrás é trivial: basta abrir o aplicativo antigo, que encontra os dados como deixou.
Substitui a decisão anterior de manter a pasta de dados no lugar.

## AD-12 — Acesso remoto desligado por padrão

**Decisão (diretriz).** O painel operacional só atende o próprio computador. Acesso de outro dispositivo fica
desligado até existirem autenticação, autorização, proteção de dados e TLS, e só então por conexão de saída ou
*proxy* configurado conscientemente. A API do Core nunca escuta fora de 127.0.0.1 por padrão.

## AD-13 — Hospedagem e publicação *(aberta)*

**Decisão parcial.** Três ambientes (desenvolvimento, homologação, produção); tudo reproduzível por contêiner;
PostgreSQL e armazenamento de mídia fora do contêiner da aplicação; HTTPS obrigatório; backup automático com
restauração ensaiada; **nenhuma publicação em produção sem autorização explícita do autor**.
**Em aberto.** O provedor. Será escolhido na Fase 11 comparando, com preços e limites **do momento**:
persistência, suspensão por inatividade, tráfego, backup, custo mensal. Planos gratuitos não são presumidos
adequados.

## AD-14 — Identidade visual e símbolo

**Decisão (diretriz).** Paleta definida (#101114, #191B20, #23262D, #E32636, #8F1725, #F2F2F2, #A6A8AF);
vermelho como acento; só 2D e 2.5D; símbolo abstrato original, sem rosto; sem elementos de obras de terceiros.
O design system especificado em `ULTRON/docs/especificacao/ESPECIFICACAO_DA_INTERFACE.md` continua valendo
para o console e é estendido ao portal (institucional) e ao admin (produtividade).

## AD-15 — Testes

**Decisão (diretriz).** pytest no backend; Vitest nos componentes; Playwright de ponta a ponta. Além dos tipos
habituais: arquitetura, autorização (cada rota, cada papel), migração, publicação, recuperação, desempenho
contra a linha de base. A suíte do legado continua rodando enquanto o legado existir.

## AD-16 — Observabilidade

**Decisão.** Log em JSON Lines com identificador de correlação e mascaramento de segredos; erro da API em
formato único com código estável; métricas com p50, p95 e p99; rota de saúde pública devolve só "no ar" e a
versão.

## AD-17 — Licenciamento *(aberta)*

**Contexto.** O repositório não tem licença. A biblioteca de voz instalada (`piper-tts` 1.8.0) declara
GPL-3.0-or-later. A licença dos modelos de reconhecimento não foi conferida. O portal terá uma página de
**downloads**, isto é, distribuição pública.
**Encaminhamento.** A decisão é do autor e da instituição. Não bloqueia o desenvolvimento. **Bloqueia publicar
qualquer instalador.** O inventário de licenças (`docs/engineering/`) será mantido a partir da Fase 2.

## AD-18 — Idioma

**Decisão.** Identificadores de código, nomes de pacote e de rota em inglês. Documentos, mensagens e interface
em português do Brasil.

## AD-19 — Versão

**Decisão.** O legado termina em 3.0.0. A nova geração começa em 4.0.0 e usa sufixo de desenvolvimento
(`4.0.0.dev0`) até a primeira versão validada.

---

## O que continua valendo do registro anterior

| Anterior | Situação |
|---|---|
| ADR-001 (migração progressiva) | **substituída** por AD-01 |
| ADR-002 (núcleo e interface em processos separados) | vale |
| ADR-003, ADR-004 (API local, contrato único) | valem; o contrato é a base da API do Core |
| ADR-005 (interface compilada versionada no Git) | **revista**: o compilado passa a ser gerado no CI e incluído no instalador |
| ADR-006 (casca em QtWebEngine) | **suspensa** por AD-07 |
| ADR-007, ADR-008 (sessões; toda alteração pelo executor) | valem |
| ADR-009, ADR-010, ADR-011, ADR-012 (sem 3D; vocabulário próprio; Análises e Projetos; Modo Operador) | valem |
| ADR-013 (exportar as tabelas antigas antes de descartar) | vale, agora como parte da importação (AD-11) |
| ADR-014 (troca gradual de identificadores) | **substituída** por AD-11: o código novo nasce com os nomes novos |
| ADR-015 (ativação só por "Safra"; tecla de atalho) | vale |
| ADR-016 (documentos históricos em arquivo legado) | vale; ao final, `ULTRON/` inteiro vira o arquivo legado |
| ADR-017 (TCC reescrito) | vale; o escopo cresce com portal, CMS e gateway de IA |
| ADR-018 (painel local primeiro) | vale (AD-12) |
| ADR-019 a ADR-023 (paleta, tipografia, banco, logs, testes) | valem, com AD-04 no lugar da parte de banco |
| ADR-024 (licença), ADR-026 (tom do assistente) | continuam abertas (AD-17; tom: vale a proposta) |
