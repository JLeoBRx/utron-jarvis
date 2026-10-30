# Noctário — firmware do ESP32

Seguidor de linha com ESP32 DevKit, ponte TB6612FNG, 8 sensores QTR analógicos, sensor digital de
cruzamento, 2 motores DC, LED e Bluetooth Clássico. Linha **branca** em pista **preta**. Controle PD
com velocidade adaptativa, rampas e contagem de 4 cruzamentos até o destino.

> **Estado honesto.** Os arquivos originais `Noctario_JARVIS(1).ino` (20/10/2026) e
> `Nefarious_6_cruzamentos(1).txt` (28/10/2026) foram localizados e comparados. Ambos confirmam a
> pinagem, linha branca em pista preta, sensor de cruzamento ativo em LOW e laço de 100 Hz. Há dois
> perfis históricos: `Noctario_JARVIS.ino` (4 cruzamentos, Kp 0,0125, Kd 0,1, PWM 220),
> `Noctario_JARVIS(1).ino` (4 cruzamentos, Kp 0,0352, Kd 0,0085, PWM 110, máximo 175) e
> `Nefarious_6_cruzamentos` (6 cruzamentos e ganhos adaptativos). Este firmware conserva o perfil
> NOCT/1 de 4 cruzamentos e ganhos configuráveis. Os algoritmos de controle não são cópias byte a byte;
> sentido físico dos motores e ordem da barra precisam da bancada.

## O que foi verificado e o que não foi

| Item | Situação |
|---|---|
| Núcleo (`src/noct_core.cpp`) compila no PC: g++, C++17, `-Wall -Wextra -Werror` | verificado |
| Testes do núcleo no PC (`test/host/test_core.cpp`: protocolo, limites, calibração, PD, parada de emergência, cruzamentos e destino, perda de linha, cão de guarda, bancada, calibração interrompida, NVS corrompida) | aprovados |
| Núcleo C++ ≡ simulador do JARVIS, **linha a linha**, numa sessão de 62 s simulados (31 071 ciclos do laço, todas as mensagens e o PWM de cada ciclo) | verificado (`tests/test_noctario_firmware.py`) |
| `src/main.cpp` (pinos, PWM, Bluetooth, NVS, LED) contra cabeçalhos com as assinaturas do arduino-esp32 2.x e 3.x (`test/host/stubs/`) | tipos e sintaxe conferidos (`-Wall -Wextra -Werror`) — não é o framework real |
| `src/main.cpp` compilado de verdade para a ESP32 | **verificado por CI**: PlatformIO compilou para `esp32dev` e publicou o `firmware.bin`; não significa que o binário foi gravado na placa |
| Comportamento no robô real (motores, sensores, Bluetooth, tempo de volta) | **NÃO verificado** — nenhum teste daqui usa o robô |

## Pinagem (exatamente como recebida)

| Função | GPIO |
|---|---|
| Motor **direito** — TB6612FNG canal A: PWMA / AIN1 / AIN2 | 21 / 18 / 19 |
| Motor **esquerdo** — TB6612FNG canal B: PWMB / BIN1 / BIN2 | 23 / 4 / 22 |
| STBY do TB6612FNG | 5 |
| Sensor de cruzamento (digital, ativo em LOW) | 34 |
| LED | 15 |
| QTR 0 → 7 (ordem física esquerda/direita a validar) | 32, 33, 25, 26, 27, 14, 12, 13 |

PWM dos motores: 20 kHz, 8 bits (inaudível; o TB6612FNG aceita até 100 kHz). Sentido pelo par IN1/IN2;
PWM 0 deixa o motor livre.

## Cuidados de hardware (leia antes de ligar)

* **Botão físico de parada**: a parada pelo Bluetooth (byte `!`, F12, "pare o Noctário") **não
  substitui** um interruptor que corte a alimentação dos motores (VM do TB6612FNG). Instale um ao
  alcance da mão.
* **QTR alimentado em 3,3 V**: os pinos do ADC da ESP32 não toleram 5 V. Sobre o preto o QTR-A dá
  tensão alta (perto da alimentação).
* **GPIO 12 é pino de *strapping***: se estiver em nível alto quando a ESP32 liga, ela escolhe 1,8 V
  para a memória flash e pode não iniciar. Como o QTR ligado ao GPIO 12 dá tensão alta sobre o preto,
  **ligue o robô fora da pista ou sobre a linha branca**. Se a placa só "não liga" quando está sobre a
  pista, a causa é esta. (Existe uma correção definitiva por eFuse, `espefuse.py set_flash_voltage
  3.3V`, mas ela é **irreversível**; este projeto não a executa.)
* **GPIO 5 (STBY) tem pull-up interno no boot**: entre o reset e o `setup()` o TB6612FNG pode ficar
  habilitado. O firmware leva o STBY a nível baixo como primeira instrução; para cobrir também esse
  intervalo, ponha um **resistor de 10 kΩ do STBY ao GND**.
* **GPIO 34 é só entrada e não tem pull-up/pull-down interno**: o sensor de cruzamento precisa dirigir
  o nível (saída *push-pull*) ou ter resistor externo; pino flutuando gera cruzamentos falsos. A leitura
  `xin` do `SENS` mostra o nível real.
* **ADC2** (GPIO 25, 26, 27, 14, 12, 13) não funciona com o Wi-Fi ligado; este firmware **nunca liga o
  Wi-Fi**. Se algum sensor ficar com valor parado com o Bluetooth ativo, o `SENS` mostra.
* GPIO 15 (LED) também é de *strapping* (só silencia as mensagens de boot da porta serial; inofensivo).
* GND comum entre a ESP32, o TB6612FNG, os sensores e a bateria dos motores.

## Compilar e gravar

**PlatformIO** (recomendado):

    cd firmware/noctario
    pio run                      # compila
    pio run -t upload            # grava pela USB
    pio device monitor -b 115200 # mensagens de diagnóstico pela USB

**Arduino IDE**: pacote *esp32* da Espressif (2.x ou 3.x), placa **ESP32 Dev Module**, *Partition
Scheme* **Huge APP (3MB No OTA)**. Crie a pasta `noctario/` com `noctario.ino` (o conteúdo de
`src/main.cpp`) e copie `src/noct_core.h` e `src/noct_core.cpp` para ela.

Os parâmetros e a calibração ficam na memória do robô (NVS) **só depois de SALVAR** ("salve os
parâmetros do Noctário" ou SALVAR NO ROBÔ). Ao ligar, o que estiver na NVS passa pelos mesmos limites do
protocolo; se algo estiver fora, o robô usa os padrões.

## LED

| Padrão | Estado |
|---|---|
| pisca 1 Hz | sem calibração (`IDLE`) |
| pisca 5 Hz | calibrando |
| aceso | pronto ou em percurso |
| pisca rápido | linha perdida, recuperando |
| pisca 10 Hz | **parada de emergência** |
| piscada dupla a cada 1,2 s | destino alcançado |
| pisca lento (1 s aceso, 1 s apagado) | parado depois de interrupção |
| pisca ~4 Hz | teste de bancada dos motores |

## Primeira vez na bancada (rodas fora do chão)

1. Robô apoiado com as **rodas fora do chão**; botão físico de corte ao alcance.
2. Grave o firmware. O LED pisca a 1 Hz (sem calibração).
3. Pareie **Noctario** no Windows (Configurações > Bluetooth). Em *Mais opções de Bluetooth > Portas COM*,
   anote a porta de **saída**. No JARVIS: CONFIGURAÇÕES > NOCTÁRIO > Conexão "Porta COM do Bluetooth" e a
   porta (ou "Bluetooth direto" com o endereço do robô).
4. Diga *"conecte o Noctário"* (ou CONECTAR na página NOCTÁRIO, F4). A faixa mostra CONECTADO e a versão
   do firmware; sem conexão, a página diz SEM CONEXÃO e não mostra dado nenhum.
5. **Sentido dos motores**: *"teste o motor esquerdo do Noctário"* (ou o botão MOTOR ESQUERDO) e confirme.
   A roda esquerda deve girar **para a frente** por 0,5 s. Girou para trás? *Sentido do motor esquerdo* =
   invertido > APLICAR. Repita com o direito.
6. **Calibração**: *"calibre o Noctário"*, confirme e, durante 3 s, passe a barra de sensores sobre a
   linha e o fundo (LED a 5 Hz). Resposta: "Sensores calibrados; robô pronto".
7. **Ordem dos sensores**: com a linha sob o sensor da **direita** (olhando no sentido em que o robô
   anda), *"leia os sensores do Noctário"* → a posição deve ficar perto de **7000**; sob o da esquerda,
   perto de 0. Ao contrário? *Inverter a ordem dos sensores* = sim > APLICAR, e confira de novo.
8. **Sensor de cruzamento**: leia os sensores com ele sobre uma marca de cruzamento e fora dela; o texto diz
   o nível do pino e se isso conta como cruzamento. Trocado? *Nível ativo do sensor de cruzamento* > APLICAR.
9. Com tudo certo: *"salve os parâmetros do Noctário"*.
10. **Primeiras voltas** com velocidade menor (por exemplo PWM base 150 e máximo 180), olhando o gráfico
    de telemetria; depois suba em direção a 220.

## O que foi confirmado no sketch original e o que ainda precisa da bancada

| Item | Aqui | Como confirmar | Parâmetro |
|---|---|---|---|
| Ordem dos sensores (GPIO 32 = esquerda?) | 32 à esquerda | passo 7 da bancada | `flip` |
| Sentido de cada motor | IN1 alto = para a frente | passo 5 da bancada | `ldir`, `rdir` |
| Nível do sensor de cruzamento | **LOW ativo; borda HIGH → LOW** | confirmado nos dois sketches originais | `xact=0` |
| Ritmo do laço de controle | **100 Hz (10 ms)** | confirmado nos dois sketches originais | `loop=100` |
| Escala do erro | posição 0–7000, centro 3500 (como a biblioteca QTRSensors da Pololu) | código original; em outra escala, Kp e Kd mudam de efeito na mesma proporção | — |
| Política sem link | parar (`onlink=stop`), cão de guarda de 1,5 s | proteção adicional do NOCT/1; os sketches antigos não tinham cão de guarda | `onlink`, `hb` |
| Contagem até o destino | perfil JARVIS: 4 cruzamentos; variante `Nefarious_6` de 28/10: 6 | manter 4 neste perfil; use `cross=6` só ao selecionar a variante de 6 | `cross`, `deb` |
| Perda de linha | recupera após 0,3 s, desiste após mais 1,5 s, giro com PWM 120 | comportamento novo do NOCT/1; os sketches antigos paravam após 500 ms sem linha | `lostms`, `loststop`, `recov` |
| Velocidade adaptativa e rampas | 0,35; 600 e 900 PWM/s | modelo simplificado novo do NOCT/1; o sketch de 28/10 usava reduções separadas por erro e derivada | `adapt`, `accel`, `decel` |
| Nome Bluetooth | `Noctario` | confirmado nos dois sketches originais | — |

A pinagem, a linha branca, o nível ativo do cruzamento, o laço e o nome Bluetooth foram confirmados.
A ordem física da barra e o sentido real dos motores ainda precisam do teste de bancada.
O perfil de ganhos/velocidade do arquivo de 28/10 é diferente do controle do NOCT/1 e não foi copiado
automaticamente. Os parâmetros do NOCT/1 seguem ajustáveis pela interface, por voz ou por `SET`,
com os limites do protocolo, sem regravar o firmware.

## Reduzir o tempo de volta (sem prometer tempo)

A volta hoje leva cerca de 5 min 40 s (informado). Só a volta **medida** diz se algo melhorou:

* Toda volta feita com o JARVIS conectado é gravada com a telemetria (página NOCTÁRIO > VOLTAS GRAVADAS). *"Peça à TARDIS para
  analisar a telemetria do Noctário"* compara as voltas: tempo, erro RMS, oscilação, saturação do PWM,
  perdas de linha e intervalos entre cruzamentos, com hipóteses de ajuste explicadas. A TARDIS só
  **propõe**; nada muda no robô sem a sua confirmação.
* Suba o **PWM base** aos poucos (mantendo o máximo ≥ base) enquanto o erro RMS, a oscilação e as perdas
  de linha continuarem aceitáveis.
* **Velocidade adaptativa** maior freia mais nas curvas (mais seguro); menor mantém a velocidade.
* **Rampa de aceleração** maior sai mais rápido das curvas e da largada.
* Oscilação nas retas → mais Kd ou menos Kp. Atraso nas curvas ou perdas de linha → mais Kp.
* **PWM mínimo** negativo permite a roda de dentro dar ré nas curvas fechadas.

## Testes no PC (sem o robô)

    cd firmware/noctario/test/host
    make && ./test_core        # "OK: núcleo do firmware aprovado"

No JARVIS: `python -m pytest tests/test_noctario_firmware.py` compila o núcleo e o compara com o
simulador linha a linha (precisa de g++ ou clang++; sem compilador, o teste é pulado e diz por quê).

## Arquivos

| Arquivo | Conteúdo |
|---|---|
| `src/noct_core.h`, `src/noct_core.cpp` | toda a lógica (protocolo, estados, PD, cruzamentos, perda de linha, cão de guarda, parada) — sem Arduino |
| `src/main.cpp` | camada da ESP32: pinos, PWM, Bluetooth SPP, NVS, LED, ritmo do laço |
| `platformio.ini` | projeto PlatformIO (`esp32dev`) |
| `test/host/` | testes do núcleo no PC, o reprodutor usado na comparação com o simulador e `stubs/` (assinaturas do Arduino só para conferir o `main.cpp` no PC) |
| `PROTOCOLO_NOCT1.md` | o protocolo Bluetooth completo |

## Pedido: o código original do Noctário

Para confirmar os itens acima sem tentativa e erro, envie o **código original do Noctário** (o `.ino`
ou a pasta do projeto, com os `.h`/`.cpp`). Com ele dá para conferir a ordem dos sensores, o sentido dos
motores, a escala do erro, o ritmo do laço, a contagem de cruzamentos e o que o robô faz sem link — e os
valores padrão daqui passam a ser os dele.
