# Plano de migração e de entregas

Data: 14/11/2026. Substitui `ULTRON/docs/especificacao/PLANO_DE_MIGRACAO.md`, escrito para uma migração
progressiva. A estratégia agora é reconstrução integral (AD-01), com portal público e painel administrativo.

## 1. Regras

1. **O legado não é alterado.** Fica em `ULTRON/`, executável e com o seu CI, até a nova versão ser validada.
2. **Cada fase termina com** código executável, testes, documentação, decisões registradas, lista de
   pendências e os critérios de aprovação conferidos — ou é declarada "em andamento".
3. **Quatro estados por funcionalidade**, sempre distinguidos: planejada, implementada, testada, validada em
   ambiente real.
4. **Nenhum dado real em teste.** Importação e migração são ensaiadas com bancos de exemplo.
5. **Nenhuma publicação na internet sem autorização explícita.**
6. **Decisão de alto impacto** é apresentada com alternativas antes de ser executada (hoje: AD-02 e AD-06).

## 2. Mapa de riscos

Probabilidade e impacto: B baixa, M média, A alta.

| # | Risco | P | I | Resposta |
|---|---|:-:|:-:|---|
| R1 | **Escopo.** A missão anterior já ocupava o calendário; esta acrescenta portal, CMS, gateway de IA, instalador e infraestrutura | A | A | fases com cortes definidos (seção 6); o caminho crítico do TCC é o Core |
| R2 | Regressão ao portar: a lógica nova diverge da antiga sem ninguém notar | M | A | testes do legado como especificação; comparação lado a lado com o legado em execução |
| R3 | Perda de dados na importação | B | A | banco antigo aberto só para leitura; banco novo em pasta nova; relatório por tabela; ensaio com banco de exemplo |
| R4 | **Superfície de ataque do portal e do CMS** (envio de arquivos, conteúdo malicioso, força bruta, CSRF, rascunhos expostos) | M | A | modelo de ameaças antes das rotas; autorização testada rota a rota e papel a papel; higienização no servidor |
| R5 | Vazamento de dado privado para o lado público | B | A | dois serviços, dois bancos, nenhuma rota entre eles; teste de arquitetura |
| R6 | Tauri não cumpre algum critério no Windows | M | M | prova de conceito cedo; alternativa definida (AD-07) |
| R7 | Hospedagem: plano gratuito insuficiente; custo mensal | M | M | comparação com dados do momento; produção só com autorização |
| R8 | **Licenças impedem distribuir** o instalador pela página de downloads | M | A | inventário de licenças desde a Fase 2; decisão do autor antes da Fase 11 (AD-17) |
| R9 | Executável sem assinatura digital gera alerta do Windows | A | M | registrar o custo do certificado como decisão do autor; publicar o resumo SHA-256 de cada arquivo |
| R10 | Comportamento no Windows só verificável pelo autor | A | M | roteiro de validação com coleta de evidência; o que não foi validado fica declarado |
| R11 | Cadeia de dependências (pip, npm, cargo) | M | M | versões travadas; nenhuma dependência sem justificativa registrada |
| R12 | Desempenho pior do que o legado | M | M | linha de base medida; orçamento por medida (`docs/performance/BASELINE.md` §6) |
| R13 | Ativação por voz continua ruim | A | M | tecla de atalho; avaliação de alternativa de detecção na Fase 6 |
| R14 | Textos legais do portal (privacidade, termos) e dados de contato | M | M | rascunhos são entregues como modelo; a versão final é do autor |
| R15 | Resultados do TCC medidos na arquitetura antiga | certa | M | refazer as medições na nova versão; os antigos entram como linha de base |

## 3. Importação dos dados do legado

| Passo | O que faz | Conferência |
|---|---|---|
| 1 | Localiza a pasta do legado; nada é alterado nela | o banco antigo é aberto em modo só leitura |
| 2 | Cria o banco novo em `%LOCALAPPDATA%\SAFRA`, na versão atual do esquema | migrações aplicadas do zero |
| 3 | Importa tabela a tabela, conforme `docs/architecture/LEGACY_AUDIT.md` §5.1 | contagem de linhas lidas, importadas e recusadas, com o motivo |
| 4 | Exporta para JSON o que não é importado (tabelas do módulo removido) | resumo SHA-256 e contagem relidos do arquivo |
| 5 | Converte as configurações; copia credenciais para o nome novo | chaves sem equivalente listadas, nunca descartadas em silêncio |
| 6 | Grava o relatório da importação | o usuário vê o relatório antes de usar a versão nova |

A importação pode ser repetida: apaga só o banco **novo** e recomeça. Voltar atrás é abrir o aplicativo antigo.

## 4. Fases, entregas e critérios de aprovação

### Fase 1 — Auditoria do legado *(concluída em 14/11/2026)*

| Entrega | Onde |
|---|---|
| Diagnóstico, dados a preservar | `docs/architecture/LEGACY_AUDIT.md` |
| Inventário de funcionalidades | `docs/engineering/FEATURE_INVENTORY.md` |
| Linha de base de desempenho | `docs/performance/BASELINE.md` e `data/` |
| Arquitetura proposta e estrutura de pastas | `docs/architecture/TARGET_ARCHITECTURE.md` |
| Decisões | `docs/decisions/ARCHITECTURE_DECISIONS.md` |
| Riscos, plano, cronograma, critérios | este documento |

**Critérios:** suíte do legado executada e registrada ✔ · medições com ambiente declarado ✔ · nenhuma
alteração em `ULTRON/` ✔ · decisões de alto impacto apresentadas com alternativas ✔.

### Fase 2 — Arquitetura, workspace, Portal e Assistant *(entregue em 15/11/2026; ver relatório)*

O escopo foi ampliado pelo autor em 15/11/2026: além da fundação, a Fase 2 passou a incluir a primeira versão do
Portal (site público e CMS), antes prevista para as Fases 8 e 9, e a prova de conceito da casca do desktop.
Relatório de execução: `docs/engineering/PHASE_2_REPORT.md`.

| Entrega | Situação |
|---|---|
| Workspace e estrutura dos dois serviços (`backend/foundation`, `backend/assistant`, `backend/portal`, `apps/admin`, `packages/design-tokens`, `desktop/`) | feita |
| Isolamento entre os serviços, conferido por teste | feito (15 testes) |
| Modelos de dados e migrações iniciais dos dois serviços | feitos e testados (Assistant: 11 tabelas; Portal: 16) |
| Autenticação, sessões, permissões, auditoria do Portal | feitas e testadas |
| Matriz de permissões, modelo de ameaças, política de autenticação conferida com a OWASP | feitos (`docs/security/`) |
| Site público inicial (12 páginas, SEO, sitemap, 404) | feito e testado |
| Painel administrativo com CMS persistente | feito e testado (unidade, componente e ponta a ponta no navegador) |
| Prova de conceito da casca (Tauri × QtWebEngine) | feita; medida no contêiner e no Windows do CI; falta o Windows do autor |
| Inventário de licenças | feito (`docs/engineering/LICENSE_INVENTORY.md`) |
| CI em Linux e Windows | feito: backend (3.11 e 3.13), PostgreSQL 16, painel, ponta a ponta, prova de conceito no Windows |
| Requisitos atualizados (portal, CMS, gateway de IA) | **pendente** → Fase 3 |
| Composição local com contêineres | **pendente** → Fase 11 |

**Critérios de aceitação da Fase 2 (enunciado do autor) e onde cada um é conferido:** ver o relatório, §4.

### Fases 8 e 9 depois da Fase 2

O que resta do portal e do CMS: agendamento de publicação, galeria pública, gestão das seções de documentação
pública, envio e conferência dos arquivos de instalação (depois da decisão de licença), segundo fator de
autenticação, envio de e-mail para recuperação de acesso, revisão dos textos legais pelo autor.

### Fase 3 — Design system e interfaces

*Entregas:* *tokens* com a paleta definida e teste de contraste; componentes com todos os estados; três
estudos do símbolo para escolha; estruturas do console, do admin e do portal sobre dados simulados e
**identificados como simulados**; prova de conceito da casca (AD-07) em paralelo.
*Critérios:* testes de componente verdes · contraste conferido por teste · capturas em três larguras ·
símbolo escolhido pelo autor · nenhum botão sem ação nas telas entregues.

### Fase 4 — Núcleo e API

*Entregas:* eventos, estado, inicialização em etapas, orquestração, intenção por regras, atividades,
monitoramento; rotas e eventos do contrato; sessões locais; linha de comando como cliente da API.
*Critérios:* testes portados do legado verdes · teste de contrato sobre todas as rotas · comando
determinístico pela API dentro do orçamento · interface abre antes dos serviços opcionais (medido).

### Fase 5 — Gateway de IA

*Entregas:* contrato de provedor; provedor local e provedor remoto; roteador por política; *fallback*; prazo;
cancelamento; fluxo de *tokens*; consumo e métricas; consentimento para nuvem.
*Critérios:* provedor fora do ar não derruba nada (teste) · conteúdo privado não sai sem política (teste) ·
p50, p95, p99 e tempo até o primeiro *token* medidos com provedor simulado e, no computador de referência,
com modelo real.

### Fase 6 — Memória e comunicação

*Entregas:* memórias, memória pessoal, lembretes, conversas, projetos; voz (captura, reconhecimento, síntese,
prosódia, diagnóstico); importador do legado; ponte de eventos.
*Critérios:* testes portados verdes · importação ensaiada com banco de exemplo, relatório conferido ·
recuperação de memória medida de novo (PV-03) · falha da voz não impede gravar e ler memória (teste).

### Fase 7 — Ferramentas e segurança

*Entregas:* executor único, permissões, autorização, verificação, recuperação; ferramentas por grupos; Modo
Operador; cofre de credenciais; modo privacidade.
*Critérios:* PV-06 repetido (toda ação indevida bloqueada) · nenhuma ferramenta alcançável sem política ·
falha de ferramenta não encerra o aplicativo (teste).

### Fase 8 — Portal público

*Entregas:* as páginas da missão, página inicial configurável, só conteúdo publicado, SEO, acessibilidade,
responsividade.
*Critérios:* visitante não alcança rascunho, rota administrativa nem dado interno (testes) · páginas legais
marcadas como modelo até a revisão do autor · textos sem promessa não comprovada.

### Fase 9 — CMS administrativo

*Entregas:* contas, papéis, sessões, histórico; páginas e conteúdos com rascunho, publicação, agendamento,
pré-visualização e histórico; mídia; página inicial; downloads.
*Critérios:* os doze testes obrigatórios da missão · cada rota conferida com cada papel e sem sessão · envio
de arquivo inválido ou malicioso recusado · edição simultânea sem perda silenciosa · nenhuma credencial padrão.

### Fase 10 — Desktop e painel operacional

*Entregas:* casca (bandeja, avisos, início automático, instância única, tecla de atalho, janela compacta);
console ligado à API real; instalador; atualização verificada.
*Critérios:* roteiro de validação executado pelo autor no Windows · encerrar a casca não encerra o Core ·
consumo comparado com a linha de base.

### Fase 11 — Infraestrutura e publicação

*Entregas:* contêineres, composição local, variáveis de ambiente com exemplo sem segredos, CI/CD, scripts de
publicação e de retorno, backup e restauração, guia de domínio, DNS e publicação.
*Critérios:* homologação publicada **com autorização** · restauração de backup ensaiada · retorno de versão
ensaiado · nenhum segredo no repositório (varredura) · produção só com nova autorização.

### Fase 12 — Testes, otimização e documentação

*Entregas:* relatórios de testes e de desempenho, guias de instalação, administração e publicação, inventário
de licenças, documentação acadêmica.
*Critérios:* todas as medidas da linha de base repetidas · cada funcionalidade com o seu estado (planejada,
implementada, testada, validada) · pendências declaradas.

## 5. Cronograma técnico

| Período | Fases | Marco |
|---|---|---|
| novembro/2026 | 1; 2 (fundação) | auditoria aprovada; backend base no CI |
| dezembro/2026 | 2 (conclusão); 3 | design system; símbolo escolhido; prova de conceito da casca |
| janeiro/2027 | 4; 5 | conversa por texto de ponta a ponta pela API |
| fevereiro/2027 | 6 | memória, voz e dados do legado importados |
| março/2027 | 7; 8 | ferramentas com políticas; portal navegável em homologação local |
| abril/2027 | 9; 10 | CMS completo; aplicativo instalável |
| maio/2027 | 11 | homologação na internet (com autorização) |
| junho/2027 | 12 | congelamento de funcionalidades; medições finais |
| julho–agosto/2027 | — | redação do TCC com os resultados medidos |
| setembro/2027 | — | revisão e entrega do texto |
| novembro/2027 | — | defesa (data a confirmar) |

O congelamento passou de maio para junho de 2027 em relação ao plano anterior, por causa do escopo maior. É
um calendário apertado para um autor só.

## 6. Ordem de corte, se atrasar

Corta-se de cima para baixo. O que está em "nunca" não se corta.

1. Itens "Adiar" do inventário (já fora do plano).
2. Agendamento de publicação e galeria no CMS.
3. Acesso remoto ao painel operacional.
4. Atualização automática do aplicativo (fica a manual, verificada).
5. Publicação em produção (fica a homologação).
6. Parte das ferramentas do Windows (ficam as essenciais).

**Nunca:** preservação e importação dos dados · autorização no servidor · separação entre público e privado ·
testes de segurança · medições comparáveis · declarar o que não foi validado.

## 7. O que depende do autor

| Quando | O quê |
|---|---|
| Agora | confirmar AD-02 (dois serviços) e AD-06 (como o portal público é gerado) |
| Fase 3 | escolher o símbolo; aprovar as telas |
| Fase 3 | rodar a prova de conceito da casca no Windows |
| Antes da Fase 9 | revisar a matriz de permissões |
| Antes da Fase 11 | decidir a licença (AD-17), o provedor de hospedagem e o domínio |
| Fase 10 | rodar o roteiro de validação no Windows |
| Fases 8 e 11 | revisar os textos legais; autorizar cada publicação |
