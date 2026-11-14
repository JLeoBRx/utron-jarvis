# Auditoria do legado

| | |
|---|---|
| Data | 14/11/2026 |
| Commit auditado | `470359f` (branch `claude/adoring-brahmagupta-vcejpt`) |
| O que é "legado" | tudo o que está em `ULTRON/`: o aplicativo atual, chamado SAFRA 3.0.0 desde 12/11/2026 e, antes, JARVIS e ULTRON |
| Ambiente | contêiner Linux 6.18, 4 CPUs lógicas, 15 GB, Python 3.13.18; sem Windows, GPU, microfone, alto-falante ou modelo de linguagem real |
| Regra desta fase | **o legado não foi alterado.** Tudo o que esta fase criou está fora de `ULTRON/` |

Este documento responde aos itens de auditoria da missão. O inventário de funcionalidades, a linha de base de
desempenho, o plano de migração e as decisões estão em documentos próprios (ver `docs/README.md`). A auditoria
anterior, mais detalhada em alguns pontos, continua em `ULTRON/docs/technical/AUDITORIA_TRANSFORMACAO_SAFRA.md`.

## 1. Diagnóstico em uma página

- **O legado funciona e é bem testado**: 475 testes automatizados, 0 falhas (seção 7).
- **É um monólito de um processo**: núcleo, voz, memória e interface Qt no mesmo processo Python; sem API.
- **A lógica de negócio é sólida e vale ser portada**: executor único com permissões e verificação, memória
  com recusa de segredos, regras de intenção em português, cadeia de voz diagnosticável, backup verificado.
- **A interface e a identidade não servem à nova missão**: avatar humanoide 3D e 2D com rosto, ambiente
  temático de uma franquia, persona com nome de personagem. São cerca de 19 mil linhas que não serão portadas.
- **Faltam por completo**: API, autenticação de usuários, portal público, CMS, gateway de IA com contrato
  próprio, infraestrutura de publicação, banco para uso concorrente.
- **Conclusão**: reconstrução integral da arquitetura e das interfaces, com **porte** (reimplementação
  guiada pelos testes existentes) da lógica que funciona. O legado fica intacto e executável até a nova versão
  ser validada.

## 2. Linguagens, frameworks e ferramentas

| Camada | Tecnologia | Observação |
|---|---|---|
| Linguagem | Python 3.11 (instalação) e 3.13 (testado) | 206 módulos, 46.364 linhas em `ULTRON/ultron/` |
| Interface | PySide6 6.8 (Qt Widgets) e QtWebEngine | 35 módulos, 14.647 linhas |
| Cena 3D | HTML, CSS, JavaScript sem framework; three.js r170 embutido | 4.517 linhas próprias |
| Voz | Vosk (reconhecimento), Piper (síntese), SAPI via `pyttsx3` (reserva), `sounddevice` | modelos em `ULTRON/assets/` (315 MB, versionados no Git) |
| IA | Ollama (local, HTTP) e OpenAI (opcional), clientes próprios sobre `urllib` | sem SDK de provedor |
| Persistência | SQLite (WAL), `sqlite3` da biblioteca padrão, migrações escritas à mão (v1–v7) | 27 tabelas |
| Windows | `pywin32`, `pywinauto`, `pycaw`, `comtypes`, `keyring`, `pyautogui`, `send2trash`, `mss`, `Pillow` | importações protegidas: cada função diz o que falta |
| Acesso remoto | agente por WebSocket de saída (`websockets`); gateway em aiohttp com Docker e Caddy | nunca implantado |
| Testes | `unittest` com executor próprio (`TEST_JARVIS.py`); pyflakes; compileall | 39 módulos de teste |
| CI | GitHub Actions: Linux (3.11 e 3.13) e Windows (3.11) | `jarvis-validation.yml` |
| Empacotamento | `tools/build_release.py` gera um ZIP validado; instalação por `.bat` com `.venv` | sem instalador, sem atualização automática |
| Documentos | Markdown; pandoc, python-docx e Playwright para gerar DOCX e PDF; Mermaid para diagramas | |

Licenças das dependências instaladas neste ambiente estão na auditoria anterior (§3.2). Dois pontos pendentes:
`piper-tts` 1.8.0 declara **GPL-3.0-or-later**, e o repositório **não tem arquivo de licença**.

## 3. Módulos

| Pacote | Arq. | Linhas | Responsabilidade | Avaliação |
|---|---:|---:|---|---|
| `core` | 9 | 3.312 | barramento de eventos, estado, ciclo de vida, *workers*, orquestrador, composição (`neural_core.py`) | sólido; composição grande demais (1.112 linhas, 62 métodos) |
| `config` | 4 | 688 | configurações validadas (119 chaves), caminhos, migração | sólido |
| `cognition` | 9 | 1.759 | intenção por regras, raciocínio, planejamento, procedência, objetivos | sólido; `intent_engine` é uma classe de 685 linhas |
| `models` | 6 | 1.536 | clientes Ollama e OpenAI, perfis, roteamento, limite de gasto, consentimento | base do futuro gateway de IA |
| `agent` | 6 | 1.089 | executor único, permissões, autorização, verificação, recuperação | **o ativo mais valioso de segurança** |
| `memory`, `graph` | 15 | 1.895 | memórias, recuperação, banco, migrações, backup, grafo | sólido; ciclo `memory` ↔ `graph` |
| `secondbrain` | 9 | 2.663 | memória pessoal, lembretes, busca, análise de datas em português | sólido; `parse` tem 170 linhas |
| `voice`, `audio` | 15 | 3.816 | captura, reconhecimento, palavra de ativação, síntese, prosódia, diagnóstico, sons | sólido; ativação por voz com acerto baixo (medido) |
| `skills`, `plugins` | 25 | 4.923 | 102 habilidades em 17 pacotes, registro, plugins | sólido; muitas só verificáveis no Windows |
| `tardis` | 10 | 1.527 | motor de tarefas de análise, analisadores determinísticos, notas de projeto | função útil sob nome e tema de terceiros |
| `perception`, `network` | 23 | 3.605 | sensores de janelas, processos, tela, OCR; inventário passivo da rede | funciona por sondagem periódica |
| `platform`, `privacy`, `health`, `remote` | 16 | 1.751 | Windows, credenciais, instância única, modo privacidade, saúde, agente remoto | sólido |
| `personality`, `proactive`, `imagination`, `world` | 19 | 1.944 | identidade e tom, sugestões, cenários, modelo do mundo | complementar |
| `hud` | 35 | 14.647 | interface Qt, avatar, telas temáticas, cena 3D, persona | **não será portado** |
| raiz | 5 | 1.209 | linha de comando, console, diagnóstico, inicialização | portar a linha de comando |

Fora do pacote: `gateway/` (1.265 linhas), `tests/`, `tools/`, `docs/`, 24 documentos históricos na raiz de
`ULTRON/`, três gerações de scripts `.bat`.

## 4. Problemas de arquitetura

### 4.1 Acoplamento

- **Interface presa ao núcleo**: `hud` importa 11 pacotes e chama objetos internos diretamente
  (`core.settings_manager.update`, `core.authorizations.resolve`, `core.voice.toggle_mic`…). Não há fronteira.
- **`core` é ao mesmo tempo base e topo**: guarda as peças que todos importam (eventos, estado) e a composição
  que importa 22 dos outros 24 pacotes. Resultado: quase todo pacote forma ciclo com `core`.
- **Ciclos reais**: `memory` ↔ `graph`; `config` → `secondbrain` → `memory` → `config`.
- **Três protocolos para a mesma coisa**: chamadas diretas (interface Qt), ponte JavaScript (cena 3D) e
  mensagens próprias (site remoto).

### 4.2 Concentração de responsabilidade

Medido por script sobre `ULTRON/ultron/` (2.953 funções):

| Indicador | Valor |
|---|---|
| Funções com mais de 100 linhas | 10 |
| Funções com mais de 60 linhas | 35 |
| Maior função | `secondbrain/parsing.py: parse`, 170 linhas |
| Classes com mais de 400 linhas | 7 — `HudController` (1.081 linhas, 71 métodos), `NeuralCore` (1.007, 62), `BrainView` (978), `SettingsPage` (874), `NeuralScene` (736), `SecondBrainService` (734), `IntentEngine` (685) |
| Arquivos com mais de 800 linhas | 11, oito deles na interface |

### 4.3 Duplicação

- **Textual: baixa.** Comparando janelas de 10 linhas normalizadas entre arquivos, há **1** bloco repetido
  (entre `cognition/reasoning_engine.py` e `imagination/generation.py`) e nenhum dentro de um mesmo arquivo.
- **Funcional: alta na apresentação.** Três implementações visuais do assistente (Qt 2D, cena 3D, site
  remoto), duas fontes de informação de projeto (notas do motor de análise e registros da memória pessoal),
  três gerações de scripts de instalação e início.

### 4.4 Gargalos e limites medidos

| Ponto | Evidência |
|---|---|
| Ativação por voz | "Safra" ativou em 2–4 % das frases com voz sintética; "Jarvis", 17–18 % (PV-01) |
| Memória por paráfrase | 45 % de acerto entre as 3 primeiras; lembrança indevida em 70 % das perguntas sem resposta (PV-03) |
| Percepção por sondagem | sensores consultados a cada 1 s (janela), 2 s (sistema), 5 s (processos), 10 s (arquivos), 20 s (visão), 30 s (dispositivos e rede) |
| Interface a 60 quadros/s | 24 usos de temporizador Qt; a cena 3D por software rende 5,3 quadros/s no contêiner (PV-04) |
| Tudo carrega na abertura | o núcleo monta todos os componentes ao iniciar; números em `docs/performance/BASELINE.md` |
| Um processo | uma falha nativa da interface encerra o núcleo |
| Banco de um só escritor | adequado ao uso local; **inadequado** a um site público com vários processos |

### 4.5 Lacunas frente à nova missão

| Exigido | No legado |
|---|---|
| Backend independente com API | não existe |
| Usuários, perfis, permissões e sessões | não existe (o sistema é de um usuário local); só o pareamento de dispositivos do gateway |
| Portal público e CMS | não existe |
| Gateway de IA independente de provedor | parcial: roteador, perfis, limite e consentimento existem, sem contrato único de provedor |
| Organização por projetos | parcial |
| Aplicativo instalável e atualização | scripts `.bat`; sem instalador |
| Infraestrutura de publicação | Dockerfile e Caddyfile do gateway; nunca implantados |
| Logs estruturados, métricas p50/p95/p99 | log em texto; métricas internas sem exportação |
| Identidade própria | nomes e temas de terceiros (ver auditoria anterior, §1.4) |

## 5. Dados que precisam ser preservados

Nada disto é apagado ou alterado pela reconstrução. A nova versão **lê** o legado e grava em local novo.

| Dado | Onde (Windows) | Conteúdo | Destino na nova versão |
|---|---|---|---|
| Banco | `%LOCALAPPDATA%\ULTRON\ultron.sqlite3` | 27 tabelas (abaixo) | importado para o banco novo; o arquivo antigo é aberto só para leitura |
| Backups | `…\ULTRON\backups\` | cópias diárias do banco | mantidos onde estão |
| Configurações | `…\ULTRON\settings.json` e cópias `settings.*-backup.json` | 119 chaves | convertidas; chaves sem equivalente ficam registradas |
| Autorizações permanentes | `…\ULTRON\autorizacoes_permanentes.json` | concessões com prazo | **não** importadas: o usuário concede de novo (decisão de segurança) |
| Modelo do mundo | `…\ULTRON\world_model.json` | fatos sobre o ambiente | importado |
| Credenciais | Gerenciador de Credenciais, serviço "JARVIS" | chave da OpenAI, *token* do agente | lidas uma vez e regravadas sob o nome novo; as antigas permanecem |
| Início automático | Registro, `HKCU\…\Run`, valor "JARVIS" | comando de início | o instalador novo cria o seu; o antigo só sai se apontar para a instalação antiga e o usuário confirmar |
| Imagens e exportações | `…\ULTRON\images\`, `exports\`, `Imagens\JARVIS` | arquivos do usuário | não são tocados |
| Plugins do usuário | `…\ULTRON\plugins\` | código Python | não importados automaticamente (interface de plugin muda); listados para o usuário |
| Modelos | `ULTRON\assets\stt\`, `assets\voices\` | Vosk e Piper | reutilizados por cópia ou por caminho configurado |
| Logs | `…\ULTRON\logs\` | texto | mantidos |

### 5.1 Tabelas do banco e o que acontece com cada uma

| Tabelas | Conteúdo | Na nova versão |
|---|---|---|
| `facts`, `preferences`, `episodes`, `procedures`, `session_notes` | memórias semântica, de preferências, episódica e procedural | importadas para o domínio `memory` |
| `sb_records`, `sb_relations`, `sb_history`, `sb_reminders`, `sb_fired`, `sb_notifications` (+ índice `sb_fts`) | memória pessoal, lembretes, histórico | importadas para `memory` (memória pessoal) |
| `goals` | objetivos persistentes | importada para `intelligence` |
| `graph_nodes`, `graph_edges` | grafo de conceitos | importadas para `memory` |
| `automations` | gatilhos de frase para ferramenta | importadas, com os nomes de ferramenta convertidos |
| `activity`, `audit` | histórico de atividades e auditoria | importadas como histórico **somente leitura** |
| `tardis_tasks`, `project_notes` | tarefas de análise e notas de projeto | importadas para `intelligence` (análises) e `projects` |
| `model_usage` | consumo de modelos (só números) | importada para `ai_gateway` |
| `network_devices` | inventário da rede local | importada para `platform` |
| `creations`, `images` | cenários e imagens geradas | importadas se a funcionalidade for mantida (ver inventário) |
| `noctario_runs`, `noctario_ops` | dados de um módulo removido | **não** importadas; exportadas para um arquivo JSON conferido, guardado com os backups |
| `meta`, `schema_version` | controle interno | não se aplicam |

Conversas: o legado não tem tabela de conversas; o histórico de pedidos e respostas está em `activity` e em
`episodes`. A nova versão cria `conversations` e `messages` e importa o que existe como conversas arquivadas.

## 6. Integrações

| Integração | Sentido | Estado no legado |
|---|---|---|
| Ollama (`127.0.0.1:11434`) | saída, local | funcional com servidor simulado; modelo real não testado aqui |
| OpenAI | saída, internet, opcional | funcional com provedor simulado; nunca chamada com chave real |
| Stable Diffusion local (`127.0.0.1:7860`) | saída, local, opcional | não verificada |
| Gateway remoto | saída (WebSocket) | funcional em teste local; nunca implantado |
| Windows (cofre, Registro, bandeja, UI Automation, áudio) | sistema | parte simulada, parte não verificada |
| Rede local (tabela de vizinhos, DNS reverso, SSDP opcional) | passiva | simulada |
| Teste de internet (1.1.1.1:443, 8.8.8.8:53) | saída | conferido por teste |

## 7. Testes

| Item | Valor |
|---|---|
| Módulos de teste | 39 |
| Casos | 475 |
| Última execução completa | 13/11/2026, commit `34c712b`: **475 aprovados, 0 falhas, 1 pulado**, 178,7 s (registro em `ULTRON/docs/research/resultados/linha_de_base_34c712b.txt`) |
| Nova execução nesta auditoria | 14/11/2026, commit `470359f`: **475 aprovados, 0 falhas, 1 pulado**, 154,5 s |
| O teste pulado | cena 3D real; executada à parte em `f1a9e2e`: 24 de 24 |
| CI | execução 64 aprovada em Linux e Windows, commit `f1a9e2e`. Os commits seguintes mudaram só documentos |
| Código de execução desde então | idêntico: `git diff 456fe23 HEAD -- ULTRON/ultron ULTRON/main.py ULTRON/gateway` é vazio |

Cobertura por assunto: núcleo e barramento (22), executor, permissões, segurança, verificação e recuperação
(51), memória e memória pessoal (34), voz (55), inteligência, modelos e planejador (45), interface e cena
(57, um deles pulado sem servidor gráfico), motor de análise (54), plataforma, inicialização e linha de comando
(39), compatibilidade com dados antigos (22), demais (95). A cobertura de linhas **não é medida**.

O que os testes **não** cobrem: Windows real, microfone, alto-falante, GPU, modelo de linguagem real, chave
real de provedor, uso prolongado além de 30 minutos.

## 8. O que será reimplementado, e como

"Reconstrução integral" não significa descartar o que foi verificado. O critério:

| Tipo de código | Tratamento |
|---|---|
| Regra de negócio com teste (executor, permissões, autorização, memória, intenção, prosódia, backup, análise de datas) | **portar**: reescrever dentro dos novos limites de módulo, levando os testes junto como especificação executável |
| Integração com serviço externo (Ollama, OpenAI, Vosk, Piper) | **portar atrás de interface nova** (gateway de IA, provedores de voz) |
| Integração com o Windows | **portar por último**, uma habilidade por vez, com teste no Windows |
| Interface, cena, avatar, telas temáticas, persona | **não portar**: refeito do zero em React |
| Protocolos entre interface e núcleo | **não portar**: substituídos pela API |
| Scripts de instalação | **substituir** por instalador |

O destino de cada funcionalidade está em `docs/engineering/FEATURE_INVENTORY.md`.

## 9. Limites desta auditoria

- Nada foi executado em Windows; nenhum dado real de usuário foi lido (só bancos de teste).
- O conteúdo real das tabelas no computador do autor é desconhecido; a importação é desenhada para qualquer
  conteúdo e será ensaiada com um banco de exemplo.
- Licenças dos modelos Vosk e das bibliotecas só de Windows não foram conferidas.
- A cobertura de linhas dos testes não foi medida.
