# Registro de Decisões Técnicas do SAFRA

Cada decisão tem contexto, o que foi decidido, consequências e situação. Uma decisão só muda por outra
decisão registrada aqui, que cite a anterior. Base: auditoria de 13/11/2026
(`../technical/AUDITORIA_TRANSFORMACAO_SAFRA.md`) e aprovação do autor na mesma data, com sete direcionamentos.

Situações possíveis: **aprovada** (pelo autor), **derivada** (consequência técnica de uma aprovada, tomada na
especificação e sujeita a veto), **aberta** (precisa de decisão do autor), **adiada**, **rejeitada**.

| # | Decisão | Situação |
|---|---|---|
| ADR-001 | Reconstrução progressiva, sem reescrita integral | aprovada |
| ADR-002 | Dois processos: núcleo e casca do desktop | aprovada |
| ADR-003 | API local com FastAPI, só em 127.0.0.1 | aprovada |
| ADR-004 | Contrato único v1, independente do transporte | aprovada |
| ADR-005 | Uma interface em React + TypeScript; compilado versionado | aprovada / derivada |
| ADR-006 | Casca em QtWebEngine; Tauri adiado; Electron rejeitado | aprovada |
| ADR-007 | Autenticação por bilhete, código de uso único e sessão | derivada |
| ADR-008 | Toda alteração passa pelo executor único; sem rota genérica de execução | derivada |
| ADR-009 | Experiência 2D/2.5D; símbolo abstrato; sem avatar e sem 3D | aprovada |
| ADR-010 | Vocabulário próprio do SAFRA | aprovada (nomes: derivada) |
| ADR-011 | Motor de Análises e domínio Projetos preservam a função da antiga TARDIS | aprovada |
| ADR-012 | Modo Operador preserva o perfil de autonomia do antigo Protocolo ULTRON | aprovada |
| ADR-013 | Tabelas do NOCTARIO: exportar, conferir e só então remover | aprovada |
| ADR-014 | Identificadores internos: troca gradual com camada de compatibilidade | aprovada |
| ADR-015 | Ativação só por "Safra", mais tecla de atalho global | aprovada |
| ADR-016 | Documentos históricos vão para `legado/`; nada é apagado | aprovada |
| ADR-017 | TCC reescrito para o novo escopo; versão 1 arquivada | aprovada |
| ADR-018 | Painel web: local primeiro, responsivo, acesso externo depois | aprovada |
| ADR-019 | Paleta definida pelo autor, mais tons derivados para acessibilidade | aprovada / derivada |
| ADR-020 | Tipografia, ícones e gráficos: recursos livres, embutidos, sem CDN | derivada |
| ADR-021 | Um banco SQLite; migrações com backup; histórico não é reescrito | derivada |
| ADR-022 | Logs estruturados, erros centralizados, identificador de correlação | derivada |
| ADR-023 | Estratégia de testes e regra para retirar testes | derivada |
| ADR-024 | Licenciamento do projeto e das dependências | **aberta** |
| ADR-025 | Modelos e pacote fora do Git; nome do repositório | aprovada (execução condicionada) |
| ADR-026 | Tom e tratamento do assistente | **aberta** (proposta) |
| ADR-027 | Alternativas adiadas ou rejeitadas | derivada |

---

## ADR-001 — Reconstrução progressiva, sem reescrita integral

**Contexto.** São 46 mil linhas e 475 testes que funcionam. A missão proíbe reescrita integral sem justificativa
e exige o repositório executável a cada etapa.
**Decisão.** A nova estrutura nasce ao lado da antiga e a substitui parte por parte. Código novo (API, contratos,
projetos, casca, interface) nasce no pacote `safra/`; o código existente muda de lugar domínio por domínio,
deixando no caminho antigo um módulo de compatibilidade. A interface antiga só é removida depois de a nova ter
paridade conferida item a item.
**Consequências.** Por algum tempo convivem duas interfaces e dois nomes de pacote. Cada etapa é pequena,
testável e reversível.

## ADR-002 — Dois processos: núcleo e casca do desktop

**Contexto.** Hoje interface e núcleo são um processo; uma falha nativa da interface encerra tudo.
**Decisão.** O **núcleo** (todos os domínios, a voz, o banco e a API) é um processo; a **casca** (janela, bandeja,
janela compacta) é outro. O núcleo inicia a casca e a reabre se ela falhar (até 3 vezes em 5 minutos); a casca
detecta a queda do núcleo, informa e oferece reiniciá-lo. O modo console continua sendo o núcleo sem casca.
**Consequências.** Atende "uma falha de interface não derruba o núcleo" de forma verificável por teste.
Custo: sequência de inicialização mais longa, porta local e autenticação entre processos.

## ADR-003 — API local com FastAPI, só em 127.0.0.1

**Contexto.** A interface chama 11 pacotes diretamente; não há contrato.
**Decisão.** FastAPI servido por uvicorn numa *thread* própria do núcleo, com laço assíncrono próprio. Escuta
**apenas** em 127.0.0.1. Porta inicial 47800, com alternativas até 47809 e, por fim, porta livre escolhida pelo
sistema; a porta em uso fica em `run/nucleo.json`. A API também entrega os arquivos da interface compilada.
**Consequências.** Esquema OpenAPI gerado do código, validação de entradas e tipos para a interface. Dependências
novas: `fastapi`, `uvicorn`, `pydantic`. O acesso direto pela rede local **não** é oferecido (ADR-018).

## ADR-004 — Contrato único v1, independente do transporte

**Contexto.** O site da ORBE usa um protocolo próprio; a missão exige os mesmos contratos no desktop e na web.
**Decisão.** Um contrato versionado (`CONTRATO_V1.md`): pedidos e consultas por HTTP, eventos por WebSocket. As
funções que atendem o contrato não dependem do transporte, para que o retransmissor remoto as acione depois.
Dentro da versão 1 só há mudanças aditivas. Um teste confere o esquema gerado contra o contrato.
**Consequências.** Desktop, painel local e, mais tarde, painel remoto usam o mesmo código de interface.

## ADR-005 — Uma interface em React + TypeScript; compilado versionado

**Decisão.** React + TypeScript, Vite para compilar, tipos gerados do esquema da API. Testes de componente com
Vitest e de ponta a ponta com Playwright.
**Derivada.** A interface compilada é **versionada no repositório** (`safra/api/static/`), e o CI recompila e
compara. Motivo: quem atualiza por `git pull` ou pelo ZIP não precisa instalar Node.
**Consequências.** Node passa a ser ferramenta de desenvolvimento e de CI, nunca de quem usa. Arquivo de trava
(`package-lock.json`) e `npm ci` obrigatórios.

## ADR-006 — Casca em QtWebEngine; Tauri adiado; Electron rejeitado

**Decisão.** A casca é PySide6 + QtWebEngine, fina: abre a interface servida pela API e cuida de janela, bandeja e
janela compacta. O código de bandeja, início automático e instância única é reaproveitado.
**Adiado.** Tauri será reavaliado quando houver necessidade de instalador e atualização automática; a casca fina
torna essa troca barata.
**Rejeitado.** Electron: segundo ambiente de execução e mais superfície de ataque, sem vantagem sobre as outras.

## ADR-007 — Autenticação por bilhete, código de uso único e sessão

**Contexto.** Qualquer programa ou página aberta no navegador alcança 127.0.0.1.
**Decisão.**
- **Casca**: recebe do núcleo, pela entrada padrão do processo, um bilhete de uso único (32 bytes, 30 s). Troca-o
  por uma sessão.
- **Navegador local**: entra com um código de uso único (60 s) gerado pelo núcleo — embutido no endereço quando
  o usuário pede "abrir o painel no navegador", ou digitado a partir do que a casca mostra.
- **Sessão**: *cookie* `safra_sessao` (`HttpOnly`, `SameSite=Strict`), mais um valor anti-CSRF exigido no
  cabeçalho `X-SAFRA-CSRF` em todo pedido que altera algo. Sessões são listadas e revogáveis.
- Todo pedido confere `Origin` e `Host` (defesa contra páginas de terceiros e *DNS rebinding*). CORS fechado.
- Limite de tentativas nas rotas de entrada.
**Consequências.** Nenhum segredo vai para arquivo nem para o JavaScript. O mesmo modelo serve ao acesso remoto
futuro (pareamento confirmado no computador).

## ADR-008 — Toda alteração passa pelo executor único

**Contexto.** As regras de segurança em vigor proíbem execução arbitrária pela web e a duplicação do núcleo.
**Decisão.** Rotas que alteram dados ou agem no computador são mapeadas, uma a uma, para habilidades de uma
lista fixa, executadas pelo executor de sempre (permissões, confirmação, verificação, auditoria). Pedidos em
linguagem natural entram por `core.submit`. **Não existe** rota para executar uma habilidade qualquer com
argumentos livres, nem rota para SQL, terminal ou Ollama.
**Consequências.** A API não tem mais poder do que a interface atual. Confirmações sensíveis só são aceitas
da janela do SAFRA (sessão `desktop`), nunca do navegador.

## ADR-009 — Experiência 2D/2.5D; símbolo abstrato

**Decisão.** Saem o holograma humanoide, o avatar 2D com rosto, a cena 3D e a biblioteca three.js. O assistente
passa a ser representado por um símbolo abstrato original, em SVG/*canvas*, com profundidade simulada por
camadas. Os estados do símbolo vêm só do estado real do núcleo. A análise de energia do áudio (hoje parte da
sincronização labial) é mantida para o símbolo reagir à voz.
**Consequências.** A interface deixa de depender de WebGL e de GPU. Os perfis de qualidade 3D e a reserva 2D
deixam de existir; fica uma opção de movimento reduzido.

## ADR-010 — Vocabulário próprio do SAFRA

**Decisão.** Nomes em português, descritivos, sem referência a obras de terceiros.

| Antes | Depois |
|---|---|
| JARVIS (nome público) | **SAFRA** — "Plataforma Inteligente Integrada" |
| holograma, avatar, ORBE | **Símbolo** |
| TARDIS (motor de análise) | **Análises** (`intelligence/analysis`) |
| memória de projeto da TARDIS | **Projetos** (`projects`) |
| página TARDIS / "segundo cérebro" | **Memória** (memória pessoal) |
| sala de controle, painéis 3D | **Central de Comando** |
| Protocolo ULTRON, `ULTRON_OPERATOR` | **Modo Operador** |
| tecla de emergência do ULTRON | **Parada de emergência** |
| JARVIS WEB ORB | **Painel SAFRA** |
| gateway da ORBE, "matriz-mãe" | **Retransmissor**, "computador principal" |
| HUD | **interface** |

Habilidades: `tardis.consult` → `analysis.consult`; `tardis.note` → `projects.note`. Eventos:
`TARDIS_TASK_*` → `ANALYSIS_TASK_*`; `PERSONA_CHANGED` → `OPERATOR_CHANGED`. Frases de voz com "TARDIS" deixam
de ser reconhecidas; passam a valer "Safra, analise…", "Safra, planeje…", "anote no projeto X que…".
**Consequências.** Referências guardadas (automações, procedimentos, autorizações permanentes) continuam
funcionando por uma tabela de apelidos lida na carga (ADR-014).

## ADR-011 — Análises e Projetos preservam a função da antiga TARDIS

**Decisão.** Ficam o motor de tarefas (fila, prazos, cancelamento, persistência), os cinco analisadores
determinísticos e as notas de projeto, com os nomes da ADR-010. Saem a sala de controle, a cabine, os sons
temáticos e a vista "Arquivo" (substituída pela página Memória). Os 37 testes de lógica do motor são mantidos e
renomeados. O domínio **Projetos** ganha a entidade projeto, que liga notas, registros de memória, tarefas de
análise e atividades.
**Consequências.** Tabela `tardis_tasks` renomeada para `analysis_tasks` (migração v8). A pasta
`sons_tardis`, se existir no computador do usuário, não é tocada.

## ADR-012 — Modo Operador preserva o perfil de autonomia

**Decisão.** Sai a persona (nome, voz, aparência, ativação ocasional e demonstração). Fica o perfil de
permissões: autonomia ampliada para rotinas que o usuário liberou, com os mesmos pisos (categorias bloqueadas
continuam bloqueadas; apagar dados, risco alto, envio para fora e ações administrativas sempre pedem
confirmação). O Modo Operador é ligado só pelo usuário no computador principal, tem prazo, aparece na tela
com rótulo permanente e é encerrado pela parada de emergência.
**Justificativa da retirada da ativação ocasional.** Elevar a autonomia ao acaso é teatro de persona e não tem
função; removê-la reduz risco.
**Consequências.** Configurações `ultron_*` migram para `operator_*` e `emergency_key`; cinco chaves deixam de
existir. Os testes que cobrem o comportamento das permissões sob o perfil são mantidos; os da persona saem.

## ADR-013 — Tabelas do NOCTARIO: exportar, conferir e só então remover

**Decisão (direcionamento 2).** Na migração v8, antes de qualquer alteração: (1) backup completo e verificado
do banco; (2) exportação de **todas** as linhas de `noctario_runs` e `noctario_ops` para
`backups/legado/noctario_<data>.json`, com as amostras binárias em base64 e um resumo SHA-256; (3) releitura do
arquivo e conferência da contagem de linhas e do resumo; (4) só então `DROP TABLE`. Se qualquer passo falhar, a
migração é interrompida e as tabelas ficam como estão.
**Consequências.** Nenhum dado se perde: fica no backup completo e no arquivo exportado. A exportação nunca é
apagada pela rotação de backups.

## ADR-014 — Identificadores internos: troca gradual com compatibilidade

**Decisão (direcionamento 3).** Ordem e regra de cada troca:

| Identificador | Destino | Compatibilidade |
|---|---|---|
| pacote `ultron` | `safra` | módulos antigos viram apelidos dos novos; `ultron.plugins`, `ultron.skills.base` e `ultron.models.ollama_client` ficam como interface de plugins até uma versão maior anunciada |
| variáveis `JARVIS_*`, `ULTRON_*` | `SAFRA_*` | as antigas continuam lidas, com aviso único no log |
| serviço "JARVIS" no cofre | "SAFRA" | lê o novo; se não houver, lê o antigo, copia, confere e passa a usar o novo; o antigo não é apagado |
| valor "JARVIS"/"ULTRON" no início automático | "SAFRA" | o valor novo é criado; o antigo só é removido se apontar para esta instalação |
| `jarvis.pid`, `jarvis.modo`, trava `ULTRON.NeuralCore` | `safra.*`, `SAFRA.Nucleo` | durante a transição as duas travas são adquiridas, para que versão antiga e nova não rodem juntas |
| `Imagens\JARVIS` | `Imagens\SAFRA` | só capturas novas; a pasta antiga não é tocada |
| scripts `*_JARVIS.bat`, `*_ULTRON.bat` | `*_SAFRA.bat` | viram redirecionadores de três linhas por um ciclo; saem depois da validação no Windows real |
| `jarvis_gateway`, *cookies* `jarvis_*` | `safra_gateway`, `safra_*` | troca direta: o retransmissor nunca foi implantado |
| pasta `ULTRON/` do repositório | nome novo | um único commit de renomeação, ao final |
| `%LOCALAPPDATA%\ULTRON`, `ultron.sqlite3` | `%LOCALAPPDATA%\SAFRA`, `safra.sqlite3` | **só ao final, por cópia verificada, comando explícito e com a pasta antiga preservada**; até lá nada muda de lugar |

**Consequências.** Um teste de identidade lista onde cada nome antigo ainda é permitido e falha se aparecer
fora dali; a lista encolhe a cada etapa.

## ADR-015 — Ativação só por "Safra", mais tecla de atalho global

**Decisão (direcionamento 4).** "Jarvis" sai das palavras de ativação, das formas padrão e da calibração. A
migração de configurações v3 → v4 retira as formas derivadas de "jarvis" (com cópia de segurança). Entra uma
**tecla de atalho global** (padrão `Ctrl+Alt+Espaço`, configurável) que abre uma janela de escuta, igual à
palavra de ativação; pressionar de novo ou `Esc` cancela. É registrada pelo núcleo (domínio Platform) com a API
`RegisterHotKey` do Windows, sem biblioteca nova e sem captura global de teclado. Se a combinação estiver
ocupada, o diagnóstico informa. Continuam o botão de microfone na interface e o texto.
**Contexto medido.** Com voz sintética, "Safra" ativou em 2–4 % das frases. A tecla é o caminho confiável até
a medição com voz humana (protocolo PV-01B).
**Consequências.** Fora do Windows a tecla global fica indisponível e isso é declarado.

## ADR-016 — Documentos históricos vão para `legado/`

**Decisão (direcionamento 5).** Pasta `legado/` na raiz do repositório, fora da árvore do produto e fora do
pacote de instalação, com um índice. Os 24 documentos da raiz de `ULTRON/` são movidos com `git mv` (o histórico
acompanha): 15 puramente históricos na Fase 3; os 9 que ainda são manual ou referência em uso só quando o
substituto estiver escrito. Nenhum é apagado.
**Consequências.** O teste de identidade ignora `legado/`.

## ADR-017 — TCC reescrito; versão 1 arquivada

**Decisão (direcionamento 6).** O TCC é reescrito para o escopo novo. A versão entregue em 12/11/2026
(capítulos, exportações, capturas da cena 3D, diagramas 04 e 07, protocolos e resultados PV-04 e PV-05) vai
para `legado/tcc-v1/`. Continuam válidos e são reaproveitados: fundamentação sobre arquitetura, voz, memória e
segurança; referências verificadas pertinentes; protocolos e resultados PV-01, PV-02, PV-03, PV-06 e PV-07.
Protocolos novos: interface web (PV-04 novo), isolamento de falhas (PV-05 novo) e API local — conformidade
com o contrato e latência (PV-08).
**Consequências.** Resultados medidos com a arquitetura antiga serão **refeitos** na nova antes de entrar no
TCC; até lá constam como linha de base, identificados como tal.

## ADR-018 — Painel web: local primeiro, responsivo, acesso externo depois

**Decisão (direcionamento 7).** Nesta migração o painel funciona no navegador do próprio computador. A
interface é responsiva desde o início (de 360 px a telas largas, alvos de toque de 44 px). O contrato já
carrega a origem da sessão (`desktop`, `painel_local`, `remoto`) e as capacidades de cada uma. O acesso de
outro dispositivo é etapa posterior, **pelo retransmissor** e por conexão de saída; a API local nunca escuta
fora de 127.0.0.1.
**Consequências.** Captura de microfone pelo navegador fica fora desta migração.

## ADR-019 — Paleta e *tokens*

**Decisão.** Os sete valores definidos pelo autor são usados sem alteração. Derivados acrescentados:
`vermelho-texto` #EB5E6A (texto vermelho pequeno: 5,7:1 sobre o fundo, 5,2:1 sobre a superfície e 4,6:1 sobre
a superfície elevada), rótulo de botão primário em #FFFFFF (4,6:1 sobre #E32636), e as cores de estado — sucesso, atenção, informação e erro — escolhidas na Fase 4 para
se distinguirem do vermelho da marca também por ícone e texto, nunca só pela cor. Fonte única:
`frontend/src/design/tokens.json`; um teste confere o contraste de todos os pares usados.

## ADR-020 — Tipografia, ícones e gráficos

**Decisão.** Tipografia: Inter (interface) e JetBrains Mono (dados e código), ambas sob SIL Open Font License,
embutidas no pacote. Ícones: conjunto Lucide (licença ISC) mais ícones próprios para o que for específico do
SAFRA. Gráficos: componentes próprios em SVG (linhas, barras, medidores); biblioteca externa só se um gráfico
exigir, com registro aqui. Nada é carregado de CDN.
**Consequências.** As licenças citadas são confirmadas e registradas no Inventário de Licenças antes de os
arquivos entrarem no repositório; se alguma não se confirmar, o recurso é trocado.

## ADR-021 — Um banco SQLite; migrações com backup

**Decisão.** Continua um único banco, aberto só pelo núcleo. Migrações são aditivas ou de renomeação, cada uma
precedida de backup automático verificado. A v8 renomeia `tardis_tasks`, cria as tabelas de Projetos e trata
as tabelas do NOCTARIO (ADR-013). **Linhas históricas não são reescritas**: atividades antigas marcadas com
nomes antigos continuam como foram gravadas, e a interface as mostra com rótulos neutros.
**Consequências.** A trilha de auditoria permanece íntegra.

## ADR-022 — Logs estruturados e erros centralizados

**Decisão.** Log em JSON Lines (`logs/safra.jsonl`, com rotação): horário, nível, componente, evento, mensagem,
identificador de correlação e campos do evento. Segredos são mascarados antes da gravação. O console continua
legível. Erros da API seguem um único formato com código estável, mensagem em português e o identificador de
correlação; nunca expõem rastros internos. O arquivo antigo `ultron.log` não é apagado.

## ADR-023 — Estratégia de testes e regra para retirar testes

**Decisão.** pytest passa a ser o executor (os testes `unittest` rodam sem reescrita). Tipos novos: arquitetura,
contrato, injeção de falhas, identidade, atualização a partir da versão atual. Um teste só é retirado quando o
que ele cobre deixa de existir, e a retirada é listada com justificativa no Relatório de Validação.
Previsão: saem por completo os da cena 3D (24), do avatar (12), da sala 3D (12) e dos sons temáticos (5); os da
sincronização labial (9) e do Protocolo ULTRON (21) são divididos — a parte de energia do áudio e a de
permissões é adaptada, o resto sai.

## ADR-024 — Licenciamento (aberta)

**Contexto.** O repositório não tem licença. `piper-tts` 1.8.0 declara GPL-3.0-or-later e é importado dentro
do processo. PySide6 é LGPL-3.0. As licenças dos modelos Vosk não puderam ser conferidas.
**Opções.** (a) adotar GPL-3.0-or-later para o SAFRA; (b) manter o Piper fora do processo, como programa
separado, e escolher outra licença; (c) trocar o mecanismo de voz.
**Encaminhamento.** A decisão é do autor e da instituição; não bloqueia o desenvolvimento, mas **bloqueia
publicar ou distribuir** o SAFRA. O Inventário de Licenças (Fase 7) traz os dados para decidir.

## ADR-025 — Modelos e pacote fora do Git; nome do repositório

**Decisão.** Os 315 MB de modelos e o ZIP deixam de ser versionados. **Condição:** isso só acontece quando o
instalador e o CI souberem obter os modelos das fontes oficiais e conferi-los por SHA-256, porque os testes de
voz usam esses arquivos. O histórico continua contendo os arquivos antigos. Renomear o repositório é ação do
autor no GitHub.

## ADR-026 — Tom e tratamento do assistente (aberta, proposta)

**Contexto.** As respostas atuais tratam o usuário por "senhor", traço da identidade antiga.
**Proposta.** Tom direto, cordial e profissional, sem vocativo fixo. Uma configuração permite escolher como
ser tratado (nenhum, nome, "senhor", "senhora"); padrão: nenhum.
**Encaminhamento.** Vale a proposta se não houver objeção.

## ADR-027 — Alternativas adiadas ou rejeitadas

| Alternativa | Situação | Motivo |
|---|---|---|
| Electron | rejeitada | ADR-006 |
| Tauri | adiada | reavaliar com instalador e atualização automática |
| Reescrever o retransmissor em FastAPI | adiada | ele só precisa retransmitir o contrato |
| API escutando na rede local | rejeitada | regra: não expor o computador; acesso externo só por conexão de saída |
| Microfone pelo navegador | adiada | depende do acesso externo |
| Manter a interface Qt e fazer outra para a web | rejeitada | duas interfaces e dois design systems |
| Rota genérica para executar habilidades | rejeitada | ADR-008 |
| Reescrever o histórico do Git para apagar nomes antigos | rejeitada | regra de preservação do histórico |
