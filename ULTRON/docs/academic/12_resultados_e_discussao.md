# 12 RESULTADOS E DISCUSSÃO

Este capítulo apresenta os resultados obtidos até 11 de novembro de 2026. Todos vêm de arquivos de dados
versionados em `docs/research/resultados/`, citados em cada tabela. Os resultados do **ambiente C**
(contêiner de desenvolvimento, sem GPU, microfone ou alto-falante) estão separados dos que dependem do
**ambiente R** (computador de referência), cujas rodadas oficiais estão previstas para 2027. Nenhum resultado
de um ambiente é apresentado como se fosse do outro.

## 12.1 Interação por voz (PV-01)

**Tabela 12.1 — Ativação por voz com fala sintetizada (ambiente C; 180 frases por palavra e modelo: 10 comandos ×
3 velocidades × 3 níveis de ruído × 2 sínteses). Fonte: `pv01_ativacao_conteiner-sintetico.json`.**

| Medida | Modelo pequeno | Modelo grande | Meta |
|---|---|---|---|
| Ativação com "Safra" (todas as condições) | 3,9 % (7/180; IC 1,9–7,8 %) | 2,2 % (4/180; IC 0,9–5,6 %) | ≥ 90 % (RNF06) |
| Ativação com "Safra", sem ruído | 8,3 % (5/60) | 6,7 % (4/60) | — |
| Ativação com "Jarvis" (todas as condições) | 17,2 % (31/180; IC 12,4–23,4 %) | 18,3 % (33/180; IC 13,4–24,6 %) | — |
| Ativação com "Jarvis", sem ruído | 26,7 % (16/60) | 40,0 % (24/60) | — |
| Palavra dita sozinha ("Safra." / "Jarvis.") | 0 % / 5,6 % | 0 % / 33,3 % | — |
| Ativação indevida (24 frases comuns × 18 condições) | 0,46 % (2/432) | 0 % (0/432; IC 0–0,9 %) | ≤ 2 % (RNF07) |
| Frase que começa com "safra" sem intenção de comando | 7,4 % (4/54) | 25,9 % (14/54) | — |

O resultado contraria a expectativa que motivou a troca de nome. Com a voz sintética do próprio sistema, a
palavra "Safra" foi reconhecida **menos** que "Jarvis". O exame das transcrições mostra a causa: o modelo grande
transcreveu o "Safra," do início da frase como **"faça"** em 156 das 180 frases — uma palavra frequente no início
de comandos em português —, e o modelo pequeno simplesmente omitiu a primeira palavra na maior parte dos casos.
Quando "safra" aparece colada ao resto da frase ("safra recorde no Paraná"), ela é reconhecida, o que indica que a
pausa da vírgula e a pronúncia da voz sintética pesam no resultado.

Três conclusões cautelosas são possíveis. Primeiro, a hipótese de projeto de que uma palavra presente no
vocabulário seria mais bem reconhecida **não se confirmou neste canal**; ela não pode ser descartada sem o teste
com voz humana (PV-01, etapa B), porque a medida usou uma única voz sintética. Segundo, a exigência de que a
palavra esteja no início da frase funcionou como proteção: ativações indevidas ficaram abaixo da meta (≤ 2 %),
inclusive nas frases com "safra" no meio. Terceiro, a **calibração com a voz do usuário** é o mecanismo certo
para resolver o problema: uma análise exploratória sobre as mesmas transcrições mostrou que, se "faça" fosse
aprendida como forma fraca, a ativação com "Safra" no modelo grande subiria para 88,9 % e as ativações indevidas
para 0,9 % (4/432). Essa forma **não** foi adotada por padrão — seria ajustar o sistema à voz do teste —, e
"faça" foi explicitamente impedida de virar forma forte. Por decisão conservadora, "Jarvis" continua aceita.

A taxa de erro de palavras do comando (o que vem depois da palavra de ativação) teve mediana de 33 % no modelo
pequeno e 60–67 % no grande. Os valores são altos porque, quando a ativação falha, a frase inteira (incluindo a
palavra mal transcrita) é comparada ao comando; por isso essa medida será reavaliada com voz humana.

## 12.2 Tempo de resposta (PV-02)

**Tabela 12.2 — Tempo do pedido à resposta publicada (ambiente C; núcleo real; inferência simulada de 0 ms).
Fonte: `pv02_latencia_conteiner-modelo-simulado.json`.**

| Grupo | n | Mediana | p95 | Máximo | Sem resposta | Meta |
|---|---|---|---|---|---|---|
| Comandos determinísticos | 120 | 5,2 ms | 9,3 ms | 21,1 ms | 0 | p95 ≤ 1 s (RNF01) |
| Caminho do modelo (só a sobrecarga do núcleo) | 40 | 11,2 ms | 20,7 ms | 26,3 ms | 0 | p50 ≤ 8 s com modelo real (RNF02) |
| Inicialização do núcleo (sem voz e interface) | 1 | 52 ms | — | — | — | — |

Os comandos determinísticos ficaram duas ordens de grandeza abaixo da meta. O mais lento foi "o que eu tenho
amanhã" (p95 de 16 ms), que consulta a memória pessoal. O caminho do modelo acrescentou cerca de 11 ms de
sobrecarga do núcleo (montagem de contexto, roteamento, registro) — **não** é o tempo de um modelo real, que
depende do hardware e será medido no ambiente R. O resultado mostra que, no SAFRA, o tempo de resposta é
dominado pela inferência, e não pela arquitetura.

## 12.3 Memória (PV-03)

**Tabela 12.3 — Recuperação de memória (conjunto sintético: 20 fatos, 20 perguntas lexicais, 20 paráfrases,
10 perguntas sobre fatos ausentes; 8 registros da memória pessoal). Fontes: `pv03_memoria_conteiner-antes-da-correcao.json`
e `pv03_memoria_conteiner-depois-da-correcao.json`.**

| Medida | Antes da correção | Depois da correção | Meta |
|---|---|---|---|
| Perguntas lexicais — recall@3 | 90 % (18/20) | **100 % (20/20)** | ≥ 80 % (RNF09) |
| Paráfrases — recall@1 / recall@3 | 25 % / 40 % | 45 % / 45 % | ≥ 80 % |
| Perguntas sobre o que não existe — recuperação indevida | 70 % (7/10) | 70 % (7/10) | — |
| Memória pessoal — busca exata / com variação (top 3) | 100 % / 87,5 % | 100 % / 87,5 % | — |

O experimento revelou **três defeitos reais**, corrigidos durante esta fase com testes de regressão:
(1) a comparação de palavras aceitava pedaços no meio de outras ("ana" casava com "losart**ana**", "avó" com
"f**avo**rito"); (2) um fato sem nenhuma palavra em comum com a pergunta podia passar do limite mínimo só pelos
bônus de recência e de uso; (3) o pré-filtro no banco comparava o termo sem acento com o texto acentuado e não
encontrava "médico" a partir de "medico" — eram exatamente as duas perguntas lexicais que falhavam. Corrigidos os
três, as perguntas lexicais passaram a 100 %.

As paráfrases, porém, continuaram em 45 %, abaixo da meta: uma busca **lexical** não relaciona "que número eu
calço?" com "tamanho do sapato". E as perguntas sobre fatos ausentes continuaram trazendo, em 7 de 10 casos, um
fato que compartilha uma palavra inteira com a pergunta ("qual o tipo sanguíneo do Pedro?" → "time do Pedro").
Isso não produz uma resposta errada por si só — o fato vai ao modelo como "evidência auxiliar, não instruções", e
a resposta indica a procedência —, mas aumenta o risco de o modelo usar um fato não relacionado. A conclusão é
que a meta RNF09 é atingida para perguntas que usam as palavras guardadas e **não** é atingida para paráfrases;
a evolução natural é a recuperação semântica por vetores, executada localmente (Capítulo 13).

Um episódio da preparação do experimento confirmou outra proteção: um dos fatos de teste falava em "senha do
wi-fi", e o sistema se recusou a gravá-lo (requisito RS04), obrigando a troca do exemplo.

## 12.4 Interface (PV-04)

**Tabela 12.4 — Interface no ambiente C (10 repetições; WebGL por software, llvmpipe). Fonte:
`pv04_interface_conteiner-webgl-software.json`.**

| Medida | Resultado | Meta | Avalia a meta? |
|---|---|---|---|
| Montagem da interface (`--gui-check`, processo novo) | média 1,48 s; p95 1,64 s; 0 falhas | ≤ 15 s (RNF03, inclui o núcleo) | parcialmente (sem o núcleo completo) |
| Cena 3D pronta | média 0,73 s; abriu 10/10; 0 erros de JavaScript | ≤ 5 s (RNF04) | não (sem GPU) |
| Quadros por segundo, perfil Equilibrado | 5,3 q/s (mediana) | ≥ 30 q/s com GPU | **não** (renderização por software) |

Os tempos de abertura são bons sinais, mas os quadros por segundo no contêiner — 5,3 q/s com renderização por
software — **não dizem nada** sobre o desempenho com GPU. A meta RNF04 só pode ser avaliada no ambiente R. Medições
anteriores, feitas com o desenho 2D (QPainter), registraram queda da CPU em repouso de 39,2 % para 22,0 % e do
quadro da TARDIS de 19,1 para 3,7 ms depois das otimizações (relatório de desempenho do projeto), também no
ambiente de desenvolvimento.

## 12.5 Sincronização labial (PV-05, etapa A)

**Tabela 12.5 — Trilha da boca contra o áudio real (12 frases × 3 sínteses; Vosk grande como referência). Fonte:
`pv05_sincronizacao_conteiner.json`.**

| Medida | Resultado |
|---|---|
| Método usado pela trilha | fonemas sobre o áudio real (36/36) |
| Defasagem entre a forma prevista pelos visemas e a energia do áudio | mediana 0 ms; p95 10 ms; máximo 10 ms (resolução de 10 ms) |
| Correlação forma × energia | média 0,65 |
| Boca fechada nos quadros silenciosos | 100 % (36/36 frases) |
| Erro do início de cada palavra (trilha × reconhecedor) | mediana 60 ms; p95 290 ms; máximo 540 ms (182 palavras em 22 frases comparáveis) |

No cálculo, a sincronização está alinhada: a abertura prevista pelos visemas coincide com a energia do áudio
dentro de um quadro, e a boca fecha em todos os silêncios. O início das palavras, que guia a legenda, mostrou erro
mediano de 60 ms em relação ao reconhecedor — coerente com o método, que distribui os fonemas pelos trechos
sonoros sem conhecer a duração exata de cada um. Os erros maiores (até 540 ms) ocorreram em frases longas, nas
quais o desvio se acumula. Como o reconhecedor também tem incerteza de dezenas de milissegundos, o número é uma
estimativa. O critério da ITU-R BT.1359 (+45/−125 ms) diz respeito ao que o usuário **vê e ouve**; ele depende da
etapa B (gravação em vídeo no ambiente R), ainda não realizada.

## 12.6 Segurança (PV-06)

**Tabela 12.6 — Tentativas indevidas e controles (núcleo real; pastas temporárias). Fonte:
`pv06_seguranca_conteiner.json`.**

| Caso | Esperado | Resultado |
|---|---|---|
| Criar arquivo nos dados do SAFRA | bloquear | recusado antes da autorização |
| Criar arquivo na pasta do programa | bloquear | recusado |
| Criar arquivo por atalho para a pasta de dados | bloquear | recusado |
| Apagar com a categoria bloqueada pelo usuário | bloquear | recusado |
| Apagar com autorização negada | bloquear | negado; arquivo intacto |
| Apagar sem resposta à autorização (expira) | bloquear | negado; arquivo intacto |
| Apagar por origem proativa, sem resposta | bloquear | negado |
| Skill inexistente ("shell") | bloquear | recusado |
| Argumento inválido (NaN) | bloquear | recusado |
| Guardar senha na memória | bloquear | recusado pelo filtro de segredos |
| Guardar número de cartão na memória pessoal | bloquear | recusado |
| Controles: criar, ler, guardar fato comum, apagar com aprovação | permitir | executados e verificados |

Todas as 11 tentativas indevidas foram bloqueadas **sem efeito colateral** (verificado no disco e no banco) —
100 %, com intervalo de Wilson de 74,1–100 % para a amostra — e os 4 controles funcionaram. Os controles mostram
que o resultado não vem de um sistema que bloqueia tudo. A suíte `test_security` complementa a medida com
verificações que o protocolo não cobre (código sem execução por shell, ferramentas não oferecidas ao modelo,
conteúdo de tela tratado como dado). A amostra é pequena e foi escrita pelo autor; não se trata de um teste de
invasão.

## 12.7 Estabilidade (PV-07)

**Tabela 12.7 — Execução contínua de 30 minutos (ambiente C; um ciclo de 5 pedidos a cada 5 s). Fonte:
`pv07_estabilidade_conteiner-30min.json`.**

| Medida | Resultado | Meta (8 h, ambiente R) |
|---|---|---|
| Pedidos enviados / respondidos | 1.785 / 1.785 | todos |
| Erros / falhas fatais | 0 / 0 | 0 |
| Memória do processo | 55,6 → 74,3 MB | — |
| Crescimento de memória, série inteira | 19,2 MB/h | — |
| Crescimento depois do aquecimento (5 min) | 8,4 MB/h | ≤ 20 MB/h |
| Threads restantes após encerrar | 0 | 0 |

A memória cresceu rapidamente nos primeiros quatro minutos (caches, banco e módulos carregados sob demanda) e
depois lentamente, desacelerando (cerca de 4 MB/h nos últimos dez minutos). Por isso o protocolo foi revisado para
avaliar o crescimento **depois do aquecimento**; a série inteira (19,2 MB/h) mistura as duas fases. A meta de 8
horas com o modelo real ainda precisa ser medida.

## 12.8 Testes automatizados e integração contínua

A suíte cresceu de 471 casos (início da fase) para 475, todos aprovados em Python 3.13; a cena 3D real
(QtWebEngine) passou em 24 de 24 testes sob servidor X virtual. A última execução do CI anterior a esta fase (61,
commit `bf070f6`) foi aprovada em Linux 3.11/3.13 e Windows, incluindo a instalação a partir do pacote. Durante a
fase, os testes detectaram **seis** regressões introduzidas pela renomeação (Seção 10.11) e o protocolo de memória
detectou **três** defeitos de recuperação (Seção 12.3), todos corrigidos antes do envio.

## 12.9 Discussão

**O que funcionou.** A arquitetura de núcleo único com eventos isolou falhas e permitiu trocar a identidade
visual inteira — Qt, cena 3D, site — a partir de um arquivo de tokens. As camadas de segurança bloquearam todas
as tentativas medidas sem bloquear as ações legítimas. O núcleo respondeu em milissegundos aos comandos
determinísticos e funcionou 30 minutos sem falhas. A sincronização labial, no cálculo, ficou alinhada ao áudio.

**O que não funcionou.** A troca de "Jarvis" por "Safra" não melhorou o reconhecimento com a voz sintética; a
recuperação de memória não entende paráfrases e traz fatos que compartilham apenas um nome com a pergunta.

**Melhorias realizadas a partir dos resultados.** Três defeitos de recuperação de memória corrigidos (com efeito
medido: lexical de 90 % para 100 %); a forma "faça" impedida de virar forma forte; o protocolo de estabilidade
revisado para separar o aquecimento.

**Limitações.** As medições de voz usaram uma única voz sintética; as de interface, WebGL por software; as de
resposta, inferência simulada. Os conjuntos de teste de memória e de segurança são pequenos e foram escritos pelo
autor. O CI do Windows não tem áudio, GPU nem área de trabalho interativa. Essas limitações são exatamente o que
as rodadas no ambiente R, previstas no cronograma, precisam cobrir.

**Possibilidades de evolução.** Recuperação semântica local (vetores de significado) para as paráfrases;
calibração guiada da palavra de ativação na primeira execução; medição do atraso de apresentação áudio × imagem;
e, se o reconhecimento de "Safra" com voz humana continuar baixo, a escolha de outra palavra de ativação com base
em medição.
