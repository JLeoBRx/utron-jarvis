# JARVIS ULTIMATE — Entrega

> **Rascunho da Fase 8.** A entrega fica em pausa até você confirmar no seu Windows que a janela e o modo
> console abrem (correção da inicialização: `AUDITORIA_INICIALIZACAO.md`).

**JARVIS 2.0.0** — JARVIS original + TARDIS + NOCTÁRIO. Este documento é o índice da entrega (Fase 8): onde
está cada um dos 20 entregáveis pedidos, como o projeto está organizado, como instalar e executar, e uma
lista precisa do que foi testado, do que foi simulado e do que ainda depende do seu computador e do robô.

## 1. Em uma página

* **Uma aplicação real, não uma demonstração.** Uma janela com seis módulos — JARVIS (rosto holográfico 3D
  renderizado em tempo real, boca ligada ao áudio real da fala, 12 estados ligados a sinais reais, legendas),
  TARDIS (sala de controle 3D com rotor e o ARQUIVO da memória pessoal), NOCTÁRIO (painel de engenharia do
  robô), ATIVIDADES, CONFIGURAÇÕES e DIAGNÓSTICOS — sobre o núcleo do JARVIS: voz offline, memória pessoal
  com lembretes que não dependem do modelo, **120 ações** executadas com permissão, autorização e
  verificação independente.
* **Um modelo de IA, dois módulos lógicos.** A TARDIS é um módulo com fila, protocolo, analisadores e
  memória de projeto próprios, mas usa **o mesmo modelo** do JARVIS (Ollama local) e cada resultado diz se
  usou o modelo ou foi uma análise determinística. Não existem dois modelos independentes.
* **O robô é controlado pelo ESP32.** O PD roda no firmware; a interface pede, lê e registra. Parada de
  emergência sempre visível (F12), sem fila nem modelo de linguagem; **ela não substitui o botão físico**.
  Estado pedido × estado confirmado pelo robô; sem resposta: "estado desconhecido", nunca "feito".
* **Testes:** 421 testes automáticos aprovados no Linux (Python 3.13 e 3.11) e no Windows (Server 2025,
  Python 3.11); firmware compilado para a ESP32 e o núcleo dele idêntico ao simulador ciclo a ciclo;
  instalação pelo `INSTALL_JARVIS.bat` executada de verdade no Windows a partir do ZIP (§5).
* **Ainda não verificado:** o robô real, o seu microfone e alto-falante, a bandeja e as notificações num
  Windows de mesa, a GPU e o Ollama com o modelo real (§6). O roteiro para verificar está em
  `PLANO_DE_EVOLUCAO.md` §1.

## 2. Instalar e executar

1. Instale o **Python 3.11** (python.org, marque *Add python.exe to PATH*) e o **Ollama** (ollama.com).
2. Extraia `JARVIS_FINAL.zip` e execute **`INSTALL_JARVIS.bat`** (cria o `.venv`, instala as dependências,
   procura os modelos de voz, oferece baixar os modelos do Ollama e pergunta sobre o início automático —
   nada é apagado). Atualizando uma instalação existente: `ATUALIZAR_JARVIS.bat` (faz backup antes).
3. Inicie com **`START_JARVIS.bat`**. Diagnóstico: `DIAGNOSTICO_JARVIS.bat`. Todos os comandos:
   `START_JARVIS.bat --help`.

Detalhes, modelos de voz e problemas comuns: `README_JARVIS.md` §§ 1, 2 e 12. Robô: `firmware/noctario/README.md`.

## 3. Os 20 entregáveis

| # | Entregável | Onde | Como foi verificado |
|---|---|---|---|
| 1 | Inventário das funcionalidades originais | `INVENTARIO_JARVIS_ORIGINAL.md`; detalhes em `docs/inventario/` (comandos, serviços, interface) | auditoria do código original no histórico do Git (`53e5a31`), com arquivo e linha de cada item |
| 2 | Plano de preservação e expansão | `ARQUITETURA_ULTIMATE.md` §2 | a lista de recuperação foi implementada na Fase 3 (`test_original_recovery`, 22 testes) |
| 3 | Arquitetura técnica | `ARQUITETURA_ULTIMATE.md` (§§ 3–13); mapa de integração em `ARCHITECTURE_JARVIS.md` | — |
| 4 | Design visual | `DESIGN_VISUAL.md`; tema em `ultron/hud/theme.py` e `palette.py` | renderizado nos testes da interface (offscreen) |
| 5 | Avatar holográfico | `ultron/hud/avatar/` (malha, rig, renderizador, animação, 12 estados) | `test_avatar` (12); desempenho medido: `docs/benchmarks/avatar_fase4.json` |
| 6 | Boca sincronizada com a fala | `ultron/voice/lipsync.py` + `ultron/hud/avatar/animator.py` | `test_lipsync` (8) com o áudio real do Piper: visemas nos trechos sonoros, boca fechada no silêncio e ao interromper |
| 7 | Interface da TARDIS | `ultron/hud/tardis_room/` (sala de controle 3D, rotor, painéis) e `ultron/hud/tardis.py` (ARQUIVO) | `test_tardis_room` (12), `test_tardis` (7); `docs/benchmarks/tardis_room_fase5.json` |
| 8 | Integração JARVIS ↔ TARDIS | `ultron/tardis/` (motor, protocolo, analisadores, memória de projeto) e `ultron/skills/tardis/` | `test_tardis_logic` (33): protocolo, fila, cancelamento, falhas honestas, ações só propostas |
| 9 | Integração com o Noctário | `ultron/noctario/` (protocolo, transportes, serviço, voltas, simulador) e `ultron/skills/noctario/` | `test_noctario` (33) por porta serial virtual, servidor local e simulador |
| 10 | Firmware completo | `firmware/noctario/` (`src/noct_core.*` lógica, `src/main.cpp` ESP32, `platformio.ini`) | núcleo testado no PC (10 grupos), **idêntico ao simulador em 31 071 ciclos**, **compilado para a ESP32 no CI**; não gravado numa placa |
| 11 | Protocolo Bluetooth documentado | `firmware/noctario/PROTOCOLO_NOCT1.md` | os dois lados (C++ e Python) testados contra ele |
| 12 | Painel de telemetria | `ultron/hud/noctario_page.py` (página NOCTÁRIO, F4) | `test_noctario` (painel: SEM CONEXÃO sem dados, SIMULADOR rotulado, pedido × confirmado, F12) |
| 13 | Sistema de comandos | frases → intenções (`ultron/cognition/intent_engine.py`); 120 ações (`ultron/skills/`, referência gerada em **`COMANDOS_JARVIS.md`**); execução, permissões, autorização, verificação e recuperação (`ultron/agent/`) | `test_executor` (12), `test_permissions` (10), `test_verifier` (5), `test_recovery` (7), `test_planner` (8), `test_security` (17) |
| 14 | Configuração de voz | CONFIGURAÇÕES > VOZ E ÁUDIO (voz, timbre, volume, velocidade, legendas, palavras de ativação, microfone, saída); DIAGNÓSTICOS > VOZ (testar, calibrar); `VOICE_DIAGNOSTICS.md` | `test_voice` (27), `test_jarvis_voice` (5): Piper → Vosk real, **sem microfone** |
| 15 | Instalação e dependências | `INSTALL_JARVIS.bat`, `requirements.txt`, `requirements-optional.txt`, `CONFIGURAR_OPENAI.bat`, `ATUALIZAR_JARVIS.bat`; `README_JARVIS.md` §1 | **executados no Windows pelo CI** a partir do ZIP extraído (§5) |
| 16 | Instruções para executar | `README_JARVIS.md` §2 e `START_JARVIS.bat --help` | `test_cli` (6) e o CI no Windows (abre a janela e fecha com `--stop`) |
| 17 | Testes | `tests/`, `TEST_JARVIS.py`, `firmware/noctario/test/host/`, CI em `.github/workflows/jarvis-validation.yml` | **`TEST_REPORT.md`** |
| 18 | Tratamento de erros e diagnóstico | DIAGNÓSTICOS (F3/F7), `DIAGNOSTICO_JARVIS.bat`, `--diagnose`, monitor de saúde (`ultron/health/`), recuperação (`ultron/agent/recovery.py`); `README_JARVIS.md` §12 | `test_failures` (7), `test_transitions` (6), `test_recovery` (7) |
| 19 | Recursos que dependem de serviços ou hardware externos | **`RECURSOS_EXTERNOS.md`** | — |
| 20 | Plano de evolução | **`PLANO_DE_EVOLUCAO.md`** | — |

## 4. Estrutura do projeto

```
utron-jarvis/
├── README.md                       porta de entrada do repositório
├── JARVIS_FINAL.zip                pacote de entrega (tools/build_release.py; sem modelos, .venv ou dados)
├── .github/workflows/              CI: Linux, Windows, firmware
├── SEGURANCA_BACKUP/, README-SEGURANCA.md   cópia de segurança feita antes das Fases 7 e 8
└── ULTRON/                         o programa (nome mantido de propósito: dados, atalhos e pacote `ultron`)
    ├── main.py                     ponto de entrada (python main.py --help)
    ├── *.bat                       instalar, iniciar, atualizar, diagnosticar, configurar a OpenAI
    ├── requirements*.txt           dependências
    ├── TEST_JARVIS.py              testes + relatório do ambiente (--env)
    ├── ultron/                     o pacote Python
    │   ├── core/                   núcleo: Event Bus, estado único, ciclo de vida, workers, agendador
    │   ├── cognition/              contexto, intenção, raciocínio, decisão, planejamento, objetivos
    │   ├── agent/                  execução, permissões, autonomia, verificação, recuperação
    │   ├── skills/                 as 120 ações (COMANDOS_JARVIS.md)
    │   ├── models/                 Ollama, OpenAI (opcional) e roteador de modelos
    │   ├── voice/                  microfone, reconhecimento, palavra de ativação, voz, boca, diagnóstico
    │   ├── hud/                    a plataforma: páginas, avatar/, tardis_room/, painel do Noctário
    │   ├── tardis/                 o módulo lógico da TARDIS
    │   ├── noctario/               protocolo NOCT/1, transportes, serviço, voltas, simulador
    │   ├── secondbrain/, memory/   memória pessoal, lembretes, banco SQLite, backup
    │   ├── perception/, world/     sensores (tela, janelas, processos, rede…) e modelo do mundo
    │   ├── network/, privacy/      rede local passiva; LOCAL MODE e registro de conexões externas
    │   ├── platform/               Windows: início automático, credenciais, instância única, --stop
    │   └── health/, plugins/, personality/, imagination/, audio/, graph/, proactive/, config/
    ├── firmware/noctario/          firmware da ESP32, protocolo e testes no PC
    ├── tests/                      testes automáticos (421)
    ├── tools/                      pacote ZIP, referência de comandos, benchmarks
    ├── plugins/                    exemplos de plugin
    ├── assets/                     modelos locais de fala e voz (fora do ZIP)
    └── docs/                       inventário detalhado, auditoria, medições de desempenho
```

Os seus dados ficam fora da pasta do programa, em `%LOCALAPPDATA%\ULTRON\` (memória, lembretes,
configurações, voltas do Noctário, backups e log) — atualizar ou reinstalar não os toca.

## 5. O que foi testado

| O quê | Onde | Resultado |
|---|---|---|
| Suíte automática (421 testes) | Linux, Python 3.13 e 3.11 (contêiner de desenvolvimento e CI) | aprovada, 0 pulados |
| Suíte automática (421 testes) | Windows Server 2025, Python 3.11 (CI) | aprovada, 0 pulados |
| Pacote ZIP: validado (nada de `.venv`, caches, bancos, configurações, credenciais ou modelos) e testado depois de extraído numa pasta nova | Linux e Windows (CI) | aprovado |
| **Instalação real**: `INSTALL_JARVIS.bat` no ZIP extraído; reinstalação sem apagar nada; início automático intocado; `START_JARVIS.bat` com `--version`, `--status`, `--backup`, `--list-backups`, `--say`; a janela aberta pelo `pythonw` e fechada com `--stop`; `DIAGNOSTICO_JARVIS.bat`; `ATUALIZAR_JARVIS.bat` (com backup antes) | Windows Server 2025 (CI, execução 57) | aprovado |
| **Modo console** pelo `START_JARVIS.bat --console` (conversa, memória, confirmação negada, `sair`) e a interface montada com a **plataforma nativa do Windows e a bandeja do sistema disponível** | Windows Server 2025 (CI, execução 57) | aprovado |
| Núcleo do firmware: testes no PC e comparação ciclo a ciclo com o simulador | Linux (g++) e CI | aprovado (31 071 ciclos idênticos) |
| Firmware compilado para a ESP32 (PlatformIO, `esp32dev`) | CI | aprovado; `firmware.bin` publicado |
| Voz: síntese Piper → reconhecimento Vosk com os modelos do repositório, calibração | Linux | aprovado (áudio gerado, **sem microfone**) |

O que cada teste prova, o que foi real e o que foi simulado, os defeitos que os testes encontraram e
corrigiram e cada execução do CI: **`TEST_REPORT.md`**.

## 6. O que não foi verificado

Não há como verificar daqui — e nada disso é apresentado como funcionando sem a sua confirmação:

* **o Noctário real**: gravar o firmware, Bluetooth, sentido dos motores, ordem física dos sensores,
  cruzamentos na pista, parada física, tempo de volta;
* **o seu microfone e alto-falante**, a privacidade de microfone do Windows e o reconhecimento da sua voz;
* bandeja, notificações e início automático num **Windows de mesa** (o CI roda num Windows Server sem área
  de trabalho interativa);
* **GPU** (a renderização por GPU é opcional; a padrão é por CPU);
* o **Ollama com o modelo real** e a **OpenAI** com uma chave real (os testes usam substitutos locais).

## 7. O que veio do original e o que ainda é pedido a você

* O código do JARVIS original foi auditado inteiro (inventário) e o que tinha se perdido foi recuperado na
  Fase 3. Ficaram de fora, com motivo: os 5 estilos de personalidade (o original travava em "jarvis"), o
  *hand-off* autônomo do Observador e o modo AUTÔNOMO (inalcançáveis no original e contrários à confirmação
  proporcional), o agente visual e o Whisper (nunca integrados no original; estão no plano de evolução).
* Os sketches originais do Noctário (`Noctario_JARVIS(1).ino`, 20/10, e `Nefarious_6_cruzamentos`, 28/10)
  foram recebidos e comparados: pinagem, linha branca, cruzamento ativo em LOW, laço de 100 Hz e o nome
  Bluetooth estão confirmados e são o padrão.
* **O que falta é medida, não material:** a ordem física dos sensores e o sentido dos motores só a bancada
  confirma (passos 5 e 7 de `firmware/noctario/README.md`) — os dois se ajustam pela interface, sem regravar.

## 8. Segurança

O modelo de linguagem não executa código, não acessa arquivos fora das ações registradas e só usa as
ferramentas oferecidas em cada pedido; mover o robô nunca é oferecido a ele. Pastas do sistema, da
inicialização automática e do próprio JARVIS são recusadas antes de qualquer autorização. Texto da tela, de
arquivos e de páginas é dado, nunca instrução. Credenciais só no cofre do sistema; senhas, tokens e dados
financeiros nunca são gravados. Nada de varredura de portas, interceptação, exploração, evasão ou
desativação de Defender, Firewall e UAC. Detalhes: `README_JARVIS.md` §9 e `TEST_REPORT.md` (`test_security`).
