# Especificação da interface do SAFRA

Especificação da Fase 2. Define **o que** a interface precisa ter e as regras do design system; o desenho final
de cada tela e do símbolo é trabalho da Fase 4, que começa por estudos para a sua escolha (seção 11). Os valores
de contraste citados foram calculados (WCAG 2.x) sobre a paleta definida.

## 1. Direção

Híbrida: **minimalista** no dia a dia, **densa e informativa** na central de comando. A mesma aplicação, os
mesmos dados; muda a densidade.

| Princípio | Regra |
|---|---|
| Verdade | a interface só mostra o que o núcleo informa. Sem conexão, mostra "sem conexão" e desabilita ações. Demonstrações e dados simulados levam uma faixa permanente "DADOS SIMULADOS" |
| Calma | uma coisa pede atenção por vez. Vermelho é marca e ação principal; não é enfeite |
| Profundidade discreta | 2.5D por camadas, sombras curtas e realces de borda. Nada de 3D, perspectiva de cena, personagens ou rostos |
| Originalidade | nenhuma forma, tela ou nome que lembre obras ou produtos de terceiros (seção 4.4) |
| Acesso | tudo por teclado; contraste conferido por teste; movimento reduzido respeitado |

## 2. Arquitetura da informação

Dois contextos, alternados por um controle sempre visível e por atalho.

```
SAFRA
├── Cotidiano                      #/
│   ├── Símbolo (estado real)
│   ├── Conversa e entrada (texto, microfone)
│   └── Atenção: autorização pendente · próximos lembretes · falhas
└── Central de Comando             #/central
    ├── Visão geral                estado, componentes, saúde, modelo, voz, atividade recente
    ├── Atividades                 pedidos, ações, confirmações, falhas; filtro e detalhe
    ├── Memória                    registros, lembretes, busca, lixeira; fatos (leitura)
    ├── Projetos                   lista; projeto com notas, itens ligados e análises
    ├── Análises                   fila, tarefas, resultados, ações propostas
    ├── Habilidades                lista por categoria, risco, disponibilidade; plugins
    ├── Voz                        estado, dispositivos, diagnóstico de 8 etapas, calibração, tecla de atalho
    ├── Saúde                      CPU, memória, disco, métricas, eventos, log
    ├── Rede                       inventário passivo da rede local
    └── Configurações              geral e início · voz e áudio · inteligência · privacidade ·
                                   permissões e Modo Operador · aparência · painel e sessões · dados e backups
```

Elementos presentes nos dois contextos: barra de estado (conexão, estado do núcleo, modo privacidade, Modo
Operador), **autorização pendente** e notificações.

### 2.1 Cotidiano

```
┌──────────────────────────────────────────────────────────────┐
│ SAFRA                    ● pronto            [Central] [⚙]   │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│                        ( SÍMBOLO )                           │
│                      "estou ouvindo"                         │
│                                                              │
│   você   que horas são?                                      │
│   SAFRA  São 14h32.                       ação verificada    │
│                                                              │
│ ┌ Atenção ─────────────────────────────────────────────────┐ │
│ │ Confirmar: mover 3 arquivos para a Lixeira   [Negar][Sim]│ │
│ └──────────────────────────────────────────────────────────┘ │
│ [ Escreva um pedido…                              ] [mic] [ok] │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Central de Comando

```
┌────────────┬─────────────────────────────────────────────────┐
│ ( símbolo )│ Visão geral                     ● pronto  [Cotid.]│
│ Visão geral├───────────────┬───────────────┬─────────────────┤
│ Atividades │ Núcleo        │ Voz           │ Modelo          │
│ Memória    │ 12/12 no ar   │ microfone ok  │ local · 3b      │
│ Projetos   ├───────────────┴───────────────┴─────────────────┤
│ Análises   │ CPU ▁▂▃▂▁   Memória ▂▂▃▃▂   Fila 0   Latência ▁▁│
│ Habilidades├─────────────────────────────────────────────────┤
│ Voz        │ Atividade recente                               │
│ Saúde      │ 14:32 pedido  que horas são?        concluído   │
│ Rede       │ 14:30 ação    abrir bloco de notas  verificado  │
│ Config.    │ …                                               │
└────────────┴─────────────────────────────────────────────────┘
```

Em telas estreitas a barra lateral vira barra inferior com cinco itens e "mais"; os painéis empilham.

## 3. Paridade com a interface atual

Lista de conferência da migração: cada linha precisa estar atendida antes de a interface antiga sair.

| Hoje | Onde fica |
|---|---|
| Página SAFRA: conversa, entrada de texto, botão de microfone, legendas | Cotidiano |
| Barra de decisão (autorização pendente) | elemento global |
| Holograma, ORBE 3D, cérebro 2D | Símbolo |
| ORBE compacta flutuante; início recolhido; expandir sozinho | janela compacta da casca |
| Bandeja: mostrar, pausar e retomar o Observador, modo privacidade, sair; avisos nativos | bandeja da casca (mais "falar") |
| Página TARDIS: memória pessoal, lembretes, organização, lixeira | Central › Memória |
| Vista "Arquivo" (memória navegável) | Central › Memória (busca e relações) |
| Painéis da sala de controle: análise, planejamento, rotinas, telemetria, diagnóstico | Central › Análises e Saúde |
| Notas e decisões de projeto | Central › Projetos |
| Página ATIVIDADES | Central › Atividades |
| DIAGNÓSTICOS: voz (testar, calibrar), rede local, autonomia, desempenho, eventos, log, serviços | Central › Voz, Rede, Saúde; autorizações permanentes em Configurações › Permissões |
| "Serviços e GPU", "Detectar OpenGL", perfis de qualidade 3D, GPU | **saem** (a interface não usa mais 3D) |
| CONFIGURAÇÕES: geral e início, voz e áudio, inteligência, privacidade e Observador, permissões, aparência, histórico e registros | Central › Configurações (mesmos grupos) |
| Parear dispositivo (QR) | Configurações › Painel e sessões: código para o navegador local; pareamento remoto fica para a etapa posterior |
| Protocolo ULTRON (ativar, demonstração, tecla de emergência) | Modo Operador em Permissões; parada de emergência global; **sem** demonstração nem ativação ocasional |
| Sons da interface | mantidos (opção em Aparência); sons temáticos saem |
| Atalhos F1–F7, F11, Esc, Ctrl+M | na casca: F1 Cotidiano, F2 Memória, F3 Saúde, F5 Atividades, F6 Configurações, F7 Voz, F11 tela cheia, Esc recolher, Ctrl+M microfone. No navegador, só os que não conflitam |

## 4. O Símbolo

### 4.1 Papel

Representa o SAFRA e o que ele está fazendo **agora**. É a única "presença" visual do assistente: não há
rosto, corpo, personagem nem cenário.

### 4.2 Conceito proposto: "Sulcos"

Um conjunto de linhas paralelas levemente curvas — os sulcos de um campo preparado para a safra, vistos de
cima — dentro de um contorno arredondado. A profundidade vem de três camadas sobrepostas com deslocamento
sutil e sombra curta. As linhas se movem conforme o estado real. É uma proposta: a Fase 4 começa com três
estudos (este e dois alternativos) para você escolher antes de qualquer tela ser fechada.

### 4.3 Estados

Só existem os estados abaixo, e cada um tem origem no núcleo. Cada estado difere por **forma e movimento**,
além da cor, e sempre vem acompanhado de um rótulo de texto.

| Estado visual | Origem (`runtime_state` ou outro campo real) | Comportamento |
|---|---|---|
| Inicializando | `BOOTING` | as linhas surgem uma a uma, na proporção dos componentes que já iniciaram |
| Repouso | `IDLE`, `DREAMING` | linhas calmas, deriva lenta |
| Escutando | `LISTENING` | as linhas se aproximam do centro; rótulo "estou ouvindo" |
| Pensando | `PERCEIVING`, `CONTEXT`, `DECIDING`, `THINKING`, `PLANNING`, `IMAGINING`, `SIMULATING`, `NETWORK` | uma onda percorre as linhas em sequência |
| Falando | `SPEAKING` | a amplitude das linhas segue o nível real da voz (`voice.level`); em silêncio, param |
| Executando | `EXECUTING`, `VERIFYING`, `RECOVERY` | um realce avança linha a linha; progresso numérico só se houver progresso real |
| Aguardando confirmação | `AWAITING_AUTHORIZATION` | linhas paradas; marcador âmbar pulsando devagar; a autorização aparece ao lado |
| Atenção | `REMINDING` | um pulso único |
| Erro | `ERROR` | uma linha interrompida; cor de erro (laranja) e ícone; sem tremor |
| Sem conexão | perda da conexão com o núcleo | símbolo acinzentado e parado, com ícone de desconexão |
| Privacidade | `privacy_shield.active` | uma faixa cobre as linhas; rótulo "microfone fechado" |
| Modo Operador | `operator.active` | contorno duplo e selo "MODO OPERADOR" com o tempo restante |

Com "movimento reduzido" ativo, o símbolo fica estático e o estado é dado por um ícone e pelo rótulo.

### 4.4 O que o símbolo não pode lembrar

Anéis concêntricos luminosos com núcleo brilhante, olho ou lente, esfera pulsante, pontos coloridos em linha,
anel de luz giratório, rosto estilizado, silhueta humana, cabine, console de nave. A Fase 4 inclui uma
conferência visual contra símbolos conhecidos de assistentes e de obras de ficção.

### 4.5 Tamanhos

Principal (Cotidiano), médio (barra da Central), compacto (janela compacta, 96–160 px), ícone (bandeja,
janela, aba do navegador, 16–48 px, versão simplificada de três linhas).

## 5. Design system

### 5.1 Cores

| *Token* | Valor | Uso | Contraste |
|---|---|---|---|
| `fundo` | #101114 | fundo da aplicação | — |
| `superficie` | #191B20 | painéis, cartões | — |
| `superficie-elevada` | #23262D | modais, menus, itens em foco | — |
| `vermelho` | #E32636 | ação principal, marca, símbolo | 4,1 sobre o fundo: preenchimentos, ícones, texto ≥ 18 px |
| `vermelho-profundo` | #8F1725 | pressionado, fundos de destaque | texto #F2F2F2 sobre ele: 8,1 |
| `texto` | #F2F2F2 | texto principal | 16,9 / 15,4 / 13,5 sobre os três fundos |
| `texto-secundario` | #A6A8AF | texto de apoio | 7,9 / 7,2 / 6,4 |
| `vermelho-texto` *(derivado)* | #EB5E6A | texto vermelho pequeno, *links* | 5,7 / 5,2 / 4,6 |
| `sobre-vermelho` *(derivado)* | #FFFFFF | rótulo sobre `vermelho` | 4,6 |
| `vermelho-ativo` *(derivado)* | #C81F2E | botão principal sob o cursor | rótulo #FFFFFF: 5,7 |
| `borda` *(derivado)* | #2E323A | divisórias (decorativas) | — |
| `borda-forte` *(derivado)* | #6E727C | contorno de campos e controles | 3,9 / 3,6 / 3,2 |
| `foco` *(derivado)* | #FF6B78 | anel de foco do teclado | 6,9 / 6,3 / 5,5 |
| `sucesso` *(derivado)* | #3FB984 | concluído, verificado | 7,6 sobre o fundo |
| `atencao` *(derivado)* | #F2B544 | confirmação pendente, aviso | 10,3 |
| `informacao` *(derivado)* | #5AA9E6 | informação neutra | 7,4 |
| `erro` *(derivado)* | #FF8A3D | falha | 8,1 |

Regras: os sete primeiros são os valores definidos pelo autor e não mudam. O erro é **laranja**, não vermelho,
para não se confundir com a marca; ainda assim, todo estado vem com ícone e texto, nunca só com cor. Os
derivados podem ser ajustados na Fase 4 desde que o teste de contraste continue passando.

### 5.2 Tipografia

| Papel | Fonte | Tamanho / altura de linha | Peso |
|---|---|---|---|
| Título de tela | Inter | 24 / 32 | 600 |
| Título de seção | Inter | 18 / 26 | 600 |
| Corpo | Inter | 16 / 24 (Cotidiano) · 14 / 20 (Central) | 400 |
| Rótulo, botão | Inter | 14 / 20 | 500 |
| Apoio, legenda | Inter | 12 / 16 | 400 |
| Dados, horários, código, log | JetBrains Mono | 13 / 18 | 400 |
| Estado do símbolo | Inter | 20 / 28 | 500 |

Números em colunas usam algarismos tabulares. Maiúsculas só em selos curtos. As licenças das duas fontes são
confirmadas no inventário antes de os arquivos entrarem no repositório (ADR-020).

### 5.3 Medidas

| Grupo | Valores |
|---|---|
| Espaçamento | 4, 8, 12, 16, 24, 32, 48, 64 px |
| Raio | 4 (campos, selos), 8 (cartões, botões), 12 (modais), círculo (pílulas) |
| Elevação | três níveis = as três superfícies; realce de 1 px no topo; sombra curta só no nível elevado |
| Larguras | 360, 600, 900, 1200, 1600 px |
| Alvo de toque | 44 px no mínimo |

### 5.4 Movimento

| Uso | Duração | Curva |
|---|---|---|
| Resposta a clique, foco | 120 ms | saída suave |
| Abrir menu, alternar aba | 200 ms | saída suave |
| Entrada de painel ou modal | 320 ms | saída suave |
| Troca de estado do símbolo | 600 ms | entrada e saída suaves |

Nada pisca mais de três vezes por segundo. Laços contínuos só no símbolo. Com movimento reduzido: sem laços,
transições de até 100 ms.

### 5.5 Componentes

| Grupo | Componentes | Estados obrigatórios |
|---|---|---|
| Botões | principal, secundário, discreto, perigo, só ícone | normal, cursor, foco, pressionado, desabilitado, carregando |
| Campos | texto, área de texto, número, busca, seleção, alternador, caixa, opção, controle deslizante, captura de atalho | vazio, preenchido, foco, erro com mensagem, ajuda, desabilitado |
| Navegação | barra lateral, barra inferior, abas, trilha, alternador de contexto | atual, cursor, foco, com pendência |
| Cartões | padrão, métrica, item de lista, ação proposta | carregando, vazio, erro |
| Gráficos | linha no tempo, barras, medidor, minigráfico | sem dados, carregando, dado parcial |
| Indicadores | estado de componente, selo, progresso, risco, procedência, conexão | — |
| Modais | confirmação simples, **autorização** (descrição, risco, reversibilidade, contagem regressiva), formulário | foco preso; `Esc` fecha sem confirmar |
| Notificações | aviso temporário, central de notificações, faixa persistente (sem conexão, Modo Operador, dados simulados) | — |
| Carregamento | esqueleto, progresso indeterminado; determinado só com dado real | — |
| Erro e vazio | erro no campo, erro no painel com "tentar de novo", tela sem conexão, estado vazio com a próxima ação | — |
| Tabelas e listas | ordenação, filtro, paginação ou rolagem contínua, linha expansível | vazio, carregando, erro |

Um catálogo de componentes (página interna, fora do produto) mostra todos em todos os estados e serve de base
para as capturas e para os testes.

### 5.6 Ícones e gráficos

Ícones de traço simples, 1,5 px, 20 e 24 px; conjunto licenciado mais ícones próprios (ADR-020). Gráficos em
SVG, com eixos discretos, valores em fonte de dados e descrição textual para leitores de tela. Cores de série
derivadas dos *tokens*; o vermelho da marca marca só a série em destaque.

## 6. Autorização

A autorização pendente é o elemento mais importante da interface.

- Aparece em qualquer tela, acima do conteúdo, e na janela compacta.
- Mostra o que será feito, o risco, se é reversível, quem pediu e o tempo restante.
- Botão "Negar" sempre com o mesmo peso visual de "Autorizar"; o foco inicial fica em "Negar" quando o risco é
  alto ou a ação é irreversível.
- "Autorizar sempre" só aparece quando o núcleo diz que o pedido é elegível.
- Ações sensíveis só são confirmadas na janela do SAFRA. No painel do navegador, o texto diz "confirme na
  janela do SAFRA" e não há botão.
- Expirado equivale a negado, e a interface diz isso.

## 7. Estados de conexão

| Situação | O que a interface faz |
|---|---|
| Conectando | símbolo em "inicializando"; nada clicável além de "tentar de novo" |
| Conectada | normal |
| Conexão de eventos caiu | faixa "reconectando"; os dados ganham a marca "de hh:mm:ss"; ações desabilitadas |
| Reconectou com `resync` | relê o estado inteiro antes de reabilitar |
| Sessão revogada ou expirada | tela de entrada com a explicação |
| Núcleo parou (na casca) | tela "o núcleo parou", com o motivo se houver, e "reiniciar" |

## 8. Responsividade

| Largura | Comportamento |
|---|---|
| até 599 px | uma coluna; barra inferior; símbolo médio; tabelas viram listas de cartões |
| 600–899 px | uma coluna larga; barra lateral recolhida a ícones |
| 900–1199 px | barra lateral aberta; grade de 2 colunas |
| 1200 px ou mais | grade de 3 a 4 colunas na Central |

O acesso por celular ainda não é entregue (ADR-018), mas todas as telas são desenhadas e testadas nas três
primeiras faixas.

## 9. Acessibilidade

Contraste conferido por teste sobre os *tokens*; foco sempre visível; ordem de tabulação igual à ordem visual;
rótulos em todos os controles; regiões e títulos marcados; mensagens de estado anunciadas; nenhum conteúdo
depende só de cor, de som ou de movimento; texto ampliável a 200 % sem perda.

## 10. Texto e tom

Português do Brasil, frases curtas e diretas, verbos no imperativo nos botões ("Autorizar", "Negar", "Tentar de
novo"). Mensagens de erro dizem o que aconteceu e o que fazer. O assistente fala de forma direta e cordial, sem
vocativo fixo; o tratamento é configurável (ADR-026, proposta em aberto). O nome é sempre "SAFRA", sem pontos.

## 11. O que a Fase 4 traz para a sua escolha

1. Três estudos do símbolo, cada um nos doze estados, com a versão de ícone.
2. Capturas do Cotidiano e da Central em 1440, 900 e 390 px, com dados simulados e identificados.
3. O catálogo de componentes.
4. O relatório de contraste gerado pelo teste.
