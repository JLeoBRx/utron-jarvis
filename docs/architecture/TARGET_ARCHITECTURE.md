# Arquitetura alvo do SAFRA

Data: 14/11/2026. Descreve o destino da reconstrução. O que já existe em código está marcado na seção 9; o
resto é plano. As decisões citadas (AD-nn) estão em `docs/decisions/ARCHITECTURE_DECISIONS.md`.

## 1. Os quatro ambientes e os dois serviços

```
                         COMPUTADOR DO USUÁRIO                              SERVIDOR (internet)
 ┌──────────────────────────────────────────────────────────┐   ┌────────────────────────────────────────┐
 │  A. Aplicativo desktop        B. Painel operacional      │   │  C. Portal público    D. Painel admin  │
 │     (casca + console)            (console no navegador)  │   │     (visitantes)         (/admin, CMS) │
 │            │                            │                │   │         │                    │         │
 │            └───────── contrato da API do Core ───────────│   │         └── API do Portal ───┘         │
 │                          │  só 127.0.0.1                 │   │              │  HTTPS                  │
 │                 ┌────────▼─────────┐                     │   │     ┌────────▼─────────┐               │
 │                 │   SAFRA CORE     │                     │   │     │  SAFRA PORTAL    │               │
 │                 │  assistente, voz │                     │   │     │ conteúdo, mídia, │               │
 │                 │  memória, tools  │                     │   │     │ downloads, contas│               │
 │                 └────────┬─────────┘                     │   │     └───┬──────────┬───┘               │
 │                    SQLite (dados privados)               │   │   PostgreSQL    mídia                  │
 └──────────────────────────────────────────────────────────┘   └────────────────────────────────────────┘
        │ saída, opcional: provedores de IA remotos
```

| Ambiente | Quem usa | Serviço | Dados |
|---|---|---|---|
| A. Aplicativo desktop | o dono do computador | Core | privados, locais |
| B. Painel operacional | o dono, no navegador do próprio computador | Core | os mesmos |
| C. Portal público | qualquer visitante | Portal | só conteúdo publicado |
| D. Painel administrativo | administradores com papel | Portal | conteúdo, mídia, versões, contas administrativas |

**Não há ligação entre os dois serviços.** O Portal não tem rota, credencial nem rede para chegar ao Core. A
única coisa que vai do autor para o Portal é conteúdo institucional, digitado no painel administrativo.

## 2. Estrutura de pastas

```
/                         raiz do repositório = a nova plataforma
├── backend/
│   ├── pyproject.toml
│   ├── src/
│   │   ├── safra/                  SAFRA Core (13 módulos, seção 3)
│   │   └── safra_portal/           SAFRA Portal (seção 5)
│   └── tests/
├── frontend/
│   ├── packages/
│   │   ├── design-system/          tokens, componentes, símbolo
│   │   └── api-client/             tipos gerados do OpenAPI, cliente HTTP e de eventos
│   └── apps/
│       ├── console/                interface operacional (desktop e navegador)
│       └── admin/                  painel administrativo do portal
├── desktop/                        casca do Windows (AD-07)
├── infra/                          contêineres, composição local, proxy, scripts de publicação
├── scripts/                        medição, importação do legado, utilitários
├── docs/
│   ├── architecture/  engineering/  security/  performance/  migration/
│   ├── deployment/    user-guide/   academic/  decisions/
└── ULTRON/                         LEGADO — preservado, não importado pela nova versão
```

As páginas públicas do portal ficam em `backend/src/safra_portal/` se a AD-06 for confirmada como proposta, ou
em `frontend/apps/portal/` se a escolha for React com renderização no servidor.

## 3. SAFRA Core: módulos

| Módulo | Responsabilidade | Não faz |
|---|---|---|
| `core` | configuração validada, erros com código, logs estruturados, eventos, relógio e identificadores | não importa nenhum outro módulo |
| `storage` | motor do banco, migrações versionadas, backup e restauração, importação do legado | não conhece regras de negócio |
| `security` | senhas, *tokens*, sessões, papéis e permissões, limite de tentativas, políticas de ferramentas, cofre de credenciais | não executa ferramentas |
| `monitoring` | saúde dos componentes, métricas com percentis, histórico de atividades, diagnóstico | não decide nada |
| `platform` | Windows: instância única, início automático, tecla de atalho, avisos, caminhos | não tem interface |
| `memory` | memórias, memória pessoal, lembretes, grafo, recuperação para o contexto, conversas | não chama modelos diretamente |
| `ai_gateway` | contrato de provedor, provedores locais e remotos, roteamento, *fallback*, prazo, cancelamento, consumo | não guarda conversas |
| `voice` | captura, reconhecimento, ativação, síntese, prosódia, nível de áudio, diagnóstico | não interpreta o pedido |
| `communication` | modelos do contrato, catálogo de eventos, ponte do barramento para assinantes | não tem rotas |
| `projects` | projetos, notas, vínculos, contexto ativo | — |
| `tools` | ferramentas, registro, executor único, verificação, recuperação | não decide permissões (pede a `security`) |
| `intelligence` | intenção, orquestração, planejamento, raciocínio, análises, identidade e tom | não acessa provedores sem o gateway |
| `api` | compõe o sistema; rotas HTTP, WebSocket, sessões | não contém regra de negócio |

Camadas e regra de dependência: AD-08. Uma interface nunca executa operação privilegiada: ela pede à API, que
passa pelo executor e pelas políticas.

## 4. Fluxos principais do Core

**Pedido de texto.** Interface → `POST /api/v1/commands` → `intelligence` (intenção por regras; se não houver,
`ai_gateway`) → plano → `tools` (executor: valida, consulta `security`, pede confirmação se preciso, executa
com prazo, verifica) → resposta com procedência → evento `response.ready` → interface.

**Pedido de voz.** `voice` (ativação por "Safra" ou tecla de atalho → reconhecimento) → o mesmo caminho do
texto → síntese → nível de áudio publicado para o símbolo.

**Chamada a modelo.** `intelligence` → `ai_gateway`: classifica a privacidade do conteúdo, escolhe o provedor
pela política, aplica prazo, transmite os *tokens* em fluxo, mede; se falhar, tenta o próximo da cadeia ou
devolve "indisponível".

**Inicialização em etapas.** (1) configuração, log, banco; (2) API no ar e interface utilizável; (3) em
segundo plano, memória e ferramentas; (4) sob demanda, voz e modelos locais. A interface mostra o estado real
de cada etapa.

## 5. SAFRA Portal

| Parte | Responsabilidade |
|---|---|
| `content` | páginas, notícias, atualizações, artigos, funcionalidades, perguntas frequentes, documentação pública, *links*, contato; rascunho, publicação, despublicação, agendamento, histórico de versões |
| `homepage` | título, seções, ordem, destaques, rodapé — configuráveis |
| `media` | envio com validação de tipo real e tamanho, nome seguro gerado no servidor, texto alternativo, categorias, uso |
| `downloads` | versões, plataforma, canal, notas, arquivo com resumo SHA-256 |
| `accounts` | administradores, papéis, sessões, histórico de ações, bloqueio por tentativas, recuperação de acesso |
| `public` | páginas e rotas públicas: **só leem conteúdo publicado** |
| `admin_api` | rotas administrativas: toda rota exige sessão e permissão |

### 5.1 Separação entre público e privado

| Barreira | Como |
|---|---|
| Física | o Portal roda noutra máquina e noutro banco; não existe rota para o Core |
| De código | `safra_portal` só importa a camada de base; conferido por teste |
| De dados | as rotas públicas consultam por uma única função de repositório, que filtra "publicado e dentro da data" |
| De autorização | cada rota administrativa declara a permissão exigida; um teste percorre todas as rotas com cada papel e sem sessão |
| De conteúdo | texto digitado no CMS é higienizado no servidor antes de gravar e ao renderizar; arquivos enviados nunca são executados nem servidos com tipo adivinhado |

### 5.2 Papéis (proposta inicial; a matriz completa vai para `docs/security/`)

| Papel | Pode |
|---|---|
| Proprietário | tudo, inclusive contas e papéis |
| Administrador | conteúdo, mídia, página inicial, downloads; não gerencia proprietários |
| Editor | criar, editar e publicar conteúdo e mídia |
| Autor | criar e editar rascunhos; não publica |

## 6. Modelo de dados (visão geral)

| Serviço | Entidades |
|---|---|
| Core | configurações · conversas, mensagens · memórias (fatos, episódios, procedimentos, preferências) · memória pessoal, lembretes · projetos, notas, vínculos · ferramentas, execuções, autorizações · provedores, consumo · atividades, auditoria · sessões locais |
| Portal | usuários, papéis, permissões, sessões · páginas, revisões · notícias, artigos, perguntas frequentes · página inicial · mídia · downloads, versões · histórico de publicação · histórico de ações |

Os dois conjuntos nunca compartilham banco. O modelo detalhado, com diagramas, é entregue na Fase 2.

## 7. Segurança

| Tema | Core | Portal |
|---|---|---|
| Exposição de rede | só 127.0.0.1 | HTTPS atrás de *proxy* |
| Identidade | bilhete (casca), código de uso único (navegador local) | usuário e senha, sessão no servidor |
| Autorização | executor e políticas de ferramenta; escopo por origem da sessão | papéis e permissões por rota |
| Entrada | modelos tipados; limites de tamanho e frequência | idem, mais higienização de conteúdo e validação de envio de arquivos |
| Segredos | cofre do sistema | variáveis de ambiente do servidor |
| Registro | atividades e auditoria | histórico de ações administrativas |
| Proibições | sem shell, `eval`, `exec`, `pickle`; nada contorna o UAC | sem credencial padrão; sem rota administrativa sem sessão |

O modelo de ameaças do Portal (envio de arquivos, conteúdo malicioso, força bruta, CSRF, enumeração de
contas, acesso a rascunhos) é entregue em `docs/security/` antes das rotas administrativas.

## 8. Desempenho equilibrado

| Princípio | Aplicação |
|---|---|
| Abrir primeiro, carregar depois | a API e a interface sobem antes da voz e dos modelos |
| Sob demanda | voz, modelos locais e ferramentas do Windows só carregam quando usados |
| Eventos em vez de sondagem | a interface recebe eventos; sensores periódicos do legado não são portados como estavam |
| Limites explícitos | concorrência, prazo e cancelamento em toda chamada a modelo e a ferramenta |
| Cache com dono | por domínio, com tamanho e validade definidos |
| Medir sempre | o mesmo instrumento da linha de base, repetido a cada fase que mexe no caminho crítico |

## 9. O que já existe em código

| Parte | Situação em 14/11/2026 |
|---|---|
| Estrutura de pastas e documentação | criada |
| `backend/`: `core` (configuração, erros, logs), `storage` (motor, migrações, backup), `security` (senhas e *tokens*), `monitoring` (saúde), `api` (aplicação base e rota de saúde) | **implementada e testada** — ver `backend/README.md` |
| Demais módulos do Core | só o pacote e a descrição da responsabilidade |
| Portal, interfaces, casca, infraestrutura | planejados |

Nada disso foi validado em ambiente real.
