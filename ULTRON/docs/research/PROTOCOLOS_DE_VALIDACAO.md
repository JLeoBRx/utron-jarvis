# Protocolos de validação experimental do SAFRA

Este documento define **como** cada métrica do TCC é medida, para que as medições possam ser repetidas por
qualquer pessoa e comparadas entre ambientes. Os instrumentos estão em `tools/experimentos/` e gravam os
dados brutos em `docs/research/resultados/` (JSON). Nenhum resultado entra no TCC sem o arquivo
correspondente.

## 0. Regras gerais

1. **Ambiente registrado.** Todo arquivo de resultado traz sistema, processador, memória, versões, commit e
   data. Para o computador de referência, registrar também: GPU e driver, microfone, alto-falante/fone,
   modelo do Ollama e a versão do Ollama.
2. **Real × simulado declarado.** Cada resultado lista o que foi real e o que foi simulado (campos `real` e
   `simulado`). Simulação nunca é apresentada como medição do hardware.
3. **Dados do usuário intactos.** Os instrumentos usam pasta de dados temporária (`SAFRA_DATA_DIR`).
4. **Versão congelada.** As rodadas oficiais usam a versão congelada do cronograma (maio/2027) e o mesmo
   modelo de linguagem em todas as repetições.
5. **Repetições e incerteza.** Tempos são resumidos por média, desvio, mediana, p95 e IC 95 %; proporções,
   pela taxa e pelo intervalo de Wilson (95 %), adequado a amostras pequenas.
6. **Ambientes de medição.**
   * **C — contêiner de desenvolvimento** (Linux, 4 vCPUs, sem GPU, sem microfone): verifica os instrumentos
     e mede o que não depende de hardware (lógica, núcleo, memória, segurança). Rótulo `conteiner`.
   * **R — computador de referência do autor** (Windows 10/11, GPU, microfone, alto-falante): rodadas
     oficiais de PV-01B, PV-02 (com modelo real), PV-04, PV-05B e PV-07. Rótulo `pc-referencia`.

## Quadro geral

| Protocolo | Área | Métrica principal | Meta (REQUISITOS) | Instrumento | Ambiente |
|---|---|---|---|---|---|
| PV-01 | Reconhecimento de voz | taxa de ativação correta; ativações indevidas; WER do comando | RNF06 ≥ 90 %; RNF07 ≤ 2 % | `pv01_ativacao.py` | A: C (voz sintética) · B: R (voz humana) |
| PV-02 | Resposta | tempo do pedido à resposta | RNF01 p95 ≤ 1 s; RNF02 p50 ≤ 8 s | `pv02_latencia.py` | C (sobrecarga do núcleo) · R (modelo real) |
| PV-03 | Memória | recall@1, recall@3; recuperação indevida | RNF09 recall@3 ≥ 80 % | `pv03_memoria.py` | C e R (independe de hardware) |
| PV-04 | Interface | montagem da interface; cena 3D pronta; quadros/s | RNF03 ≤ 15 s; RNF04 ≤ 5 s e ≥ 30 q/s | `pv04_interface.py` | R (C só verifica o instrumento) |
| PV-05 | Sincronização labial | defasagem forma×áudio; fechamento no silêncio; erro no início das palavras; atraso de apresentação | RNF08 (ITU-R BT.1359) | `pv05_sincronizacao.py` + gravação em vídeo | A: C · B: R |
| PV-06 | Segurança | taxa de bloqueio de ações indevidas; controles positivos | 100 % e 100 % | `pv06_seguranca.py` | C e R |
| PV-07 | Estabilidade | falhas, pedidos sem resposta, crescimento de memória, threads restantes | RNF10: 8 h, ≤ 20 MB/h, 0 threads | `pv07_estabilidade.py` | C (30 min) · R (8 h) |
| — | Testes automatizados | suíte completa e cobertura | RNF14 | `TEST_JARVIS.py`, CI | C, CI Linux/Windows |

---

## PV-01 — Palavra de ativação e reconhecimento de comandos

* **Objetivo:** medir quantas ativações intencionais o SAFRA reconhece, quantas frases comuns o ativam
  indevidamente e quanto do comando é transcrito corretamente.
* **Hipótese/requisitos:** H4 (interação), RF08, RF09, RNF06, RNF07.
* **Variáveis:** palavra de ativação ("Safra", "Jarvis"); modelo do reconhecedor (pequeno, grande);
  velocidade da fala; nível de ruído (sem ruído, SNR 20 dB, SNR 10 dB); falante (etapa B).
* **Etapa A — canal sintético (ambiente C):** `python tools/experimentos/pv01_ativacao.py --rotulo conteiner-sintetico`.
  A voz Piper do SAFRA fala 10 comandos com cada palavra, a palavra sozinha, 24 frases sem a palavra (3 delas
  com "safra" no meio) e 3 frases que começam com "safra" sem intenção de comando; 3 velocidades × 3 ruídos ×
  2 repetições (o Piper é estocástico). Mede o canal reconhecedor ↔ detector; **não representa voz humana**.
* **Etapa B — voz humana (ambiente R):**
  1. Participantes: o autor e, se a instituição permitir, voluntários (mín. 5), com **termo de consentimento**;
     as gravações ficam fora do repositório e podem ser apagadas após a extração dos resultados.
  2. Gravar em WAV 16 kHz mono (o próprio microfone do PC de referência), a ~50 cm, em dois ambientes
     (silencioso e com ruído de TV/conversa).
  3. Roteiro (`roteiro.csv`, `arquivo;texto;tipo`): por participante, 10 frases "Safra, <comando>",
     5 "Jarvis, <comando>", 3 "Safra." sozinha e 15 frases sem a palavra (tipo `negativa`).
  4. Rodar `pv01_ativacao.py --gravacoes PASTA --rotulo pc-referencia-voz-humana`.
* **Métricas:** taxa de ativação = ativações / frases com a palavra; ativação indevida = ativações / frases
  sem a palavra; WER do comando (distância de edição entre palavras ÷ palavras de referência).
* **Critério:** RNF06 ≥ 90 % (etapa B, ambiente silencioso); RNF07 ≤ 2 %.
* **Limitações:** uma única voz sintética na etapa A; sotaque e microfone dos participantes; o modelo de
  ruído é branco, não ruído real de ambiente.

## PV-02 — Tempo de resposta

* **Objetivo:** medir o tempo entre o pedido e a resposta publicada pelo núcleo.
* **Requisitos:** H3, RNF01, RNF02.
* **Procedimento:** `python tools/experimentos/pv02_latencia.py --repeticoes 20` (ambiente C: inferência
  simulada de 0 ms → sobrecarga do núcleo). No ambiente R, com o Ollama aberto e o modelo baixado:
  `pv02_latencia.py --ollama http://127.0.0.1:11434 --modelo qwen2.5:3b --rotulo pc-referencia`.
  Fazer uma pergunta de aquecimento antes (o primeiro uso carrega o modelo na memória) e registrar à parte.
* **Métricas:** média, mediana, p95 por grupo (determinístico × modelo) e por frase; pedidos sem resposta.
* **Critério:** RNF01 p95 ≤ 1 s (determinístico); RNF02 p50 ≤ 8 s (modelo real).
* **Limitações:** o tempo do modelo depende de GPU/CPU e do tamanho da resposta; a voz (fala) não entra
  nesta medida (ver PV-05B para o atraso de apresentação).

## PV-03 — Recuperação de memória

* **Objetivo:** medir se o SAFRA recupera a memória certa para uma pergunta.
* **Requisitos:** RF16, RNF09.
* **Procedimento:** `python tools/experimentos/pv03_memoria.py`. Conjunto sintético versionado no próprio
  script: 20 fatos, cada um com uma pergunta lexical e uma paráfrase, 10 perguntas sobre fatos ausentes e
  8 registros da memória pessoal com buscas exatas e com variações (sem acento, outra forma da palavra).
* **Métricas:** recall@1 e recall@3 por tipo de pergunta; taxa de recuperação indevida (perguntas sobre o
  que não existe que recuperam algum fato).
* **Critério:** recall@3 ≥ 80 % (RNF09) — avaliado separadamente para perguntas lexicais e paráfrases.
* **Limitações:** conjunto pequeno e escrito pelo autor; não mede a qualidade da resposta final do modelo.

## PV-04 — Interface

* **Objetivo:** tempo de montagem da interface, tempo até a cena 3D ficar pronta e quadros por segundo.
* **Requisitos:** H3, RNF03, RNF04, RNF05.
* **Procedimento (ambiente R):** com o SAFRA fechado, `python tools/experimentos/pv04_interface.py --repeticoes 10
  --rotulo pc-referencia`; repetir com o notebook na tomada e fora dela, se for o caso. Registrar GPU e driver.
  Complementar com `python tools/benchmark.py` (CPU em repouso, atraso do laço da interface).
* **Métricas:** tempo de `--gui-check` (média, p95); tempo até "pronta" da cena; renderizador; erros de
  JavaScript; quadros/s no perfil Equilibrado.
* **Critério:** cena pronta ≤ 5 s; ≥ 30 quadros/s no Equilibrado com GPU; montagem ≤ 15 s.
* **Limitações:** no ambiente C o WebGL roda por software — serve só para verificar o instrumento.

## PV-05 — Sincronização labial

* **Etapa A — cálculo (ambiente C):** `python tools/experimentos/pv05_sincronizacao.py`. 12 frases × 3 sínteses:
  defasagem entre a abertura prevista pelos visemas e a energia do áudio (correlação cruzada, ±300 ms,
  resolução 10 ms); fechamento da boca nos quadros silenciosos; erro do início de cada palavra da trilha
  (base da legenda) em relação ao Vosk grande (referência independente), quando o número de palavras coincide.
* **Etapa B — apresentação (ambiente R):**
  1. Filmar a tela e o som com um celular a 60 quadros/s (ou capturar a tela com o áudio do sistema).
  2. Pedir 10 frases curtas que comecem com consoante bilabial ("Pronto", "Bom dia", "Muito bem").
  3. No vídeo, medir o intervalo entre o início do som e o primeiro quadro com a boca abrindo (ou o último
     quadro com a boca fechada antes da abertura), em quadros de 16,7 ms.
  4. Registrar em `pv05b_apresentacao_pc-referencia.json` (formato livre: frase, quadro do som, quadro da boca).
* **Critério (RNF08):** a defasagem fica dentro da faixa de não detecção da ITU-R BT.1359 (som adiantado em
  até 45 ms ou atrasado em até 125 ms em relação à imagem).
* **Limitações:** etapa A mede o algoritmo, não a tela; etapa B tem resolução de um quadro de vídeo.

## PV-06 — Segurança

* **Objetivo:** verificar que ações indevidas são bloqueadas sem efeito colateral e que ações legítimas
  continuam funcionando.
* **Requisitos:** H2, RF29–RF32, RS02–RS04, RS07.
* **Procedimento:** `python tools/experimentos/pv06_seguranca.py` (pastas temporárias; um "usuário"
  automático aprova, nega ou não responde às autorizações conforme o caso).
* **Casos:** 11 tentativas indevidas (alvos protegidos, atalho para pasta protegida, categoria bloqueada,
  autorização negada, autorização expirada, origem proativa, skill inexistente, argumento inválido, segredo
  na memória, número de cartão na memória pessoal) e 4 controles positivos.
* **Métricas e critério:** bloqueio correto = 100 % (com efeito colateral verificado no disco/banco);
  controles = 100 %.
* **Complemento:** a suíte `test_security.py` (17 testes) cobre a varredura do código (sem shell, `eval`,
  `exec`, `pickle`), ferramentas não oferecidas ao modelo e conteúdo de tela tratado como dado.
* **Limitações:** não é um teste de invasão; não cobre o sistema operacional nem a rede.

## PV-07 — Estabilidade

* **Objetivo:** verificar que o SAFRA funciona por horas sem falha, sem vazamento de memória relevante e
  sem deixar threads ao encerrar.
* **Requisitos:** RNF10, H1.
* **Procedimento:** ambiente C: `pv07_estabilidade.py --minutos 30`. Ambiente R: `pv07_estabilidade.py --minutos 480
  --ollama http://127.0.0.1:11434 --rotulo pc-referencia-8h`, com o computador sem suspensão automática.
  Opcional: deixar a interface aberta ao mesmo tempo e anotar a memória do processo da interface a cada hora.
* **Métricas:** pedidos enviados × respondidos; erros; RSS inicial e final; inclinação da memória (MB/h,
  regressão linear) na série inteira e **depois do aquecimento** (sem os 5 minutos iniciais ou os primeiros
  10 % da execução, o que for maior — nos primeiros minutos caches, banco e módulos carregados sob demanda
  enchem; medido na rodada de 30 min do ambiente C); eventos descartados pelo Event Bus; threads restantes
  após o encerramento.
* **Critério:** 0 falha fatal; ≤ 20 MB/h **depois do aquecimento**; 0 threads restantes.

## Análise e apresentação

* Cada tabela de resultado no TCC cita o arquivo JSON de origem e o ambiente (C ou R).
* Metas atingidas, não atingidas ou não medidas são declaradas como tais; "não medido" sempre traz o motivo.
* Gráficos: gerados a partir dos JSON (ver `docs/research/resultados/README.md`).
