# JARVIS ULTIMATE — Fase 1: inventário do JARVIS original, da plataforma atual e do Noctário

Este documento é o entregável 1 ("inventário de todas as funcionalidades originais"). Tudo o que
está aqui foi lido no código ou executado; o que não pôde ser verificado está marcado.
Os relatórios completos, linha a linha e com citações `arquivo:linha`, estão em
[`docs/inventario/`](docs/inventario/).

## 1. O que existe e onde

| Material | Onde | Situação |
|---|---|---|
| **JARVIS original** (o seu código) | commit `53e5a31` ("up"), pasta `JARVIS/` | Removido da árvore pelo commit `d77db35` ("ULTRON build … remoção do JARVIS"); continua íntegro no histórico: `git show 53e5a31:JARVIS/<arquivo>` ou `git archive 53e5a31 JARVIS` |
| **Plataforma atual** (evolução do original: ULTRON → JARVIS) | `ULTRON/` (pacote Python `ultron`) | 157 módulos, ~31 mil linhas, 93 skills, 197 testes automáticos (todos passando em Python 3.13 e 3.11 no início desta missão) |
| **Noctário** (firmware, esquemas, código da ESP32) | — | **Não existe no repositório.** Procurado em todos os commits: nenhum `.ino`, `.cpp`, `.h`, `platformio.ini`, nenhuma menção a ESP32, TB6612, QTR ou Noctário. Só há a especificação da sua mensagem (ver §7) |

Números do original: 131 arquivos Python (26.196 linhas, das quais 38% são cópias de backup como
`*_BACKUP_*`, `*_ANTES_*` e `_backup_antes_do_copilot/`), 46 documentos de fases, 21 scripts de
teste, modelos Vosk (pequeno e grande), voz Piper `pt_BR-faber-medium`, ícones.

## 2. Como o original realmente funcionava

Leitura do código e execução de partes com *stubs* (nada foi executado em Windows):

| Caminho | Situação no original | Evidência |
|---|---|---|
| `START_JARVIS.bat` → `main.py` → `core/brain.py` | **Quebrado**: `AttributeError` antes de a interface abrir (`goal_manager.summary/active/activate/checkpoint` não existem) | `core/brain.py:25-34`, `goal_manager.py:26-47` |
| `Abrir_JARVIS.bat` / autostart → `jarvis_hud.py` | **Funcionava** (era a entrada real): HUD + `backend.py` (voz, TTS, agente Ollama, memória) + `copilot.py` + `telemetria.py` | `jarvis_hud.py:3097-3114` |
| Observador (`copilot.py`), ciclo de visão | **Quebrado**: `autonomous_perception` usado sem import → `NameError` engolido em todo ciclo; tudo "depois" da visão (agente autônomo, `autonomous_core`, `execution_loop`) nunca rodava | `copilot.py:892,902,939` |
| `config.db_dir()` | **Não existe**: `context_state.json`, `orchestrator_state.json`, `apps_index.json` nunca eram gravados | `context_state.py:33`, `orchestrator.py:29`, `app_index.py:64` |
| Integração OpenAI (`openai_provider.py`) | **Não conectada**: só usada por `testar_openai.py`; `chat()` lia `config.OPENAI_WEB_SEARCH`, que não existe | `openai_provider.py:168` |

## 3. Inventário por área (resumo)

Status em relação à plataforma atual: **PRESERVADO** (equivalente presente), **PARCIAL** (existe,
com diferença material), **AUSENTE**, **SUBSTITUÍDO** (trocado de propósito por outro mecanismo).

### 3.1 Comandos e ferramentas ([detalhes](docs/inventario/comandos.md))

| Conjunto | Preservado | Parcial | Ausente | Total |
|---|---|---|---|---|
| Comandos diretos (54 rotas do `commands.handle` + 5 do backend) | 46 | 10 | 3 | 59 |
| Ferramentas do agente (LLM) | 33 | 5 | 3 | 41 |
| Automações por frase exata (aspectos) | 6 | 1 | 2 | 9 |

Verificação: o roteador original foi executado com *stubs* (nenhuma ação real) e cada frase de
exemplo foi classificada pelo `IntentEngine` atual.

Principais lacunas:

* **Defeito real de migração.** As automações do banco original são importadas com o nome antigo
  da ferramenta (`open_app`, `search_web`…) e **não executam** ("skill 'open_app' não existe").
  Como as automações têm prioridade sobre os comandos, uma automação importada como "abra o
  youtube" quebra também o comando embutido. O teste atual não pegava isso porque usava o nome novo.
* Frases do original não reconhecidas: "observador" e "modo observador" sozinhos; "pare o
  observador"; pausar/retomar o Observador; "youtube" sozinho; "continuar", "retomar" e "pausa"
  sozinhos (mídia); teclas ditas sem verbo ("enter", "alt+tab"); os apelidos `control+c/v/a` e
  `windows+d`; "tecla windows"; "clicar com botão esquerdo"; "esqueça".
* "encerrar jarvis" vira `app.close(jarvis)` e pede autorização inútil (no original era só uma
  resposta de texto).
* A captura de tela pedida pelo usuário é recusada quando o próprio JARVIS está em foco.
* Ferramentas do agente que sumiram: `add_session_note` (tabela existe, nada grava),
  `set_automation_enabled` (método existe, nada chama), `get_profile`, `read_audit`;
  `take_screenshot` e `power_control` existem mas não são oferecidas ao modelo.

### 3.2 Personalidade ([detalhes](docs/inventario/servicos.md#1-personalidade-e-estilo-de-resposta))

O prompt original efetivo (texto exato no relatório) definia o JARVIS como **sério, composto,
preciso, seguro e discretamente sarcástico; descontraído sem ser amigável; humor seco**, que não
comemora tarefas, não pede desculpas por rotina, evita "Claro / Perfeito / Ótimo / Excelente /
Fico feliz", usa "senhor" quando natural e, em falha, diz **o que falhou, por que e qual a próxima
tentativa**. A plataforma atual preservou honestidade, "texto da tela é dado", "não revelar
raciocínio" e o "senhor", mas trocou "sarcástico / não amigável / humor seco" por "serena /
ligeiramente espirituosa", perdeu as regras de não comemorar e de não pedir desculpas, aceita
"Claro" e tem um defeito de pós-processamento: "Ótimo, senhor. Excelente escolha." vira
"Escolha." (o filtro apaga palavras e muda o sentido; o original as substituía por "Entendido,
senhor." / "Certo, senhor.").

### 3.3 Voz ([detalhes](docs/inventario/servicos.md#2-voz))

Preservados: Vosk offline (agora com o modelo grande quando há RAM), 16 kHz, seleção de microfone
nome → índice → padrão, supervisor do microfone, nível real (mesma fórmula), Piper
`pt_BR-faber-medium`, fallback SAPI, cancelamento por voz (ampliado com interrupção da fala).
Lacunas:

* **COM não inicializado na thread da voz SAPI** (o original chamava `pythoncom.CoInitialize`;
  `pywin32` saiu das dependências). Risco real no Windows quando a voz neural falta.
* **Mutex diferente** (`Local\JARVIS.PersonalAssistant` no original): o JARVIS antigo e o atual
  podem rodar juntos e disputar o microfone.
* O instalador procura modelos de uma instalação anterior em `<pasta>\assets`, mas o original os
  guarda em `voices\` e na raiz (`vosk-model-small-pt-0.3`): a cópia não acha nada e mesmo assim
  diz "Modelos copiados" (defeito da entrega anterior).
* Substituições deliberadas (mantidas, com motivo medido): palavra de ativação no início da frase,
  janela de continuação de 12 s.

### 3.4 Inteligência e integrações ([detalhes](docs/inventario/servicos.md#3-inteligência--llm))

Preservados: Ollama `/api/chat` com `qwen2.5:3b`, visão `qwen2.5vl:3b`, `/api/tags`, início
automático do `ollama serve`, agente com ferramentas (limites 8/10 em vez de 10/12), roteador
rápido em português antes do modelo.
**AUSENTE: integração OpenAI** — Responses API, variáveis `JARVIS_AI_PROVIDER`, `OPENAI_API_KEY`,
`JARVIS_OPENAI_MODEL`, `JARVIS_OPENAI_WEB_SEARCH`, pesquisa web e visão pela OpenAI, *fallback*
OpenAI → Ollama. No original ela estava documentada e parcialmente escrita, mas não conectada; a
plataforma atual só tem um plugin genérico de Chat Completions com outras variáveis.

### 3.5 Observador e visão ([detalhes](docs/inventario/servicos.md#4-observador--copilot-e-agente-visual))

Preservados: análise da tela sob demanda, OCR, UI Automation, clique por descrição com
confirmação, filtros de privacidade e de *prompt injection* (lista e regex idênticas), oferta de
análise quando o título da janela indica erro.
Diferenças importantes:

* **No original o Observador sempre iniciava DESATIVADO** e tinha modos (desativado, assistente,
  autônomo supervisionado, observador) com consentimento por sessão. **Na plataforma atual a
  observação de tela vem ligada por padrão** e não há modos — regressão de privacidade em relação
  ao original.
* Sem pausar/retomar; exclusões do usuário sem interface e sem migração do `copilot.json`;
  detecção de alternância repetitiva entre apps ausente.
* O hand-off autônomo e a execução automática do modo AUTÔNOMO eram inalcançáveis no original
  (quebrados); a plataforma atual exige aceite para tudo o que nasce da observação (mantido).

### 3.6 Memória e dados ([detalhes](docs/inventario/servicos.md#5-memória-e-dados))

O banco original `%LOCALAPPDATA%\JARVIS\assistant.sqlite3` é importado uma vez (só leitura):
fatos (sem segredos), 4 preferências e automações (com o defeito do §3.1). Não migrados:
`session_notes`, `audit`, tabelas de aprendizado (do caminho quebrado), preferência
`personality`, `copilot.json` (exclusões e intervalo), `initiative.json`, `permissions.json`.
O filtro de segredos, que no caminho ativo do original **não** era aplicado, hoje é aplicado em
toda gravação.

### 3.7 Telemetria, sistema e dependências ([detalhes](docs/inventario/servicos.md#6-telemetria-autostart-diagnóstico-configuração-dependências-e-testes))

Preservados: CPU/RAM, bateria, GPU (`nvidia-smi`), Wi-Fi, latência do Ollama, host/uptime, "N/D"
quando falta dado, autostart pelo Registro (mesmo valor "JARVIS"), diagnóstico (ampliado), log
com rotação. Ausentes: **taxa de rede (download/upload)**, contagem de automações, verificação da
entrada de autostart (hoje qualquer valor "JARVIS" — inclusive o do original — conta como
ativado), `pywin32`.

### 3.8 Interface (HUD) e tela de sessão ([detalhes](docs/inventario/interface.md))

| Conjunto (80 recursos da versão final) | Preservado | Parcial | Ausente | Substituído |
|---|---|---|---|---|
| Elementos centrais | 3 | 4 | 3 | 0 |
| Estados, efeitos e camadas | 2 | 4 | 6 | 5 |
| Painéis e interações | 3 | 11 | 8 | 4 |
| Janela, bandeja, botão flutuante, atalhos, início | 10 | 5 | 3 | 6 |
| Tela de sessão (PIN) | 0 | 0 | 2 | 1 |

* **Elemento central ao longo do tempo:** avatar humanoide holográfico em wireframe (Fase 13) →
  globo wireframe → cérebro de partículas. Na versão final o avatar e o globo eram **código morto**
  (não instanciados); o rosto da nova interface é um projeto novo que herda o DNA visual do avatar
  (plataforma de projeção, varredura, partículas que sobem, reator, "MARK VII").
* **Ausentes que voltam:** clique no núcleo liga/pausa o microfone, grade/scanlines/partículas e
  varredura de fundo, menu de clique direito dos módulos (ativar/pausar escuta, reiniciar voz,
  pausar automação, parar tarefa, copiar), histórico de atividade, **console de eventos com filtro,
  COPIAR e LIMPAR**, botões STATUS e HORAS, **COPIAR RESPOSTA**, **LIMPAR + Ctrl+L**, indicador
  "observação suspensa — HUD aberta" (o sensor de tela já aceita a informação, mas a interface não
  a envia), relógio e data, bandeja com pausar/retomar automação e "Iniciar com Windows".
* **Parciais que serão completados:** painel de status com barras e faixas de cor, chips da barra
  superior (bateria, Wi-Fi, tempo de sessão, LEDs de voz e IA), rede com tráfego, botão PARAR,
  exclusões do Observador editáveis, orbe que guarda a posição, reinício da voz, log que captura
  exceções não tratadas, início recolhido configurável.
* **Substituições mantidas:** estado central e Event Bus no lugar dos motores visuais paralelos;
  tema único azul (a troca de tema do original já não fazia nada: só havia um tema); notificações
  nativas.
* **Tela de sessão com PIN:** no código enviado é um **esboço desativado** (`jarvis_lock.py` não
  implementa o que o `README_TELA_JARVIS.md` descreve); o formato do `lock.json` não pode ser
  verificado. **Não será recriada às cegas** — se você tiver a versão funcional, envie-a.

## 4. O que funcionava, o que estava incompleto e o que estava quebrado no original

* **Funcionava** (caminho `jarvis_hud.py`): voz Vosk + supervisor, nível do microfone, TTS Piper
  com fallback SAPI e COM, agente Ollama com 32 ferramentas e confirmação falada, roteador regex,
  memória/preferências/automações, telemetria real, HUD (cérebro de partículas, painéis,
  console de eventos, conversa com botões e Ctrl+L, bandeja, botão flutuante, F11, instância
  única), autostart.
* **Incompleto ou não integrado**: OpenAI, agente visual (`visual_computer_task` nunca
  registrado), `ConversationEngine`, voz proativa, roteadores de inteligência (só informativos),
  gerenciador de missões, `session_notes`, auditoria pelo modelo, índice do menu Iniciar
  (`app_index.py`, nunca importado), teste do Whisper (script avulso).
* **Quebrado**: entrada `main.py`, ciclo de visão do Observador, persistência de contexto
  (`db_dir`), modo OBSERVADOR no botão flutuante (`KeyError`), `test_fase18.py`,
  `testar_neural_core.py`; a tela de PIN era só um esboço desativado.

## 5. Lista de recuperação (entra na Fase 3)

Itens do original que a plataforma atual perdeu ou degradou e que serão restaurados, sem
regredir o que já funciona:

1. Migração das automações com o mapeamento de nomes (e reparo das já importadas); pausar e
   reativar automações; automação de captura de tela.
2. Personalidade original (tom, regras, substituições em vez de cortes) mantendo as regras de
   honestidade atuais.
3. Observador com modos e **desligado ao iniciar**, como no original; comandos de pausar/retomar
   e as frases "observador", "acompanhe o que eu fizer…"; exclusões na interface e migração do
   `copilot.json`.
4. Frases e apelidos de comandos perdidos (§3.1); "encerrar o JARVIS" como encerramento real com
   confirmação; captura de tela pedida pelo usuário com o JARVIS em foco.
5. Ferramentas do agente: notas de sessão, perfil, auditoria, ativar/desativar automação,
   captura de tela e energia oferecidas ao modelo (energia sempre com confirmação).
6. COM na thread da voz SAPI (`pywin32`); mutex do JARVIS original também respeitado.
7. Instalador: copiar modelos de `voices\` e da raiz da instalação original, verificando o que
   foi copiado.
8. Integração OpenAI (Responses API, variáveis do original, pesquisa web, visão, *fallback*), com
   a chave no Gerenciador de Credenciais do Windows ou na variável de ambiente — nunca em texto
   no `settings.json` — e só com consentimento explícito (os dados saem do computador).
9. Taxa de rede na telemetria; contagem de automações; verificação da entrada de autostart.
10. Itens da interface original (§3.8): clique no núcleo para o microfone, console de eventos,
    botões STATUS/HORAS/PARAR/COPIAR RESPOSTA/LIMPAR (+ Ctrl+L), relógio e data, chips de bateria,
    Wi-Fi e sessão, "observação suspensa" com a interface cobrindo a tela, bandeja (pausar/retomar
    automação, iniciar com Windows, reiniciar voz), orbe que guarda a posição, log de exceções não
    tratadas.

Não serão restaurados (com motivo): os 5 estilos de personalidade (no original a personalidade
estava travada em "jarvis"); o hand-off autônomo do Observador e a execução automática do modo
AUTÔNOMO (eram inalcançáveis no original e contrariam a regra de confirmação proporcional); o
agente visual e o Whisper (nunca integrados; ficam no plano de evolução).

## 6. Plataforma atual: o que já existe e será a base

Núcleo por eventos (Event Bus, estado central único, ciclo de vida, workers), executor com
autonomia por risco e autorização escopada, verificação e recuperação, 93 skills, memória pessoal
com lembretes determinísticos, TARDIS como memória espacial, rede local passiva, voz restaurada
com diagnóstico de 8 etapas, perfis de qualidade medidos, scripts do Windows, 197 testes. Detalhes
em `ARCHITECTURE_JARVIS.md`, `README_JARVIS.md` e `TEST_REPORT.md`.

## 7. Noctário

**Nenhum código do Noctário foi fornecido** (procurado em todo o histórico). O que existe é a
especificação da sua mensagem:

| Item | Especificação recebida |
|---|---|
| Placa | ESP32 DevKit (Bluetooth Clássico) |
| Driver | TB6612FNG — STBY GPIO 5 |
| Motor direito | PWMA GPIO 21, AIN1 GPIO 18, AIN2 GPIO 19 |
| Motor esquerdo | PWMB GPIO 23, BIN1 GPIO 4, BIN2 GPIO 22 |
| Sensores QTR analógicos (8) | GPIO 32, 33, 25, 26, 27, 14, 12, 13 |
| Sensor de cruzamento (digital) | GPIO 34 |
| LED de status | GPIO 15 |
| Pista | preta com linha branca |
| Controle | PD; PWM base 220; PWM máximo inicial 220; Kp 0,0125; Kd 0,1; velocidade adaptativa; rampas de aceleração e frenagem; 4 cruzamentos até o destino |
| Tempo atual de percurso | ≈ 5 min 40 s |

O firmware será escrito a partir desta especificação, com a pinagem exatamente como recebida.
Pontos que **só o código original pode confirmar** e que ficam como parâmetros ajustáveis e
testes de bancada até lá: ordem física dos sensores (esquerda → direita), sentido de rotação de
cada motor (AIN1/AIN2), nível lógico do sensor de cruzamento, frequência/resolução do PWM, ritmo
do laço de controle (o Kd depende dele), rotina de calibração e política original de desconexão.

Observações de hardware que o código não resolve (registradas para a montagem):

* GPIO 25, 26, 27, 14, 12 e 13 são canais do **ADC2**, que deixa de funcionar com o Wi-Fi ligado:
  o firmware nunca liga o Wi-Fi.
* GPIO 12 é pino de *strapping*: em nível alto no boot pode impedir a ESP32 de iniciar (tensão do
  flash). Se o robô não ligar sobre a pista, a solução é fixar a tensão do flash por eFuse ou
  trocar o sensor de pino.
* GPIO 34 é só entrada e não tem *pull-up* interno: o sensor de cruzamento precisa de resistor
  externo se a saída for de coletor aberto.
* GPIO 5 (STBY) e 15 (LED) também são de *strapping* e podem pulsar no boot: o firmware coloca o
  STBY em nível baixo antes de qualquer outra coisa; um *pull-down* externo no STBY evita
  trancos de motor durante o boot.
* A parada pelo Bluetooth não substitui um botão físico de emergência que corte a alimentação dos
  motores.

**Material solicitado:** o firmware original do Noctário (arquivo `.ino` ou projeto PlatformIO),
para conferir a pinagem e preservar o comportamento que ele já tem.

## 8. Capacidades do ambiente, verificadas para planejar

| Verificação | Resultado |
|---|---|
| Voz Piper instalada fornece fonemas por frase | **Sim** (IPA do espeak). Duração de cada fonema: **não** (o modelo `faber-medium` não exporta alinhamento) |
| Renderização 3D em tempo real com QPainter | Protótipo medido: rosto holográfico 3D (malha projetada, iluminação, silhueta, brilho) entre ~14 e ~17 ms por quadro em 1320×820 neste contêiner; o custo é por segmento traçado (reduzir a resolução não ajuda), então a densidade da malha entra nos perfis de qualidade |
| QPainter sobre OpenGL (`QOpenGLWidget`) | Funciona (verificado com Mesa sob Xvfb): mesma imagem; desempenho real depende da GPU |
| Qt Quick 3D | Ausente do pacote usado (`PySide6-Essentials`) |
| Compilar para ESP32 aqui | **Não** (servidores da Espressif/Arduino/PlatformIO bloqueados neste ambiente); compilador C++ do PC disponível para testar a lógica do firmware |
| Bluetooth real neste ambiente | Não há adaptador; o transporte será testado por porta serial virtual e servidor local |
