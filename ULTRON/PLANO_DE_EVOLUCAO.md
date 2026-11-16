# JARVIS ULTIMATE — Plano de evolução

> Rascunho da Fase 8 (entrega em pausa até a confirmação da inicialização no seu Windows).

Entregável 20. O que fazer depois desta entrega, em ordem. A regra que valeu até aqui continua: **medir
antes de mudar** e não declarar melhora sem a medida. Nada aqui tem prazo prometido — cada etapa começa
quando a anterior trouxer os dados de que ela depende.

## 1. Validar o que só existe no seu ambiente (antes de qualquer código novo)

Estas verificações não dependem de programar nada; dependem do seu PC, do seu microfone e do robô. O
resultado de cada uma decide o que entra na etapa 2.

| # | O que | Como | O que registrar |
|---|---|---|---|
| 1.1 | Instalação no seu Windows | ZIP → `INSTALL_JARVIS.bat` → `DIAGNOSTICO_JARVIS.bat` | componentes ausentes, avisos do pip |
| 1.2 | Voz real | `START_JARVIS.bat --voice-test`; DIAGNÓSTICOS > VOZ > CALIBRAR | em qual das 8 etapas parou; acertos e falsos disparos do "Jarvis" num dia normal |
| 1.3 | Interface no seu monitor | perfis Econômico → Cinematográfico; `python tools/benchmark_avatar.py` | quadros por segundo e uso de CPU em repouso e falando |
| 1.4 | Ollama com o modelo real | conversar, planejar, consultar a TARDIS | tempo até a primeira palavra; respostas erradas ou inventadas (copie do histórico de ATIVIDADES) |
| 1.5 | Bandeja, notificações, início com o Windows | uso normal por alguns dias | lembretes no horário; o que falhou |
| 1.6 | **Noctário na bancada** (rodas fora do chão, botão físico ao alcance) | roteiro de `firmware/noctario/README.md`: gravar o firmware, sentido dos motores, ordem dos sensores, nível do cruzamento, F12 e o botão físico | o que precisou ser invertido; se a parada pelo F12 parou na hora |
| 1.7 | **Noctário na pista** | primeiras voltas com PWM menor; voltas gravadas; *"analise as voltas do Noctário"* | tempo de cada volta, perdas de linha, cruzamentos contados × reais |

## 2. Ajustes guiados pelas medidas (curto prazo)

* **Tempo de volta do Noctário.** Com as voltas gravadas, ajustar PWM base, máximo, Kp/Kd, velocidade
  adaptativa e rampas pela interface (sem regravar), uma mudança por vez, comparando as voltas na TARDIS. A
  volta hoje leva cerca de 5 min 40 s (informado); a meta é reduzir **medindo**, sem prometer um tempo.
* **Palavra de ativação.** Se 1.2 mostrar falsos disparos ou falhas frequentes, ajustar as formas
  calibradas; se não bastar, avaliar um detector de palavra-chave dedicado e local (medido contra o atual
  com as mesmas gravações).
* **Desempenho.** Se 1.3 mostrar quadros abaixo da meta, ajustar o perfil padrão para a sua máquina ou
  ligar a renderização por GPU (CONFIGURAÇÕES > APARÊNCIA), sempre com `tools/benchmark_avatar.py` antes e
  depois.
* **Modelo de linguagem.** Se 1.4 mostrar respostas lentas, testar um modelo menor ou quantizado; se
  mostrar respostas fracas, um maior (cabendo na RAM). O roteador de modelos já escolhe por tarefa; a troca
  é configuração, não código.

## 3. Evoluções que dependem das medidas (médio prazo)

* **Noctário — perfil de velocidade por trecho.** Hoje o firmware freia pelo erro (velocidade adaptativa).
  Com voltas suficientes, a TARDIS pode identificar os trechos (entre cruzamentos) e propor uma velocidade
  para cada um. Exige uma extensão do protocolo (nova versão, mantendo o NOCT/1 aceito), testes no PC
  contra o simulador e validação na bancada antes da pista. O controle continua no ESP32.
* **Noctário — variante de 6 cruzamentos** (`Nefarious_6`): selecionável hoje por parâmetro (`cross=6`);
  os ganhos adaptativos daquele sketch não foram copiados — só entram se as voltas mostrarem vantagem.
* **Boca do avatar com o tempo exato de cada fonema.** A voz `faber-medium` não exporta a duração dos
  fonemas (hoje os visemas são distribuídos pelos trechos sonoros do áudio real). Uma voz que exporte o
  alinhamento seria usada automaticamente — o código já aceita.
* **Reconhecimento com Whisper** (o original tinha um teste avulso, nunca integrado): opcional, para
  máquinas com GPU, ao lado do Vosk e medido com as mesmas frases.
* **Python e Qt mais novos.** O pacote está limitado ao PySide6 6.8 (testado) e Python 3.10–3.13. Subir
  quando houver versões estáveis com rodas para Windows e a suíte passar no CI.
* **Cobertura da linha de comando.** Medir `main.py` também nos processos filhos (coverage em modo
  paralelo) e cobrir as páginas da interface que ainda têm pouca cobertura.

## 4. O que fica de fora até haver um desenho seguro

* **Agente visual autônomo** (`visual_computer_task` do original, nunca registrado) e o *hand-off*
  autônomo do Observador: só com confirmação a cada clique e verificação do resultado — não como execução
  livre a partir do que aparece na tela (texto da tela é dado, nunca instrução).
* **Serviços na internet** (agendas, e-mail, casa conectada): só como plugin, com consentimento explícito,
  credenciais no cofre do sistema e respeitando o LOCAL MODE — nunca ligados por padrão.
* **Controle de aparelhos da rede**: descobrir continua não sendo administrar; nada de acesso a
  equipamentos de terceiros.

## 5. Como evoluir sem quebrar o que funciona

| Para acrescentar | Onde | O que acompanha |
|---|---|---|
| Uma ação nova | `ultron/skills/<área>/` (classe `Skill` com `validate`, `refuse_reason` se houver o que recusar, `execute` e `verify`) e a categoria em `ultron/agent/permissions.py` | teste da ação e da verificação; `python tools/gerar_comandos.py` (o teste de integridade cobra) |
| Um plugin | pasta `plugins/` do programa ou `plugins` na pasta de dados (exemplos em `plugins/`); declara `capabilities` e requisitos | as ações de arquivo do JARVIS nunca gravam nessas pastas; plugin com falha ou lento não impede o início |
| Uma análise da TARDIS | `ultron/tardis/analyzers/` | resultado diz se usou o modelo ou foi determinístico; a TARDIS só propõe |
| Uma página da plataforma | `ultron/hud/` + navegação em `ultron/hud/platform.py` | estado preservado ao trocar de página; não desenhar fora de vista |
| Um comando do robô | `firmware/noctario/src/noct_core.cpp` + `ultron/noctario/` + `PROTOCOLO_NOCT1.md` | teste no PC (`test/host`), comparação com o simulador, confirmação a cada vez, a parada nunca condicionada |

Toda mudança passa pela suíte (`python TEST_JARVIS.py`) e pelo CI (Linux, Windows e firmware) antes de
chegar a você; os dados do usuário (memória, configurações, modelos) nunca são apagados por atualização.
