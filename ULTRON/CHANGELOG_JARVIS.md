# JARVIS — Registro de mudanças

Transformação do ULTRON em JARVIS, na ordem obrigatória das fases (A → I). Cada fase foi
testada antes do commit; os commits estão na branch `claude/adoring-brahmagupta-vcejpt`.

## Fase A — Auditoria (commit `1b4b8e2`)
* Mapa real dos subsistemas, testes existentes (131 OK em Python 3.13 e 3.11), inicialização
  real sem exceções. Relatório: `docs/JARVIS_AUDITORIA_E_PLANO.md`.
* Voz **medida**: o Vosk transcreve "Jarvis" como "aviso", "aves", "já vi", "davis";
  gramática restrita descartada (22/22 falsos positivos no modelo grande, 0/14 no pequeno).
* Linha de base de desempenho gravada (`docs/benchmarks/before_jarvis.json`).

## Fase B — Plano
* Prioridades P0 (voz, identidade, Event Bus), P1 (tema, TARDIS, desempenho, memória, rede),
  P2 (autonomia escopada, entrega). Preservar o que funciona; mudar só o necessário.

## Fase C — Estabilização (commits `369d368`, `e692875`)
* **Voz restaurada**: palavra de ativação "Jarvis" com formas medidas (fortes; nomes só no
  início; fracas só com comando reconhecido); formas do ULTRON migradas; calibração ao vivo.
* **Microfone**: PyAudio e, na falta ou falha, **sounddevice**; dispositivos que recusam 16 kHz
  abrem na taxa nativa com reamostragem (filtro FIR); silêncio absoluto detectado
  (privacidade do Windows); escolha de microfone na interface e no console.
* **Diagnóstico de voz em 8 etapas** (interface, `--voice-test`, `--diagnose`, "diagnóstico de
  voz"), que espera o modelo carregar e mostra evidência por etapa.
* Encerramento ordenado de fala e saída de áudio (threads com `join`).
* **Event Bus**: aviso de descarte agregado a cada 5 s (antes: uma linha de log por evento).
* Configurações v2 com migração da identidade ULTRON e cópia de segurança
  (`settings.ultron-backup.json`); variáveis `JARVIS_*` (aceita `ULTRON_*`).
* Pedidos de autorização citam o recurso exato (registro, quantidade, URL).

## Fase D — Desempenho (commit `a706c27`)
Medido com `tools/benchmark.py` (agora cobre TARDIS, perfis e orbe). Detalhes e números
finais em `PERFORMANCE_REPORT.md`.
* Causa do CORE "nunca em repouso": a verificação de saúde de rotina (a cada 15 s) fazia a
  sinapse de TELEMETRIA crescer e prendia o teto de quadros por ~4 s. Agora só mudanças reais
  de saúde animam (assinatura do quadro de problemas).
* Repouso com giro mais lento e cadência ociosa menor (Econômico 10, Equilibrado 15, Alto 24,
  Cinematográfico 40 quadros/s).
* Hub atrás do outro (CORE atrás do TARDIS e vice-versa) cai para a cadência de fundo.
* TARDIS: camada estrutural em cache (fundo, anéis, corredores, portais, textos), traços
  cosméticos de 1 px (caminho rápido do QPainter), marcas dos anéis giradas por
  transformação, desenho direto durante a viagem da câmera.
* Percepção relaxa os intervalos com o usuário ausente (> 5 min) e restaura ao voltar.

## Fase E — Identidade JARVIS (commits `369d368`, `329a37c`)
* Nome JARVIS em janelas, textos, mensagens, notificações, bandeja, voz, prompts e scripts;
  pacote `ultron`, pasta de dados e mutex preservados por compatibilidade.
* Personalidade: inteligente, serena, confiante, analítica, elegante, ligeiramente
  espirituosa e profissional; uma pergunta objetiva quando falta o essencial; nunca afirma
  execução sem verificação.
* Voz masculina, grave e natural (perfil JARVIS), mais inteligível que a anterior (medido).
* Tema único azul profundo/ciano com fonte única (`hud/palette.py` → `hud/theme.py`).
* Estados visuais ligados a sinais reais: repouso azul profundo, escuta (halo pelo nível do
  microfone), percepção (ondas por análise real), planejamento (conexões acesas conforme as
  etapas terminam), execução (pulsos das operações), memória (nós em azul), fala (anéis pelo
  nível da voz), imaginação (profundidade), erro (contorno fixo, sem alarme).
* Ícone novo em vários tamanhos.

## Fase F — TARDIS e memória pessoal (commits `e692875`, `a706c27`)
* **TARDIS**: câmara central (hoje), anéis concêntricos, corredores e portais com registros
  reais, partículas com orçamento, pulsos só para eventos reais, câmera com transição suave,
  painel lateral de consulta/edição, captura rápida, som ambiente opcional, volta ao CORE sem
  perder o estado.
* **Conflitos de agenda** informados (nunca bloqueados) na captura, edição, TARDIS e linha do
  tempo.
* **Exportação** JSON/CSV para arquivo novo; **backup** consistente diário com rotação;
  restauração segura só com o JARVIS fechado.
* Filtros de prioridade e período (30 dias, sem data) nas tarefas.

## Fase G — Rede local (commit `9b5aba1`)
* Observação honesta por aparelho (respondeu recentemente / inferido / conhecido antes / sem
  resposta / este computador), gateway, interface, primeira e última vez, origem e
  confiabilidade; desconhecido aparece como desconhecido.
* **Descobrir ≠ administrar**, explícito por aparelho e na tela.

## Fase H — Validação (commit `10b0ab6` e seguintes)
* **Autorização permanente escopada** ("sim, sempre" / SEMPRE 24 h): mesma ação + mesmo
  recurso + validade; nunca para sensível, crítico, irreversível ou proativo; revalidada a
  cada uso; revogável. Aba **AUTONOMIA** com histórico e registro de ações.
* Falhas de varredura de rede sempre registradas como limitação visível.
* Novos testes: memória pessoal completa, dois hubs com núcleo real, desempenho/cadência,
  identidade de estados, autorização escopada, integridade (todos os módulos importam),
  falha de rede, parada limpa por `--stop`.

## Fase I — Entrega
* `README_JARVIS.md`, `ARCHITECTURE_JARVIS.md`, `PERFORMANCE_REPORT.md`,
  `VOICE_DIAGNOSTICS.md`, `TEST_REPORT.md`.
* Scripts: `INSTALL_JARVIS.bat` (não apaga nada; copia modelos de uma instalação anterior só
  quando faltam), `START_JARVIS.bat` (`--status`, `--stop`, `--diagnose`, `--voice-test`,
  `--backup`…), `ATUALIZAR_JARVIS.bat` (para, faz backup, atualiza, diagnostica),
  `DIAGNOSTICO_JARVIS.bat` (componentes ausentes, saúde, voz, backups); `START_ULTRON.bat`,
  `INSTALL_ULTRON.bat` e `TEST_ULTRON.py` mantidos como atalhos de compatibilidade.
* `--status` e `--stop` (parada normal pedida à instância em execução, sem forçar).
* Dependências: `sounddevice` obrigatório (funciona sem PyAudio), `tzdata` no Windows.
* `JARVIS_FINAL.zip` sem `.venv`, caches, dados pessoais nem modelos grandes.
* `tools/build_release.py`: o pacote sai só de arquivos versionados no Git, é validado
  (conteúdo obrigatório, nada proibido, `.bat` em ASCII com CRLF, tamanho) e foi **testado depois
  de extraído** numa pasta nova.
* Esse teste encontrou um defeito: o diagnóstico de voz acusava "modelo ausente" quando os
  arquivos não estavam no disco, mesmo com o reconhecedor carregado e em uso. Agora a etapa 5
  confia primeiro no reconhecedor em uso; teste de regressão em `test_jarvis_voice.py`.

---

# JARVIS ULTIMATE — JARVIS original + TARDIS + Noctário

## Fases 1 e 2 — Auditoria e arquitetura (commit `a725f56`)
* `INVENTARIO_JARVIS_ORIGINAL.md` (e `docs/inventario/`): o que o JARVIS original tinha, o que
  funcionava, o que estava quebrado e o que precisava voltar. `ARQUITETURA_ULTIMATE.md` e
  `DESIGN_VISUAL.md`: módulos, protocolos, estados, identidades visuais.

## Fase 3, parte 1 — Recuperação do original no núcleo (commit `fb55f2d`)
* Observador (desligado ao iniciar, pausar/retomar), **modo privacidade** que fecha o microfone
  de verdade, automações do original reparadas (nomes antigos mapeados), personalidade do
  original, frases de encerramento, teclas e apelidos do original, mutex do original respeitado,
  `--autostart-check`, importação de modelos sem sobrescrever, **OpenAI** opcional (Responses
  API, chave no cofre do sistema, LOCAL MODE bloqueia, falha → Ollama), notas de sessão.

## Fase 3, parte 2 — Permissões, histórico e a plataforma (commits `bab7370` e seguinte)
* **Permissões por categoria** aplicadas pelo executor, com pisos (apagar dados e robô nunca
  abaixo de "confirmar") e parada de emergência sempre liberada.
* **Histórico de atividades** no mesmo banco (migração v4), alimentado pelo núcleo, pelo
  executor e pelos eventos; skills `activity.recent` e `activity.clear`.
* **Plataforma**: janela única com navegação F1–F7, páginas preservadas, transição
  holográfica, barra superior com estado e indicadores reais, conversa do original (horários,
  STATUS, HORAS, PARAR, COPIAR RESPOSTA, LIMPAR, Ctrl+L), Esc como no original, histórico ↑/↓
  com rascunho, ENVIAR.
* Páginas **ATIVIDADES**, **CONFIGURAÇÕES** e **DIAGNÓSTICOS** (console de eventos, log,
  serviços e GPU); TARDIS e Sistemas embutidos sem perder estado.
* Bandeja: Reiniciar voz, Modo privacidade, Observador (modos e pausa), Iniciar com o Windows.
* **Saída de áudio** selecionável; orbe lembra a posição; a interface informa quando cobre a
  tela (observação suspensa); "encerre o JARVIS" fecha a interface e o modo console;
  exceções não tratadas vão para o log.
* Testes: 263 aprovados em Python 3.13 e 3.11 (novos: permissões, histórico, plataforma).

## Fase 4 — Rosto holográfico, boca sincronizada, 12 estados e legendas
* `hud/avatar/`: geometria esculpida (NumPy; normais em repouso calculadas uma vez, só a parte de
  baixo recalculada quando a mandíbula abre), os 12 estados por sinais reais (função pura, prioridade
  da arquitetura), animador (cabeça, olhar, piscadas, expressões, montagem pelo progresso real do
  boot, pulsos de conexão/desconexão), renderização por camadas com QPainter (fundo em cache, grade
  3D, anéis de dados, partículas, varredura, brilho em NumPy) e widget CPU ou GPU (QOpenGLWidget com
  o mesmo desenho; volta para a CPU com o motivo).
* `voice/lipsync.py`: visemas pelos fonemas do Piper sobre os trechos sonoros do áudio real
  (alinhamento do modelo quando existir; espectro quando não há fonemas); abertura pela energia real.
* `Speaker`: síntese por frase com fonemas; `mouth()`, `caption()` e `audible()` pela posição real de
  reprodução; interromper fecha a boca no mesmo quadro. Indicador "reconhecendo" na voz.
* Indicador de estado da barra superior = estado resolvido do avatar.
* Otimização medida: traços longos com caneta de 1 px (o caminho rápido do QPainter) — 21–29 ms →
  11–15 ms por quadro no perfil equilibrado a 1280×760.
* `tools/benchmark_avatar.py` e `docs/benchmarks/avatar_fase4.json`.
* Testes: `test_avatar.py` (12) e `test_lipsync.py` (8, inclusive com a voz Piper real quando
  instalada).


## Fase 5 — TARDIS: segundo cérebro, sala de controle 3D e rotor ligado ao estado real
* `tardis/`: módulo lógico com protocolo de tarefas (`id`, entrada, estado, resultado, erros, tempos,
  origem, cadeia, registro de operações e modelo usado), fila e thread próprias, prazo por tipo,
  cancelamento imediato, análise travada abandonada com TIMEOUT sem parar a fila, tarefas
  interrompidas marcadas na abertura seguinte. Cadeia de delegação verificada na entrada: no máximo
  2 saltos, nenhum repetido, a TARDIS nunca devolve tarefas ao JARVIS.
* Persistência no **mesmo banco** (migração v5: `tardis_tasks` e `project_notes`); textos que parecem
  segredo redigidos; a memória de projeto recusa senhas e tokens. Cada tarefa entra no histórico de
  atividades, ligada à ação e ao pedido que a originaram (o executor agora leva o vínculo do histórico
  para a thread da skill).
* Analisadores: consulta contextual com fontes (segue os registros de um projeto encontrado; nunca usa o
  próprio pedido como fonte), planejamento (exige o modelo), organização, rotinas, telemetria do
  Noctário (tempo, RMS do erro, oscilação por cruzamentos e FFT, saturação, perdas, cruzamentos,
  comparação entre voltas; voltas do simulador rotuladas e nunca viram comando), diagnóstico e
  coordenação. Sem dado → FAILED com o motivo. Linguagem natural com o **mesmo modelo do JARVIS**,
  identificado em cada resultado; sem modelo, "sem modelo: análise determinística".
* A TARDIS só **propõe** ações. Pelo JARVIS, a proposta vira sugestão ("sim"/"não"); comandos ao robô e
  apagar dados não são pré-aprovados — o executor pede a confirmação da categoria.
* Skills `tardis.consult` e `tardis.note`; intenções "consulte/pergunte à TARDIS…", "TARDIS, organize/
  planeje/diagnostique…", "anote na TARDIS…", "memória de projeto…"; "abra a TARDIS" (sala) e "abra o
  segundo cérebro" (ARQUIVO). "Cancelar" para as consultas do JARVIS à TARDIS.
* Núcleo: TARDIS no ciclo de vida e no monitor de saúde; backups, exportações e escritas acendem o modo
  OPERAÇÃO do rotor (o backup automático também).
* `hud/tardis_room/`: sala de controle 3D em QPainter — console hexagonal com seis painéis clicáveis,
  rotor de vidro que sobe e desce pelo modo REAL (repouso, processando, consulta do JARVIS com o feixe
  JARVIS ⇄ TARDIS, operação, falha com anel no piso), paredes com círculos, piso, colunas, telas
  flutuantes com a fila e o último resultado. Painéis laterais por tipo de análise, resultado com fontes
  (texto do modelo sempre escapado), **APLICAR** pelo executor, **CANCELAR**, lista de tarefas.
* Página TARDIS = sala de controle + ARQUIVO (a memória espacial anterior, intacta; "← SALA DE
  CONTROLE"). Cada vista preserva o próprio estado; Esc solta o painel ou fecha a região.
* Desempenho medido (contêiner Linux, Qt offscreen, CPU; medianas): câmera parada 7,7–11,0 ms por
  quadro a 1280×720 e 8,9–14,4 ms a 1920×1080; volta da câmera até um painel 23,5–36,1 ms (só durante
  ~1 s); ida e volta de uma tarefa no motor 0,8 ms. A sala anima a no máximo 24 quadros/s e usa no máximo 25% da
  thread da interface. `tools/benchmark_tardis_room.py` e `docs/benchmarks/tardis_room_fase5.json`.
* Testes: `test_tardis_logic.py` (33) e `test_tardis_room.py` (12); `test_tardis.py` e
  `test_platform.py` atualizados para o ARQUIVO dentro da página TARDIS.

## Fase 6 — Noctário: firmware ESP32, protocolo Bluetooth, serviço, skills e painel
> O código original do Noctário **não foi fornecido**. O firmware foi escrito a partir da especificação
> (pinagem, parâmetros iniciais, comportamentos); o que só o original confirma virou parâmetro ajustável
> e está listado em `firmware/noctario/README.md` (A CONFIRMAR), junto com o pedido do código.

* **Firmware** (`firmware/noctario/`): núcleo sem Arduino (`noct_core.cpp`: protocolo, 12 estados, posição
  da linha com 8 QTR, linha branca em pista preta, PD com velocidade adaptativa e rampas, 4 cruzamentos com
  filtro, perda de linha com recuperação limitada, cão de guarda do link com política `stop`/`continue`,
  parada imediata pelo byte `!`, teste de bancada) e camada da ESP32 (`main.cpp`: pinagem exata recebida,
  STBY baixo antes de tudo, PWM 20 kHz para arduino-esp32 2.x e 3.x, Bluetooth Clássico SPP, NVS, LED,
  laço em ritmo fixo). Parâmetros lidos da NVS passam pelos limites do protocolo (memória corrompida →
  padrões); calibração interrompida não permite partida.
* **Protocolo NOCT/1** (`PROTOCOLO_NOCT1.md`): linhas ASCII até 240 bytes, `!` de emergência em qualquer
  ponto, batimento, comandos com sequência e resposta única (ACK/NAK com código), STA/TEL/EVT/PAR/SEN,
  limites validados nos dois lados, `SET` tudo-ou-nada.
* **Serviço no PC** (`ultron/noctario/`): transportes porta COM (pyserial), RFCOMM direto e SIMULADOR
  (sempre rotulado; só conecta ao que foi configurado, sem varredura); estado **solicitado × confirmado**
  ("aguardando confirmação", "sem confirmação do robô — estado desconhecido"); prazo por comando (TIMEOUT
  nunca vira "feito"); PARADA direto no transporte, repetida até o ESTOP confirmado; reconexão com espera
  crescente que nunca dá partida; voltas gravadas no mesmo banco (migração v6, amostras comprimidas,
  volta parcial marcada) e entregues à TARDIS; alertas; operações registradas; taxa de telemetria das
  configurações aplicada a cada conexão.
* **Simulador** (`simulator.py`): a mesma lógica do núcleo C++ em Python + física de uma pista de TESTE
  inventada. `tests/test_noctario_firmware.py` compila o núcleo com g++ e compara os dois **linha a linha**
  numa sessão de 62 s simulados (31 071 ciclos: mensagens, eventos, telemetria e PWM de cada ciclo).
* **Skills e voz**: 18 skills (`noctario.*`) e frases ("pare o Noctário", "calibre o Noctário", "dê a
  partida no Noctário", "teste o motor esquerdo do Noctário", "ajuste o Kd do Noctário para 0,12"…).
  Paradas são emergência (nenhuma permissão as bloqueia; "pare o Noctário" sai na hora, sem fila nem
  modelo; "pare"/"cancelar" com o robô andando também param). Tudo que move ou reconfigura o robô pede
  confirmação a cada vez e não é oferecido ao modelo de linguagem.
* **Página NOCTÁRIO (F4)**: SEM CONEXÃO / SIMULADOR / CONECTADO, estado informado pelo robô e pedido em
  andamento, valores, barras dos sensores, gráfico de 20 s (posição, PWM, mapa dos sensores, cruzamentos),
  PARADA DE EMERGÊNCIA (F12) sempre visível com o aviso do botão físico, comandos, parâmetros com limites
  (inclusive os de fiação a confirmar), voltas gravadas com ANALISAR NA TARDIS, alertas. CONFIGURAÇÕES >
  NOCTÁRIO ganhou "Reconectar se o link cair".
* **Defeitos encontrados pelos testes novos e corrigidos**:
  * **F12 e Esc da plataforma nunca disparavam** (PySide6 6.8: sinal passado como `activated=` do atalho
    não é chamado); F2/F3/Esc da janela antiga tinham o mesmo defeito. Agora `.emit`, com teste.
  * O modo agêntico executava **ferramentas que não tinham sido oferecidas ao modelo** (inclusive as
    reservadas a pedidos diretos, como dar partida no robô — o executor ainda pediria confirmação); e o
    planejador listava essas skills. Agora são recusadas e ficam fora da lista.
  * Pedido em que nada foi executado respondia "Feito e verificado. 0 etapa(s) verificada(s)." Agora diz
    "Nenhuma ação foi executada." e não marca verificado.
  * Sem Bluetooth no PC, abrir o RFCOMM derrubava a thread do link e a mensagem culpava o robô; agora o
    motivo real chega à interface.
  * A volta era anunciada antes de gravada no banco; o ACK de `SET`/`TEL` não atualizava o parâmetro no
    PC; o indicador da barra superior dizia "DESCONECTADO" em vez de "SEM CONEXÃO".
  * Argumentos numéricos NaN ou infinitos passavam pela validação das skills (toda comparação com NaN é
    falsa); agora são recusados.
  * Frases que só **mencionam** o robô viravam comando a ele ("lembre-me de calibrar o robô amanhã" →
    calibrar; "crie uma tarefa para testar os motores do Noctário" → teste de motores). Ainda pediriam
    confirmação, mas um "sim" distraído moveria o robô. Lembretes, tarefas, notas, pesquisas e perguntas
    agora seguem para as regras certas; as frases de parada continuam valendo sempre.
  * `STOP` durante o teste de bancada ou a calibração passava por `STOPPING`, e o PC gravava isso como
    uma "volta interrompida" falsa. Agora o robô para na hora e volta a pronto/sem calibração; só o
    percurso de verdade (RUN) abre uma volta.
* **Medido** (`tools/benchmark_noctario.py`, `docs/benchmarks/noctario_fase6.json`; contêiner Linux, CPU,
  Qt offscreen, **simulador — não é Bluetooth nem o robô**): PARADA até o ESTOP confirmado 2,0 ms
  (mediana; máx. 8,1 ms); PING ida e volta 10,5 ms (o simulador processa em lotes de 10 ms); atualização
  da página 0,43 ms; pintura do gráfico com a janela cheia (400 amostras) 6,8 ms (p95 13 ms) — o mapa dos
  sensores virou uma imagem única: nos mesmos dados (400 amostras, 1000×300) 16,2 → 5,5 ms (p95 22,9 →
  6,6 ms); uma volta da pista de teste (27,4 s simulados, 548 amostras a 20 Hz) ocupa 6,6 KB no banco.
* **Não verificado**: compilação real do `main.cpp` para a ESP32 (o ambiente bloqueou o download do
  toolchain; o `main.cpp` foi conferido contra cabeçalhos com as assinaturas do arduino-esp32 2.x e 3.x) e
  qualquer comportamento no robô real.
* Testes: `test_noctario.py` (33), `test_noctario_firmware.py` (3) e `firmware/noctario/test/host`
  (10 grupos); `test_platform.py`, `test_permissions.py` e `test_tardis_room.py` atualizados.

## PR #2 integrada — segurança do repositório, CI e os sketches originais do Noctário
Trabalho do proprietário sobre `d16c9d1`, integrado sem alterações (avanço rápido, a pedido):
* cópia de segurança integral antes das Fases 7 e 8 (branch `safety/backup-before-phase-7-8-20261029`,
  manifesto em `SEGURANCA_BACKUP/`), guia `SEGURANCA_E_BACKUP.md` e `.gitignore` que impede enviar bancos,
  credenciais, `.env`, caches e builds;
* CI (`.github/workflows/jarvis-validation.yml`): Python 3.11 e 3.13 no Linux, **Windows** (runner do GitHub,
  Windows Server 2025: dependências e suíte), testes C++ do firmware, **compilação real do firmware para a
  ESP32 (PlatformIO)** e pacotes ZIP extraídos numa pasta limpa e testados; `CI_E_RELEASE.md`;
* PyAudio opcional (o `sounddevice` basta), Qt limitado à série 6.8 testada, backend de áudio desconhecido
  recusado, caminhos de ZIP no estilo Windows (`..\`) recusados em qualquer sistema;
* Noctário alinhado aos sketches originais: sensor de cruzamento ativo em **LOW** e laço de **100 Hz**
  como padrão, migração da NVS antiga preservando a calibração; simulador e testes acompanham.

## Fase 7 — Testes de segurança, falhas, transições, voz e linha de comando
* Cobertura medida antes de escrever testes (74 % das linhas); os testes novos miraram os menos cobertos e
  o que a fase pede: **39 testes novos** — `test_security.py` (17), `test_failures.py` (7),
  `test_transitions.py` (6), `test_cli.py` (4), perguntas sobre a memória pessoal (+3), calibração da voz
  com Piper e Vosk reais (+1), cancelamento do modelo (+1). Total: **404 testes**, todos aprovados em
  Python 3.13 e 3.11. Detalhes, o que é real e o que é simulado: `TEST_REPORT.md`.
* **Defeitos encontrados pelos testes e corrigidos:**
  * as skills de arquivos podiam criar, alterar, mover ou apagar dentro do sistema operacional, da
    inicialização automática e do próprio JARVIS — um `.py` gravado na pasta de plugins seria executado na
    próxima partida. Agora é recusado antes de qualquer autorização (novo gancho `refuse_reason`, conferido
    pelo executor); ler e listar continuam livres;
  * a segunda edição de um arquivo sobrescrevia a cópia `.ultron.bak` (o original do usuário se perdia);
  * "cancelar" com o modelo ainda carregando deixava o JARVIS preso até o primeiro token; agora a conexão
    é encerrada e ele volta ao repouso na hora;
  * o modelo que quebra no meio do pedido não acendia o estado de erro do rosto nem entrava no histórico;
  * banco de memória danificado derrubava o início com um traceback (sem console, a janela simplesmente
    não abria); agora a mensagem diz o que houve, que o arquivo não foi tocado e como restaurar (código 3);
  * `settings.json` ilegível era substituído na gravação seguinte; agora o original é guardado antes;
  * banco que recusa gravação respondia "Falha interna (OperationalError)"; backup que falhava deixava
    um `.partial`;
  * um título de janela com quebras de linha podia simular uma seção nova no prompt do sistema;
  * achados pelo CI no **Windows** (Server 2025, o runner do GitHub): o cancelamento dependia de encerrar
    o socket de outra thread (no Windows isso não acorda quem espera; agora a espera é numa fila e não
    depende do sistema), os testes da linha de comando liam UTF-8 de um pipe em cp1252, e o
    `TEST_JARVIS.py` caía ao imprimir as falhas. Depois das correções: 404/404 também no Windows.
* A cobertura depois: 75 % no total; skills de arquivos 36 % → 61 %, perguntas sobre a memória 21 % → 84 %,
  calibração da voz 22 % → 58 %. Os testes da linha de comando rodam `main.py` em processos separados,
  fora da medição.
