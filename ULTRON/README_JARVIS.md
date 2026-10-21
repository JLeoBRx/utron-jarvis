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
| F2 | TARDIS (memória pessoal) |
| F4 | NOCTÁRIO (robô) |
| F5 | ATIVIDADES (histórico) |
| F6 | CONFIGURAÇÕES |
| F3 ou F7 | DIAGNÓSTICOS (voz, rede, autonomia, desempenho, eventos, log, serviços e GPU) |
| F11 | tela cheia |
| Esc | como no original: interrompe a fala; senão cancela o pedido ou a autorização pendente; senão sai da tela cheia. Nunca minimiza. No TARDIS, fecha a região aberta |
| Ctrl+M | microfone |
| Ctrl+L | limpa a conversa da tela |

Por voz: *"abra o TARDIS"*, *"abra as configurações do JARVIS"* (sem "do JARVIS", abre as
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
* **REDE LOCAL** — aparelhos da sua rede (seção 7).
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

## 4. TARDIS (memória espacial)

Abra pelo botão TARDIS, por **F2** ou dizendo *"abra o TARDIS"*. No centro, a **câmara de
energia** (HOJE: prioridades, compromissos, atrasados); em volta, portais para as regiões:

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
"ideia: …", "o que está atrasado?"). **← JARVIS CORE** volta ao hub principal sem perder
câmera, região ou filtros. **EXPORTAR** (JSON/CSV) e **BACKUP** ficam na barra superior;
**SOM AMBIENTE** é opcional (desligado por padrão).

Pulsos percorrem os corredores só quando algo real acontece (registro criado, editado,
concluído, lembrete disparado).

---

## 5. Falando com o JARVIS

**Voz.** Diga **"Jarvis"** no início: *"Jarvis, abra o bloco de notas"*. Depois de uma
resposta há 12 s de continuação sem repetir o nome. *"Pare"* interrompe a fala;
*"fique quieto"* / *"pode falar"* desligam/religam a voz. Se ele não entende o seu "Jarvis",
use DIAGNÓSTICOS > VOZ > **CALIBRAR**.

**Texto.** Digite na barra inferior (↑/↓ percorrem o histórico).

Exemplos: *"o que tenho para hoje?"*, *"lembre-me de pagar a conta amanhã às 9h"*,
*"anote uma ideia: horta vertical"*, *"tenho conflito de horário na agenda?"*,
*"exporte minhas tarefas em planilha"*, *"faça um backup da memória"*, *"quais dispositivos
estão na rede?"*, *"diagnóstico de voz"*, *"revogue as autorizações"*, *"prepare meu projeto
Atlas"*, *"o que está na tela?"*.

Quando falta informação essencial, ele faz **uma** pergunta objetiva; quando há evidência
suficiente no contexto, completa o pedido; nunca diz que fez algo sem verificar.

---

## 6. Memória pessoal e lembretes

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

## 7. Rede local

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

## 8. Autonomia e segurança

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
* Texto da tela, de arquivos e de páginas é **dado**, nunca instrução.
* O JARVIS não desativa Defender, Firewall ou UAC, não contorna monitoramento e não faz
  invasão, captura de credenciais, exploração ou interceptação.

---

## 9. Qualidade visual e desempenho

Bandeja > *Qualidade visual*: **Econômico**, **Equilibrado** (padrão), **Alto**,
**Cinematográfico**. O perfil muda só o custo visual (quadros, partículas, densidade) —
memória, lembretes, execução e segurança funcionam igual. Em repouso o JARVIS desenha
poucos quadros; o hub que fica atrás do outro (CORE atrás do TARDIS e vice-versa) cai para
a cadência de fundo; minimizado ou oculto, não desenha. Números medidos em
`PERFORMANCE_REPORT.md`.

---

## 10. Dados e privacidade

Tudo em `%LOCALAPPDATA%\ULTRON\`: `ultron.sqlite3` (memórias, Second Brain, lembretes,
grafo, rede, auditoria), `settings.json`, `world_model.json`, `backups\`, `exports\`,
`logs\ultron.log`, `autorizacoes_permanentes.json`. Senhas, tokens, dados financeiros e de
autenticação são recusados antes de qualquer gravação. LOCAL MODE (padrão): só o Ollama
desta máquina; conexões externas automáticas são bloqueadas e registradas.

---

## 11. Problemas comuns

| Sintoma | O que fazer |
|---|---|
| Não responde ao "Jarvis" | `START_JARVIS.bat --voice-test`; DIAGNÓSTICOS > VOZ > CALIBRAR; veja `VOICE_DIAGNOSTICS.md` |
| "Silêncio absoluto" no microfone | Configurações do Windows > Privacidade > Microfone: permitir aplicativos da área de trabalho |
| Responde só por texto | botão VOZ ligado? voz neural instalada (`assets\voices`)? |
| "Ollama indisponível" | instale/abra o Ollama e baixe `qwen2.5:3b` |
| Interface pesada | perfil Econômico; feche o TARDIS quando não estiver usando |
| Lembrete não tocou | horário de silêncio? central de notificações (TARDIS > LEMBRETES) |
| Algo estranho depois de atualizar | `DIAGNOSTICO_JARVIS.bat`; se preciso, restaure o backup feito pela atualização |

## 12. Documentos

`CHANGELOG_JARVIS.md` · `ARCHITECTURE_JARVIS.md` (mapa de integração) ·
`PERFORMANCE_REPORT.md` · `VOICE_DIAGNOSTICS.md` · `TEST_REPORT.md` ·
`docs/JARVIS_AUDITORIA_E_PLANO.md` (auditoria e plano). Testes: `python TEST_JARVIS.py`.
