# ULTRON — ARCHITECTURE REPORT (Fase 1: Auditoria)

Este documento registra a auditoria completa do projeto legado **J.A.R.V.I.S.** (pasta `JARVIS/`,
commit `53e5a31`) e as decisões que guiaram a construção do **ULTRON**.

A auditoria foi feita lendo o código-fonte integral dos módulos ativos e executando o que era
executável no ambiente de desenvolvimento (Linux, sem Windows, sem microfone e sem Ollama).
Afirmações marcadas como **[VERIFICADO]** foram confirmadas por execução; as demais vêm da
leitura do código.

---

## 1. Visão geral do legado

| Métrica | Valor |
|---|---|
| Arquivos Python (sem cache) | 131 |
| Linhas Python | 26.196 |
| Linhas em cópias de backup (`*BACKUP*`, `*ANTES*`, `_backup_antes_do_copilot/`) | 10.066 (38%) |
| Arquivos `.pyc` versionados no Git | 40 |
| Arquivos README/CHANGELOG de "fases" | 46 |
| Scripts de teste (`test_*.py`, `_testes/`) | 21 |
| Ativos binários | modelo Vosk pequeno (52 MB), modelo Vosk grande (203 MB), voz Piper pt-BR (61 MB), ícones (5,6 MB) |

O projeto cresceu por **acréscimo de fases** (1 a 40). Cada fase adicionou módulos novos
sem remover nem integrar os anteriores. O resultado é um núcleo funcional pequeno, cercado
por camadas paralelas que repetem as mesmas responsabilidades.

---

## 2. Arquitetura atual (como o código realmente executa)

### 2.1 Caminho de execução real

```
START_JARVIS.bat ──► main.py ──► core/runtime.start_gui() ──► core/brain.JarvisBrain.start()   ✗ QUEBRA (ver §4.1)
Abrir_JARVIS.bat ──► jarvis_hud.py main()                                                         ✓ caminho que funciona
autostart (HKCU\Run) ──► jarvis_hud.py --boot                                                     ✓
```

Com `jarvis_hud.py` como entrada efetiva:

```
jarvis_hud.MainWindow (PySide6, thread da UI, timer 16 ms)
 ├── backend.py ............ voz Vosk (thread), TTS pyttsx3/Piper (thread), Ollama, agente com tools,
 │                            memória SQLite, automações, máquina de estados, fila de eventos p/ HUD
 │    └── commands.py ...... roteador por regex em português + 25 ferramentas Windows allowlisted,
 │                            confirmação falada (12 s), verificação pós-condição
 ├── telemetria.py ......... CPU/RAM/GPU/rede/Wi-Fi/Ollama/SQLite em threads próprias
 ├── neural_core.py ........ cérebro de partículas (BrainSim) + ponte para autonomous_core
 └── copilot.py ............ Observador: captura de tela, análise VLM, sugestões, modos
      ├── agent.py, tools.py, memory.py, automation.py, vision.py
      └── neural_core.observe() ─► autonomous_core.py ─► (≈25 módulos de "fases")
```

### 2.2 Módulos por camada

| Camada | Módulos legados | Estado |
|---|---|---|
| Entrada/boot | `main.py`, `core/runtime.py`, `core/brain.py`, `jarvis_hud.main()` | `main.py` quebrado; `jarvis_hud.py` funciona |
| Interface | `jarvis_hud.py` (3.118 linhas), `neural_core.py` (desenho), `neural_hud_engine.py`, `interface/` | Funciona; monolítica |
| Voz | `backend.py` (Vosk + pyttsx3), `voice_engine.py` (Piper), `voice_pipeline.py`, `conversational_engine.py`, `proactive_voice.py` | Núcleo funciona; extras desconectados |
| IA | `backend._ollama_chat`, `agent.py`, `intelligence_router.py`, `dynamic_router.py`, `openai_provider.py` | Duas implementações paralelas do agente |
| Ações | `commands.py`, `tools.py`, `automation.py`, `action_engine.py`, `computer_control.py` | `commands.py` é a autoridade real |
| Percepção | `vision.py`, `copilot.py`, `perception_engine.py`, `autonomous_perception.py`, `active_observation.py`, `multimodal_*.py`, `windows_state_adapter.py`, `context_state.py`, `context_engine.py` | Sobreposição alta |
| Cognição | `autonomous_core.py`, `intent_engine.py`, `intent_engine_v2.py`, `decision_engine.py`, `planner_engine.py`, `planning_graph.py`, `action_selector.py`, `capability_*.py`, `human_in_loop.py`, `permission_engine.py`, `initiative_engine.py` | Muitas camadas sem efeito real no comportamento |
| Execução | `execution_loop.py`, `autonomous_agent_runtime.py`, `verification_engine.py`, `state_verifier.py`, `recovery_engine.py` | Verificação por palavras-chave na resposta do modelo |
| Memória | `memory.py`, `memory_engine.py`, `memory_v2.py`, `learning_engine.py` | Quatro esquemas SQLite independentes |
| Objetivos | `goal_manager.py`, `orchestrator.py`, `mission_manager.py`, `long_running_agent.py`, `autonomous_loop.py` | Três gerenciadores de objetivo/missão |
| World model | `world_model.py` | Apenas em memória; perdido ao fechar |
| Sistema | `telemetria.py`, `autostart.py`, `diagnostico.py`, `app_index.py`, `jarvis_lock*.py` | `app_index.py` nunca é usado |

### 2.3 Dependências externas

| Pacote | Uso | Obrigatório |
|---|---|---|
| PySide6 | HUD | sim |
| vosk, PyAudio | reconhecimento de voz | voz |
| pyttsx3 (+ pywin32) | TTS do Windows | fallback |
| piper-tts, numpy | voz neural | opcional |
| pyautogui, pyperclip | mouse/teclado/captura | ações |
| psutil | telemetria | sim |
| mss, Pillow | captura de tela | visão |
| send2trash | Lixeira | arquivos |
| pytesseract, pywinauto | OCR, UI Automation | opcional (não listado) |

Comunicação com o Ollama via `urllib` (sem SDK). Ferramentas de sistema invocadas com
argumentos fixos: `powershell -EncodedCommand` (scripts fixos), `netsh`, `nvidia-smi`,
`taskkill`, `shutdown`.

---

## 3. Funcionalidades que funcionam (e devem ser preservadas)

Lidas linha a linha; são o patrimônio real do projeto.

1. **Reconhecimento de voz offline (Vosk)** com seleção de microfone por nome/índice/padrão,
   supervisor que reabre o microfone (30 tentativas), espera do Ollama no boot e
   **auto-inicialização do `ollama serve`**.
2. **Medidor real de nível do microfone** (RMS em dB → 0..1).
3. **TTS** com voz neural Piper (pt-BR, offline) e fallback pyttsx3, em thread dedicada com COM.
4. **Agente com ferramentas** via tool-calling do Ollama, limites de passos/ferramentas e cancelamento por voz.
5. **25 ferramentas Windows allowlisted** (`commands.py`): apps, URLs, busca, volume, mídia,
   janelas, mouse, teclado com proteção contra digitação em terminais, rolagem, captura,
   arquivos (abrir/criar/copiar/mover/Lixeira), energia, brilho (WMI), Wi-Fi/Bluetooth/modo avião
   (WinRT), status do sistema. Nunca usa shell com texto livre.
6. **Confirmação falada** para ações destrutivas (“sim/confirmo” em 12 s).
7. **Verificação de pós-condição** por ferramenta (arquivo existe, rádio mudou, brilho mudou).
8. **Roteador rápido em português** (regex) para comandos diretos sem LLM.
9. **Memória SQLite**: fatos, preferências, notas de sessão, auditoria, automações por frase exata.
10. **Filtro de segredos** (senha/token/cpf/cartão) antes de persistir.
11. **Observador** (copilot): modos, exclusão de apps sensíveis, detecção de mudança de tela por
    miniatura, limites de frequência, sugestões, análise sob demanda, captura só em memória.
12. **Visão estruturada opcional**: OCR (pytesseract), UI Automation (pywinauto), localizar e clicar com confirmação.
13. **Telemetria real** (nada simulado; "N/D" quando ausente).
14. **HUD**: orbe compacto, botão flutuante arrastável, bandeja, F11, instância única (mutex), log em arquivo sob `pythonw`.
15. **Autostart** pelo Registro (HKCU\Run) sem administrador, com diagnóstico.
16. **Índice de programas do menu Iniciar** (`app_index.py`) — bem escrito, porém **nunca conectado**.

---

## 4. Problemas encontrados

### 4.1 Defeitos que quebram funcionalidades

| # | Defeito | Evidência | Impacto |
|---|---|---|---|
| D1 | `main.py` (entrada oficial, usada por `START_JARVIS.bat`) chama `core/brain.py`, que invoca `goal_manager.summary()`, `goal_manager.active()`, `goal_manager.activate()`, `goal_manager.checkpoint()` — **nenhuma existe**. | `hasattr(goal_manager, "summary") == False` **[VERIFICADO]** | `START_JARVIS.bat` termina com `AttributeError` antes da HUD abrir. |
| D2 | `copilot.py` usa `autonomous_perception.reset()` / `.observe()` **sem importar o módulo**. | `grep import copilot.py` **[VERIFICADO]** | Todo ciclo de observação que chega à captura gera `NameError`; o Observador nunca analisa a tela. |
| D3 | `config.db_dir()` é chamado por `context_state.py`, `app_index.py`, `orchestrator.py`, mas **não existe** em `config.py`. | **[VERIFICADO]** | Persistência dessas camadas falha silenciosamente (exceção engolida). |
| D4 | `test_fase18.py` falha: `'Plan' object has no attribute 'graph'`. | execução **[VERIFICADO]** | Integração planner ↔ planning_graph foi desfeita sem atualizar o teste. |
| D5 | Modelo Vosk grande marcado como "removido" (sem `HCLG.fst`/`G.carpa`) e nunca usado. | Carregado com sucesso em modo *lookahead* (HCLr+Gr) em 1,1 s, +231 MB **[VERIFICADO]** | Precisão desperdiçada: o modelo pequeno transcreveu "abre o bloco de notas se verifica a rede"; o grande, "abra o bloco de notas e verifique a rede". |
| D6 | Palavra de ativação: o modelo pequeno **não possui "ultron"** no vocabulário; o grande possui. | `words.txt` e testes com voz sintetizada **[VERIFICADO]** | Exige o modelo grande + variantes fonéticas + calibração. |
| D7 | `verification_engine` / `state_verifier` consideram sucesso quando a resposta do modelo contém palavras como "aberto", "criado", "salvo". | leitura | Viola "não afirmar sucesso sem evidência". |
| D8 | `world_model.py`, `goal_manager.py`, `mission_manager.py` vivem só na RAM. | leitura | Nada persiste entre sessões. |

### 4.2 Duplicações

| Responsabilidade | Implementações paralelas |
|---|---|
| Chamada ao Ollama | `backend._ollama_chat`, `agent.chat`, `intelligence_router._ollama` |
| Loop de agente com tools | `backend.ask_agent`, `agent.run` |
| Allowlist de automações | `backend._validate_automation`, `automation._validate_automation` |
| Esquema SQLite | `backend._open_memory_db`, `memory.open_db`, `memory_engine.init`, `memory_v2.init`, `learning_engine._ensure` |
| Prompt de personalidade | `backend.BASE_SYSTEM_PROMPT`, `config.BASE_SYSTEM_PROMPT`, `Jarvis.py` |
| Intenção | `intent_engine`, `intent_engine_v2`, regras em `neural_core.RULES` |
| Roteamento de modelo | `intelligence_router`, `dynamic_router` |
| Objetivos/missões | `goal_manager`, `orchestrator`, `mission_manager` |
| Percepção de tela | `copilot`, `perception_engine`, `autonomous_perception`, `active_observation`, `proactive_monitor` |
| Contexto multimodal | `multimodal_context`, `multimodal_fusion`, `context_engine`, `context_state` |
| Estado visual | `neural_core.BrainSim`, `neural_hud_engine`, `live_hud_state` |
| HUD inteira | `jarvis_hud.py` + 2 backups idênticos + `_backup_antes_do_copilot/` + `interface.py` (Tkinter) |
| Backend | `backend.py` + 2 backups + `_backup_antes_do_copilot/` |

### 4.3 Módulos órfãos (nunca importados pelo caminho real)

`app_index`, `proactive_monitor`, `tool_registry`, `computer_control`, `live_hud_state`,
`skill_visualizer`, `planning_graph`, `multimodal_context`, `conversational_engine`
(só via *shim*), `action_engine` (só via *shim*), `openai_provider` (só por script de teste),
`Jarvis.py` e `interface.py` (versões iniciais em Tkinter). As pastas `actions/`,
`intelligence/`, `interface/`, `perception/`, `voice/` contêm apenas re-exportações de uma linha.

### 4.4 Funcionalidades incompletas

- **Skill system**: registra descrições, não executa nada (`skill_system.py`).
- **Planner**: decompõe objetivos por palavras-chave fixas; o plano não guia a execução.
- **Recovery**: só decide "replanejar/parar"; não diagnostica tipo de erro.
- **Goal manager**: sem persistência, sem dependências, sem estados formais.
- **World model**: sem hardware, rede, periféricos ou projetos.
- **Rede**: apenas tráfego, IP e SSID; sem gateway, DNS, sub-rede, dispositivos ou diagnóstico.
- **Imaginação, cenários, mundos, grafo neural, modo sonho**: inexistentes.
- **Saúde do sistema, plugins, modo de privacidade**: inexistentes.

### 4.5 Pontos frágeis e riscos

| Risco | Descrição |
|---|---|
| Monólito de UI | `jarvis_hud.py` mistura desenho, estado, threads e regras de negócio (viola separação UI/lógica). |
| Estado global mutável | `backend` usa ~15 variáveis globais modificadas por várias threads. |
| Exceções engolidas | Dezenas de `except Exception: pass` escondem falhas (origem de D2 e D3). |
| Sleeps bloqueantes | `time.sleep` dentro de verificações chamadas pelo agente (aceitável em worker, nunca na UI). |
| Repositório pesado | `.pyc` e backups versionados; sem `.gitignore`. |
| Caminhos absolutos | `Abrir_JARVIS.bat` aponta para `C:\Users\pedro\Desktop\JARVIS`. |
| Identidade | Nome, prompts, regex de ativação e ícones são "JARVIS/MARK VII". |

---

## 5. Decisões de arquitetura do ULTRON

1. **Pacote único `ultron/`** com subpacotes por responsabilidade (evita colisão de nomes
   genéricos como `config`, `memory`, `network` no `sys.path`).
2. **Event Bus** tipado como espinha dorsal; HUD, voz e áudio apenas **reagem a eventos reais**.
3. **Estado global único** (`ULTRON_STATE`) com lock e cópias imutáveis para leitura.
4. **Separação estrita** Decisão ≠ Execução ≠ Verificação ≠ Recuperação.
5. **Um único caminho de chamada ao Ollama** (`ultron/models/ollama_client.py`) com
   roteador dinâmico que consulta `/api/tags` e nunca finge disponibilidade.
6. **Uma base SQLite** (WAL) com migração automática dos dados do JARVIS
   (fatos, preferências, automações) — os dados do usuário não são perdidos.
7. **Grafo neural persistente** como fonte do crescimento do cérebro visual.
8. **Personalidade separada** da lógica (pós-processamento de estilo + perfil de voz).
9. **Workers dedicados** (IA, visão, voz, rede, memória) com filas, *timeouts*, cancelamento e
   limites de tentativa; a UI apenas desenha.
10. **Modelo Vosk grande como padrão** (verificado) com fallback para o pequeno.

---

## 6. Funcionalidades preservadas e onde vivem no ULTRON

| Funcionalidade legada | Destino no ULTRON |
|---|---|
| Vosk + seleção de microfone + supervisor | `ultron/voice/stt.py`, `ultron/voice/audio.py`, `ultron/voice/processor.py` |
| Nível real do microfone | `ultron/perception/microphone.py` |
| Wake word "jarvis" | `ultron/voice/wake_word.py` ("ultron" + variantes + calibração) |
| Piper + pyttsx3 | `ultron/voice/tts.py` (+ DSP do perfil ULTRON, interrupção, pausa) |
| Auto-start do Ollama | `ultron/models/ollama_client.py` (`ensure_server`) |
| Agente com tool-calling | `ultron/cognition/planner_engine.py` (passo agêntico) + `ultron/agent/` |
| 25 ferramentas Windows | `ultron/skills/*` (cada uma com `execute()` e `verify()`) |
| Confirmação falada | `ultron/agent/autonomy.py` (`AuthorizationManager`) |
| Roteador regex em português | `ultron/cognition/intent_engine.py` (caminho rápido) |
| Memória/preferências/automações/auditoria | `ultron/memory/*` (migração automática do banco JARVIS) |
| Filtro de segredos | `ultron/memory/store.py` |
| Observador/copilot | `ultron/perception/vision.py` + `ultron/proactive/intelligence.py` |
| OCR / UI Automation / clique por descrição | `ultron/perception/ocr.py`, `ultron/skills/vision/` |
| Telemetria | `ultron/perception/system.py`, `ultron/network/` |
| Índice do menu Iniciar (órfão) | `ultron/skills/applications/app_index.py` — agora conectado |
| HUD, orbe flutuante, bandeja, mutex, F11 | `ultron/hud/*` |
| Autostart | `ultron/platform/autostart.py` |
| Diagnóstico | `ultron/health/monitor.py` + `python main.py --diagnose` |

## 7. Funcionalidades substituídas

| Legado | Substituído por | Motivo |
|---|---|---|
| `autonomous_core`, `execution_loop`, `autonomous_agent_runtime`, `orchestrator`, `mission_manager`, `long_running_agent`, `autonomous_loop` | `ultron/core/neural_core.py` + `ultron/core/orchestrator.py` | sete coordenadores concorrentes |
| `intent_engine`, `intent_engine_v2`, `decision_engine`, `human_in_loop`, `permission_engine`, `initiative_engine` | `ultron/cognition/intent_engine.py`, `decision_engine.py`, `ultron/agent/autonomy.py` | regras sobrepostas |
| `planner_engine`, `planning_graph`, `action_selector`, `capability_*` | `ultron/cognition/planner_engine.py` + `ultron/skills/registry.py` | plano não guiava execução |
| `verification_engine`, `state_verifier` | `ultron/agent/verification.py` | sucesso inferido de texto (D7) |
| `recovery_engine` | `ultron/agent/recovery.py` | sem diagnóstico por tipo de erro |
| `memory_engine`, `memory_v2`, `learning_engine`, `memory.py` | `ultron/memory/*` + `ultron/graph/neural_graph.py` | quatro esquemas paralelos |
| `world_model`, `context_state`, `context_engine`, `multimodal_*`, `windows_state_adapter` | `ultron/world/world_model.py`, `ultron/perception/*`, `ultron/cognition/context_engine.py` | sem persistência; sobreposição |
| `intelligence_router`, `dynamic_router`, `openai_provider` | `ultron/models/router.py` + plugin opcional | dois roteadores, nenhum consultava o Ollama |
| `jarvis_hud.py`, `neural_core.py`, `neural_hud_engine.py`, `live_hud_state.py` | `ultron/hud/*` | monólito; identidade JARVIS |
| `voice_pipeline`, `conversational_engine`, `proactive_voice` | `ultron/voice/processor.py` | desconectados do backend |
| `jarvis_lock*.py`, tela de PIN | removidos | já estavam desativados no legado |
| Backups `*BACKUP*`, `*ANTES*`, `_backup_antes_do_copilot/`, `__pycache__/` | removidos | permanecem no histórico Git |

O código legado completo continua acessível no histórico:
`git checkout 53e5a31 -- JARVIS`.

---

## 8. Arquitetura alvo

```
                              ULTRON
                                 │
                           PERSONALITY            ultron/personality
                                 │
                           NEURAL CORE            ultron/core (event bus, state, runtime, lifecycle)
                                 │
          ┌──────────────────────┼──────────────────────┐
     PERCEPTION              COGNITION               MEMORY
  ultron/perception       ultron/cognition       ultron/memory + ultron/graph
          └──────────────────────┼──────────────────────┘
                            WORLD MODEL           ultron/world
                                 │
                           GOAL MANAGER           ultron/cognition/goal_manager.py
                                 │
                          PLANNER ENGINE          ultron/cognition/planner_engine.py
                                 │
                           SKILL ROUTER           ultron/skills/registry.py
                                 │
                         EXECUTION ENGINE         ultron/agent/execution.py
                                 │
                       VERIFICATION ENGINE        ultron/agent/verification.py
                                 │
                         RECOVERY ENGINE          ultron/agent/recovery.py
                                 │
                              MEMORY
```

Subsistemas transversais: `ultron/models` (router), `ultron/voice`, `ultron/network`,
`ultron/privacy`, `ultron/imagination`, `ultron/audio`, `ultron/health`, `ultron/plugins`,
`ultron/proactive`, `ultron/hud`.
