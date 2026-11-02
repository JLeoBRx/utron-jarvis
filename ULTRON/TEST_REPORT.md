# JARVIS — Relatório de testes

Situação na Fase 7 do JARVIS ULTIMATE (JARVIS original + TARDIS + Noctário).

## 1. Resultado

| Ambiente | Resultado |
|---|---|
| Python 3.13.16, Linux (contêiner, 4 vCPUs), PySide6 6.8.1 offscreen | **404 testes, 404 OK, 0 falhas, 0 pulados** (~2 min) |
| Python 3.11.17, mesmo ambiente | **404 testes, 404 OK, 0 falhas, 0 pulados** (~2 min) |
| Windows Server 2025 (CI do GitHub; núcleo 10.0.26100, o mesmo do Windows 11 24H2), Python 3.11.9 | **404 testes, 404 OK, 0 falhas, 0 pulados** (178 s) |
| Núcleo do firmware do Noctário (g++, C++17, `-Wall -Wextra -Werror`) | `test_core` aprovado (10 grupos) e igual ao simulador linha a linha (31 071 ciclos) |
| CI no GitHub (`.github/workflows/jarvis-validation.yml`): Windows + Python 3.11, Linux + Python 3.11/3.13, testes C++ e **compilação real do firmware para a ESP32 (PlatformIO)**, pacote ZIP extraído e testado | ver §6 |

Evolução: 197 (fim da missão JARVIS) → 263 (Fase 3) → 328 (Fase 5) → 364 (Fase 6) → 365 (integração da
PR #2) → **404 (Fase 7)**. Nenhum teste foi desativado, pulado ou afrouxado para passar. Quando um teste novo
falhou, a causa foi corrigida no código (§3) ou na suposição errada do próprio teste — os dois casos estão
registrados.

## 2. Como rodar

```
python TEST_JARVIS.py              todos os testes + relatório do ambiente
python TEST_JARVIS.py --quick      sem os testes lentos
python TEST_JARVIS.py --env        só o relatório do ambiente (componentes ausentes)
python -m pytest tests             o mesmo, pelo pytest

cd firmware/noctario/test/host && make && ./test_core      núcleo do firmware no PC (precisa de g++)
cd firmware/noctario && pio run                            firmware para a ESP32 (precisa do PlatformIO)
```

Os testes usam pastas temporárias (`JARVIS_DATA_DIR`/`ULTRON_DATA_DIR` apontam para elas antes de qualquer
import): **nenhum dado real do usuário é lido ou alterado**. O Ollama é um servidor HTTP local de teste
(`tests/fake_ollama.py`); o robô é o simulador ou um "robô de teste" roteirizado; a interface roda com
`QT_QPA_PLATFORM=offscreen`. Os testes de segurança conferem as pastas protegidas do sistema SEM escrever
nelas (a recusa vem antes da execução), trocam a pasta do programa por uma cópia temporária e usam uma
Lixeira falsa.

## 3. Fase 7 — campanha de testes e o que ela encontrou

Antes da campanha, a cobertura de linhas foi medida (`coverage.py`, a suíte inteira): **74 %**. Os
menos cobertos incluíam exatamente o que a Fase 7 pede — skills de arquivos (36 %), linha de comando
(`app.py`, 9 %), perguntas sobre a memória pessoal (21 %), calibração da voz (22 %). Foram escritos
**39 testes novos**:

| Arquivo | O que prova |
|---|---|
| `test_security.py` (17) | código sem shell, `eval`/`exec`, `os.system` ou `pickle`, processos só com lista de argumentos (varredura do código-fonte, conferida contra exemplos ruins); TLS nunca desligado; a rede não sonda portas (a única conexão TCP é o teste de conectividade com 2 endereços fixos, desligado no modo local); skills proibidas não existem nem rodam; **o modelo só executa ferramentas oferecidas no pedido**; o planejador nunca vê as reservadas; **pastas protegidas** (sistema, inicialização automática, programa e dados do JARVIS) recusadas antes de pedir autorização, inclusive por link simbólico; exclusão só pela Lixeira e nunca da pasta pessoal ou da raiz; **cópias de segurança nunca sobrescritas**; criar/mover/copiar nunca sobrescreve; conteúdo de arquivo e da tela rotulado como dado; programas e scripts só abrem com autorização; texto da janela entra no prompt numa linha, entre aspas; saída da visão saneada; credenciais só no cofre do sistema |
| `test_failures.py` (7) | `settings.json` ilegível → padrões e o original guardado; **banco danificado → início para com mensagem clara (código 3) e o arquivo intacto**; backup restaura banco danificado e guarda a cópia danificada; backup que falha (disco cheio) não deixa arquivo pela metade; **banco somente leitura → a conversa continua e a resposta diz o que não foi gravado**; modelo que quebra → resposta honesta; sensor que falha → marcado com o motivo e recupera |
| `test_transitions.py` (6) | para sucesso, skill que quebra, autorização negada, autorização sem resposta, **cancelar com o modelo ainda carregando** e modelo que quebra: a sequência real de estados termina em IDLE e o rosto volta a "aguardando interação"; durante a espera do "sim" o rosto pede confirmação; a falha do modelo acende a janela de erro de 8 s |
| `test_cli.py` (4) | comandos documentados executados de verdade em processos separados: `--version`, `--status`, `--say`, `--backup`, `--list-backups`, `--restore-backup`, `--export` (nunca sobrescreve), `--diagnose` sem modelo |
| `test_second_brain.py` (+3) | perguntas sobre a memória pessoal respondidas **só** com registros salvos; sem registro, "não encontrei"; referência ambígua pergunta |
| `test_voice.py` (+1) | CALIBRAR com Piper e Vosk reais: as formas conhecidas ficam, palavra comum nunca vira forma forte (o Vosk pequeno ouve o "Jarvis" sintetizado como "aves") |
| `test_model_router.py` (+1) | cancelar antes do primeiro token libera quem esperava na hora |

**Defeitos reais encontrados pelos testes novos e corrigidos** (cada um com teste que falha sem a correção):

1. **Arquivos**: as skills podiam criar, alterar, mover ou apagar arquivos dentro do sistema operacional, da
   inicialização automática e do próprio JARVIS — um `.py` gravado na pasta de plugins rodaria na próxima
   partida (o carregador executa todo `.py` dali). Agora isso é recusado **antes** de qualquer pedido de
   autorização (gancho `refuse_reason` no executor); ler e listar continuam livres.
2. **Cópias de segurança**: a segunda edição sobrescrevia `.ultron.bak` e o conteúdo original do usuário
   se perdia. Agora `x.ultron.bak`, `x.ultron.1.bak`… — nenhuma é sobrescrita.
3. **Cancelar com o modelo carregando**: o JARVIS ficava "pensando" até o primeiro token (com um modelo
   real, dezenas de segundos). O cancelamento agora encerra a conexão e libera na hora.
4. **Modelo que quebra no meio do pedido**: a resposta dizia, mas o rosto e o histórico não mostravam a
   falha (nada publicava `MODEL_UNAVAILABLE`). Agora publicam.
5. **Banco danificado**: o início caía com um traceback (e, sem console, a janela simplesmente não abria).
   Agora para com mensagem clara, código 3, arquivo intacto e os comandos de restauração.
6. **`settings.json` ilegível**: a próxima gravação o substituía. Agora o original é guardado antes.
7. **Banco que recusa gravação**: "Falha interna (OperationalError)". Agora a resposta diz que nada foi
   gravado e o que conferir.
8. **Backup que falha no meio** deixava um `.partial` para trás. Agora é removido.
9. **Prompt**: um título de janela com quebras de linha podia simular uma seção nova dentro do prompt do
   sistema. Agora entra numa linha só, entre aspas, rotulado como dado.
10. **No Windows** (achados pelo CI, §6): o cancelamento dependia do comportamento do socket, os testes da
    linha de comando liam a codificação errada e o `TEST_JARVIS.py` caía ao imprimir falhas.

Cobertura depois (mesma medição): **75 %** no total (o código cresceu com as correções); skills de arquivos
36 % → 61 %, perguntas sobre a memória 21 % → 84 %, calibração da voz 22 % → 58 %. A linha de comando
(`app.py`) continua com número baixo na medição porque os testes dela rodam `main.py` em processos
separados, que o `coverage` não acompanha — os comandos em si estão testados.

Nas Fases 5 e 6 os testes novos já tinham encontrado: F12 e Esc da plataforma que nunca disparavam
(PySide6 6.8), ferramentas não oferecidas executadas pelo modo agêntico, "Feito e verificado" quando nada
rodava, frases que só mencionam o robô virando comando a ele, NaN aceito na validação de argumentos,
`STOP` do teste de bancada gravado como volta falsa.

## 4. O que cada módulo cobre

| Área | Arquivos de teste |
|---|---|
| Núcleo, eventos, estados, configurações | `test_core` (15), `test_event_bus` (7), `test_integrity` (7: todos os módulos importam, código compila, skills registradas, `--stop` com processo real, ZIP com caminho malicioso recusado) |
| Agente: execução, autorização, permissões, recuperação, verificação | `test_executor` (12), `test_permissions` (10), `test_recovery` (7), `test_verifier` (5), `test_planner` (8), `test_activity` (7) |
| Segurança, falhas, transições, linha de comando | `test_security` (17), `test_failures` (7), `test_transitions` (6), `test_cli` (4) |
| Memória pessoal e modelo do mundo | `test_memory` (8), `test_second_brain` (25), `test_world_model` (5) |
| Voz, boca e legendas | `test_voice` (27), `test_jarvis_voice` (5), `test_lipsync` (8) |
| Interface: plataforma, avatar, cérebro, desempenho | `test_platform` (21), `test_avatar` (12), `test_hud` (22), `test_performance` (10) |
| TARDIS | `test_tardis_logic` (33), `test_tardis_room` (12), `test_tardis` (7) |
| Noctário | `test_noctario` (33: protocolo, transportes, serviço, skills pelo núcleo, painel), `test_noctario_firmware` (3: testes C++, camada Arduino conferida contra as assinaturas, firmware ≡ simulador) |
| Modelos e provedores | `test_model_router` (9), `test_openai_provider` (6) |
| Rede, imaginação, plugins, original recuperado | `test_network` (14), `test_imagination` (6), `test_plugins` (4), `test_original_recovery` (22) |

## 5. Real × simulado

**Real neste ambiente:** núcleo completo, banco SQLite em arquivo, Event Bus, workers, agendador,
lembretes (relógio controlado, banco e lógica reais), plataforma Qt renderizando (offscreen), avatar,
sala da TARDIS, síntese Piper → reconhecimento Vosk com os modelos do pacote (áudio gerado, **sem
microfone**), processos reais da linha de comando, núcleo do firmware compilado com g++ e comparado ao
simulador.

**Simulado (e dito assim nos testes):** microfone e áudio de saída, resultado do reconhecimento em parte
dos testes, Ollama (servidor HTTP local), OpenAI, o robô (simulador com pista de teste inventada, ou robô
roteirizado), Bluetooth, rede física, cofre de credenciais e Lixeira (falsos), disco cheio e banco
somente leitura (falhas injetadas).

**Não verificável aqui:** microfone físico e a privacidade do Windows, reconhecimento da sua voz,
reprodução de áudio, bandeja e notificações do Windows, `winreg` (início automático), UI Automation, GPU,
os scripts `.bat` em `cmd.exe`, **o robô de verdade** (gravar o firmware, Bluetooth, ordem física dos
sensores, sentido dos motores, cruzamentos na pista, parada física, tempo de volta). Roteiros:
`DIAGNOSTICO_JARVIS.bat`, `START_JARVIS.bat --voice-test` e, para o robô, a bancada em
`firmware/noctario/README.md`.

## 6. CI no GitHub

Disparado manualmente na branch `claude/adoring-brahmagupta-vcejpt`. O job do Windows roda no runner
`windows-latest` do GitHub — **Windows Server 2025** (10.0.26100), sem microfone, alto-falante, GPU ou
área de trabalho interativa: ele prova o Python, o Qt (offscreen), o SQLite, os processos e os caminhos
do Windows, não o hardware de um PC.

| Execução | Linux 3.11 / 3.13 (suíte, estáticos, ZIP extraído) | Firmware (C++ no PC e ESP32) | Windows (Server 2025, Python 3.11.9) |
|---|---|---|---|
| [41364163195](https://github.com/JLeoBRx/utron-jarvis/actions/runs/41364163195) — `8c01d70` | aprovado | aprovado; `firmware.bin` gerado | **6 falhas** (abaixo) |
| [41365361463](https://github.com/JLeoBRx/utron-jarvis/actions/runs/41365361463) — `746d7f7` | aprovado | aprovado; `firmware.bin` gerado | **aprovado: 404/404, 0 pulados** (178 s); ZIP extraído: aprovado no modo `--quick` (7 pulados: os testes lentos e os que usam os modelos de voz, que o ZIP não traz) |

O Windows encontrou o que o Linux não mostra:

1. **Cancelar com o modelo carregando** (2 testes): a correção dependia de encerrar o socket de outra thread,
   o que no Windows não acorda quem está bloqueado nele. Agora uma thread lê a resposta numa fila e quem
   pediu espera na fila, olhando o cancelamento a cada 50 ms — conferido também com o encerramento do
   socket desligado, ou seja, sem depender do sistema.
2. **Linha de comando** (4 testes): num pipe, o Windows escreve em cp1252 e os testes liam UTF-8; o
   processo filho agora recebe `PYTHONIOENCODING=utf-8` (no console de verdade nada muda).
3. **O próprio `TEST_JARVIS.py`** caía ao imprimir as falhas (um caractere que a cp1252 não tem) e o resumo
   nunca saía; agora a saída redirecionada é UTF-8 e nenhum caractere derruba o relatório.

## 7. Verificações estáticas

| Verificação | Resultado |
|---|---|
| `pyflakes ultron tests tools TEST_JARVIS.py TEST_ULTRON.py main.py` | limpo |
| `compileall` (pacote, testes, ferramentas) | OK |
| Varredura do código (`test_security`): shell, `eval`/`exec`, `os.system`, `pickle`, comando em texto, TLS desligado | nada encontrado |
| Importação de todos os módulos do pacote | OK (`test_integrity`) |
| Pacote ZIP | validado por `tools/build_release.py --check` e testado depois de extraído numa pasta nova (no CI) |
