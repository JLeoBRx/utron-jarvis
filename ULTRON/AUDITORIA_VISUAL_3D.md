# Redesign premium J.A.R.V.I.S. / TARDIS 3D — auditoria, arquitetura e evidências

Este documento cobre as cinco etapas pedidas (auditoria → ambiente → avatar → integração → polimento), as
decisões técnicas com o motivo de cada uma e **o que foi verificado e como**. O que não foi verificado está
dito na seção 9.

> As imagens de referência citadas no pedido ("imagens 1–3") **não chegaram** a esta sessão: o visual foi
> construído a partir do texto do pedido.

## 1. Etapa 1 — auditoria do que existia

| Peça | Como era | Limite encontrado |
|---|---|---|
| Página JARVIS | `AvatarView` — rosto holográfico desenhado com QPainter (CPU) ou QOpenGLWidget + QPainter | só cabeça e colar; 12–19 ms/quadro na CPU (benchmark da Fase 4); sem corpo, sem câmera livre |
| Sala da TARDIS | `RoomView` — projeção 3D feita à mão em NumPy + QPainter (linhas, polígonos) | "3D" por arame; sem materiais, luz ou profundidade real; rotor e console simplificados |
| Exterior da TARDIS | não existia | — |
| ORBE | botão **ORBE** (barra inferior) e **Esc** → `HudController.collapse()`: esconde a janela e mostra `OrbWindow`, um orbe 2D flutuante (sempre visível, arrastável; clique duplo expande; botão direito abre o menu). `avatar_mode="neural"` mostra o núcleo neural 2D (`BrainView`) no lugar do rosto | o orbe é 2D; não havia núcleo 3D dentro da interface |
| Estados | `avatar/states.py` resolve 12 estados a partir de sinais REAIS (estado central, eventos, telemetria, fala) | — (reaproveitado sem mudança) |
| Dependências | `PySide6-Essentials` (sem QtWebEngine, sem Qt Quick 3D) | — |

**Comportamento do botão ORBE identificado e preservado:** ele continua recolhendo a janela no orbe flutuante
(nada mudou no `collapse()`/`expand()`/`OrbWindow`). O ORBE 3D novo é o **núcleo dentro da cena** (vista
NÚCLEO), não uma segunda janela nem um segundo motor.

### Alternativas avaliadas

| Opção | Por que não / por que sim |
|---|---|
| Continuar no QPainter | não chega a corpo inteiro, materiais e luz em tempo real sem custo alto na thread da interface |
| Qt Quick 3D | exige reescrever a vista em QML e modelos em arquivos (`.mesh`); malha procedural com 51 ossos e *skinning* próprio fica difícil |
| OpenGL cru (QOpenGLWidget) | seria escrever um motor 3D (pós-processamento, materiais PBR, sombras, partículas) do zero |
| **Three.js num QWebEngineView** | motor maduro (PBR, bloom, controles de câmera), roda no processo de desenho do Chromium (fora do GIL do Python), uma página local, sem rede; **escolhido** |

Não é uma migração: o resto da interface continua Qt; só a vista central da página JARVIS e a vista da sala
da TARDIS passam a ser a cena 3D. O desenho 2D antigo continua no projeto como **reserva** automática.

## 2. Arquitetura (módulos)

```
ultron/hud/scene3d/
  __init__.py       disponibilidade (configuração, plataforma, QtWebEngine, marcador de falha), prepare_qt()
  view.py           Scene3DView (QWebEngineView + _AvatarCore): ponte QWebChannel, bloqueio de rede, reserva
  web/index.html    página local; importmap para o three embutido
  web/css/scene.css camada de interface (vidro escuro, bordas finas, tipografia técnica)
  web/js/engine.js  motor: WebGL2, compositor (bloom), ritmo de quadros, qualidade adaptativa, perda de contexto
  web/js/materials.js materiais e texturas feitos no código (holograma com skinning na GPU, metais, madeira)
  web/js/avatar.js  holograma de corpo inteiro: esqueleto de 51 ossos, malha, projetor, movimento por estado
  web/js/exterior.js a cabine azul por fora
  web/js/room.js    sala de controle: paredes, roundels, galeria, console de 6 painéis, rotor do tempo
  web/js/orb.js     ORBE: núcleo, rede neural, filamentos, anéis orbitais, partículas, ondas
  web/js/deck.js    o convés do JARVIS: piso gravado, salão de nervuras, feixes, poeira, painel de sistema
  web/js/camera.js  vistas nomeadas, voo suave, órbita/zoom com limites, enquadramento do corpo inteiro
  web/js/hud.js     estado, legenda sincronizada, cartões presos à cena, avisos, botões de vista
  web/js/bridge.js  QWebChannel (página ⇄ Python)
  web/js/main.js    montagem, transições pela porta, cliques, demonstração rotulada (só fora do JARVIS)
  web/vendor/three  three.js r170 (licença MIT, arquivo LICENSE junto)
```

**Um motor, uma cena.** A mesma `Scene3DView` é a vista da página JARVIS e, quando a página TARDIS abre, é
**emprestada** à sala (`TardisRoomPage.attach_scene3d`) — a página JARVIS fica com um fundo neutro enquanto
isso. Não existe segundo QWebEngineView nem segunda instância do Three.js.

### Fluxo de dados

* **Python → página** (`JARVIS.receive`): o sinal resolvido pelo mesmo `states.resolve` do rosto 2D (estado,
  rótulo e motivo, cores do estado, forma da boca da trilha labial, níveis reais de microfone e saída,
  progresso real do boot, tarefa em curso, projeções reais, legenda), a fotografia do motor da TARDIS (modo e
  estilo do rotor vindos de `tardis_room/scene.py`, atividade de cada painel, telas) e pedidos de vista/modo.
  30 envios/s só durante fala e escuta; 4/s no resto; 1/s de batimento sem mudança.
* **Página → Python** (`QWebChannel`, objeto `jarvis`): `ready`, `report` (estatísticas, erros de JS, perda de
  contexto, falha), `select(painel)` e `request(ação)`. **As ações aceitas são só `tardis`, `jarvis` e `mic`**
  (lista fechada em `view.py`); qualquer outra é registrada e ignorada. Elas seguem o mesmo caminho dos botões
  da interface (`open_tardis`, `open_page`, botão do microfone).

## 3. O que cada estado REAL faz na cena

| Estado (sinal real) | Holograma | ORBE |
|---|---|---|
| Em espera | respiração, apoio alternado, olhar que deriva, piscadas | pulsos raros e lentos, anéis lentos |
| Escutando / reconhecendo (escuta aberta, parciais do reconhecimento) | atenção, leve inclinação, ondas na base, brilho pelo nível real do microfone | partículas convergem ao núcleo, ondas que se fecham, núcleo oscila com o microfone |
| Pensando (contexto, decisão, planejamento) | mão ao queixo, olhar que varre, pulsos de circuito no corpo | pulsos rápidos e numerosos pela rede, anéis acelerados |
| Falando (posição real de reprodução) | mandíbula e boca pela trilha labial; gestos e acenos só com energia real da voz | partículas saem do núcleo e o núcleo pulsa com a energia real da voz |
| Executando (execução, verificação, recuperação) | mãos em trabalho, painel com o texto REAL da tarefa | circuitos rápidos, fluxo de partículas |
| Consultando a TARDIS | olhar para a cabine | executando |
| Confirmação / alerta | âmbar, mãos abertas (confirmação) | âmbar |
| Erro de integração | tom coral, falha de projeção, postura caída, tudo mais lento | âmbar/coral, quase parado |
| Privacidade | brilho baixo, olhos apagados | quase apagado |
| Inicializando | o corpo se monta de baixo para cima pelo progresso REAL do boot | partículas convergindo |
| (sem sinal do Python há > 6 s) | — | **SEM CONEXÃO**: apagado; a página avisa "sem sinal" |

**TARDIS:** o rotor (curso, velocidade, giro, brilho, cor) segue o modo REAL do motor (repouso, processando,
operação, consulta do JARVIS, falha) — os mesmos valores de `tardis_room/scene.py`. Cada painel do console
(botões, luzes indicadoras, ponteiros, alavancas) acende só enquanto uma tarefa REAL do seu tipo roda, pisca
âmbar ao concluir e vermelho ao falhar; a tela de cada painel e as telas holográficas mostram o texto que o
motor informou ("sem tarefa nesta sessão" quando não há). O fluxo de partículas JARVIS → rotor só existe com
uma tarefa pedida pelo JARVIS em execução. A lâmpada da cabine pulsa com o modo real. Sem motor, a sala fica
apagada e diz "TARDIS indisponível". **Não há viagem no tempo simulada.**

## 4. Interação

* Vistas: FRENTE (corpo inteiro, enquadramento automático pela proporção da janela), NÚCLEO (ORBE ampliado,
  com órbita/zoom e cartões de estado; Esc ou FRENTE volta sem perder nada), CABINE, ENTRAR NA TARDIS. Na
  TARDIS: CONSOLE, PAINEL, VOLTAR AO JARVIS. Arrastar gira, rolar aproxima (com limites), duplo clique volta.
* Clique na cabeça do holograma: liga/desliga o microfone (como o clique no rosto 2D). Clique no ORBE: vista
  NÚCLEO. Clique na cabine: entra na TARDIS. Clique num painel do console: escolhe o painel (é a mesma aba
  ANÁLISE/PLANEJAMENTO/… do lado direito).
* Passagem JARVIS ⇄ TARDIS pela porta da cabine (portas abrem, clarão, sala por dentro). Com efeitos pesados
  desligados ou perfil econômico, a troca é instantânea.

## 5. Desempenho (o que existe e o que foi medido)

* Ritmo próprio: teto de quadros por perfil (econômico 30/20, equilibrado 45/30, alto 60/40, cinematográfico
  60/50 — ativo/repouso); pausa total quando a janela some (página oculta → o Chromium para de desenhar).
* Qualidade adaptativa medida a cada 2 s: abaixo de 72 % da meta por duas janelas seguidas, desce um degrau
  (resolução → brilho → partículas); acima de 95 % por seis janelas, sobe de volta.
* Instâncias (botões, luzes, alavancas, roundels, colunas, nervuras), materiais compartilhados, geometria
  estática agrupada por material (`Batch`), partículas animadas na GPU, liberação de tudo no encerramento,
  perda/recuperação do contexto WebGL tratada (sem recuperação em 6 s → reserva 2D).
* O desenho roda no processo do Chromium: na thread da interface do Python fica só o envio dos sinais.

Medições (`docs/benchmarks/cena3d.json`, `python tools/benchmark_scene3d.py --seconds 14`, janela 1280×760,
estado "falando") — **só com renderização por software** (Mesa llvmpipe, sem placa de vídeo, 4 CPUs):

| Perfil | q/s (mediana) | meta | degrau de redução atingido | desenhos/quadro | triângulos | Python por passo |
|---|---|---|---|---|---|---|
| econômico | 9,3 | 30 | 2 | 75 | 57 mil | 0,80 ms |
| equilibrado | 3,7 | 45 | 3 | 75 | 57 mil | 0,85 ms |
| alto | 3 | 60 | 3 | 75 | 57 mil | 0,74 ms |
| cinematográfico | 1,6 | 60 | 2 (ainda descendo) | 88 | 57 mil | 0,82 ms |

O que esses números provam: a qualidade desce sozinha quando a máquina não acompanha, e a thread da interface
do Python gasta ~0,8 ms por passo com a cena 3D (o rosto 2D gastava 12–19 ms de pintura por quadro na mesma
thread — Fase 4). O que eles **não** dizem: quantos quadros por segundo a cena terá numa placa de vídeo — para
isso, rode `python tools/benchmark_scene3d.py` no próprio computador.

**Defeito encontrado pela medição e corrigido:** abaixo de ~2,5 q/s a página não gerava estatística e a
qualidade **não descia** (justamente quando mais precisava); depois, a primeira correção passou a reagir aos
quadros lentos da compilação de shaders na abertura. Agora a meta é comparada com os quadros realmente
desenhados na janela de 2 s, com 5 s de aquecimento na abertura e 3 s de espera depois de cada ajuste.

## 6. Reserva 2D (a interface nunca fica em branco)

A cena 3D só é usada quando: CONFIGURAÇÕES > APARÊNCIA > **Cena 3D** = Automática; a plataforma gráfica tem
janela (nunca no modo `offscreen`); o QtWebEngine importa (`PySide6-Addons`); e a última tentativa não falhou.
Ela cai para o rosto 2D, com o motivo no registro, em DIAGNÓSTICOS e numa notificação, quando: o WebGL 2 não
abre, a página não diz "pronta" em 25 s, o processo de desenho termina, o contexto WebGL some e não volta em
6 s. Uma falha fica anotada (`cena3d.estado` na pasta de dados) e a próxima abertura já usa 2D; para tentar de
novo: Cena 3D → Desligada → Automática. Um processo que morre durante a abertura também deixa a anotação.

## 7. Segurança

* Página 100 % local; um interceptador bloqueia qualquer endereço que não seja a própria pasta da cena
  (`file://…/scene3d/web`) ou o `qwebchannel.js` embutido no Qt; navegação para fora é recusada; janelas
  novas, área de transferência, plugins e conteúdo remoto desligados; perfil sem cache e sem cookies em disco.
* A página não executa nada no computador: só pede (três ações fechadas), e quem decide é o Python pelo mesmo
  caminho dos botões. Textos vindos do modelo ou do usuário entram na página como dados (`textContent`, canvas),
  nunca como HTML.
* Sem modelos de terceiros: cabine, sala, console, rotor, holograma e ORBE são geometria construída no código;
  texturas desenhadas em canvas. O único código de terceiros é o three.js r170 (MIT), embutido com a licença.

## 8. Testes e evidências

| Verificação | Onde | Resultado |
|---|---|---|
| Disponibilidade, marcador de falha, pasta permitida, arquivos e importações da página, ausência de endereços remotos, licença, rótulo da demonstração, lista fechada de pedidos, sintaxe dos módulos (node) | `tests/test_scene3d.py` (sem tela) | passa em 3.11 e 3.13 |
| Controlador com uma cena FALSA (mesma interface): empréstimo à TARDIS e devolução, clique no painel 3D = aba, pedidos da página, lâmpada da cabine pelo `TARDIS_STATE`, queda → rosto 2D na hora, desligar nas configurações | `tests/test_scene3d.py::ControllerSceneTest` | passa — **teste de lógica, não de WebGL** |
| Cena REAL (QtWebEngine + WebGL desta máquina) num processo próprio: pronta, sinais chegam, modo JARVIS mostra o convés, modo TARDIS mostra a sala e o painel escolhido, botão da página vira pedido ao Python, zero erros de JS | `tests/test_scene3d.py::NativeSceneTest` + `tests/scene3d_probe.py` | Linux + Xvfb (llvmpipe): passa, pronta em ~2,4 s. Windows: roda no CI nativo (resultado no relatório do CI) |
| JARVIS completo (núcleo real) com a cena: `main.py --gui-check` | Xvfb | "cena 3D pronta, WebGL 2 (llvmpipe)", montada em 4,3 s |
| App completo: ida e volta da TARDIS, tarefa REAL (coordenação de módulos) acendendo o painel DIAGNÓSTICO com o resumo verdadeiro, clique no painel 3D, queda simulada → 2D, sala 2D volta a desenhar | roteiro em Xvfb | os 9 passos conferidos |
| Falha real de WebGL (Chromium recusa o llvmpipe sem `--ignore-gpu-blocklist`) | Xvfb | "o WebGL 2 não abriu…" → reserva 2D em 0,4 s |

Capturas (`docs/capturas/`, renderização por software): `cena3d_app_jarvis.jpg` e
`cena3d_app_tardis_diagnostico.jpg` são do **JARVIS real** (núcleo real, Xvfb) — na segunda, a tela 3D do painel
DIAGNÓSTICO mostra o resumo verdadeiro da tarefa "coordenação de módulos", o mesmo do RESULTADO ao lado. As
outras (`cena3d_demo_*.jpg`) são da página aberta fora do JARVIS, com o aviso "DEMONSTRAÇÃO … não são dados
reais" visível na própria imagem.

## 9. Limitações conhecidas (honestas)

* **Não verificado no computador do usuário**: placa de vídeo, driver, quadros por segundo reais e a
  aparência na tela dele. O CI do Windows roda num servidor sem placa de vídeo dedicada.
* O pacote `PySide6-Addons` (QtWebEngine) é grande: **122 MB** de download no Windows (6.8.1). Sem ele, tudo
  funciona com a vista 2D.
* O rosto do holograma 3D é menos detalhado que o rosto 2D antigo (que era só cabeça); a boca usa abertura,
  largura e arredondamento da trilha labial real, sem língua/dentes.
* O orbe flutuante do botão ORBE continua 2D (comportamento original preservado); o ORBE 3D é a vista NÚCLEO.
* Com renderização por software a cena roda devagar (3–8 quadros/s medidos aqui) e a qualidade desce sozinha;
  as transições ficam lentas nesse caso.
* Linux: o Qt Quick é forçado para OpenGL (com Vulkan disponível, o compositor do QtWebEngine entregava
  imagem vazia). No Windows fica o padrão do Qt.
