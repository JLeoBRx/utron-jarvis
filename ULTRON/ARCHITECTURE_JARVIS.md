# JARVIS — Arquitetura e mapa de integração

Este documento descreve o JARVIS como ele está no código (branch `claude/adoring-brahmagupta-vcejpt`).
O pacote Python continua se chamando `ultron` e a pasta de dados continua em
`%LOCALAPPDATA%\ULTRON`: são identificadores internos mantidos de propósito para não quebrar
dados, configurações, atalhos e entradas de início automático que o usuário já tem. Tudo o que
o usuário **vê** chama-se JARVIS.

## 1. Princípios

1. **Uma fonte de verdade por assunto.** Um único banco SQLite, um único estado global
   (`JARVIS_STATE`), um único Event Bus, um único executor de ações, um único gerenciador de
   autorizações, um único dono do microfone. Os dois hubs são **leitores** desses mesmos objetos.
2. **Nada visual sem causa real.** Animações, pulsos, ondas e halos derivam de eventos e níveis
   reais (nível do microfone, nível da voz, etapas do plano, eventos de registro).
3. **Executar ≠ verificar.** Toda ação passa pelo `ExecutionEngine`; o resultado só é dado como
   concluído quando a skill relê o efeito (Verification Engine).
4. **Interface nunca bloqueia.** Consultas, varreduras e ações rodam em workers; a interface
   recebe resultados por sinais do Qt.

## 2. Mapa de integração (componente → arquivo → papel)

| Componente | Onde | Papel e fonte de verdade |
|---|---|---|
| Ponto de entrada | `main.py` → `ultron/app.py:main()` | Linha de comando: HUB (padrão), `--headless`, `--diagnose`, `--voice-test`, `--list-mics`/`--mic`, `--backup`/`--list-backups`/`--restore-backup`/`--export`, `--status`/`--stop`, `--say`. Garante instância única (`platform/single_instance.py`) e registra o PID (`platform/control.py`). |
| Neural Core | `ultron/core/neural_core.py` | Constrói e liga todos os componentes; `boot()`/`shutdown()` ordenados pelo `LifecycleManager`; `submit()` (texto/voz) e `run_skill()` (hubs e skills) — **toda ação dos hubs passa por aqui**. |
| Event Bus | `ultron/core/event_bus.py`, `core/events.py` | Publicação assíncrona com fila limitada (descartes contados e avisados de forma agregada a cada 5 s). Um assinante que falha não afeta os outros. |
| Estado global | `ultron/core/state.py` (`JarvisState`, `StateStore`) | Único estado estruturado (`runtime_state`, `activity`, plano atual, autorização pendente, saúde, rede, Second Brain…). `STATE_CHANGED` informa só os campos alterados; os hubs copiam só esses campos. `activity` é o contrato reduzido de estados compartilhado pelos dois hubs. |
| Ciclo de vida e workers | `core/lifecycle.py`, `core/runtime.py` | Ordem de início/parada com dependências; `WorkerPool` com filas nomeadas (`ai`, `vision`, `voice`, `network`, `memory`, `perception`, `imagination`, `health`, `actions`), `Scheduler` periódico, cancelamento cooperativo e `run_with_timeout`. |
| Orquestrador | `core/orchestrator.py` | Pedido → percepção do pedido → contexto → decisão → plano → execução → verificação → resposta, publicando cada fase. |
| Cognição | `cognition/intent_engine.py`, `context_engine.py`, `decision_engine.py`, `planner_engine.py`, `reasoning_engine.py`, `goal_manager.py` | Intenção por regras determinísticas em português (palavra de ativação, comandos, memória pessoal, rede, voz, autonomia) e modelo local (Ollama) para o resto. `goal_manager` = objetivos persistentes de várias etapas. |
| Memória | `memory/system.py`, `memory/store.py`, `graph/neural_graph.py` | Memória de trabalho, episódica, semântica, procedimental e preferências; Neural Graph persistente. `store.Database` = **o banco único** (SQLite WAL, migrações versionadas, auditoria). |
| Banco de dados | `%LOCALAPPDATA%\ULTRON\ultron.sqlite3` | Tabelas de memória, grafo, `sb_*` (Second Brain, lembretes, disparos, notificações, histórico), `network_devices`, `audit`, `meta`. Nenhum banco paralelo. Backups: `memory/backup.py` (API de backup do SQLite, rotação). |
| Memória pessoal (Second Brain) | `secondbrain/service.py` (+ `store.py`, `capture.py`, `parsing.py`, `queries.py`, `timeutil.py`, `models.py`) | CRUD, busca sem acentos (FTS5), conflitos de agenda, exportação JSON/CSV, captura explícita/automática com revisão, perguntas quando a data é ambígua. Recusa senhas/tokens/dados financeiros antes de gravar. |
| Lembretes | `secondbrain/reminders.py` | Agendador determinístico (sem IA): thread própria que dorme até o próximo instante; disparos deduplicados em `sb_fired`; recuperação de lembretes perdidos com o programa fechado (um aviso, sem rajada); recorrência no horário de parede; horário de silêncio. |
| Skills | `skills/registry.py` + pacotes `skills/*` | Registro único de capacidades (aplicativos, janelas, arquivos, navegador, visão, rede, dispositivos, diagnóstico, autonomia, desenvolvimento, áudio/voz, memória, imaginação, sistema, Second Brain). Nunca há "shell com texto livre". |
| Executor | `agent/execution.py` | Valida argumentos, decide autonomia, pede autorização quando preciso, executa com prazo, classifica erros, publica `ACTION_*` e audita. |
| Autonomia e autorizações | `agent/autonomy.py` | `AutonomyPolicy` (risco × reversibilidade × origem × nível) e `AuthorizationManager` (um pedido pendente por vez; expirar = negar; autorização específica para categorias sensíveis; autorização permanente **escopada** — ação + recurso + validade — nunca para sensível/crítico/irreversível/proativo, revalidada a cada uso). |
| Verificação | `agent/verification.py` | Confirmação independente do efeito (a skill relê o mundo). |
| Recuperação | `agent/recovery.py` | Estratégias com tentativas limitadas; erros não recuperáveis (não autorizado, argumento inválido, cancelado…) não são repetidos. |
| Voz — captura e STT | `voice/audio.py`, `voice/processor.py`, `voice/stt.py`, `voice/wake_word.py` | Microfone por PyAudio ou sounddevice (reamostragem para 16 kHz quando o dispositivo recusa), Vosk offline em português, formas medidas de "Jarvis", janela de continuação, proteção contra autoescuta. Único dono do microfone. |
| Voz — diagnóstico | `voice/diagnostics.py`, `voice/calibrate.py`, `hud/voice_panel.py` | As 8 etapas (microfone detectado → resposta reproduzida), no console (`--voice-test`, `--diagnose`) e na interface. |
| Voz — TTS | `voice/tts.py`, `voice/dsp.py`, `personality/voice_profile.py` | Piper (`pt_BR-faber-medium`) com perfil JARVIS (masculino, grave, natural), SAPI como alternativa; voz pode ser desligada. |
| Notificações | `secondbrain/reminders.py` → `REMINDER_DUE`/`NOTIFICATION` → `hud/controller.py:_notify` | Central de notificações no banco (`sb_notifications`), notificação nativa do Windows pela bandeja, fala (se não estiver em silêncio). |
| Configurações | `config/settings.py`, `config/profiles.py`, `config/paths.py` | `SettingsManager` com validação de faixas/escolhas, migração v1 (ULTRON) → v2 (JARVIS) com cópia de segurança, variáveis `JARVIS_*` (com `ULTRON_*` aceitas). |
| Rede local | `network/world_integration.py`, `discovery.py`, `inventory.py`, `interfaces.py`, `oui.py`, `ssdp.py`, `diagnostics.py` | Só fontes legítimas (tabela de vizinhos, ping de um pacote, DNS reverso, SSDP opcional), só na sub-rede privada. Inventário persistente com estados observados e classificação honesta; **descobrir ≠ administrar**. |
| Percepção | `perception/engine.py` + sensores | Janelas, processos, sistema, tela/visão/OCR, arquivos, rede, dispositivos, microfone. Intervalos relaxados com o usuário ausente (> 5 min). Texto da tela é dado não confiável. |
| Saúde e métricas | `health/monitor.py`, `core/metrics.py` | Verificações a cada 15 s; "mudou" só quando o quadro de problemas muda. Métricas de quadros, atraso da interface e latências. |
| Tema | `hud/palette.py` (sem Qt) → `hud/theme.py` | Fonte única de cores (#030712, #071426, #0B1F3A, #075985, #00D9FF, #67F3FF, #168BFF, #DCEEFF), tons e estilo de cada estado (cor, intensidade, efeito, rótulo). |
| Perfis visuais | `hud/quality.py` | Econômico / Equilibrado / Alto / Cinematográfico: teto, repouso, fundo, partículas, densidade. Só mudam o custo visual. |
| HUB principal — JARVIS CORE | `hud/controller.py`, `window.py`, `brain_view.py`, `scene.py`, `brain_model.py`, `orb.py` | Cérebro neural 3D, anel de subsistemas, módulos (plano, autorização, memória…), estados visuais, barra de entrada, orbe compacto, bandeja. |
| Segundo HUB — TARDIS | `hud/tardis.py`, `hud/tardis_scene.py`, `hud/panels.py` | Memória espacial: câmara central (hoje), anéis, corredores, portais por região com dados reais, painel lateral de consulta/edição. |
| Painel de Sistemas | `hud/systems_panel.py` (+ `voice_panel.py`, `panels.py`) | VOZ, REDE LOCAL, AUTONOMIA, DESEMPENHO E SAÚDE. |

## 3. Como os dois hubs se integram

```
              ┌──────────── Neural Core (core/neural_core.py) ─────────────┐
 voz/texto ──▶│ submit() → Orchestrator → Intent/Plan → ExecutionEngine ──▶│──▶ skills (verificadas)
 hubs ───────▶│ run_skill(skill, args, origin)            ▲               │
              │                                  AuthorizationManager    │
              │  StateStore (JARVIS_STATE)   EventBus   Database (SQLite) │
              └──────┬─────────────────────────┬────────────────────────┘
                     │ STATE_CHANGED (campos)   │ eventos (fila limitada)
                     ▼                          ▼
              HudController (thread da interface: drena em lotes)
                 ├── JARVIS CORE: NeuralScene + BrainView
                 ├── TARDIS: TardisScene + TardisView + páginas (leitura em thread)
                 └── Sistemas: Voz · Rede · Autonomia · Saúde
```

* **Eventos → interface.** O `HudController` assina o Event Bus; cada evento entra numa fila
  limitada e a thread da interface drena em lotes (uma única chamada enfileirada por rajada).
  O mesmo evento vai para a cena do CORE, para o TARDIS e para o painel de Sistemas.
* **Estado → interface.** `STATE_CHANGED` traz os nomes dos campos; o controlador copia só esses
  campos para um cache compartilhado pelos hubs (`state_cache`).
* **Interface → núcleo.** Botões e capturas chamam `core.run_skill()` num worker (`actions`);
  o resultado volta por sinal e é exibido como sucesso **verificado**, sucesso sem confirmação
  independente, negado/cancelado ou falha — nunca maquiado.
* **Autorização.** Uma única pendência por vez, visível nos três lugares (CORE, TARDIS,
  Sistemas) e respondível por voz, texto ou botão.
* **TARDIS ↔ CORE.** O botão TARDIS (ou F2, ou "abra o TARDIS") abre o segundo hub; "← JARVIS
  CORE" apenas o esconde: câmera, região aberta e filtros ficam como estavam. Com o TARDIS em
  foco, o CORE desenha na cadência de fundo; e vice-versa.

## 4. Fluxos principais

**Pedido por voz.** microfone (`ultron-microphone`) → Vosk → palavra de ativação → texto →
`core.submit(source="voice")` → orquestrador → resposta → fala (`ultron-speaker`) com a escuta
suspensa enquanto fala (sem autoescuta; interromper com "pare").

**Lembrete.** `secondbrain.capture` grava registro + lembrete no banco → thread `ultron-reminders`
acorda no instante certo → `sb_fired` impede duplicata → `REMINDER_DUE` → central de
notificações + notificação do Windows + fala (se permitido). Se o JARVIS estava fechado, o
próximo início avisa uma vez como "perdido".

**Ação sensível.** skill com categoria sensível → `AutonomyPolicy` = autorizar →
`AuthorizationManager.request()` → pendência no estado → resposta → execução → verificação →
auditoria (`audit`) e registro na aba AUTONOMIA.

## 5. Threads

| Thread | Dono | Observação |
|---|---|---|
| principal (Qt) | interface | só desenho e eventos de interface; nada de E/S |
| `ultron-event-bus` | Event Bus | entrega de eventos |
| `ultron-scheduler` | runtime | tarefas periódicas (saúde, métricas, modelos, consolidação, descoberta, backup…) |
| `ultron-<worker>` | runtime | um por fila nomeada (ai, vision, voice, network, memory, perception, imagination, health, actions) |
| `ultron-reminders` | lembretes | dorme até o próximo instante relevante |
| `ultron-microphone` | voz | único leitor do microfone; parada com `join` |
| `ultron-speaker` | TTS | fila de fala; parada com `join` |
| `ultron-hub2` | páginas dos hubs | leitura do banco fora da interface (1 por hub) |
| curtas | — | snapshot do grafo, verificação de saúde com prazo, diagnóstico/calibração de voz |

Encerramento: `quit()` da interface → `core.shutdown()` → `LifecycleManager.stop_all()` na ordem
inversa → workers, agendador e Event Bus param. O teste `test_tardis.ShutdownTest` confirma que
nenhuma thread do JARVIS sobra.

## 6. Dados e segurança

* Dados do usuário: `%LOCALAPPDATA%\ULTRON\` — `ultron.sqlite3`, `settings.json`,
  `world_model.json`, `backups\`, `exports\`, `logs\ultron.log`, `autorizacoes_permanentes.json`.
* Nunca gravados: senhas, tokens, dados financeiros ou de autenticação (recusados antes de
  gravar em memória, Second Brain e notas da rede).
* Rede: nenhuma varredura de portas, exploração, interceptação ou acesso a aparelhos.
* Sistema: o JARVIS não desativa Defender, Firewall ou UAC e não altera o registro do Windows
  além da entrada opcional de início automático (desligada por padrão; o instalador pergunta).
