# NOCT/1 — protocolo entre o JARVIS (PC) e o Noctário (ESP32)

Versão 1 (`proto=1`). Implementações:

| Lado | Arquivo |
|---|---|
| Robô (C++) | `firmware/noctario/src/noct_core.cpp` (núcleo, sem Arduino) + `src/main.cpp` (pinos, Bluetooth, NVS) |
| PC (Python) | `ultron/noctario/protocol.py` (formato, limites) e `ultron/noctario/service.py` (conexão, comandos, estados) |
| Simulador | `ultron/noctario/simulator.py` (`FirmwareModel`: a mesma lógica do núcleo C++) |

O núcleo C++ e o modelo do simulador são conferidos **linha a linha** por
`tests/test_noctario_firmware.py`: uma sessão de 62 s simulados (calibração, teste de motores, três
voltas, parada de emergência, perda de linha com reencontro e com parada, cão de guarda do link,
desconexão, linhas inválidas) gera as mesmas mensagens e o mesmo PWM em todos os 31 071 ciclos do laço.

---

## 1. Transporte e formato

* **Bluetooth Clássico, perfil serial (SPP/RFCOMM)**. Nome do robô: `Noctario`. No Windows, depois de
  parear, use a **porta COM de saída** criada pelo Windows (transporte "serial") ou o endereço do robô
  (transporte "RFCOMM"). O JARVIS só conecta ao que foi configurado: não procura nem varre aparelhos.
* Texto **ASCII**, uma mensagem por linha, terminada em `\n` (`\r\n` também aceito).
* No máximo **240 bytes** por linha (sem o `\n`). Linha maior é descartada inteira e o robô responde
  `NAK 0 code=SYNTAX msg=linha_longa_demais`.
* Campos `chave=valor` separados por espaço; nenhum valor contém espaço (nas mensagens o robô escreve
  `_` no lugar do espaço e o PC mostra espaço de novo). No máximo 40 campos por linha
  (`NAK 0 code=SYNTAX msg=campos_demais`).
* Números com ponto decimal no formato `%g` (o PC também aceita vírgula ao validar o que o usuário
  digitou; o robô aceita vírgula num `SET`).

---

## 2. Do PC para o robô

### 2.1 `!` — PARADA DE EMERGÊNCIA

Um único byte `!`, em **qualquer ponto** do fluxo, inclusive no meio de uma linha. O robô, antes de
analisar qualquer outra coisa:

1. corta os motores (PWM 0 e STBY do TB6612FNG em nível baixo);
2. descarta a linha parcial;
3. vai para `ESTOP` e envia `EVT estop src=bt` e um `STA`.

Só `CLEAR` sai de `ESTOP` (para `READY`, ou `IDLE` se não houver calibração). `START` e `CAL` em
`ESTOP` recebem `NAK code=ESTOP`.

O PC envia o `!` direto no transporte — sem fila, sem modelo de linguagem, sem esperar resposta — e o
**repete a cada 100 ms até o robô confirmar `ESTOP`** (no máximo 1,5 s). Sem confirmação: "o robô NÃO
confirmou — use o botão físico". **A parada pelo Bluetooth não substitui um botão físico que corte a
alimentação dos motores.**

### 2.2 `HB` — batimento

Sem resposta. Qualquer linha completa recebida conta como sinal de vida do PC. O PC manda `HB` a cada
500 ms enquanto conectado (CONFIGURAÇÕES > NOCTÁRIO; 0 desliga).

**Cão de guarda (no robô)**: com `hb` > 0, em `RUN`/`LOST`, se nada chegar por `hb` ms e
`onlink=stop`, o robô vai para `STOPPING` (motivo `link`), freia pela rampa e termina em `STOP`
(`EVT stop reason=link`). Com `onlink=continue`, segue o percurso. A política é **do firmware**: o PC
só a mostra e a registra.

### 2.3 `CMD <seq> <VERBO> [chave=valor ...]`

`seq` de 1 a 65535 (o PC volta a 1 depois de 65535). Todo `CMD` recebe **exatamente uma** resposta
`ACK <seq> ...` ou `NAK <seq> code=... msg=...`, às vezes acompanhada de `STA`, `PAR` ou `SEN`. O PC
espera até 2 s; sem resposta, o resultado é **TIMEOUT — estado desconhecido** (nunca "feito").
Verbo desconhecido: `NAK <seq> code=UNKNOWN`. Linha que não começa com `CMD <número> <verbo>`:
`NAK 0 code=SYNTAX msg=linha_malformada`. Argumento sem `=`: `NAK <seq> code=SYNTAX`.

| Verbo | Argumentos | Aceito em | Resposta |
|---|---|---|---|
| `PING` | — | sempre | `ACK n pong=1 t=<ms desde que o robô ligou>` |
| `INFO` | — | sempre | `ACK n fw=<versão> proto=1 sensors=8 cal=<0\|1>` |
| `STATUS` | — | sempre | `ACK n st=<estado>` + `STA` |
| `START` | — | `READY`, `STOP`, `DONE` (calibrado) | zera cruzamentos, rampa e cronômetro; `STA` (RUN) + `ACK n st=RUN`. Recusas: `NAK code=ESTOP`, `NOCAL`, `STATE` |
| `STOP` | — | sempre | em `RUN`/`LOST`: `STOPPING` (motivo `cmd`), freia pela rampa e termina em `STOP`. Em `TEST` ou `CAL`: para na hora e vai a `READY`/`IDLE` (não é volta; calibração interrompida fica sem calibração). `ACK n st=<estado>` |
| `CLEAR` | — | sempre | em `ESTOP`: vai a `READY` (ou `IDLE`). `ACK n st=<estado>` |
| `CAL` | `ms` (500–20000, padrão 3000), `auto` (0/1, padrão 0) | parado (`IDLE`, `READY`, `STOP`, `DONE`) | zera mínimos e máximos e invalida a calibração anterior (`cal=0` até terminar: calibração interrompida não permite partida); `STA` (CAL) + `ACK n st=CAL ms=.. auto=..`. Ao fim: `EVT cal ok=1` → `READY`, ou `EVT cal ok=0 msg=sensores_sem_contraste` → `IDLE`. `auto=1`: o robô gira no lugar (±80 PWM, troca de lado a cada 600 ms) |
| `SET` | `chave=valor` (um ou mais, ver §5) | sempre; `loop`, `white`, `flip`, `ldir`, `rdir` só parado (ou em `ESTOP`) | **tudo ou nada**: valida cada valor e as regras entre eles; aceito → `ACK n <chave=valor aceito ...>` + `PAR`; recusado → `NAK code=RANGE` (ou `STATE`) e **nada muda** |
| `PARAMS` | — | sempre | `ACK n` + `PAR` |
| `SAVE` | — | sempre | `ACK n saved=1`; parâmetros e calibração vão para a NVS (valem depois de religar) |
| `DEFAULTS` | — | parado ou `ESTOP` | volta aos padrões (não grava até `SAVE`); `ACK n defaults=1` + `PAR` |
| `RESETX` | — | sempre | zera a contagem de cruzamentos; `ACK n x=0` |
| `TEL` | `hz` (0–50) | sempre | taxa da telemetria (0 desliga); `ACK n tel=<hz>` |
| `SENS` | — | sempre | `ACK n` + `SEN ...` |
| `MOTOR` | `l`, `r` (−255–255), `ms` (100–3000, padrão 500) | parado | teste de bancada: `STA` (TEST) + `ACK n st=TEST`; aplica `l`/`r` (já com `ldir`/`rdir`) por `ms` e volta a `READY`/`IDLE` |

---

## 3. Do robô para o PC

### `HELLO`
Ao abrir cada conexão, seguido de `STA` e `PAR`:

    HELLO fw=noctario-1.0 proto=1 st=READY cal=1 name=Noctario

O PC só considera o link "conectado" depois do `HELLO` (6 s de prazo).

### `STA` — estado completo
Enviado a cada mudança de estado, em `STATUS` e na conexão.

| Campo | Significado |
|---|---|
| `st` | estado (§4) |
| `cal` | 1 = sensores calibrados |
| `x` / `xt` | cruzamentos contados / destino (`cross`) |
| `lap` | ms da volta atual ou da última |
| `why` | motivo da última parada (`cmd`, `link`, `lost`, `done`, `estop`) ou `-` |
| `fw`, `tel`, `onlink`, `hb` | firmware, taxa da telemetria, política sem link, cão de guarda |

### `TEL` — telemetria periódica
A `tel` Hz enquanto há conexão:

    TEL t=12034 st=RUN pos=3610 err=110 corr=2.11 l=203 r=199 x=1 lost=0 b=201 s=0,0,120,980,1000,140,0,0

| Campo | Significado |
|---|---|
| `t` | ms do relógio do robô |
| `pos`, `err` | posição da linha (0–7000, centro 3500) e erro (`pos − 3500`) |
| `corr` | correção do PD (2 casas) |
| `l`, `r` | PWM aplicado em cada motor (com sinal e com `ldir`/`rdir`) |
| `x` | cruzamentos contados |
| `lost` | 1 = linha não vista neste ciclo |
| `b` | velocidade alvo depois da rampa (inteiro) |
| `s` | os 8 valores calibrados (0–1000, já com `white` e `flip`) |

### `EVT` — eventos

| Evento | Campos | Quando |
|---|---|---|
| `cross` | `n`, `t` | borda de entrada no cruzamento, respeitado o filtro `deb` (só em `RUN`/`LOST`/`STOPPING`) |
| `lost` | — | sem linha por `lostms` → `LOST` |
| `found` | `ms` | linha reencontrada durante a recuperação → `RUN` |
| `done` | `lap_ms`, `x` | destino alcançado e robô parado → `DONE` |
| `stop` | `reason` (`cmd`, `link`, `lost`) | parada concluída → `STOP` |
| `estop` | `src=bt` | byte `!` recebido |
| `cal` | `ok=1`, ou `ok=0 msg=...` | fim da calibração |

`fault` e `link` estão reservados (o PC os entende; esta versão do firmware não os envia).

### `PAR` — parâmetros
Os 23 parâmetros na ordem fixa do §5, em linhas de no máximo 12 campos (`PAR kp=... thr=...` e
`PAR lostms=... rdir=...`); o PC junta as linhas. Vem depois de `HELLO`, `SET`, `PARAMS` e `DEFAULTS`.
O `ACK` de `SET` e de `TEL` também traz os valores aceitos.

### `SEN` — leitura avulsa (resposta a `SENS`)

    SEN cal=0,0,120,980,1000,140,0,0 pos=3610 line=1 x=0 xin=0

`cal` (8 valores calibrados), `pos`, `line` (1 = linha vista), `x` (cruzamentos) e `xin` — o **nível
lido no pino do sensor de cruzamento** (1 = alto), para conferir na bancada qual nível significa
"cruzamento" (`xact`).

### `ACK` / `NAK`

    ACK 12 st=RUN
    NAK 13 code=STATE msg=parametro_so_com_o_robo_parado

| Código | Significado |
|---|---|
| `RANGE` | valor fora do limite ou regra entre parâmetros violada |
| `STATE` | não permitido no estado atual |
| `SYNTAX` | linha ou argumento malformado |
| `UNKNOWN` | verbo desconhecido |
| `NOCAL` | sensores não calibrados (use `CAL`) |
| `ESTOP` | em parada de emergência (use `CLEAR`) |
| `BUSY` | reservado |

`msg` é texto explicativo livre (pode diferir entre o robô e o simulador); o que vale é `code`.

---

## 4. Estados

| Estado | Motores | Significado |
|---|---|---|
| `IDLE` | desligados | parado, sem calibração |
| `CAL` | só com `auto=1` | calibrando |
| `READY` | desligados | parado, calibrado, pronto para `START` |
| `RUN` | PD | em percurso |
| `LOST` | recuperação | linha perdida, girando para o último lado visto |
| `STOPPING` | rampa até 0 | parando (destino, pedido, link ou linha perdida de vez) |
| `STOP` | desligados | parado depois de um percurso interrompido (`why` diz o motivo) |
| `DONE` | desligados | destino alcançado |
| `ESTOP` | **cortados** | parada de emergência |
| `TEST` | valores fixos | teste de bancada (`MOTOR`) |
| `BOOT`, `FAULT` | — | reservados |

O robô liga em `IDLE` (ou `READY`, se a NVS tiver calibração válida) com o STBY em nível baixo antes de
qualquer outra coisa. **Nada põe o robô em movimento sozinho**: só `START`, `CAL auto=1` e `MOTOR`.
Reconectar nunca dá partida.

    IDLE --CAL--> CAL --ok--> READY --START--> RUN <--found-- LOST
                     \--sem contraste--> IDLE       RUN --lostms--> LOST --lostms+loststop--> STOPPING
    RUN --x = cross--> STOPPING --(rampa)--> DONE
    RUN/LOST --STOP | cão de guarda--> STOPPING --(rampa)--> STOP
    qualquer estado --'!'--> ESTOP --CLEAR--> READY | IDLE
    READY/STOP/DONE/IDLE --MOTOR--> TEST --ms | STOP--> READY | IDLE
    CAL --STOP--> IDLE (sem calibração)

---

## 5. Parâmetros

A ordem da tabela é a ordem do `PAR`. Valores iniciais da especificação recebida: **PD, PWM base 220,
Kp 0,0125, Kd 0,1, PWM máximo 220, 4 cruzamentos**. Os demais são escolhas desta implementação, marcadas
para conferência.

| Chave | Padrão | Limites | Significado |
|---|---|---|---|
| `kp` | 0.0125 | 0–0,2 | ganho proporcional |
| `kd` | 0.1 | 0–2 | ganho derivativo, **por ciclo do laço** (muda de efeito se `loop` mudar) |
| `base` | 220 | 0–255 | PWM nas retas (≤ `max`) |
| `max` | 220 | 0–255 | teto de cada motor |
| `minpwm` | 0 | −255–255 | piso de cada motor (≤ `base`; negativo permite ré nas curvas e na recuperação) |
| `accel` | 600 | 0–5000 PWM/s | rampa de aceleração (0 = sem rampa) |
| `decel` | 900 | 0–5000 PWM/s | rampa de frenagem (0 = sem rampa) |
| `adapt` | 0.35 | 0–1 | velocidade adaptativa: quanto a base cai com o erro |
| `cross` | 4 | 0–20 | cruzamentos até o destino (0 = sem destino) |
| `deb` | 150 | 20–2000 ms | intervalo mínimo entre duas contagens |
| `xact` | 1 | 0 ou 1 | nível do pino 34 que significa "cruzamento" — **a confirmar** |
| `thr` | 200 | 0–1000 | valor calibrado mínimo para "linha vista" |
| `lostms` | 300 | 50–3000 ms | sem linha por este tempo → `LOST` |
| `loststop` | 1500 | 100–10000 ms | recuperação sem sucesso por este tempo → parada |
| `recov` | 120 | 0–255 | PWM do giro de recuperação |
| `hb` | 1500 | 0–10000 ms | cão de guarda do link (0 = desligado) |
| `onlink` | stop | stop/continue | política sem link — **a confirmar** no código original |
| `tel` | 20 | 0–50 Hz | taxa da telemetria |
| `loop` | 500 | 100–2000 Hz | ritmo do laço de controle — **a confirmar**; só parado |
| `white` | 1 | 0 ou 1 | 1 = linha branca em pista preta; só parado |
| `flip` | 0 | 0 ou 1 | inverte a ordem dos sensores — **a confirmar**; só parado |
| `ldir` | 1 | −1 ou 1 | sentido do motor esquerdo — **a confirmar na bancada**; só parado |
| `rdir` | 1 | −1 ou 1 | sentido do motor direito — **a confirmar na bancada**; só parado |

O PC valida os limites **antes de enviar** (e mostra todos os problemas de uma vez); o robô valida de
novo e responde `NAK code=RANGE` se algo escapar. Parâmetros lidos da NVS passam pelos mesmos limites
ao ligar; se algum estiver fora, o robô usa os padrões.

---

## 6. O que o firmware faz a cada ciclo do laço (`loop` Hz)

1. **Leitura**: 8 leituras analógicas de 12 bits (0–4095) e o pino de cruzamento.
2. **Calibração** (só em `CAL`): guarda mínimo e máximo de cada sensor; no fim, cada sensor precisa de
   contraste ≥ 200 (ADC bruto), senão `ok=0`.
3. **Valores calibrados**: `c = (bruto − mín) × 1000 / (máx − mín)`, limitado a 0–1000; com `white=1`,
   `v = 1000 − c` (o QTR-A dá tensão baixa sobre o branco). `flip=1` inverte a ordem.
4. **Posição**: linha vista se algum `v ≥ thr`; posição = média ponderada `Σ(i·1000·vᵢ)/Σvᵢ` (só
   `vᵢ ≥ 50`), 0–7000. Sem linha: 0 ou 7000, conforme o lado do último erro. `err = pos − 3500`.
5. **Cruzamento**: borda de entrada no nível `xact`, com intervalo mínimo `deb`, em
   `RUN`/`LOST`/`STOPPING`. Ao atingir `cross` → `STOPPING` (motivo `done`).
6. **Velocidade**: alvo `base × (1 − adapt × min(1, |err|/3500))` (0 em `STOPPING`), aproximado pela
   rampa `accel`/`decel` (PWM/s).
7. **PD**: `corr = kp·err + kd·(err − err_anterior)`; esquerdo `= arred(rampa + corr)`, direito
   `= arred(rampa − corr)`, limitados a `[minpwm, max]`; depois × `ldir`/`rdir`.
8. **Linha perdida**: `RUN` sem linha por `lostms` → `LOST`: gira para o último lado visto (±`recov`,
   limitado a `[minpwm, max]` — com `minpwm = 0` gira sobre uma roda). Linha de volta → `RUN`
   (`EVT found`). Sem linha por `lostms + loststop` → `STOPPING` (motivo `lost`).
9. **Fim**: em `STOPPING`, com a rampa ≤ 0,5 → motores a 0 e `DONE` (destino) ou `STOP` (demais).
10. **Telemetria**: `TEL` a cada `1000/tel` ms com conexão.

A interface do JARVIS **não roda o PD**: só envia pedidos, lê e registra.

---

## 7. Exemplo de sessão

    PC  → (conecta)
    ROB ← HELLO fw=noctario-1.0 proto=1 st=IDLE cal=0 name=Noctario
    ROB ← STA st=IDLE cal=0 x=0 xt=4 lap=0 why=- fw=noctario-1.0 tel=20 onlink=stop hb=1500
    ROB ← PAR kp=0.0125 kd=0.1 base=220 max=220 minpwm=0 accel=600 decel=900 adapt=0.35 cross=4 deb=150 xact=1 thr=200
    ROB ← PAR lostms=300 loststop=1500 recov=120 hb=1500 onlink=stop tel=20 loop=500 white=1 flip=0 ldir=1 rdir=1
    PC  → CMD 1 START
    ROB ← NAK 1 code=NOCAL msg=sensores_nao_calibrados:_use_CAL
    PC  → CMD 2 CAL ms=3000
    ROB ← STA st=CAL ...
    ROB ← ACK 2 st=CAL ms=3000 auto=0
    ROB ← EVT cal ok=1
    ROB ← STA st=READY cal=1 ...
    PC  → CMD 3 SET kd=0.12
    ROB ← ACK 3 kd=0.12
    ROB ← PAR ... (2 linhas)
    PC  → CMD 4 START
    ROB ← STA st=RUN ...
    ROB ← ACK 4 st=RUN
    ROB ← TEL t=... (20 por segundo)
    ROB ← EVT cross n=1 t=...
    PC  → !
    ROB ← EVT estop src=bt
    ROB ← STA st=ESTOP ... why=estop
    PC  → CMD 5 CLEAR
    ROB ← STA st=READY ...
    ROB ← ACK 5 st=READY

---

## 8. Compatibilidade

* `proto` muda se o formato mudar de modo incompatível.
* O PC ignora campos que não conhece e linhas estranhas (nunca derrubam o link); o robô responde
  `NAK UNKNOWN` a verbos que não conhece.
* Linhas de até 240 bytes cabem em qualquer buffer SPP; o `PAR` é dividido para caber mesmo com os
  valores mais longos.
