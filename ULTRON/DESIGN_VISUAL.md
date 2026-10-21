# JARVIS ULTIMATE — Design visual

Entregável 4. Uma plataforma, três identidades com a mesma gramática: fundo espacial profundo,
luz como informação, tipografia técnica, movimento só quando há um sinal real.

## 1. Fundamentos comuns

| Token | Valor | Uso |
|---|---|---|
| `space` | `#030712` | fundo de todas as áreas |
| `abyss` / `deep` | `#071426` / `#0B1F3A` | painéis, trilhos, superfícies |
| `ice` | `#DCEEFF` | texto principal |
| `dim_text` | `#7F9BB7` | texto secundário |
| `alert` | `#FFB547` | aviso, autorização pendente (âmbar suave, sem piscar) |
| `error` | `#FF5D73` | falha real (coral, identificável sem alarme) |

* **Fonte única de cores:** `ultron/hud/palette.py` (sem Qt) → `ultron/hud/theme.py`. Nenhum
  módulo define cores próprias; as três identidades abaixo também vivem ali.
* **Tipografia:** títulos em Bahnschrift/Segoe UI, caixa alta com espaçamento; dados em Cascadia
  Mono/Consolas. Legendas da fala em corpo grande (≥ 18 px em 1320×820), alto contraste.
* **Legibilidade antes do efeito:** texto sobre painel com contraste ≥ 4,5:1; nada pisca acima de
  3 Hz; efeitos pesados desligáveis; o perfil Econômico reduz densidade e brilho.
* **Movimento:** transições de 150–400 ms com aceleração suave; repouso quase parado (respiração
  lenta e discreta); qualquer animação mais intensa corresponde a um evento real.

## 2. JARVIS — presença holográfica (ciano sobre azul profundo)

| Token | Valor | Papel |
|---|---|---|
| `cyan` | `#00D9FF` | atividade, percepção, dados |
| `glow` | `#67F3FF` | olhos, lábios, silhueta, brilho |
| `electric` | `#168BFF` | estrutura, execução, planejamento |
| `tech` | `#075985` | contornos apagados |

**Rosto:** cabeça robótica esculpida (crânio, têmporas, órbitas, maçãs, nariz, lábios, queixo)
desenhada como holograma: contornos de varredura que seguem o relevo, meridianos discretos,
silhueta com luz de borda, costuras de placas faciais, orelhas modulares com anéis, pescoço e colar
com o **reator** (herança do avatar original), olhos luminosos com íris, boca com abertura real e
"grade de voz" interna. Material translúcido: linhas mais fracas atrás, mais fortes de frente e na
borda; brilho real (camada desfocada) nos olhos, lábios e silhueta.

**Ambiente:** grade 3D em perspectiva sob o projetor, plataforma de projeção com raios (DNA do
original), feixe do projetor, partículas que sobem, linhas de varredura finas, anéis orbitais com
marcações, projeções de dados (estado, modelo, microfone, tarefa), forma de onda da voz real.
Nada disso cobre o texto: legendas e conversa ficam em painéis translúcidos legíveis.

### 2.1 Os 12 estados

| Estado | Rótulo | Olhos e rosto | Iluminação e ambiente | Indicadores |
|---|---|---|---|---|
| Inicializando | INICIALIZANDO | o rosto se monta por um plano de varredura que desce conforme o progresso real do boot | grade acende de baixo para cima | etapas do boot |
| Aguardando | EM ESPERA | olhar à frente, piscadas naturais | azul profundo, respiração lenta | relógio, microfone |
| Escutando | ESCUTANDO | atenção: sobrancelhas sobem, olhos mais abertos, cabeça levemente inclinada | halo ciano que acompanha o nível real do microfone | nível do microfone |
| Reconhecendo a fala | RECONHECENDO | olhos focados, micro-movimentos | anéis de áudio de entrada | texto parcial reconhecido |
| Pensando | PENSANDO | olhar desvia e varre; sobrancelhas levemente franzidas | linhas de dados correm pelos anéis | fase cognitiva |
| Consultando a TARDIS | CONSULTANDO A TARDIS | olhar para o lado, íris âmbar | feixe âmbar ligando o rosto ao emblema da TARDIS | tarefa e tempo decorrido |
| Executando | EXECUTANDO | expressão firme | pulsos elétricos pelos anéis a cada etapa real | etapa atual / total |
| Falando | FALANDO | **boca sincronizada com o áudio real**, acenos sutis nas sílabas fortes | anéis de saída pela voz real | legenda com a palavra atual |
| Aguardando confirmação | AGUARDANDO CONFIRMAÇÃO | olhar direto, sobrancelhas erguidas (pergunta) | contorno âmbar estável | ação pendente e botões |
| Alerta | ALERTA | atenção súbita | tinta âmbar sobre o estado atual | motivo do alerta |
| Erro de integração | ERRO DE INTEGRAÇÃO | leve "falha" de projeção (deslocamento horizontal discreto) | contorno coral fixo | componente e causa |
| Privacidade | PRIVACIDADE · MICROFONE DESLIGADO | olhos apagados por uma "viseira" de linhas | brilho reduzido, sem partículas | microfone desligado em destaque |

## 3. TARDIS — sala de controle (petróleo profundo e energia âmbar)

| Token | Valor | Papel |
|---|---|---|
| `tardis_hull` | `#06222E` | estrutura da sala |
| `tardis_panel` | `#0B3443` | console e painéis |
| `tardis_roundel` | `#5FD3E6` | nichos circulares das paredes (luz fria) |
| `tardis_energy` | `#FFB347` | energia do rotor, ativação |
| `tardis_core` | `#FFE3A8` | núcleo do rotor |
| `tardis_fault` | `#FF6B3D` | falha (pulso âmbar-avermelhado) |

Sala circular com paredes de nichos circulares, piso em grade concêntrica, pilares curvos, console
hexagonal com seis painéis (ANÁLISE, PLANEJAMENTO, ARQUIVO, ROTINAS, TELEMETRIA, DIAGNÓSTICO) e o
**rotor temporal** no centro: coluna de vidro com anéis e cristais internos que sobem e descem.

| Estado do motor da TARDIS | Rotor | Sala |
|---|---|---|
| Repouso | subida e descida lentas, brilho baixo | nichos em luz fria tênue |
| Processando | ciclo rápido, brilho alto, pulsos sobem pela coluna | painéis ativos acendem |
| Operação (gravando, sincronizando) | anéis giram em sentidos opostos | cascata de luzes no console |
| Falha | brilho âmbar-avermelhado intermitente lento | anel de alerta no piso, painel com a causa |
| Consulta do JARVIS | feixe ciano liga o rotor ao emblema do JARVIS | rótulo "JARVIS ⇄ TARDIS" |

Referência criativa a Doctor Who sem copiar logotipos, sons ou elementos protegidos.

## 4. NOCTÁRIO — painel de engenharia (grafite e sinais)

| Token | Valor | Papel |
|---|---|---|
| `noct_base` | `#0A0F15` | fundo do painel |
| `noct_grid` | `#1A2633` | grades dos gráficos |
| `noct_ok` | `#3DFFA8` | sinal confirmado pelo robô |
| `noct_pending` | `#FFD447` | solicitado, aguardando confirmação |
| `noct_stop` | `#FF4D4D` | PARADA DE EMERGÊNCIA |
| `noct_line` | `#00D9FF` | posição estimada da linha |

Visualizações: barras dos 8 sensores (refletância calibrada 0–1000, branco = linha) com o
marcador da posição estimada; gráfico do erro e da correção PD; medidores de PWM esquerdo e
direito com a velocidade-alvo; contador de cruzamentos (n / destino); chips de estado (conexão,
seguidor, calibração, modo, recuperação); última falha; histórico das operações.
**Estado solicitado × confirmado:** amarelo = solicitado e aguardando o robô; verde = confirmado
pelo robô; cinza = sem dados. Sem conexão, os gráficos ficam vazios com "SEM CONEXÃO" — nunca
valores inventados. O botão **PARADA** é vermelho, grande, sempre visível na página e também como
chip na barra global (F12).

## 5. Navegação e transições

Barra superior: emblema MARK VII + nome da área, abas (JARVIS · TARDIS · NOCTÁRIO · ATIVIDADES ·
CONFIGURAÇÕES · DIAGNÓSTICOS), chips (microfone, voz, IA, Noctário, bateria, Wi-Fi, sessão),
relógio e data. Trocar de área: varredura holográfica de ~300 ms; a página anterior continua viva
(tarefas, conexões e animações reais seguem; o desenho pausa quando a página não está visível).
