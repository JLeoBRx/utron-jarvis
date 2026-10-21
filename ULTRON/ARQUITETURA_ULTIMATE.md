# JARVIS ULTIMATE — Fase 2: plano de preservação e expansão e arquitetura técnica

Entregáveis 2 (plano de preservação e expansão) e 3 (arquitetura). Baseado no inventário da
Fase 1 ([`INVENTARIO_JARVIS_ORIGINAL.md`](INVENTARIO_JARVIS_ORIGINAL.md)) e em protótipos medidos.

## 1. Princípios

1. **Evoluir, não reescrever.** A plataforma atual (pacote `ultron`) já preserva 46 dos 59
   comandos do original e todo o seu núcleo útil. Os três pilares novos entram como módulos ligados
   ao mesmo Event Bus, ao mesmo estado central e ao mesmo executor de ações.
2. **Um só caminho para ações.** Voz, teclado, TARDIS e Noctário usam o mesmo protocolo de ações
   (skills com validação, risco, autorização, verificação e registro). O modelo de linguagem só
   escolhe skills; nunca executa código, nunca acessa arquivos fora das skills e nunca fala com o
   robô diretamente.
3. **A interface apresenta; não decide e não controla tempo real.** O controle PD do Noctário
   pertence ao firmware. A interface envia pedidos e mostra o que foi **confirmado**.
4. **Animação = sinal real.** Estados do avatar, rotor da TARDIS e painéis do Noctário só reagem a
   estado central, eventos, telemetria e à posição real do áudio em reprodução.
5. **Honestidade operacional.** "Solicitado" ≠ "confirmado"; indisponível é dito com a causa;
   simulado é rotulado como simulado; nada é afirmado sem verificação.

## 2. Plano de preservação e expansão

### 2.1 Preservar (não muda de comportamento)
Núcleo por eventos, 93 skills e suas confirmações, memória pessoal e lembretes, TARDIS como
memória espacial (vira o **Arquivo** da nova TARDIS, sem perder nada), rede local passiva,
diagnóstico de voz em 8 etapas, perfis de qualidade, scripts do Windows, pasta de dados
`%LOCALAPPDATA%\ULTRON`, pacote `ultron` e todos os 197 testes existentes.

### 2.2 Recuperar do original (Fase 3)
A lista completa está no inventário (§5): automações migradas que não executam, personalidade
original, Observador com modos e desligado ao iniciar, frases de comando perdidas, ferramentas do
agente, COM da voz SAPI, mutex do original, cópia de modelos do instalador, integração OpenAI,
taxa de rede, e os itens da interface original.

### 2.3 Expandir
| Pilar / área | O que entra | Fase |
|---|---|---|
| Plataforma | Janela única com navegação JARVIS · TARDIS · NOCTÁRIO · ATIVIDADES · CONFIGURAÇÕES · DIAGNÓSTICOS e transições que preservam estado; permissões por categoria; histórico de atividades unificado | 3 |
| JARVIS | Rosto robótico holográfico 3D, boca sincronizada com o áudio real, 12 estados visuais, legendas sincronizadas, interrupção, modo de privacidade | 4 |
| TARDIS | Sala de controle 3D (console, rotor temporal, painéis) ligada a estados reais; módulo lógico próprio com protocolo de tarefas; "JARVIS, consulte a TARDIS" | 5 |
| Noctário | Firmware ESP32 completo, protocolo Bluetooth NOCT/1, serviço com estado solicitado × confirmado, painel de telemetria, parada de emergência, análise de voltas | 6 |

## 3. Visão geral

```
┌──────────────────────────────── INTERFACE (PySide6) ─────────────────────────────────┐
│ PlatformWindow  [JARVIS][TARDIS][NOCTÁRIO][ATIVIDADES][CONFIGURAÇÕES][DIAGNÓSTICOS]   │
│  ├─ JarvisPage ── AvatarView (rosto 3D) · legendas · conversa · modo NÚCLEO NEURAL   │
│  ├─ TardisPage ── TardisRoomView (sala 3D) · consoles · ARQUIVO (memória espacial)   │
│  ├─ NoctarioPage ─ sensores · posição da linha · PD · motores · parâmetros · PARADA  │
│  ├─ ActivityPage · SettingsPage · DiagnosticsPage (inclui o Painel de Sistemas)      │
│  └─ barra de entrada global · barras de autorização · orbe · bandeja · notificações  │
│ HudController: fila limitada Event Bus → interface; relógio adaptativo por perfil    │
└──────────────────────────────────────────────────────────────────────────────────────┘
        ▲ eventos e estado (só leitura)                 │ pedidos (texto, botões, voz)
┌───────┴────────────────────────── NÚCLEO (NeuralCore) ▼──────────────────────────────┐
│ EventBus · StateStore (JarvisState) · Lifecycle · WorkerPool · Agendador · Atividades │
│ Coordenador: Intent → Decision → Planner/Orchestrator → ExecutionEngine               │
│   (Autonomia + Permissões por categoria + Autorização) → Verificação → Recuperação    │
│ Personalidade · Roteador de modelos (Ollama local | OpenAI opcional)                  │
├──────────────┬───────────────┬────────────────┬───────────────┬──────────────────────┤
│ VOZ          │ TARDIS        │ NOCTÁRIO       │ MEMÓRIA       │ percepção, rede,     │
│ captura, STT │ TardisEngine  │ NoctarioService│ SQLite único  │ saúde, plugins       │
│ TTS, visemas │ protocolo de  │ transporte BT  │ + tarefas da  │ (existentes)         │
│ legendas     │ tarefas,      │ NOCT/1         │ TARDIS, voltas│                      │
│ privacidade  │ analisadores  │ telemetria     │ do Noctário,  │                      │
│              │ memória proj. │ alertas        │ atividades    │                      │
└──────────────┴───────────────┴───────┬────────┴───────────────┴──────────────────────┘
                                       │ Bluetooth Clássico (SPP / RFCOMM)
                            ┌──────────▼───────────┐
                            │ FIRMWARE ESP32       │ PD em tempo real, rampas, cruzamentos,
                            │ (Noctário)           │ perda de linha, calibração, segurança
                            └──────────────────────┘
```

## 4. Tecnologias (e por que estas)

| Escolha | Motivo |
|---|---|
| **Python 3.11 + PySide6-Essentials** (mesma base do original e da plataforma atual) | Reescrever em outra linguagem/engine (Unity, Electron, C#) perderia as 93 skills, as integrações Windows já verificadas e os testes, sem ganho funcional. |
| **3D em tempo real por malhas procedurais projetadas** (NumPy: transformação, perspectiva, normais, iluminação, descarte de faces traseiras) e **traçado em lote com QPainter** | Avaliado e medido (Fase 1): Qt Quick 3D não está no pacote Essentials (Addons acrescentam ~150 MB e exigem GPU/RHI sem alternativa por software confiável); OpenGL puro exigiria shaders próprios e não roda sem GPU. A escolha roda em qualquer máquina, é testável sem GPU, e o **mesmo renderizador funciona sobre `QOpenGLWidget`** (aceleração por GPU opcional, verificada funcionalmente). Não há imagem de fundo fazendo papel de cena: rosto e sala são geometria 3D calculada a cada quadro. |
| Conversão NumPy → Qt por `QDataStream` (caminhos por nível de brilho) | Medido: 11× mais rápido que criar pontos um a um; a malha inteira do rosto em ~1,4 ms. |
| **Vosk** (reconhecimento offline) e **Piper** (voz neural) — existentes | Já instalados, offline e verificados. O Piper entrega os fonemas de cada frase (base dos visemas). |
| **Ollama** local (`qwen2.5:3b`, `qwen2.5vl:3b`) — existente; **OpenAI Responses API** opcional (restauração do original) | Local por padrão; externo só com chave do usuário e consentimento explícito. |
| **Firmware Arduino-ESP32 (C++)**: `BluetoothSerial` (SPP), `Preferences` (NVS), LEDC (PWM) | Padrão do ecossistema da ESP32 DevKit; a lógica de controle fica num módulo C++ portátil, compilável no PC para testes automatizados. |
| Transporte no PC: **RFCOMM nativo do Python** (socket `AF_BLUETOOTH`, sem dependência) ou **porta COM Bluetooth** (`pyserial`) | O Windows cria portas COM para dispositivos SPP pareados; o RFCOMM nativo dispensa escolher a porta. |

## 5. Componentes

### 5.1 Interface gráfica — `ultron/hud/`
* `platform.py` — **PlatformWindow**: barra de navegação, pilha de páginas com transição
  holográfica (≈300 ms; as páginas nunca são destruídas, então operações em andamento continuam),
  barra de entrada global, barras de autorização/sugestão, indicadores (microfone, voz, IA,
  Noctário, TARDIS) e o **chip de PARADA do Noctário** sempre visível quando há robô conectado.
  Atalhos: F1 JARVIS, F2 TARDIS, F4 NOCTÁRIO, F5 ATIVIDADES, F6 CONFIGURAÇÕES, F3/F7
  DIAGNÓSTICOS, F11 tela cheia, F12 **parada de emergência do Noctário**, Esc interrompe a fala
  (segundo Esc recolhe ao orbe, como no original).
* As janelas existentes (TARDIS memória espacial, Painel de Sistemas) passam a ser páginas, sem
  mudança de lógica; o orbe e a bandeja continuam.

### 5.2 Avatar — `ultron/hud/avatar/`
* `geometry.py` — cabeça esculpida em coordenadas cilíndricas (crânio, têmporas, órbitas, maçãs,
  nariz, lábios, queixo), contornos de varredura, meridianos, placas e costuras, orelhas, pescoço e
  colar com o reator (DNA do avatar original: plataforma de projeção, varredura, partículas).
* `rig.py` — parâmetros de expressão (mandíbula, largura e arredondamento dos lábios, pressão,
  pálpebras, sobrancelhas, olhar) e deformações (a mandíbula gira em torno da articulação; a malha
  inferior acompanha).
* `renderer.py` — desenho por camadas: fundo em cache, ambiente (grade 3D, partículas, anéis,
  projeções de dados), cabeça (malha por níveis de brilho), traços do rosto, brilho (camada
  pequena desfocada em NumPy, somada), linhas de varredura. Densidade por perfil de qualidade.
* `animator.py` — relógio do avatar: transições suaves entre estados, movimento sutil da cabeça,
  piscadas, olhar, expressões, inicialização ligada ao progresso real do boot, animações de
  conexão/desconexão ligadas a componentes reais.
* `states.py` — os 12 estados (§7) resolvidos a partir de sinais reais (função pura, testável).
* `view.py` — o widget da página JARVIS (clique no rosto liga/pausa o microfone, como o clique no
  núcleo do original).

### 5.3 Áudio, reconhecimento e síntese — `ultron/voice/` (existente, ampliado)
* Captura e STT inalterados; novo indicador "reconhecendo" (parciais do Vosk em curso).
* **Modo de privacidade**: fecha de fato o dispositivo de captura (verificado pelo próprio
  pipeline), suspende a observação de tela e mostra o estado do microfone. Não pode ser desligado
  por voz (o microfone está fechado): só por teclado/mouse.
* `lipsync.py` (novo) — fonemas do Piper → visemas; alinhamento estimado **apenas sobre os trechos
  sonoros do áudio real**; abertura da boca pela energia real; boca fechada no silêncio; trilha de
  palavras para a legenda.
* `tts.py` — a síntese passa a devolver também os trechos por frase com fonemas; o `Speaker`
  expõe `mouth(agora)` e `caption(agora)` a partir da **posição real de reprodução** informada pelo
  mixer (amostras consumidas pelo dispositivo, descontada a latência de saída). Interrompida a
  fala, a trilha é descartada no mesmo instante: a boca fecha.
* Saída de áudio selecionável (novo) e volume da voz/efeitos.

### 5.4 Coordenador de tarefas — `ultron/core`, `ultron/cognition`, `ultron/agent` (existente, ampliado)
Recebe pedidos (voz, texto, TARDIS, botões) → classifica a intenção (regras rápidas em português
antes do modelo) → decide a rota (resposta direta, skill, TARDIS, Noctário, agente LLM) → executa
pelo `ExecutionEngine` → verifica → recupera dentro de limites → responde → registra.
* `permissions.py` (novo): cada skill pertence a uma categoria — **consultar**, **configurar**,
  **executar programas**, **robô**, **arquivos**, **apagar dados** — com política configurável
  (permitir / confirmar / bloquear) e pisos que a configuração não rebaixa: apagar dados e mover o
  robô sempre confirmam; a parada do robô nunca pede confirmação.
* `activity.py` (novo): histórico unificado (pedidos e respostas, ações, tarefas da TARDIS,
  operações do Noctário, erros), persistido, filtrável na página ATIVIDADES.

### 5.5 Inteligência — `ultron/models/`
Roteador existente + `openai_provider.py` (Responses API, ferramentas, pesquisa web, visão) com as
variáveis do original (`JARVIS_AI_PROVIDER`, `OPENAI_API_KEY`, `JARVIS_OPENAI_MODEL`,
`JARVIS_OPENAI_WEB_SEARCH`); chave no Gerenciador de Credenciais do Windows ou no ambiente; só
com consentimento explícito; falha da API → volta ao Ollama.

### 5.6 TARDIS — `ultron/tardis/` (lógica) e `ultron/hud/tardis_room/` (sala)
Ver §8.

### 5.7 Noctário — `ultron/noctario/` (PC) e `firmware/noctario/` (ESP32)
Ver §9.

### 5.8 Armazenamento
**Um único banco** (`ultron.sqlite3`); migração v4 acrescenta `tardis_tasks`, `project_notes`,
`noctario_runs`, `noctario_ops` e `activity`. Nenhum banco paralelo. Backups, exportação e
restauração existentes passam a cobrir as tabelas novas automaticamente (cópia do banco inteiro).

### 5.9 Logs e diagnóstico
Log existente (`logs\ultron.log`, rotação 5 MB × 3) e página DIAGNÓSTICOS: saúde de cada serviço
(voz, modelos, TARDIS, Noctário, renderização, GPU), diagnóstico de voz em 8 etapas, teste do link
do Noctário, visualizador de log com filtro e cópia.

### 5.10 Configurações
`SettingsManager` existente (validação, migração, cópia de segurança) com campos novos (página
inicial, modo do avatar, legendas, efeitos pesados, renderização CPU/GPU, saída de áudio, volumes,
privacidade, Observador, provedor de IA, Noctário, permissões). "Restaurar padrões" guarda antes
uma cópia do arquivo atual.

## 6. Fluxos

**Voz → resposta.** microfone → STT → palavra de ativação → `USER_INPUT` → intenção → rota →
execução (autorização quando a política pede) → verificação → `RESPONSE_READY` → síntese com
fonemas → reprodução + boca + legenda → registro.

**"JARVIS, consulte a TARDIS sobre X".** intenção `tardis.consult` → envelope de tarefa
(origem `jarvis`, cadeia `[jarvis]`) → TardisEngine executa o analisador → o avatar mostra
"Consultando a TARDIS" e o rotor mostra o elo com o JARVIS → resultado (ou motivo da falha) → o
JARVIS resume e fala → registro.

**"Noctário, inicie o percurso".** intenção `noctario.start` → categoria **robô** → confirmação
(movimento físico) → `START` enviado (estado **SOLICITADO**) → `ACK` + telemetria `st=RUN`
(estado **CONFIRMADO**) → "Noctário em movimento, confirmado pelo robô." Sem confirmação no prazo:
"Sem confirmação do robô; estado desconhecido."

**Parada de emergência.** Botão, F12, chip global ou "pare o Noctário" → `NoctarioService.estop()`
escreve **imediatamente** no transporte (byte `!` + `STOP`, repetidos até o `ACK`), sem fila, sem
modelo de linguagem e sem esperar animação. Sem link: "SEM CONEXÃO — use o botão físico".

## 7. Estados do avatar (sinais reais)

| # | Estado | Sinal | Prioridade |
|---|---|---|---|
| 12 | Modo de privacidade | modo de privacidade ativo (microfone fechado) | 1 (maior) |
| 11 | Erro de integração | componente falhou, modelo indisponível, link do Noctário perdido sem pedido, `runtime_state=ERROR` (janela de 8 s) | 2 |
| 9 | Aguardando confirmação | autorização pendente | 3 |
| 8 | Falando | áudio da fala em reprodução (posição real > 0 e < fim) | 4 |
| 10 | Apresentando alerta | lembrete devido, alerta do Noctário, aviso de saúde (janela de 6 s; tinge os demais estados) | 5 |
| 4 | Reconhecendo a fala | parciais do STT nos últimos 0,8 s com a escuta aberta | 6 |
| 3 | Escutando | escuta aberta (palavra de ativação ou continuação) | 7 |
| 6 | Consultando a TARDIS | tarefa da TARDIS com origem `jarvis` em execução | 8 |
| 7 | Executando uma tarefa | `EXECUTING`, `VERIFYING`, `RECOVERY` | 9 |
| 5 | Pensando | `THINKING`, `DECIDING`, `PLANNING`, `CONTEXT`, `PERCEIVING` | 10 |
| 1 | Inicializando | `BOOTING` (progresso real dos componentes) | 11 |
| 2 | Aguardando interação | nenhum dos anteriores | 12 |

## 8. TARDIS

### 8.1 Papel
Ambiente de **análise, planejamento e coordenação**. O JARVIS conversa; a TARDIS analisa. É um
**módulo lógico separado**, com fila, protocolo, analisadores e memória de projeto próprios. **Não é
um segundo modelo de IA**: quando precisa de linguagem natural, usa o **mesmo modelo local do
JARVIS** com instruções próprias, e isso é exibido em cada resultado ("modelo: qwen2.5:3b (o
mesmo do JARVIS)" ou "sem modelo: análise determinística").

### 8.2 Protocolo de tarefas
`TaskEnvelope`: `id`, `kind`, `input`, `origin` (`jarvis`, `tardis`, `agendador`), `chain`
(saltos), `state` (`QUEUED → RUNNING → DONE | FAILED | REJECTED | CANCELLED`), `result`
(resumo, itens, fontes, ações propostas), `error` (código e mensagem), `created/started/finished`,
`duration_ms`, `log` (operações relevantes), `model`.
Regras: a TARDIS **nunca** executa ações nem chama o JARVIS de volta; quando o resultado implica
ação, ela devolve **ações propostas** que o JARVIS só executa com a confirmação do usuário; cadeia
máxima de 2 saltos e nenhum salto repetido (impede ciclos de delegação); prazo por tipo;
cancelamento; sem dado suficiente → `FAILED` com o motivo (nunca um resultado inventado).

### 8.3 Analisadores
Consulta contextual (memória pessoal, fatos, notas de projeto, atividades — com fontes),
planejamento (decomposição em etapas, sem executar), organização (atrasados, conflitos, duplicados,
sem data), rotinas (agendamentos e recorrências), telemetria do Noctário (tempo de volta, RMS do
erro, oscilação, saturação, perdas de linha, intervalos entre cruzamentos, comparação entre voltas,
sugestões de ajuste **explicadas e nunca aplicadas sozinhas**), diagnóstico (saúde + voz +
Noctário + modelos → achados com gravidade), coordenação de módulos (quem está fazendo o quê),
memória de projeto (decisões, notas, histórico de parâmetros).

### 8.4 Sala de controle
Cena 3D: sala circular com paredes de nichos circulares ("roundels"), piso em grade concêntrica,
console hexagonal com seis painéis (ANÁLISE, PLANEJAMENTO, ARQUIVO, ROTINAS, TELEMETRIA,
DIAGNÓSTICO), **rotor temporal** vertical de vidro com elementos internos que sobem e descem, e
telas flutuantes com dados reais. O rotor reflete o estado real do `TardisEngine`: repouso lento;
processamento intenso; operação (estado próprio); falha (alerta específico); consulta do JARVIS
(feixe ligando o rotor ao emblema do JARVIS). Clicar num painel leva a câmera até ele e abre os
dados e ações daquela função; ARQUIVO abre a memória espacial existente.
Identidade própria: estrutura azul-petróleo profundo com energia âmbar/dourada do rotor — distinta
do ciano do JARVIS, na mesma família. Referência criativa à série Doctor Who, sem copiar
logotipos, sons ou elementos protegidos ("TARDIS" é marca da BBC: para distribuição comercial, o
módulo deve ser renomeado e a cena revisada).

## 9. Noctário

### 9.1 Divisão de responsabilidades
| Firmware (ESP32) | Aplicação (PC) |
|---|---|
| leitura dos 8 QTR e do sensor de cruzamento, calibração (NVS), posição da linha, **PD**, velocidade adaptativa, rampas, contagem de cruzamentos, parada no destino, perda de linha e recuperação limitada, parada por desconexão (política), *watchdog* de comunicação, LED, telemetria | conexão, comandos com número de sequência e prazo, estado **solicitado × confirmado**, telemetria ao vivo, alertas, histórico, análise de voltas (TARDIS), parâmetros com limites e confirmação, **parada de emergência imediata** |

### 9.2 Protocolo NOCT/1 (resumo; especificação completa na Fase 6)
Texto por linhas sobre SPP. PC → robô: `CMD <seq> <VERBO> [chave=valor…]`; byte `!` isolado =
parada imediata, tratado antes de qualquer análise de linha. Robô → PC: `HELLO`, `ACK <seq>`,
`NAK <seq> code=… msg=…`, `STA …` (estado completo), `TEL …` (telemetria periódica), `EVT …`
(cruzamento, perda/recuperação de linha, fim de percurso, falha, parada). Verbos: `PING`, `INFO`,
`STATUS`, `START`, `STOP`, `CAL`, `SET`, `GET`, `PARAMS`, `SAVE`, `DEFAULTS`, `RESETX`, `TEL`,
`SENS`, `MOTOR` (teste de bancada). Limites validados **nos dois lados**.

### 9.3 Simulação (rotulada)
Para testes automatizados e treino da interface sem o robô: um simulador do protocolo com modelo
cinemático simples. Só é usado quando escolhido explicitamente; toda tela mostra "SIMULADOR — não é
o robô" e os registros são marcados como simulados.

## 10. Threads e tempo real

| Thread | Faz | Nunca faz |
|---|---|---|
| Interface | desenha a partir de cópias de estado; envia pedidos | consulta ao banco, espera de rede, `sleep` |
| `ultron-speaker` | síntese, trilha da boca (≈15 ms por frase), espera da reprodução | — |
| *callback* de áudio (PortAudio) | mistura e posição de reprodução | trabalho pesado |
| `ultron-microphone` | captura e reconhecimento | — |
| `tardis-worker` | analisadores; modelo via roteador | executar ações |
| `noctario-reader` / *heartbeat* / reconexão | leitura e despacho de linhas; batimento; reconexão com espera crescente | controle de motor |

A parada de emergência é escrita pela thread da interface com prazo curto (escrita não bloqueante);
se falhar, a falha é mostrada na hora.

## 11. Desempenho (metas)

| Item | Meta |
|---|---|
| Avatar, perfil Equilibrado | ≤ 10–12 ms por quadro em 1320×820 neste contêiner; repouso na cadência ociosa do perfil; fala ≥ 30 quadros/s |
| Sala da TARDIS | estrutura estática em cache; só rotor, luzes e telas animados |
| Página do Noctário | gráficos ≤ 20 Hz; nada é desenhado com o robô desconectado além do estado |
| Página fora de vista | não desenha; o estado segue atualizado |

Toda melhoria será **medida** com `tools/benchmark.py` (ampliado), nas mesmas condições.

## 12. Segurança

* O modelo não executa código arbitrário, não acessa arquivos fora das skills e não aciona o robô
  sem validação; texto na tela é dado, nunca instrução.
* Operações destrutivas e movimento do robô exigem confirmação explícita; a parada nunca exige.
* A TARDIS não executa ações; só propõe.
* Credenciais (chave da OpenAI) no cofre do sistema operacional ou no ambiente; nunca no
  `settings.json` nem em logs.
* O Noctário é controlado só pelo Bluetooth pareado pelo usuário; descobrir um dispositivo não é
  autorização para controlá-lo.

## 13. Testes (estratégia)

Testes automáticos novos por módulo (avatar: estados e boca ligada ao áudio real; TARDIS:
protocolo, ciclos, falhas honestas; Noctário: protocolo, solicitado × confirmado, parada, perda de
conexão, por porta serial virtual e por servidor local; firmware: lógica compilada no PC com
`g++`), mais a regressão completa (Python 3.13 e 3.11). Testes com simulação são marcados como tal
e não substituem os testes com o robô, o microfone e o Windows reais — roteiro de validação na
entrega.
