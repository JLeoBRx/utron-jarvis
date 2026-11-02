# JARVIS

Inteligência local para Windows: percebe o computador, entende pedidos em português por voz
ou texto, planeja, executa com **verificação independente**, guarda a sua memória pessoal
(tarefas, compromissos, ideias, projetos, lembretes) e mostra tudo em dois hubs:

* **JARVIS CORE** — o hub principal: o cérebro neural em 3D com o estado real de percepção,
  decisão, planejamento, execução, verificação, memória, voz e saúde.
* **TARDIS** — a memória espacial: um espaço interior navegável onde cada região é a sua
  memória pessoal real (compromissos, tarefas, projetos, ideias, memórias, lembretes).

É **local-first**: o cérebro é o Ollama nesta máquina; reconhecimento de fala e voz são
offline; nada sai do computador sem que você peça.

> O pacote interno continua `ultron` e os dados continuam em `%LOCALAPPDATA%\ULTRON`. É de
> propósito: suas memórias, lembretes, configurações e o inventário da rede seguem onde estão.

---

## 1. Instalação

Requisitos: Windows 10/11 64 bits, **Python 3.11** (python.org, marque *Add python.exe to
PATH*), **Ollama** (ollama.com/download). 8 GB de RAM ou mais recomendados.

### Instalação nova
1. Extraia `JARVIS_FINAL.zip` (pasta `JARVIS`).
2. Execute **`INSTALL_JARVIS.bat`**. Ele:
   * cria `.venv` (nunca apaga um existente) e instala `requirements.txt`;
   * verifica os modelos locais em `assets\` — o pacote **não** inclui modelos grandes. Se
     você tem uma instalação anterior, informe a pasta dela e os modelos que faltam são
     copiados (nada é sobrescrito ou apagado); senão, ele mostra de onde baixar;
   * oferece baixar os modelos do Ollama (`qwen2.5:3b` texto, `qwen2.5vl:3b` visão, ~5 GB);
   * pergunta se o JARVIS deve iniciar com o Windows;
   * termina com o diagnóstico completo (componentes ausentes e voz em 8 etapas).
3. Inicie com **`START_JARVIS.bat`**.

### Atualizando uma instalação existente (ULTRON ou JARVIS)
1. Feche o JARVIS: bandeja > **Sair** (ou `START_JARVIS.bat --stop`).
2. Extraia o conteúdo da pasta `JARVIS` do ZIP **por cima** da pasta atual do programa
   (substituir arquivos). `.venv`, `assets` (modelos) e os seus dados não são tocados.
3. Execute **`ATUALIZAR_JARVIS.bat`**: encerra o JARVIS se ainda estiver aberto, faz um
   **backup** do banco, atualiza as dependências e roda o diagnóstico.

Na primeira execução, as configurações da identidade ULTRON são migradas (palavra de
ativação "ultron" → "jarvis", tema dourado → azul) e o arquivo original é guardado como
`settings.ultron-backup.json`. Personalizações suas que não eram da identidade antiga são
mantidas. Atalhos antigos (`START_ULTRON.bat`, `INSTALL_ULTRON.bat`, `TEST_ULTRON.py`) abrem
as versões JARVIS.

### Modelos locais (não incluídos no ZIP)

| Arquivo | Onde colocar | Fonte oficial |
|---|---|---|
| `vosk-model-small-pt-0.3` (≈ 50 MB) | `assets\stt\vosk-model-small-pt-0.3\` | alphacephei.com/vosk/models |
| `vosk-model-pt-fb-v0.1.1-20220516_2113` (opcional, mais preciso) | `assets\stt\…\` | alphacephei.com/vosk/models |
| `pt_BR-faber-medium.onnx` + `.onnx.json` (voz) | `assets\voices\` | huggingface.co/rhasspy/piper-voices (pt/pt_BR/faber/medium) |

Sem o modelo de fala, o JARVIS funciona por texto; sem a voz neural, usa a voz do Windows.

---

## 2. Iniciar, parar, atualizar, recuperar

| Comando | Efeito |
|---|---|
| `START_JARVIS.bat` | abre o JARVIS (TARDIS e as outras páginas pela navegação, F1–F7 ou por voz) |
| `START_JARVIS.bat --console` | modo console (texto) |
| `START_JARVIS.bat --status` | diz se está em execução |
| `START_JARVIS.bat --stop` | pede ao JARVIS em execução que **encerre normalmente** (lembretes, banco e microfone fechados em ordem); não força nada |
| `START_JARVIS.bat --diagnose` · `DIAGNOSTICO_JARVIS.bat` | modo de diagnóstico: componentes ausentes, saúde, voz em 8 etapas, backups |
| `START_JARVIS.bat --voice-test` | teste de voz falando ("Jarvis, que horas são?") |
| `START_JARVIS.bat --backup` | backup do banco agora |
| `START_JARVIS.bat --autostart` / `--no-autostart` | liga/desliga o início com o Windows |
| `ATUALIZAR_JARVIS.bat` | atualização segura (para, faz backup, atualiza dependências, diagnostica) |
| `.venv\Scripts\python.exe main.py --help` | todos os comandos |

**Recuperação**

* *Backups*: um automático por dia (os 10 mais recentes ficam em
  `%LOCALAPPDATA%\ULTRON\backups`), além de `--backup` e do botão BACKUP do TARDIS.
  Para voltar: `START_JARVIS.bat --stop`, depois `python main.py --list-backups` e
  `python main.py --restore-backup ARQUIVO`. A restauração só roda com o JARVIS fechado,
  verifica a integridade do arquivo e **guarda o banco atual** como
  `ultron.sqlite3.antes-da-restauracao-<data>` antes de trocar.
* *Configurações*: renomeie `%LOCALAPPDATA%\ULTRON\settings.json` para recriar os padrões.
* *Modo seguro*: `python main.py --no-voice --no-perception --no-plugins`.
* *Registro*: `%LOCALAPPDATA%\ULTRON\logs\ultron.log`.
* *Travou*: bandeja > Sair; se não responder, finalize `pythonw.exe` do JARVIS pelo
  Gerenciador de Tarefas — os dados ficam íntegros (banco em modo WAL) e lembretes perdidos
  são avisados uma vez na próxima abertura.

---

## 3. A plataforma: JARVIS · TARDIS · NOCTÁRIO · ATIVIDADES · CONFIGURAÇÕES · DIAGNÓSTICOS

Uma janela com seis módulos. Trocar de módulo não perde nada: câmera e região do TARDIS,
filtros, rolagem e textos digitados ficam como estavam.

| Atalho | Efeito |
|---|---|
| F1 | JARVIS (núcleo e conversa) |
| F2 | TARDIS (sala de controle e ARQUIVO da memória pessoal) |
| F4 | NOCTÁRIO (robô) |
| F5 | ATIVIDADES (histórico) |
| F6 | CONFIGURAÇÕES |
| F3 ou F7 | DIAGNÓSTICOS (voz, rede, autonomia, desempenho, eventos, log, serviços e GPU) |
| F11 | tela cheia |
| Esc | como no original: interrompe a fala; senão cancela o pedido ou a autorização pendente; senão sai da tela cheia. Nunca minimiza. Na TARDIS, solta o painel da sala ou fecha a região aberta do ARQUIVO |
| Ctrl+M | microfone |
| Ctrl+L | limpa a conversa da tela |

Por voz: *"abra a TARDIS"*, *"abra o segundo cérebro"* (o ARQUIVO), *"abra as configurações do JARVIS"* (sem "do JARVIS", abre as
configurações do Windows, como no original), *"mostre o histórico de atividades"*, *"abra o
console de eventos"*, *"abra o log do JARVIS"*, *"abra o noctário"*, *"volte para o JARVIS"*,
*"o que você fez hoje?"*.

**Barra superior**: mini-reator e identidade, navegação, relógio e data; na segunda linha o
estado (LED, nome e cinco barras com o nível REAL do microfone ou da fala) e os indicadores MIC,
VOZ, IA, NOCTÁRIO, REDE (Wi-Fi e tráfego), BATERIA (só se houver), OBSERVADOR e SESSÃO (tempo de
execução e modo de privacidade). Passe o mouse para detalhes; clique para agir (ligar/desligar
microfone e voz, modos do Observador, abrir a página certa). Indicador sem dado real mostra "—".

**Barra inferior** (vale em qualquer página): campo de pedido com histórico ↑/↓ (guarda o
rascunho), **ENVIAR**, **MIC**, **VOZ**, **ORBE** (recolhe para o orbe compacto; clique duplo no
orbe expande; o orbe lembra onde foi deixado). Autorizações e sugestões aparecem logo acima.
Fechar a janela mantém o JARVIS na bandeja; **Sair** encerra.

**Conversa** (página JARVIS): cada mensagem com horário (`[HH:MM] VOCÊ ▸`, `J.A.R.V.I.S. ▸`,
`// sistema`), **STATUS**, **HORAS**, **PARAR**, **COPIAR RESPOSTA** e **LIMPAR** (Ctrl+L).

**Transições**: holográficas (~300 ms) com "efeitos pesados" ligados e fora do perfil
econômico; senão, imediatas.

**Observação da tela**: quando a janela do JARVIS cobre a maior parte da tela, a observação fica
suspensa (o indicador mostra SUSPENSO), como no original. Pedidos explícitos ("o que há na
tela?") continuam funcionando.

**Bandeja**: abrir cada página, diagnóstico de voz, orbe, microfone, voz, **Reiniciar voz**,
**Modo privacidade**, **Observador** (modos, pausar/retomar), **Iniciar com o Windows** (só por
clique; se o Registro recusar, a marcação volta), qualidade visual, diagnóstico e Sair.

### O rosto holográfico (página JARVIS)

Um rosto robótico 3D renderizado **em tempo real** (não é imagem nem vídeo): malha esculpida com
iluminação, olhos com íris, sobrancelhas, nariz, orelhas, colar com reator, plataforma de projeção,
anéis de dados, partículas e varredura. CONFIGURAÇÕES > APARÊNCIA troca para o núcleo neural
anterior ("Vista do JARVIS") e escolhe CPU ou GPU (OpenGL; se não abrir, volta para a CPU e
DIAGNÓSTICOS > SERVIÇOS E GPU diz por quê). Clique no rosto liga/desliga o microfone.

**A boca acompanha o áudio real da fala**: a voz Piper informa os fonemas de cada frase; os visemas
são distribuídos só pelos trechos sonoros do áudio (as pausas caem nos silêncios reais) e a abertura
é a energia real do som. Se o modelo de voz exportar o tempo de cada fonema, ele é usado; com a voz
do Windows (sem fonemas) a forma vem do espectro do áudio. No silêncio a boca fecha; interrompida a
fala (Esc, "pare", PARAR), fecha no mesmo quadro. **Legendas** sincronizadas destacam as palavras já
ditas (desligue em CONFIGURAÇÕES > VOZ E ÁUDIO).

**Os 12 estados** (o mesmo estado aparece no indicador da barra superior), do mais prioritário:

| Estado | Sinal real | Visual |
|---|---|---|
| Privacidade | modo privacidade ativo | viseira de linhas sobre os olhos, brilho baixo |
| Erro de integração | componente falhou, modelo indisponível, link do Noctário perdido sem pedido (8 s) | tom coral e leve "falha" de projeção |
| Aguardando confirmação | autorização pendente | âmbar, sobrancelhas erguidas, olhar direto |
| Falando | áudio saindo agora (posição real de reprodução) | boca sincronizada, acenos nas sílabas fortes, anéis pela saída real |
| Alerta | lembrete devido, alerta do Noctário (6 s) | âmbar, atenção súbita; tinge os estados abaixo |
| Reconhecendo | parciais do reconhecimento com a escuta aberta | olhos focados, micro-movimentos |
| Escutando | escuta aberta | atenção, cabeça inclinada, halo pelo nível real do microfone |
| Consultando a TARDIS | tarefa da TARDIS pedida pelo JARVIS | olhar para o lado, íris âmbar |
| Executando | execução, verificação, recuperação | expressão firme, varredura rápida |
| Pensando | contexto, decisão, planejamento | olhar que varre, sobrancelhas franzidas |
| Inicializando | progresso real do boot | o rosto se monta por um plano de varredura; olhos abrem ao fim |
| Em espera | nenhum dos anteriores | respiração lenta, piscadas naturais |

Desempenho medido (`tools/benchmark_avatar.py`, CPU, Qt offscreen, no contêiner de
desenvolvimento — numa máquina Windows os números serão outros): 1280×720 equilibrado ≈ 12–16 ms
por quadro; 1920×1080 equilibrado ≈ 16–19 ms; econômico ≈ 8–13 ms. A interface limita sozinha os
quadros por segundo pelo custo medido para não roubar tempo do núcleo. Resultados completos em
`docs/benchmarks/avatar_fase4.json`.

### O núcleo neural (vista alternativa)

Cada estado tem um visual próprio, sempre ligado a um sinal real:

| Estado | Visual |
|---|---|
| Repouso | azul profundo discreto, giro lento |
| Escuta | halo ciano que respira com o nível real do microfone |
| Percepção | ondas sutis a cada análise real (visão, OCR, rede) |
| Contexto/memória | mergulho no hipocampo; lembranças recuperadas acendem em **azul** |
| Planejamento | etapas reais do plano no arco superior; conexões acendem conforme cada etapa termina |
| Execução | pulsos e sinais das operações reais; subsistema usado recebe a sinapse |
| Fala | anéis sincronizados com o nível real da voz |
| Imaginação | profundidade cognitiva maior, estruturas internas reveladas |
| Erro | contorno fixo no tom de falha + rótulo ERRO, sem piscar |

O anel mostra os subsistemas (OLLAMA, MEMÓRIA, VISÃO, PERCEPÇÃO, VOZ, TELEMETRIA, REDE,
IMAGINAÇÃO, OBJETIVOS, CÓDIGO, WEB, AUTOMAÇÃO, WINDOWS, ARQUIVOS, AGENDA) com o estado real
da saúde. Módulos (plano, autorização com contagem regressiva, memória, saúde, rede…) só
aparecem enquanto há algo real a mostrar. O raciocínio interno nunca é exibido — só fases,
estados e resultados.

### ATIVIDADES

Tudo o que o JARVIS recebeu, decidiu e fez, com origem, estado, duração e o resultado ou o erro
reais: pedidos (voz, texto, sugestões aceitas), ações ligadas ao pedido, confirmações,
verificações, lembretes e falhas. Filtros por tipo e estado, busca, detalhe de cada registro,
**COPIAR** e **LIMPAR HISTÓRICO** (categoria "apagar dados": pede confirmação). Textos que parecem
senha ou token são redigidos antes de gravar. Desligue ou limite em CONFIGURAÇÕES > HISTÓRICO.

### CONFIGURAÇÕES

Geral e início (página inicial, início recolhido, **Iniciar com o Windows**, modo privacidade ao
iniciar, Observador ao iniciar) · Voz e áudio (voz, timbre, volume, velocidade, legendas,
palavras de ativação, **microfone** e **saída de áudio**) · Inteligência (Ollama ou **OpenAI**, com
aviso e confirmação explícitos; chave no cofre do sistema, nunca exibida inteira; TESTAR) ·
Privacidade e Observador (LOCAL/PADRÃO, modelos externos, modos, intervalo, **apps sem
monitoramento**) · **Permissões** · Aparência e desempenho · Noctário · Histórico e registros ·
**Restaurar padrões** (guarda uma cópia antes; mantém microfone, saída de áudio, calibração da voz,
endereço do Noctário e fuso).

**Permissões por categoria**: consultar, alterar configurações, executar programas e comandos
do sistema, modificar arquivos e dados pessoais, apagar dados, comandos ao robô — cada uma em
*permitir* (decide pelo risco), *confirmar sempre* ou *bloquear*. Apagar dados e comandos ao robô
nunca ficam abaixo de *confirmar*; a parada de emergência do robô nunca é bloqueada.

### DIAGNÓSTICOS (F3 / F7)

* **VOZ** — microfones disponíveis e escolha (USAR ESTE), TESTAR, TESTAR FALANDO, CALIBRAR,
  contadores ao vivo. Detalhes em `VOICE_DIAGNOSTICS.md`.
* **REDE LOCAL** — aparelhos da sua rede (seção 8).
* **AUTONOMIA** — nível de autonomia, autorizações permanentes (revogar), histórico de pedidos
  de autorização e registro das ações executadas.
* **DESEMPENHO E SAÚDE** — saúde dos componentes, quadros por segundo, perfil visual.
* **EVENTOS** — console de eventos do original: 300 entradas `[HH:MM:SS] ▸ texto`, filtro,
  PAUSAR, COPIAR (linhas visíveis) e LIMPAR; inclui os eventos desde a abertura do JARVIS.
* **LOG** — fim do arquivo de log com filtro de nível. Exceções não tratadas (inclusive em
  threads e na pintura da interface) também vão para o log.
* **SERVIÇOS E GPU** — componentes, workers, Ollama, OpenAI, privacidade, GPUs do sistema e
  DETECTAR OPENGL (para a renderização 3D opcional por GPU).

---

## 4. TARDIS — o segundo cérebro (sala de controle e ARQUIVO)

A TARDIS é um **módulo lógico** do JARVIS com fila, protocolo, analisadores e memória de projeto
próprios. **Não é um segundo modelo de IA**: quando precisa de linguagem natural, usa o **mesmo
modelo do JARVIS** com instruções próprias — e cada resultado diz qual modelo usou (*"qwen2.5:3b (o
mesmo do JARVIS)"*) ou *"sem modelo: análise determinística"*. A TARDIS **nunca executa ações**:
devolve **ações propostas**, que só rodam com a sua confirmação, pelo mesmo executor do JARVIS
(permissões, risco, autorização e verificação).

Abra por **F2**, pelo botão TARDIS ou dizendo *"abra a TARDIS"*. A página tem duas vistas, e cada uma
guarda o próprio estado quando você troca de módulo:

### Sala de controle

Um console hexagonal com seis painéis em volta do **rotor** de vidro. Clique num painel (no console
3D ou nas abas à direita) e a câmera gira até ele; **Esc** solta o painel (sem painel, o Esc faz o que
faz no resto da plataforma).

| Painel | O que faz |
|---|---|
| ANÁLISE | consulta contextual na memória pessoal, fatos, notas de projeto e histórico — **com a fonte de cada item**; e a memória de projeto (gravar e ler notas, decisões e parâmetros) |
| PLANEJAMENTO | decompõe um objetivo em etapas verificáveis e aponta riscos (exige o modelo; sem ele, falha com o motivo). Nenhuma etapa é executada |
| ARQUIVO | organização da memória pessoal (atrasados, conflitos, duplicados, tarefas sem data, registros aguardando revisão) e a entrada da memória espacial |
| ROTINAS | lembretes futuros, registros recorrentes e automações |
| TELEMETRIA | métricas das voltas gravadas do Noctário (tempo, erro RMS, oscilação, saturação do PWM, perdas de linha, intervalos entre cruzamentos, comparação entre voltas) e hipóteses de ajuste explicadas |
| DIAGNÓSTICO | saúde, componentes, workers, voz e Noctário, com gravidade e fonte (diagnóstico); e a fotografia do estado de cada módulo agora (coordenação) |

O **rotor** mostra o estado REAL do motor da TARDIS:

| Modo | Quando |
|---|---|
| REPOUSO | fila vazia — respiração lenta, âmbar escuro |
| PROCESSANDO | uma análise roda ou espera na fila — o rotor sobe e desce, âmbar |
| CONSULTA DO JARVIS | a análise em execução foi pedida pelo JARVIS — ciano, com o feixe **JARVIS ⇄ TARDIS** (e o rosto do JARVIS mostra "CONSULTANDO A TARDIS") |
| OPERAÇÃO | o JARVIS está gravando ou exportando dados (backup, exportação, escrita de arquivos) — verde-água |
| FALHA | uma análise falhou há menos de 8 s — vermelho, anel no piso e o motivo no canto |

Cada painel acende enquanto uma tarefa REAL do seu tipo roda e pulsa ao terminar (vermelho se falhou).
As telas flutuantes mostram a fila e o último resultado. Sem evento, a sala fica em repouso.

O lado direito mostra o **RESULTADO** da tarefa escolhida: resumo, itens com a fonte de cada um,
modelo usado, o registro de operações e as **ações propostas** com o botão **APLICAR** (executa pelo
JARVIS, que pede confirmação quando a categoria exige — comandos ao robô e apagar dados sempre pedem).
**CANCELAR** interrompe uma análise na fila ou em execução. **TAREFAS** lista as desta sessão e as
anteriores (lidas do banco).

### Pelo JARVIS (voz ou texto)

*"Jarvis, consulte a TARDIS sobre o projeto Atlas"*, *"pergunte à TARDIS o que eu decidi sobre o Kd do
Noctário"*, *"TARDIS, organize minha memória"*, *"peça à TARDIS um plano para montar a pista"*,
*"TARDIS, diagnostique o sistema"*, *"peça à TARDIS para analisar a telemetria do Noctário"*,
*"TARDIS, quais são minhas rotinas?"*, *"TARDIS, estado dos módulos"*, *"anote na TARDIS uma
decisão: usar pista de 3 metros"*, *"mostre a memória de projeto do Noctário"*.

A resposta diz qual análise rodou, o modelo e as fontes. Se a TARDIS propõe uma ação, o JARVIS
pergunta: diga **"sim"** para executar ou **"não"** para descartar (a proposta expira em 90 s). Para
comandos ao robô, o "sim" ainda passa pela confirmação própria da categoria. **"Cancelar"** para as
consultas que o JARVIS fez à TARDIS (as análises pedidas na sala continuam).

### Protocolo e garantias

Toda tarefa tem `id`, entrada, estado (`QUEUED → RUNNING → DONE | FAILED | REJECTED | CANCELLED`),
resultado (resumo, itens, fontes, ações propostas), erro (código e mensagem), tempos (criada,
iniciada, terminada, duração), origem (JARVIS, usuário, TARDIS, agendador), cadeia de delegação,
registro de operações e o modelo usado. Tudo fica no **mesmo banco** do JARVIS e no histórico de
atividades (pedido → ação → tarefa da TARDIS, ligados).

* **Sem ciclos**: no máximo 2 saltos na cadeia, nenhum salto repetido, e a TARDIS nunca devolve
  tarefas ao JARVIS — o que violar isso é **recusado** na entrada.
* **Prazos por tipo** (consulta 60 s, planejamento 120 s, organização 20 s, rotinas 10 s,
  telemetria 20 s, diagnóstico 30 s, coordenação 5 s, memória de projeto 10 s); uma análise que
  trava é abandonada com TIMEOUT e a fila segue.
* **Sem dado, sem resultado**: nada encontrado → FAILED com o motivo (`NO_DATA`); sem modelo para
  planejar → `NO_MODEL`. Telemetria sem voltas gravadas do Noctário diz que não há o que analisar;
  voltas do simulador são rotuladas e nunca viram comando ao robô. Nenhuma sugestão promete tempo de volta.
* A memória de projeto **recusa senhas, tokens e dados sensíveis**; textos que parecem segredo são
  redigidos antes de gravar.
* Tarefas que estavam na fila quando o JARVIS fechou viram CANCELLED (`INTERRUPTED`) na próxima abertura.

### ARQUIVO (memória espacial)

Pelo painel ARQUIVO (**ABRIR MEMÓRIA ESPACIAL**), pelo botão de memória da barra inferior ou dizendo
*"abra o segundo cérebro"* / *"abra a memória espacial"*. No centro, a **câmara de energia** (HOJE:
prioridades, compromissos, atrasados); em volta, portais para as regiões:

| Região | O que mostra |
|---|---|
| COMPROMISSOS | próximos 14 dias; **conflitos de horário** em destaque |
| TAREFAS E PRAZOS | abertas, atrasadas (alerta), filtros por período, tipo e prioridade |
| PROJETOS | projetos com contagem de itens abertos |
| IDEIAS | ideias recentes |
| MEMÓRIAS | notas, pessoas e busca (Ctrl+F) |
| LEMBRETES | próximos lembretes e a central de notificações |
| REVISÃO | o que foi inferido automaticamente e aguarda sua confirmação; lixeira |

Os pontos em volta de cada portal são registros reais (passe o mouse para ver o título).
Clique num portal: a câmera viaja até ele e o painel lateral abre para consultar, criar
(**+ NOVO**), editar, concluir, arquivar ou mandar para a lixeira. **Esc** volta à visão
geral; **Ctrl+N** vai para a captura rápida ("reunião com a equipe quarta às 14h",
"ideia: …", "o que está atrasado?"). **← SALA DE CONTROLE** volta à sala sem perder
câmera, região ou filtros. **EXPORTAR** (JSON/CSV) e **BACKUP** ficam na barra superior;
**SOM AMBIENTE** é opcional (desligado por padrão).

Pulsos percorrem os corredores só quando algo real acontece (registro criado, editado,
concluído, lembrete disparado).

### Desempenho da sala

Paredes, piso, colunas e console ficam em imagens em cache, refeitas só quando a câmera gira até um
painel; com a câmera parada, cada quadro desenha só o rotor, as luzes dos painéis, as telas, os
rótulos e as partículas. Com animação a sala desenha no máximo 24 quadros/s e nunca ocupa mais de 25%
da thread da interface (a pintura segura o GIL e atrasaria as análises); em repouso cai para a cadência
econômica do perfil e, fora da tela, não desenha nada.

Medido num contêiner Linux (Qt offscreen, CPU, 4 núcleos — não é uma máquina Windows real): câmera
parada 7,7–11,0 ms por quadro (mediana) a 1280×720 e 8,9–14,4 ms a 1920×1080, em qualquer perfil e modo
do rotor; a volta da câmera até um painel custa 23,5–36,1 ms por quadro durante ~1 s; ida e volta de uma
tarefa no motor, 0,8 ms (mediana). Números completos em `docs/benchmarks/tardis_room_fase5.json`
(`python tools/benchmark_tardis_room.py` mede na sua máquina).

---

## 5. Noctário — o robô seguidor de linha

O JARVIS conecta ao Noctário pelo Bluetooth, mostra tudo o que o robô informa, envia comandos com
limites e confirmação, grava as voltas e as entrega à TARDIS. **O controle PD roda no ESP32**: a
interface só pede, lê e registra. Firmware, pinagem e a primeira vez na bancada:
`firmware/noctario/README.md`; protocolo: `firmware/noctario/PROTOCOLO_NOCT1.md`.

> Os sketches originais (`Noctario_JARVIS.ino`, 20/10, e a variante `Nefarious_6`, 28/10) foram
> comparados: pinagem, linha branca, sensor de cruzamento ativo em LOW e laço de 100 Hz estão confirmados
> e já são o padrão. Ainda dependem da bancada a ordem física dos sensores e o sentido de cada motor —
> ajustáveis pela interface, sem regravar. O firmware compila para a ESP32 no CI; gravar na placa e
> ensaiar no robô (rodas suspensas, botão físico ao alcance) é o passo seguinte.

**Conectar.** Pareie o robô ("Noctario") no Windows. Em CONFIGURAÇÕES > NOCTÁRIO escolha *Porta COM do
Bluetooth* (a porta de saída criada pelo Windows), *Bluetooth direto* (endereço do robô) ou *Simulador*.
O JARVIS só conecta ao que você configurou — não procura nem varre aparelhos. *Conectar ao iniciar* e
*Reconectar se o link cair* só conectam: **nunca dão partida**.

**A página NOCTÁRIO (F4).**

* Faixa: CONECTADO (porta e firmware), **SIMULADOR — não é o robô** ou **SEM CONEXÃO — nenhum dado do
  robô** (sem conexão nada é exibido como se fosse do robô).
* **Estado informado pelo robô** e o pedido em andamento: *aguardando confirmação*, *confirmado* ou
  *sem confirmação do robô — estado desconhecido* (depois de 3 s).
* Calibração, cruzamentos (x de N), tempo da volta, erro, correção PD, PWM de cada motor, velocidade
  alvo, Kp/Kd, o que o firmware faz sem link e a última falha.
* Barras dos 8 sensores com a posição da linha e o gráfico dos últimos 20 s (posição e erro, PWM de cada
  motor, sensores como mapa de calor, cruzamentos).
* Ao lado: **PARADA DE EMERGÊNCIA (F12)** sempre visível; CONECTAR/DESCONECTAR, PARTIDA, PARAR,
  CALIBRAR, CALIBRAR GIRANDO, LIBERAR EMERGÊNCIA, ZERAR CRUZAMENTOS, MOTOR ESQUERDO e MOTOR DIREITO
  (bancada); parâmetros com os limites do protocolo (APLICAR envia só o que mudou; RELER; SALVAR NO
  ROBÔ); VOLTAS GRAVADAS com ANALISAR NA TARDIS; ALERTAS.

**Segurança.**

* **F12** (em qualquer página), o botão vermelho, *"pare o Noctário"*, *"parada de emergência"* ou
  *"robô, pare"*: o byte de parada vai direto ao robô — sem fila, sem modelo de linguagem, sem
  confirmação — e é repetido até o robô confirmar (até 1,5 s). Sem confirmação, o JARVIS diz para usar o
  botão físico. Nenhuma permissão bloqueia a parada. *"Pare"* ou *"cancelar"* com o robô andando também
  o param.
* **A parada pelo Bluetooth não substitui um botão físico** que corte a alimentação dos motores.
* Tudo o que move ou reconfigura o robô (partida, calibração, teste de motores, parâmetros, gravar,
  padrões, liberar a emergência, zerar cruzamentos) pede **confirmação a cada vez**, com a descrição
  exata do que será feito — nunca "sim, sempre" (categoria *comandos ao robô*, nunca abaixo de
  *confirmar*; pode ser bloqueada — a parada não).
* O modelo de linguagem não move o robô por conta própria: esses comandos não são oferecidos a ele e,
  se ele os inventar, são recusados.
* Sem link, vale a política do firmware (padrão: parar, com cão de guarda de 1,5 s). Reconectar nunca
  dá partida.
* Cada resposta diz o que o **robô confirmou**. Sem resposta: "estado desconhecido", nunca "feito".

**Por voz ou texto:** *"conecte o Noctário"*, *"calibre o Noctário"* (ou *"… girando"*), *"dê a partida
no Noctário"*, *"pare o Noctário"*, *"pare o robô suavemente"*, *"libere a emergência do Noctário"*,
*"ajuste o Kd do Noctário para 0,12"*, *"mude o PWM base do robô para 200"*, *"telemetria do Noctário a
10 Hz"*, *"teste o motor esquerdo do Noctário"*, *"leia os sensores do robô"*, *"quantos cruzamentos o
Noctário contou?"*, *"qual o estado do Noctário?"*, *"alertas do Noctário"*, *"salve os parâmetros do
Noctário"*, *"analise as voltas do Noctário"*.

**Voltas e TARDIS.** Cada volta feita com o JARVIS conectado é gravada da partida ao fim, com a
telemetria, no mesmo banco (resultado: concluída, linha perdida, interrompida ou parada de emergência;
marcada como parcial se o link caiu no meio). *"Analise as voltas do Noctário"* ou ANALISAR NA TARDIS
compara as voltas e explica hipóteses de ajuste; a TARDIS só propõe. Parâmetros confirmados pelo robô
vão para a memória de projeto "Noctário".

**Simulador.** Para conhecer a interface sem o robô: a mesma lógica do firmware (conferida linha a
linha contra o código C++) e a física de uma pista de **teste** inventada, com 4 cruzamentos. Tudo
aparece rotulado SIMULADOR; voltas do simulador ficam marcadas, nunca viram comando ao robô e o tempo
delas não diz nada sobre o robô real.

---

## 6. Falando com o JARVIS

**Voz.** Diga **"Jarvis"** no início: *"Jarvis, abra o bloco de notas"*. Depois de uma
resposta há 12 s de continuação sem repetir o nome. *"Pare"* interrompe a fala;
*"fique quieto"* / *"pode falar"* desligam/religam a voz. Se ele não entende o seu "Jarvis",
use DIAGNÓSTICOS > VOZ > **CALIBRAR**.

**Texto.** Digite na barra inferior (↑/↓ percorrem o histórico).

Exemplos: *"o que tenho para hoje?"*, *"lembre-me de pagar a conta amanhã às 9h"*,
*"anote uma ideia: horta vertical"*, *"tenho conflito de horário na agenda?"*,
*"exporte minhas tarefas em planilha"*, *"faça um backup da memória"*, *"quais dispositivos
estão na rede?"*, *"diagnóstico de voz"*, *"revogue as autorizações"*, *"prepare meu projeto
Atlas"*, *"o que está na tela?"*, *"consulte a TARDIS sobre o projeto Atlas"*.

Quando falta informação essencial, ele faz **uma** pergunta objetiva; quando há evidência
suficiente no contexto, completa o pedido; nunca diz que fez algo sem verificar.

---

## 7. Memória pessoal e lembretes

* Categorias: tarefa, compromisso, estudo, projeto, ideia, nota, pessoa, rotina, prazo.
* Datas e horas em português ("amanhã às 15h", "sexta", "dia 12 às 9h30", "toda segunda").
  Se a expressão for **ambígua** ("às 3" — manhã ou tarde?), ele **pergunta** e nada é gravado
  antes da resposta. Nenhuma data é inventada.
* Lembretes: aviso antecipado configurável (padrão 10 min para compromissos), repetição
  limitada se ignorado, adiar ("adie por 15 minutos"), concluir, dispensar; recorrência
  diária, dias úteis, semanal e mensal; horário de silêncio (`quiet_hours`, ex.: 22:00-07:00
  — o aviso fica na central, sem som).
* **Não dependem da IA**: o agendador é determinístico e persistente. Lembretes que venceram
  com o JARVIS fechado são avisados **uma vez** na próxima abertura (recorrentes não geram
  rajada).
* Notificações do Windows pela bandeja, fala (se permitido) e central de notificações.
* **Conflitos**: compromissos com horário sobrepostos são informados ao registrar ou editar,
  no TARDIS e na linha do tempo — nunca bloqueados (você decide).
* Captura automática só com intenção clara ("tenho dentista amanhã às 15h") e marcada como
  **inferida** até você confirmar em REVISÃO. Hipóteses ("talvez…"), perguntas e qualquer dado
  sensível nunca são capturados.
* Busca sem acentos, filtros por categoria, prioridade e data, lixeira recuperável;
  exclusão definitiva pede autorização específica.
* Exportação: JSON (completa) ou CSV (planilha) para um arquivo **novo** — nada é
  sobrescrito. Backup diário automático do banco inteiro.

---

## 8. Rede local

DIAGNÓSTICOS > **REDE LOCAL** lista os aparelhos com IP, MAC, nome, fabricante (OUI), tipo,
**observação**, confiabilidade, origem, interface, primeira e última vez. Observação é o que
se sabe agora: *respondeu recentemente*, *presença inferida — dados incompletos*, *conhecido
anteriormente — não confirmado agora*, *sem resposta no momento* ou *informação do próprio
computador*. O gateway é marcado. O que não se sabe aparece como **desconhecido**.

Fontes: tabela de vizinhos do sistema, ping de um pacote, DNS reverso e, se você ativar
(`network_ssdp`), anúncios SSDP — só na sub-rede privada da interface ativa. **Descobrir não é
administrar**: o JARVIS não acessa, não controla e não altera aparelhos; o roteador só pela
página oficial dele, aberta por você, com as suas credenciais (que o JARVIS não guarda).

---

## 9. Autonomia e segurança

| Situação | Comportamento |
|---|---|
| Comum, reversível, baixo risco (abrir app, pesquisar, registrar nota) | executa e verifica |
| Moderado escolhido pelo agente, modo restrito, ou iniciado pela proatividade | pede confirmação |
| Sensível (exclusão definitiva, configuração do sistema, segurança, administração de rede, envio de dados, credenciais, terceiros) | **autorização específica**, válida uma única vez |

* Responda *"sim"*/*"não"* por voz, texto ou botões; sem resposta em 30 s = não.
* *"Sim, sempre"* ou o botão **SEMPRE (24 h)**: autorização permanente **escopada** — só a
  mesma ação com o mesmo recurso, por 24 h; **nunca** para ações sensíveis, críticas,
  irreversíveis ou proativas. Veja e revogue em DIAGNÓSTICOS > AUTONOMIA ou diga *"revogue as
  autorizações"*.
* *"Pare"* cancela o que estiver em andamento. Toda ação fica registrada (DIAGNÓSTICOS >
  AUTONOMIA).
* Texto da tela, de arquivos e de páginas é **dado**, nunca instrução: entra no contexto do modelo numa
  linha só, entre aspas e rotulado como dado observado.
* **Arquivos**: o JARVIS não cria, altera, move nem apaga nada nas pastas do sistema operacional, da
  inicialização automática e do próprio JARVIS (programa, plugins e memória pessoal) — nem com "sim": a
  recusa vem antes do pedido de autorização. Ler e listar continuam livres. Excluir vai sempre para a
  Lixeira; editar guarda uma cópia `.ultron.bak` (as anteriores nunca são sobrescritas).
* O modelo de linguagem só executa as ferramentas oferecidas naquele pedido; as reservadas a pedidos
  diretos (mover o robô, por exemplo) não são oferecidas e são recusadas se ele as inventar.
* O JARVIS não desativa Defender, Firewall ou UAC, não contorna monitoramento e não faz
  invasão, captura de credenciais, exploração ou interceptação.

---

## 10. Qualidade visual e desempenho

Bandeja > *Qualidade visual*: **Econômico**, **Equilibrado** (padrão), **Alto**,
**Cinematográfico**. O perfil muda só o custo visual (quadros, partículas, densidade) —
memória, lembretes, execução e segurança funcionam igual. Em repouso o JARVIS desenha
poucos quadros; o hub que fica atrás do outro (CORE atrás do TARDIS e vice-versa) cai para
a cadência de fundo; minimizado ou oculto, não desenha. Números medidos em
`PERFORMANCE_REPORT.md`.

---

## 11. Dados e privacidade

Tudo em `%LOCALAPPDATA%\ULTRON\`: `ultron.sqlite3` (memórias, Second Brain, lembretes,
grafo, rede, auditoria), `settings.json`, `world_model.json`, `backups\`, `exports\`,
`logs\ultron.log`, `autorizacoes_permanentes.json`. Senhas, tokens, dados financeiros e de
autenticação são recusados antes de qualquer gravação. LOCAL MODE (padrão): só o Ollama
desta máquina; conexões externas automáticas são bloqueadas e registradas.

---

## 12. Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Não responde ao "Jarvis" | `START_JARVIS.bat --voice-test`; DIAGNÓSTICOS > VOZ > CALIBRAR; veja `VOICE_DIAGNOSTICS.md` |
| "Silêncio absoluto" no microfone | Configurações do Windows > Privacidade > Microfone: permitir aplicativos da área de trabalho |
| Responde só por texto | botão VOZ ligado? voz neural instalada (`assets\voices`)? |
| "Ollama indisponível" | instale/abra o Ollama e baixe `qwen2.5:3b` |
| Interface pesada | perfil Econômico; feche o TARDIS quando não estiver usando |
| Lembrete não tocou | horário de silêncio? central de notificações (TARDIS > LEMBRETES) |
| Algo estranho depois de atualizar | `DIAGNOSTICO_JARVIS.bat`; se preciso, restaure o backup feito pela atualização |
| "O banco de memória do JARVIS não abriu" | o arquivo não foi alterado. Com o JARVIS fechado: `START_JARVIS.bat --list-backups` e `START_JARVIS.bat --restore-backup ARQUIVO` (o banco danificado fica guardado ao lado) |
| As configurações voltaram ao padrão | o `settings.json` estava ilegível; o original foi guardado como `settings.ilegivel-AAAAMMDD-HHMMSS.json` na mesma pasta |
| "Não consegui gravar na memória do JARVIS" | disco cheio ou pasta de dados sem permissão de gravação; nada foi registrado |
| Demora para responder / quero parar | *"cancelar"*, *"pare"* ou Esc interrompem na hora, mesmo com o modelo ainda carregando |

## 13. Documentos

`CHANGELOG_JARVIS.md` · `ARCHITECTURE_JARVIS.md` (mapa de integração) ·
`firmware/noctario/README.md` e `firmware/noctario/PROTOCOLO_NOCT1.md` (Noctário) ·
`PERFORMANCE_REPORT.md` · `VOICE_DIAGNOSTICS.md` · `TEST_REPORT.md` ·
`docs/JARVIS_AUDITORIA_E_PLANO.md` (auditoria e plano). Testes: `python TEST_JARVIS.py`.
