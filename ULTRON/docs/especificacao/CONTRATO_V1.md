# Contrato de comunicação do SAFRA — versão 1

Especificação da Fase 2. É o único caminho entre o núcleo e qualquer interface (casca do desktop, painel no
navegador e, mais tarde, painel remoto pelo retransmissor). Quando a API for implementada, o esquema OpenAPI
gerado do código passa a ser o artefato normativo e um teste o confere contra este documento.

Base: `http://127.0.0.1:<porta>/api/v1`. Corpo em JSON (UTF-8). Horários em milissegundos desde a época Unix.

## 1. Regras gerais

| Regra | Definição |
|---|---|
| Versão | no caminho (`/api/v1`). Dentro da v1 só mudanças aditivas: campo novo opcional, rota nova, evento novo. Quem lê ignora o que não conhece |
| Autenticação | *cookie* de sessão `safra_sessao`; sem sessão válida: `401` |
| Origem | `Origin` e `Host` precisam ser os da própria API; senão `403 origem_recusada` |
| Alteração | métodos `POST`, `PATCH`, `PUT`, `DELETE` exigem `X-SAFRA-CSRF`; senão `403 csrf_invalido` |
| Idempotência | pedidos marcados com **I** aceitam `Idempotency-Key` (até 64 caracteres). Repetir a chave em até 10 minutos devolve a primeira resposta, sem repetir o efeito |
| Limites | corpo até 64 KiB; texto de comando até 4.000 caracteres; frequência por sessão (padrão: 30 comandos/min; 5 tentativas de entrada/min) → `429` |
| Escopo | cada sessão tem origem `desktop`, `painel_local` ou `remoto`. Rotas marcadas **D** só atendem `desktop`; as demais atendem `desktop` e `painel_local`. A coluna "remoto" de cada rota será definida quando o acesso externo for especificado; até lá, nenhuma |
| Efeitos | toda rota que altera algo executa uma habilidade pelo executor único ou chama a fachada do núcleo indicada. Não há rota genérica de execução |
| Correlação | toda resposta traz `X-SAFRA-Correlacao`; o mesmo valor aparece no log e na atividade gerada |

### 1.1 Formato de erro

```json
{"error": {"code": "validacao", "message": "O campo 'text' é obrigatório.",
           "correlation_id": "c-7f3a…", "details": {"campo": "text"}}}
```

| HTTP | `code` | Quando |
|---|---|---|
| 401 | `nao_autenticado` | sem sessão, sessão expirada ou revogada |
| 403 | `origem_recusada`, `csrf_invalido`, `nao_permitido_nesta_sessao` | origem errada; sem anti-CSRF; rota **D** numa sessão que não é `desktop` |
| 404 | `nao_encontrado` | item inexistente |
| 409 | `ocupado`, `conflito` | núcleo ocupado com outro pedido; autorização já resolvida |
| 422 | `validacao` | corpo ou parâmetro inválido; chave de configuração desconhecida |
| 429 | `limite_excedido` | frequência |
| 503 | `indisponivel` | componente necessário parado (por exemplo, voz) — a resposta diz qual e por quê |
| 500 | `erro_interno` | falha não prevista; nunca expõe rastro interno |

## 2. Entrada e sessões

| Método e rota | Escopo | O que faz |
|---|---|---|
| `GET /health` | sem sessão | `{"status": "ok", "version": "…"}` — nada além disso |
| `POST /auth/desktop` | sem sessão | corpo `{ticket}`; bilhete de uso único entregue à casca pelo núcleo. Cria sessão `desktop` |
| `POST /auth/code` | sem sessão | corpo `{code, device_name}`; código de uso único (60 s). Cria sessão `painel_local` |
| `POST /auth/codes` | **D** | gera um código de uso único para abrir o painel no navegador |
| `GET /session` | sessão | origem, capacidades, valor anti-CSRF, validade, versão do contrato |
| `POST /auth/logout` | sessão | encerra a própria sessão |
| `GET /sessions` | **D** | lista as sessões ativas (origem, nome do dispositivo, criada, último uso) |
| `DELETE /sessions/{id}` | **D** | revoga uma sessão |

Capacidades devolvidas em `GET /session` (a interface esconde o que a sessão não pode):
`comandos`, `autorizar`, `autorizar_sensivel`, `configurar`, `operador`, `sessoes`, `voz`.

## 3. Estado e sistema

| Método e rota | Escopo | Fonte no núcleo |
|---|---|---|
| `GET /state` | sessão | `state.as_dict()` filtrado para os campos do contrato (3.1) |
| `GET /system/components` | sessão | `lifecycle.statuses()` — cada componente com estado e motivo |
| `GET /system/telemetry` | sessão | `telemetry()` — só métricas medidas |
| `GET /system/metrics` | sessão | `metrics.snapshot()` |
| `POST /system/shutdown` | **D** | `shutdown()` — encerramento ordenado |

### 3.1 Campos de estado do contrato

`runtime_state`, `activity`, `runtime_reason`, `cognitive_phase`, `current_goal`, `current_action`,
`current_plan`, `active_model`, `active_skills`, `risk`, `last_result`, `last_error`,
`pending_authorization`, `voice_state`, `memory_state`, `health`, `telemetry`, `privacy`, `privacy_shield`,
`observer`, `models`, `second_brain` (publicado como `personal_memory`), `operator` (sucessor de `persona`),
`boot`, `version`, `updated_at`.

Ficam **fora** do contrato, por privacidade: `vision_state`, `current_window`, `current_application`,
`current_processes`, `world_model`, `network_state`, `device_state`. O que a interface precisar deles vem por
rotas próprias, com o conteúdo resumido (seção 9).

## 4. Conversa e comandos

| Método e rota | Escopo | O que faz |
|---|---|---|
| `POST /commands` **I** | sessão | corpo `{text}`. Chama `submit(text, source="api:<origem>")`. Resposta `202 {"command_id": "…"}`; o resultado chega pelo evento `response.ready` com o mesmo `command_id`. `409 ocupado` se o núcleo recusar |
| `POST /commands/cancel` | sessão | `cancel()` — cancela o pedido em andamento |
| `GET /conversation?limit=` | sessão | últimas trocas (pedido, resposta, tipo, procedência), do histórico de atividades |
| `POST /suggestions/resolve` | sessão | corpo `{accept}` — `accept_suggestion()` |

Uma resposta (`response.ready` e itens de `/conversation`) tem: `text`, `kind`
(`answer`, `result`, `error`, `question`, `refusal`, `info`), `spoken`, `success`, `verified`, `provenance`,
`command_id`.

## 5. Autorizações

| Método e rota | Escopo | O que faz |
|---|---|---|
| `GET /authorizations/pending` | sessão | o pedido pendente (ou `null`): `id`, `description`, `skill`, `risk`, `category`, `reversible`, `origin`, `permission`, `created`, `expires` |
| `POST /authorizations/{id}/resolve` **I** | sessão | corpo `{approved, remember_seconds?}` — `authorizations.resolve(approved, by=<origem>, request_id=id, remember=…)`. Pedidos de categoria sensível, de apagar dados ou de risco alto só são aceitos de sessão `desktop`; das outras, `403` |
| `GET /authorizations/standing` | sessão | autorizações permanentes em vigor |
| `DELETE /authorizations/standing/{key}` | sessão | revoga uma |
| `DELETE /authorizations/standing` | **D** | revoga todas |
| `GET /authorizations/history?limit=` | sessão | decisões anteriores |

Expirar equivale a negar, como hoje. Só existe uma pendência por vez.

## 6. Atividades

| Método e rota | Fonte |
|---|---|
| `GET /activity?limit=&kinds=&states=&before=` | `activity.recent()` |
| `GET /activity/{id}` | `activity.get()` |
| `GET /activity/{id}/children` | `activity.children()` |
| `GET /activity/summary?since=` | `activity.summary()` |

## 7. Memória, Projetos e Análises

Leituras chamam os serviços do domínio; **alterações executam habilidades** (a coluna diz qual), portanto
passam por permissões, confirmação e auditoria.

| Método e rota | Efeito |
|---|---|
| `GET /memory/records?query=&kind=&limit=` | busca na memória pessoal (texto, sem acentos) |
| `GET /memory/records/{id}` | um registro, com histórico |
| `POST /memory/records` **I** | cria registro — habilidade de captura da memória pessoal |
| `PATCH /memory/records/{id}` | edita — habilidade de edição |
| `DELETE /memory/records/{id}` | apaga — habilidade de exclusão (categoria "apagar dados": **sempre** pede confirmação) |
| `GET /memory/reminders?state=` | lembretes abertos, atrasados, próximos |
| `POST /memory/reminders/{id}/snooze` | adia |
| `GET /memory/facts?query=&limit=` | memória semântica (leitura) |
| `GET /projects`, `GET /projects/{id}` | projetos; um projeto com contagens |
| `POST /projects` **I**, `PATCH /projects/{id}` | cria, edita |
| `POST /projects/{id}/archive` | arquiva (não apaga) |
| `GET /projects/{id}/items?type=` | itens ligados: notas, registros, tarefas de análise, atividades |
| `POST /projects/{id}/links`, `DELETE /projects/{id}/links/{link}` | liga e desliga um item existente |
| `GET /projects/{id}/notes`, `POST /projects/{id}/notes` **I** | notas, decisões, parâmetros — `projects.note` |
| `GET /analysis/state` | estado do motor (fila, tarefa em curso) |
| `GET /analysis/tasks?limit=&state=`, `GET /analysis/tasks/{id}` | tarefas de análise e resultado |
| `POST /analysis/tasks` **I** | corpo `{kind, question?, goal?, project_id?}` — `analysis.consult`. `kind`: `consulta`, `planejamento`, `organizacao`, `rotinas`, `telemetria`, `diagnostico`, `coordenacao`, `projeto` |
| `POST /analysis/tasks/{id}/cancel` | cancela |

O motor de Análises nunca executa ações: devolve **ações propostas**, que só rodam por `POST /commands` com as
confirmações de sempre.

## 8. Voz

| Método e rota | Fonte |
|---|---|
| `GET /voice/status` | estado do microfone, do reconhecimento e da síntese; modelo de fala e voz em uso |
| `POST /voice/listen` | abre uma janela de escuta (o mesmo que a tecla de atalho) |
| `POST /voice/stop` | interrompe a fala (`speaker.interrupt`) |
| `POST /voice/mute` | corpo `{muted}` |
| `POST /voice/microphone` | corpo `{enabled}` — `voice.toggle_mic` |
| `GET /voice/devices` | microfones e saídas disponíveis |
| `POST /voice/device` | escolhe o microfone ou a saída |
| `POST /voice/restart` | reinicia o componente de voz |
| `POST /voice/diagnostics` | executa o diagnóstico de 8 etapas e devolve o resultado de cada uma |
| `POST /voice/calibration` | calibra a palavra de ativação (só "Safra") |

O áudio não trafega pelo contrato nesta versão: o microfone e o alto-falante são os do computador principal.

## 9. Saúde, diagnóstico, rede e habilidades

| Método e rota | Escopo | Fonte |
|---|---|---|
| `GET /health/report` | sessão | `health()` — CPU, memória, disco, modelos, voz, interface |
| `POST /diagnostics/run` | sessão | `diagnose()` |
| `GET /logs?level=&after=&limit=` | **D** | cauda do log estruturado, já com segredos mascarados |
| `GET /skills` | sessão | habilidades: nome, categoria, risco, descrição, disponível ou o que falta |
| `GET /plugins` | sessão | plugins carregados e recusados, com motivo |
| `GET /models/status` | sessão | roteador de modelos: provedor ativo, perfil, consumo do mês |
| `GET /network/devices` | sessão | inventário passivo da rede local |
| `GET /platform/summary` | sessão | aplicativo em foco e contagem de processos — sem títulos de janela nem conteúdo de tela |

## 10. Configurações, privacidade, operador e backups

| Método e rota | Escopo | O que faz |
|---|---|---|
| `GET /settings` | sessão | valores e descrição de cada chave (tipo, faixa, grupo, rótulo, se exige reinício). Segredos nunca são devolvidos |
| `PATCH /settings` | sessão | corpo `{changes}` — `settings_manager.update`; chave desconhecida ou valor fora da faixa: `422` com o motivo de cada uma |
| `POST /settings/reset` | **D** | volta aos padrões (com cópia de segurança) |
| `GET /settings/credentials` | sessão | só `{"openai": {"configured": true|false}}` |
| `PUT /settings/credentials/openai`, `DELETE …` | **D** | grava ou remove a chave no cofre do sistema; o valor nunca volta |
| `POST /privacy/shield` | sessão | corpo `{active}` — modo privacidade |
| `POST /observer` | sessão | corpo `{action}` — pausa, retoma ou muda o modo do Observador |
| `POST /operator` | **D** | corpo `{active, duration_seconds?}` — liga (com confirmação e prazo) ou encerra o Modo Operador |
| `POST /emergency-stop` | sessão | parada de emergência: cancela o pedido em andamento e encerra o Modo Operador |
| `GET /backups` | sessão | backups existentes |
| `POST /backups` **I** | sessão | cria um backup verificado |
| `POST /exports` **I** | sessão | corpo `{format}` (`json` ou `csv`) — exporta a memória pessoal para um arquivo novo |

Restaurar um backup **não** está na API: continua exigindo o SAFRA fechado, pela linha de comando.

## 11. Eventos (WebSocket)

`GET /api/v1/events` (WebSocket; mesma sessão e mesma conferência de origem).

Envelope de cada evento:

```json
{"v": 1, "id": 18342, "type": "response.ready", "ts": 1794583020123, "data": {}}
```

- `id` cresce de um em um. O cliente guarda o último e, ao reconectar, envia
  `{"op": "subscribe", "since": 18342, "types": ["*"]}`.
- O núcleo guarda os últimos 1.000 eventos não descartáveis. Se o que o cliente pede já saiu dessa janela,
  recebe `resync` e deve reler `GET /state`.
- Ao conectar, o servidor envia `hello` com a versão do contrato, a sessão e o último `id`.
- Fila limitada por assinante. Eventos **descartáveis** são perdidos primeiro; os demais nunca. Se a fila
  de não descartáveis encher, a conexão é encerrada e o cliente reconecta com `since`.
- O servidor envia `ping` a cada 20 s; sem resposta em 60 s, encerra.
- **Catálogo fechado**: um tipo interno que não esteja na tabela abaixo nunca é transmitido.

| Evento do contrato | Origem interna | Descartável | Dados |
|---|---|:-:|---|
| `system.ready`, `system.shutdown` | `SYSTEM_READY`, `SYSTEM_SHUTDOWN` | | versão, resumo do início |
| `component.started`, `component.failed`, `component.stopped` | `COMPONENT_*` | | componente, motivo |
| `state.changed` | `STATE_CHANGED` | | só os campos do contrato que mudaram |
| `input.received` | `USER_INPUT` | | texto, origem, `command_id` |
| `response.ready` | `RESPONSE_READY` | | a resposta (seção 4) |
| `authorization.required`, `authorization.resolved` | `AUTHORIZATION_*` | | o pedido; a decisão e quem decidiu |
| `action.started`, `action.finished` | `ACTION_*` | | habilidade, descrição, risco, resultado |
| `verification.result` | `VERIFICATION_*` | | verificado, sem confirmação independente ou falhou |
| `activity.updated` | `ACTIVITY_UPDATED` | | o item de atividade |
| `voice.listening`, `voice.speaking` | `LISTENING_*`, `VOICE_STARTED/FINISHED`, `WAKE_WORD` | | início ou fim; origem (palavra, tecla, botão) |
| `voice.level` | energia do áudio falado | ✔ | amplitude de 0 a 1, até 20 por segundo |
| `voice.heard` | `VOICE_RECEIVED` | | texto reconhecido |
| `memory.record` | `RECORD_CREATED/UPDATED/DELETED/RESTORED` | | operação e resumo do registro |
| `reminder.due` | `REMINDER_DUE`, `REMINDER_SNOOZED` | | lembrete |
| `notification` | `NOTIFICATION`, `INSIGHT` | | texto, nível |
| `analysis.task` | `ANALYSIS_TASK_*` (hoje `TARDIS_TASK_*`) | | tarefa e estado |
| `project.updated` | novo | | projeto |
| `goal.updated`, `plan.updated` | `GOAL_*`, `PLAN_*` | | objetivo, plano |
| `model.changed` | `MODEL_SELECTED/CHANGED/UNAVAILABLE` | | modelo, motivo |
| `operator.changed` | `OPERATOR_CHANGED` (hoje `PERSONA_CHANGED`) | | ativo, desde, até |
| `privacy.changed` | `PRIVACY_UPDATED` | | modo privacidade e Observador |
| `health.updated` | `HEALTH_UPDATED` | ✔ | resumo de saúde |
| `telemetry` | métricas periódicas | ✔ | métricas medidas |
| `network.inventory` | `NETWORK_INVENTORY_UPDATED` | ✔ | contagem e mudanças |
| `log` | `LOG` | ✔ | linha de log (só sessão `desktop`) |
| `session.revoked` | novo | | motivo |
| `resync` | novo | | — |

Não são transmitidos: `SCREEN_CHANGED`, `WINDOW_CHANGED`, `APPLICATION_CHANGED`, `PROCESS_ENDED`,
`FILESYSTEM_CHANGED`, `VISION_UPDATED`, `OCR_UPDATED`, `PERCEPTION_FUSED`, `DEVICE_*`, `GRAPH_*`, `MEMORY_*`
(consolidação interna), `IMAGINATION_*`, `DREAM_*`, `WORLD_*`, `UI_REQUEST`, `COGNITIVE_PHASE` (já refletido em
`state.changed`).

## 12. Conformidade

| Verificação | Como |
|---|---|
| Toda rota e todo evento desta especificação existem na implementação, e nada além deles | teste que compara o esquema gerado com a lista deste documento |
| Toda rota recusa pedido sem sessão, de outra origem e sem anti-CSRF | teste parametrizado sobre todas as rotas |
| Rotas **D** recusam sessão `painel_local` | idem |
| Nenhuma resposta contém segredo | teste com segredos de exemplo no cofre simulado |
| Mesma bateria contra a API local e, depois, contra o retransmissor | reaproveitamento dos testes de contrato |
