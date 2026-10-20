# JARVIS — Relatório de testes

## 1. Resultado

| Ambiente | Resultado |
|---|---|
| Python 3.13.16, Linux (contêiner, 4 vCPUs), PySide6 6.8.1 offscreen | **197 testes, 197 OK, 0 falhas, 0 pulados** (32 s) |
| Python 3.11.17, mesmo ambiente | **197 testes, 197 OK, 0 falhas, 0 pulados** (31 s) |
| `JARVIS_FINAL.zip` extraído numa pasta nova (sem os modelos de voz, como é distribuído), Python 3.13 | **197 testes, 196 OK, 0 falhas, 1 pulado** — o pulado é o teste de fala real Piper → Vosk, que exige os modelos em `assets/` |

Evolução durante a missão: 131 (auditoria) → 141 (Fase C) → 180 (Fases D/F) → 187 (G) → 194 (H)
→ 197 (I). Nenhum teste foi desativado, pulado ou afrouxado para passar; quando um teste
novo falhou, a causa foi corrigida no código (ex.: falha de rede que escapava do `scan()`)
ou no próprio teste quando a suposição dele estava errada (ex.: título com "senha" é recusado
de propósito).

O teste do pacote extraído encontrou um defeito real que a árvore de desenvolvimento escondia:
o diagnóstico de voz conferia os arquivos do modelo no disco antes de olhar o reconhecedor já
carregado e em uso, e acusava "modelo ausente" com a escuta funcionando. A ordem foi corrigida
(`ultron/voice/diagnostics.py`) e o caso ganhou um teste próprio, que falha sem a correção.

## 2. Como rodar

```
python TEST_JARVIS.py            todos os testes + relatório do ambiente
python TEST_JARVIS.py --quick    sem os testes lentos
python TEST_JARVIS.py --env      só o relatório do ambiente (componentes ausentes)
python -m unittest discover -s tests
```

Os testes usam pastas temporárias (`JARVIS_DATA_DIR`/`ULTRON_DATA_DIR` apontam para elas antes
de qualquer import): **nenhum dado real do usuário é lido ou alterado**. O Ollama é simulado
por um servidor HTTP local (`tests/fake_ollama.py`). A interface roda com
`QT_QPA_PLATFORM=offscreen`.

## 3. O que cada módulo cobre

| Módulo | Cobertura |
|---|---|
| `test_core.py` | identidade e personalidade JARVIS, ciclo de vida (falha de componente isolada), workers, cancelamento, configurações e validação |
| `test_event_bus.py` | entrega, isolamento de assinante com erro, fila cheia com descarte contado e aviso agregado |
| `test_executor.py` | executor, autonomia por risco/origem/nível, autorização (sim/não/expiração), pré-aprovação exata e única, timeout, erros classificados, falha nunca vira sucesso, **autorização permanente escopada** (escopo exato, expiração, nunca para sensível/crítico/irreversível/proativo, arquivo adulterado ignorado, persistência, revogação) |
| `test_planner.py` | intenções em português (incluindo memória pessoal, conflitos, exportação, backup, TARDIS, autonomia), objetivos persistentes, planejamento e preparação real de projeto |
| `test_memory.py`, `test_world_model.py` | memória (fatos, episódios, procedimentos, preferências, segredos recusados), World Model |
| `test_second_brain.py` | CRUD completo, lixeira/restauração/exclusão definitiva, busca sem acentos e filtros, segredos recusados, **data ambígua pergunta e não grava**, hoje/atrasados, **persistência após reinício**, aviso antecipado e no horário sem duplicata, repetição limitada, **lembrete perdido com o programa fechado avisado uma vez após reinício**, rotina diária e recuperação sem rajada, adiar/concluir, horário de silêncio, agendador sem IA, captura explícita/automática (hipóteses e dados sensíveis recusados), **conflitos de agenda**, exportação JSON/CSV sem sobrescrever, **backup/rotação/restauração** com verificação de integridade |
| `test_tardis.py` | os dois hubs com o núcleo real: regiões com dados reais (incluindo conflito), **evento real chega aos dois hubs**, voltar ao CORE preserva o estado do TARDIS (relógio parado quando oculto), ações pelo núcleo verificadas, perfis aplicados aos dois hubs, painel de Sistemas, **encerramento sem threads restantes** |
| `test_hud.py` | malha neural, câmera, profundidade, inicialização guiada por componentes reais, anel de subsistemas, módulos só com dados reais, grafo, repouso calmo, **identidade dos estados** (halo pelo nível real do microfone, leitura velha ignorada, anéis pela voz, ondas só por análise real, memória em azul, arco do plano = plano real, contorno de erro), renderização e orbe |
| `test_performance.py` | perfis ordenados e limitados pelo `hud_fps`, cadência de fundo, verificação de saúde de rotina não anima, mudança real anima, giro de repouso lento, assinatura de saúde, fluxo do TARDIS em repouso × atividade, só eventos reais põem o TARDIS em movimento, **percepção adaptativa à ausência do usuário**, cache da camada estrutural do TARDIS |
| `test_voice.py` | formas da palavra de ativação, nomes só no início, formas fracas só com comando, calibração, continuação, eco/autoescuta, *barge-in*, pausa, contadores, silêncio absoluto, texto injetado (diagnóstico), falhas do microfone com nova tentativa, **reamostragem**, escolha de microfone, ausência das bibliotecas de áudio, perfil de voz (inteligibilidade), mixer e sons ligados a eventos reais, e **fala sintetizada real (Piper) reconhecida pelo Vosk real** através do pipeline (pulado se os modelos não estiverem em `assets/`) |
| `test_jarvis_voice.py` | migração de configurações (ULTRON → JARVIS) com cópia de segurança, **diagnóstico de voz de ponta a ponta** (8 etapas), modelo avaliado pelo reconhecedor em uso (não pelos arquivos no disco), microfone ausente, **voz e texto ao mesmo tempo** |
| `test_network.py` | escopo só privado, limites de sub-rede, tabelas de vizinhos (Windows/Linux, IPv6), SSDP restrito ao mesmo IP privado, inventário (estados observados, leitura passiva, dados do usuário preservados, outra rede), campos desconhecidos não inventados, exportação, **categorias de observação, gateway, administração e "descobrir ≠ administrar"** |
| `test_integrity.py` | **todos os 146 módulos importam**, código compila, skills obrigatórias registradas, **falha de varredura de rede registrada** (e trava liberada), **`--stop` com processo real** (saída normal, PID limpo) |
| `test_recovery.py`, `test_verifier.py`, `test_model_router.py`, `test_imagination.py`, `test_plugins.py` | recuperação limitada, verificação independente, roteamento de modelos, imaginação, plugins (falha isolada, permissões) |

## 4. Real × simulado

**Real neste ambiente:** núcleo completo, banco SQLite em arquivo, Event Bus, workers e
agendador, lembretes com relógio simulado (mas banco e lógica reais), os dois hubs Qt
renderizando (offscreen), síntese Piper → reconhecimento Vosk com os modelos reais (áudio
gerado, sem microfone), processo filho real para `--stop`, importação de todos os módulos.

**Simulado (e marcado como tal nos testes):** microfone (`FakeStream`), resultado do
reconhecimento (`ScriptedSTT`), síntese e saída de áudio (`FakeSynth`, `FakeOutput`), Ollama
(`fake_ollama.py`), varredura de rede (resultados fixos; nenhuma rede física é varrida),
falha de adaptador de rede (injetada).

**Não verificável aqui (precisa do Windows real):** microfone físico e privacidade do
Windows, reconhecimento da sua voz, reprodução de áudio, notificações da bandeja do Windows,
`winreg` (início automático), UI Automation/pywinauto, GPU, tela real em alta resolução, os
scripts `.bat` (validados estaticamente: blocos balanceados, parênteses escapados, ASCII
com CRLF). Roteiro de validação no Windows: `DIAGNOSTICO_JARVIS.bat`,
`START_JARVIS.bat --voice-test`, abrir o TARDIS (F2), criar um lembrete para 2 minutos e
fechar/reabrir o JARVIS antes do horário.

## 5. Verificações estáticas

| Verificação | Resultado |
|---|---|
| `pyflakes ultron tests tools TEST_JARVIS.py TEST_ULTRON.py main.py` | limpo |
| `compileall` (pacote, testes, ferramentas) | OK |
| Importação de todos os módulos do pacote (146) | OK (`test_integrity`) |
| Scripts `.bat` | ASCII + CRLF, blocos balanceados, parênteses escapados dentro de blocos (verificação estática; não há `cmd.exe` neste ambiente) |
| Pacote `JARVIS_FINAL.zip` | validado por `tools/build_release.py --check` (conteúdo obrigatório presente; sem `.venv`, caches, bancos, configurações, logs ou modelos grandes) e testado depois de extraído numa pasta nova: 197 testes, 0 falhas, 1 pulado (fala real sem os modelos) |
