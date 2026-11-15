# Arquitetura alvo do SAFRA

Data: 14/11/2026. Descreve o destino da reconstrução. O que já existe em código está marcado na seção 9; o
resto é plano. Os nomes "Core" e "SAFRA Core" desta versão do texto correspondem ao **SAFRA Assistant**. As decisões citadas (AD-nn) estão em `docs/decisions/ARCHITECTURE_DECISIONS.md`.

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
/                                 raiz do repositório = a nova plataforma
├── backend/
│   ├── foundation/               safra_foundation — biblioteca de base, sem domínio (AD-20)
│   ├── assistant/                safra — SAFRA Assistant (13 módulos, seção 3)
│   ├── portal/                   safra_portal — SAFRA Portal (seção 5)
│   └── requirements.lock         versões com que as suítes passaram
├── apps/
│   └── admin/                    painel administrativo (React + TypeScript), servido pelo Portal em /admin/
├── packages/
│   └── design-tokens/            fonte única da identidade visual (gera o CSS do site e do painel)
├── desktop/                      provas de conceito da casca (Tauri e QtWebEngine) e o instrumento de medição
├── tests/
│   ├── isolation/                os dois serviços não se conhecem
│   └── workspace/                regras do repositório inteiro
├── scripts/                      medição, teste de ponta a ponta, inventário de licenças
├── docs/                         architecture, engineering, security, performance, decisions…
└── ULTRON/                       LEGADO — preservado, não importado pela nova versão
```

Previsto para as próximas fases, e só quando houver conteúdo: `apps/console` (interface operacional),
`apps/desktop` (casca escolhida), `packages/contracts` (tipos do contrato da API do Assistant), `deployment/`
(publicação do Portal e empacotamento do Assistant).

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

| Parte | Situação em 15/11/2026 |
|---|---|
| Biblioteca de base | implementada e testada (62 testes) |
| SAFRA Assistant | configuração, armazenamento (modelo inicial de 11 tabelas), aplicação base, rota de saúde, linha de comando — implementados e testados (32 testes); os demais módulos são só pacotes com a responsabilidade |
| SAFRA Portal | autenticação, permissões, CMS, mídia, site público, linha de comando — implementados e testados (159 testes + 2 sobre PostgreSQL no CI) |
| Painel administrativo | implementado e testado (15 testes de unidade e componente; 15 etapas de ponta a ponta no navegador) |
| Isolamento entre serviços e regras do repositório | 23 testes |
| Casca do desktop | duas provas de conceito; decisão aberta |
| Console operacional, gateway de IA, voz, memória, ferramentas, infraestrutura | planejados |

Nada foi validado no Windows do autor nem publicado na internet.
