# JARVIS — Voz: causas encontradas, correções e diagnóstico

## 1. O que estava quebrado (medido, não suposto)

| # | Causa | Evidência | Correção |
|---|---|---|---|
| 1 | A palavra de ativação procurada era "ultron", mas o usuário diz **"Jarvis"**. | Fala sintetizada "Jarvis, …" (Piper pt-BR) transcrita pelos dois modelos Vosk: pequeno → "aviso que horas são", "e já vi…"; grande → "aves", "davis abra o navegador". Gramática restrita `["jarvis","[unk]"]`: 22/22 falsos positivos no modelo grande, 0/14 aceitos no pequeno — descartada. | Formas **fortes** de "jarvis" (aceitas sozinhas) e **fracas** (confusões comuns, só aceitas seguidas de um comando reconhecido), formas antigas do ULTRON migradas, e **calibração com a voz real do usuário** (`CALIBRAR`). |
| 2 | Captura só por PyAudio, sem alternativa. Em Python 3.13/3.14 no Windows o PyAudio pode não ter pacote pronto: sem ele, nem microfone nem saída. | Histórico com `cpython-313/314`; `sounddevice` era opcional e só para saída. | Entrada e saída por **PyAudio → sounddevice** (automático, ou forçado em `mic_backend`); se o dispositivo recusa 16 kHz, abre na taxa nativa e **reamostra** (filtro FIR) para 16 kHz. `sounddevice` passa a ser dependência obrigatória. |
| 3 | `--diagnose` relatava antes de o modelo de fala carregar ("STT —"). | Execução isolada de `main.py --diagnose`. | Diagnóstico em **8 etapas** que espera o carregamento (com prazo) e mostra evidência de cada etapa. |
| 4 | Microfone só escolhível editando `settings.json`. | — | Lista e escolha na interface (DIAGNÓSTICOS > VOZ > USAR ESTE) e no console (`--list-mics`, `--mic N`). |
| 5 | Voz robótica (altura 0,86, rouquidão 0,22, camada sintética). | Perfil antigo. | Perfil **JARVIS**: masculino, grave, natural — altura 0,95, ritmo 0,97, sem rouquidão nem camada sintética, graves +2,5 dB. Medida no teste `test_voice`: presença na faixa de inteligibilidade 0,717 (JARVIS) contra 0,475 (perfil antigo). |
| 6 | Silêncio absoluto (privacidade do Windows bloqueando o microfone) passava despercebido. | — | Detecção de silêncio absoluto: aviso explícito com o caminho de correção nas configurações de privacidade do Windows. |

## 2. Caminho da voz

```
microfone ─▶ backend (PyAudio | sounddevice, reamostragem p/ 16 kHz)
          ─▶ thread "ultron-microphone" (único leitor do microfone)
          ─▶ Vosk (modelo grande se houver RAM; senão o pequeno)
          ─▶ palavra de ativação ("Jarvis…") ou janela de continuação (12 s após uma resposta)
          ─▶ core.submit(texto, source="voice") ─▶ Neural Core ─▶ resposta
          ─▶ fala (Piper/SAPI, thread "ultron-speaker") com a escuta tratada como eco
```

* **Sem autoescuta.** Enquanto o JARVIS fala, o que o microfone ouve é comparado com o texto
  falado (`echo_ratio`); eco é descartado e contado. Só "Jarvis…" ou um controle curto ("pare",
  "pausa") dito por você interrompe a fala (*barge-in*).
* **Ordem de início/parada.** Saída de áudio → áudio neural → voz; na parada, na ordem inversa,
  com `join` das threads (nenhuma fica bloqueada indefinidamente: toda leitura tem prazo).
* **Voz desligável.** Botão VOZ (só texto), "fique quieto"/"pode falar", ou `voice_enabled`.

## 3. Como diagnosticar

| Onde | Como |
|---|---|
| Interface | **SISTEMAS > VOZ**: `TESTAR` (sem falar: etapas 1–5, 7 e 8), `TESTAR FALANDO` (as 8 etapas: diga "Jarvis, que horas são?"), `CALIBRAR` (repete "Jarvis" 3 vezes e aprende as formas da sua voz), escolha do microfone e contadores ao vivo. Também pela bandeja: *Diagnóstico de voz*. |
| Voz/texto | "diagnóstico de voz", "liste os microfones", "use o microfone 2" |
| Console | `START_JARVIS.bat --voice-test` (8 etapas, interativo) · `START_JARVIS.bat --diagnose` (saúde + voz) · `python main.py --list-mics` · `python main.py --mic 2` |

Com o JARVIS já aberto, o teste de console recusa iniciar (dois processos disputariam o
microfone): use a interface ou feche-o antes (`START_JARVIS.bat --stop`).

### As 8 etapas

| Etapa | O que comprova | Falhas comuns e o que fazer |
|---|---|---|
| 1. Microfone detectado | lista real de dispositivos de entrada (PyAudio e/ou sounddevice) | "nenhuma biblioteca de áudio utilizável" → rode `INSTALL_JARVIS.bat`; "nenhum dispositivo" → conecte/ative o microfone no Windows |
| 2. Dispositivo selecionado | qual será aberto (nome → índice → padrão) | o configurado sumiu → escolha outro em USAR ESTE |
| 3. Captura de áudio | blocos chegando, nível e pico | "silêncio absoluto" → Configurações > Privacidade > Microfone (permitir apps da área de trabalho) ou microfone mudo; "não foi possível abrir" → outro app usando em modo exclusivo |
| 4. Mecanismo STT | Vosk importável | `INSTALL_JARVIS.bat` |
| 5. Modelo de português | modelo encontrado e carregado | modelo ausente em `assets\stt` → ver README_JARVIS (modelos) |
| 6. Palavra de ativação | "Jarvis" reconhecido na sua fala (teste falando) | "ouvido: …" mostra o que o Vosk entendeu → `CALIBRAR`; fale mais perto; prefira o modelo grande |
| 7. Texto entregue ao cérebro | `USER_INPUT` de origem voz chegou ao Neural Core | falha aqui é defeito: veja `logs\ultron.log` |
| 8. Resposta produzida e reproduzida | `RESPONSE_READY` + fala realmente tocada | "voz desligada" → botão VOZ; "não reproduzida" → saída de áudio indisponível (veja a etapa 1) |

Cada etapa termina em OK, AVISO, FALHA ou "—" (não executada), sempre com o motivo; nenhuma
etapa é dada como OK sem evidência.

## 4. O que foi testado aqui e o que precisa ser validado no Windows

**Testado neste ambiente (Linux, sem placa de som):**
* caminho completo com **microfone, STT e síntese simulados** (`tests/test_jarvis_voice.py`:
  `FakeStream`, `ScriptedSTT`, `FakeSynth`, `FakeOutput`) — da detecção à fala, ausência de
  microfone, concorrência voz + texto, entrega ao núcleo;
* reamostragem, escolha de candidatos, ausência das bibliotecas de áudio, silêncio absoluto,
  formas de ativação, eco (`tests/test_voice.py`);
* perfil de voz (DSP sobre sinal sintético).

Isso **não** é um teste real de microfone, de Windows ou de reconhecimento da sua voz. Os
testes simulados estão marcados como tal no código.

**Para validar no seu computador (5 minutos):**
1. `START_JARVIS.bat --voice-test` — siga as instruções e diga "Jarvis, que horas são?".
2. Se a etapa 6 falhar: DIAGNÓSTICOS > VOZ > `CALIBRAR`, e repita o teste.
3. Se a etapa 3 indicar silêncio: libere o microfone para aplicativos da área de trabalho.
4. Com o JARVIS aberto, diga "Jarvis" e observe o halo ciano do CORE acompanhar a sua voz;
   a resposta deve ser falada sem que ele "se ouça".
