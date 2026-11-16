# 11 TESTES E VALIDAÇÃO

A validação do SAFRA combina dois instrumentos complementares: uma **suíte de testes automatizados**, que
verifica o comportamento do sistema a cada alteração, e **protocolos experimentais**, que medem as métricas
definidas nos requisitos não funcionais. Este capítulo descreve os dois; os resultados estão no Capítulo 12.

## 11.1 Estratégia

A estratégia segue a definição de Myers, Sandler e Badgett (2011): testar é tentar encontrar erros. Por isso,
além de verificar que as funções funcionam, a suíte tenta quebrar o sistema — injeta falhas (banco danificado,
disco cheio, modelo que cai no meio da resposta, sensor com erro), envia entradas inválidas e tenta executar
ações proibidas. Três regras valem para todos os testes:

1. **Nenhum dado real do usuário é lido ou alterado.** A pasta de dados aponta para uma pasta temporária antes
   de qualquer importação do pacote.
2. **Dublês são declarados.** O servidor do Ollama e o da OpenAI são substituídos por servidores HTTP locais
   que seguem o mesmo protocolo; o microfone, a Lixeira e o cofre de credenciais têm versões falsas. Os testes
   dizem o que é real e o que é simulado.
3. **Componentes reais sempre que possível.** O núcleo, o banco SQLite em arquivo, o Event Bus, os *workers*,
   a interface Qt (em modo *offscreen*), a síntese Piper e o reconhecimento Vosk com os modelos do repositório
   e o servidor da WEB ORB rodam de verdade nos testes.

## 11.2 Composição da suíte

A suíte tem 39 módulos de teste e 475 casos (versão desta fase). O Quadro 11.1 os agrupa pelos tipos de teste
pedidos para este trabalho.

**Quadro 11.1 — Testes automatizados por tipo.**

| Tipo | Módulos (casos) | O que verificam |
|---|---|---|
| Unitários | `test_event_bus` (7), `test_lipsync` (9), `test_voice_prosody` (10), `test_planner` (8), `test_verifier` (5), `test_recovery` (7), `test_world_model` (5), `test_tardis_sfx` (5), `test_imagination` (6) | componentes isolados: fila de eventos, trilha labial, prosódia, planejamento, verificação, recuperação |
| Integração com o núcleo real | `test_core` (15), `test_executor` (12), `test_permissions` (10), `test_activity` (7), `test_memory` (9), `test_second_brain` (25), `test_intelligence` (22), `test_model_router` (9), `test_openai_provider` (6), `test_original_recovery` (22), `test_tardis_logic` (30), `test_network` (14), `test_plugins` (4) | pedidos atravessando intenção, orquestração, execução, memória e resposta |
| Inicialização e linha de comando | `test_startup` (10), `test_cli` (7), `test_integrity` (8) | processos reais: janela, bandeja, segunda instância, `--stop`, modo console, `--diagnose`, backup, exportação |
| Interface | `test_platform` (22), `test_hud` (22), `test_avatar` (12), `test_scene3d` (24), `test_tardis_room` (12), `test_tardis` (7), `test_performance` (10), `test_ultron_protocol` (21) | páginas, atalhos, conversa, estados visuais, cena 3D real (QtWebEngine) e reserva 2D, identidade e restauração |
| Comunicação | `test_web_orb` (7), `test_scene3d` (ponte Python ↔ página) | gateway real, agente de saída, pareamento, sessões, CSRF, origem; lista branca da ponte 3D |
| Segurança | `test_security` (17), `test_permissions`, `test_executor` | código sem shell/`eval`/`exec`/`pickle`; alvos protegidos recusados antes da autorização; ferramentas não oferecidas ao modelo; conteúdo de tela como dado; credenciais só no cofre |
| Falhas e transições | `test_failures` (7), `test_transitions` (6) | banco danificado e somente leitura, backup interrompido, modelo que cai, sensor com erro; sequência real de estados até o repouso |
| Voz | `test_voice` (30), `test_jarvis_voice` (6) | detector de ativação ("Safra" e "Jarvis"), calibração com Piper → Vosk reais, autoescuta, migração das configurações |
| Desempenho | `test_performance` (10) | cadência de quadros por perfil, ausência de E/S na thread da interface, custo limitado por perfil |
| Estabilidade | `test_tardis` (encerramento sem threads restantes), `test_core` | ciclo de vida completo; ver também PV-07 |

## 11.3 Integração contínua

O fluxo `jarvis-validation.yml`, no GitHub Actions, executa a cada disparo três trabalhos:

* **Linux, Python 3.11 e 3.13:** instala as bibliotecas do Qt, executa a suíte completa, executa a **cena 3D
  real** (QtWebEngine com WebGL por software) sob um servidor X virtual, faz as verificações estáticas
  (`compileall`, `pyflakes`), gera o pacote ZIP e testa o pacote extraído numa pasta nova;
* **Windows (Python 3.11):** executa a suíte, as verificações estáticas, gera e testa o pacote e **instala o
  sistema a partir do ZIP extraído** com o `INSTALL_JARVIS.bat`, executando os scripts documentados (console,
  diagnóstico, `--status`, `--stop`, início automático).

O CI do Windows roda num servidor sem microfone, alto-falante, GPU ou área de trabalho interativa: prova o
Python, o Qt, o SQLite, os processos e os caminhos do Windows, mas **não** o hardware de um computador pessoal.

## 11.4 Protocolos experimentais

Os requisitos não funcionais são avaliados por sete protocolos (Quadro 11.2), descritos em detalhe no
Apêndice A. Cada um tem um instrumento em `tools/experimentos/`, que grava os dados brutos em JSON com o
ambiente e a lista do que foi real e do que foi simulado.

**Quadro 11.2 — Protocolos de validação.**

| Protocolo | Métrica | Meta | Ambiente C (executado nesta fase) | Ambiente R (previsto) |
|---|---|---|---|---|
| PV-01 Ativação por voz | taxa de ativação; ativações indevidas; WER | ≥ 90 %; ≤ 2 % | voz sintética, 2 modelos, 3 velocidades, 3 ruídos, 2 repetições | voz humana, microfone real |
| PV-02 Resposta | tempo pedido → resposta | p95 ≤ 1 s (regras); p50 ≤ 8 s (modelo) | núcleo real, inferência simulada de 0 ms | modelo real |
| PV-03 Memória | recall@1, recall@3; recuperação indevida | recall@3 ≥ 80 % | conjunto sintético de 20 fatos | o mesmo |
| PV-04 Interface | montagem; cena pronta; quadros/s | ≤ 15 s; ≤ 5 s; ≥ 30 q/s | verificação do instrumento (WebGL por software) | GPU real |
| PV-05 Sincronização | defasagem forma × áudio; silêncio; início das palavras; atraso de apresentação | ITU-R BT.1359 | cálculo da trilha (etapa A) | gravação em vídeo (etapa B) |
| PV-06 Segurança | bloqueio de ações indevidas; controles | 100 %; 100 % | 11 tentativas, 4 controles | o mesmo |
| PV-07 Estabilidade | falhas; memória (MB/h); threads restantes | 8 h; ≤ 20 MB/h; 0 | 30 minutos | 8 horas, modelo real |

## 11.5 Critérios de aceitação do protótipo

O protótipo será considerado aceito para a defesa quando: (CA01) a suíte estiver aprovada no CI em Linux e
Windows no commit entregue; (CA02) todos os requisitos essenciais estiverem atendidos ou com a limitação
documentada; (CA03) os protocolos tiverem sido executados no computador de referência, com os dados brutos
versionados; (CA04) cada meta tiver um resultado registrado — atingida, não atingida ou não medida, com o motivo;
(CA05) a instalação a partir do pacote funcionar num Windows limpo seguindo apenas o manual.
