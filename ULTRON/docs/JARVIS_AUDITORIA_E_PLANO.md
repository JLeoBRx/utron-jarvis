# JARVIS — Auditoria inicial (Fase A) e plano priorizado (Fase B)

Registro do estado REAL do repositório no início da transformação ULTRON → JARVIS
(commit `6f73c2b` + HUB 2 em andamento), com o que foi medido e reproduzido. Nada aqui é
estimado: cada item cita o comando ou a medição que o comprova.

## 1. Estrutura e caminho real de execução

```
main.py → ultron.app.main()
  ├─ --diagnose  → NeuralCore.boot() → core.diagnose() → relatório e saída
  ├─ --headless / --say → NeuralCore + console (RESPONSE_READY impresso)
  └─ padrão      → single_instance.acquire() → NeuralCore → hud.run_hud(core)
                     HudController (ponte Event Bus → Qt, relógio adaptativo, bandeja)
                       ├─ HUB 1: HudWindow + BrainView + NeuralScene + OrbWindow
                       └─ HUB 2: SecondBrainWindow (sob demanda; estava em construção)
                     core.boot() em thread própria; app.aboutToQuit → core.shutdown()
```

O pacote Python continua `ultron` (149 módulos). O projeto JARVIS original (antes da
transformação em ULTRON) está no histórico (`git show 53e5a31:JARVIS/...`).

### Mapa dos subsistemas (implementação em produção · duplicações · órfãos)

| Responsabilidade | Implementação usada | Observação |
|---|---|---|
| Ponto de entrada | `main.py` → `ultron/app.py` | único |
| Interface principal | `hud/controller.py`, `window.py`, `brain_view.py`, `scene.py`, `orb.py` | única |
| Segunda interface | `hud/second_hub.py` | painel de abas; ainda não espacial |
| Neural Core | `core/neural_core.py` | entrada única de pedidos (`submit`) e de respostas |
| Event Bus | `core/event_bus.py` | único; fila limitada |
| Estado global | `core/state.py` (`ULTRON_STATE`, contrato de atividade) | único |
| Memória | `memory/system.py` (trabalho, episódica, semântica, procedural, grafo) + `secondbrain/` | um só banco |
| Banco de dados | `memory/store.py` `Database` → `%LOCALAPPDATA%\ULTRON\ultron.sqlite3`, migrações v1–v3 | único (sem banco paralelo) |
| Objetivos | `cognition/goal_manager.py` | único |
| Planner | `cognition/planner_engine.py` | único |
| Registry de skills | `skills/registry.py` (96 skills após o Second Brain) | único; nomes proibidos (shell, eval…) |
| Executor | `agent/execution.py` + `agent/autonomy.py` (autorização central) | único |
| Verificação | `agent/verification.py` + `verify()` de cada skill | único |
| Recuperação | `agent/recovery.py` (máx. 3 por objetivo) | único |
| STT | `voice/stt.py` (Vosk) + `voice/wake_word.py` + `voice/processor.py` | único dono do microfone |
| TTS | `voice/tts.py` (Piper → SAPI) + `voice/audio.py` (mixer) | único |
| Notificações | `secondbrain/reminders.py` (central + eventos) + bandeja no `controller.py` | único |
| Configurações | `config/settings.py` (`SettingsManager`, validação) + `config/profiles.py` | único |
| Rede | `network/` (interfaces, descoberta, inventário, SSDP opcional) + sensor `perception/network.py` | sensor só lê o inventário |
| Temas | `hud/theme.py` (paleta dourada) | 17 cores ainda fixas fora do tema |

Órfãos: nenhum módulo sem uso (detecção por importação); `voice/calibrate.py` é usado como
comando (`python -m ultron.voice.calibrate`). Sem duplicação de banco, estado ou microfone:
`perception/microphone.py` NÃO abre o microfone (lê `voice.mic_probe()`).

## 2. Testes e verificações iniciais

| Verificação | Resultado |
|---|---|
| `python -m unittest discover -s tests` (Python 3.13) | 131 testes, OK (18,6 s) |
| Mesma suíte em Python 3.11.17 (`ULTRON_TEST_QUICK=1`) | 131 testes, OK, 4 pulados (lentos) |
| `pyflakes ultron tests tools` | limpo |
| `compileall` | OK |
| `main.py --diagnose` (isolado) | 19 componentes RUNNING; voz informada como "iniciando" |
| HUD real offscreen, 25 s (`main.py` com `QT_QPA_PLATFORM=offscreen`) | sem exceções no log; nenhuma thread restante |

## 3. Problemas reproduzíveis encontrados

1. **Palavra de ativação** (crítico): o reconhecimento procura "ultron". Medição com a voz
   Piper pt-BR dizendo "Jarvis…" e os dois modelos Vosk instalados:
   * modelo pequeno: "aviso que horas são", "e já vi anote essa ideia", "abra o navegador"
     (palavra perdida);
   * modelo grande: "aves", "aviso", "davis abra o navegador", "a vez quais são…";
   * vocabulário: o grande contém `jarvis` e `jarbas`; o pequeno não contém `jarvis`.
   * gramática restrita (`["jarvis", "[unk]"]`): no modelo grande TODA frase vira "jarvis"
     (22/22 falsos positivos); no pequeno nada é aceito (0/14). **Descartada.**
   * conclusão: detecção por transcrição com formas fortes (próximas de "jarvis") e fracas
     (confusões comuns, só válidas seguidas de comando reconhecido) + calibração com a voz
     real do usuário.
2. **Áudio sem alternativa para o microfone** (crítico): a captura usa só PyAudio. O
   JARVIS original foi executado em Python 3.13/3.14 (os `__pycache__` do histórico mostram
   `cpython-313`/`cpython-314`), versões para as quais o PyAudio pode não ter pacote pronto
   no Windows; sem ele não há microfone NEM saída de áudio, e o motivo só aparece na saúde.
   `sounddevice` (com PortAudio embutido) estava como opcional e só para saída.
3. **Diagnóstico de voz insuficiente**: `--diagnose` imprime "STT — · microfone —" porque
   consulta antes de o modelo de fala terminar de carregar; não há lista de dispositivos,
   teste de captura, nem verificação de entrega ao núcleo ou de reprodução.
4. **Seleção de microfone**: só por `settings.json` (`mic_name`/`mic_index`); sem lista nem
   escolha na interface.
5. **Identidade**: 66 arquivos com "ULTRON"; a personalidade PROÍBE "JARVIS"
   (`FORBIDDEN_IDENTITIES`); perfil de voz robótico (altura 0,86, rouquidão 0,22, dobra
   sintética) — contrário a "natural e inteligível"; tema único `ultron-gold`; entrada de
   inicialização automática `ULTRON` no registro (não será alterada sem pedido do usuário).
6. **Event Bus**: cada evento descartado em sobrecarga gera um aviso no log (milhares de
   linhas na suíte de testes) — sob saturação real isso vira escrita contínua em disco.
7. **Desempenho (antes, mesmo harness `tools/benchmark.py`, 4 CPUs, offscreen)**:
   * repouso estável: CPU 42,7 %, 34 pinturas/s, `paintEvent` 342 ms por segundo;
     a rotação lenta do cérebro conta como "movimento" e mantém o teto de quadros;
   * atividade: quadro médio 15,6 ms, p95 24,9 ms (217 de 600 quadros > 16 ms);
   * núcleo ocupado: atraso do laço da interface p95 23,8 ms, máx. 45,9 ms.
8. **Segundo HUB**: funcional como painel de abas (consulta, criação, edição, exclusão,
   autorização), mas não é a interface espacial pedida.
9. Faltam na memória pessoal: detecção de compromissos conflitantes, cópia de segurança e
   exportação dos registros, filtros por prioridade e data na interface.

## 4. Plano priorizado (Fase B)

Preservar o que funciona (núcleo, Event Bus, estado, executor, verificação, memória, Second
Brain, rede) e mudar só o necessário.

| Prioridade | Item | Estratégia |
|---|---|---|
| P0 | Voz | backend de áudio PyAudio → sounddevice (entrada e saída); `sounddevice` obrigatório; formas "jarvis" medidas + calibração; diagnóstico em 8 etapas (interface e console); lista e escolha de microfone; início/parada ordenados; proteção contra autoescuta verificada por teste |
| P0 | Identidade | nome JARVIS em tudo que o usuário vê; personalidade nova; migração das palavras de ativação/tema padrão sem tocar em configurações personalizadas; pacote `ultron`, banco e pasta de dados preservados |
| P0 | Event Bus | aviso de descarte limitado por tempo (contagem agregada) |
| P1 | Tema | tokens azul/ciano centralizados e cores por estado (repouso, escuta, percepção, planejamento, execução, memória, imaginação, fala, erro) |
| P1 | TARDIS | segundo HUB espacial (câmara central, anéis, portais, partículas, regiões = dados reais) com painel de consulta/edição; volta ao HUB principal mantendo o estado |
| P1 | Desempenho | repouso real em cadência econômica; perfis Econômico/Equilibrado/Alto/Cinematográfico; orçamento de pintura nos dois HUBs; medir de novo |
| P1 | Memória | conflitos de horário, backup/exportação, filtros |
| P1 | Rede | visualização no HUB principal com gateway, interface, origem e confiabilidade |
| P2 | Autonomia | autorização permanente ESCOPADA (ação + recurso + validade), nunca para ações críticas/sensíveis |
| P2 | Entrega | documentação, scripts Windows, modo diagnóstico, testes novos, ZIP validado |
