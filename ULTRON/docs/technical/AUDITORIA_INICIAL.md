# Auditoria inicial do projeto — transformação JARVIS → SAFRA

| Campo | Valor |
|---|---|
| Projeto | SAFRA (identidade anterior: JARVIS; antes dela, ULTRON) |
| Repositório | `JLeoBRx/utron-jarvis` |
| Branch auditada | `claude/adoring-brahmagupta-vcejpt` |
| Commit de referência (estado inicial) | `bf070f6` — 2026-11-03 ("Aprimoramento 6: JARVIS WEB ORB …") |
| Data da auditoria | 2026-11-11 |
| Método | leitura do código e da documentação, histórico do Git, execução da suíte de testes, consulta aos relatórios de CI |

Esta auditoria descreve o projeto **antes** de qualquer alteração da fase SAFRA. Nada foi apagado,
renomeado ou reescrito para produzi-la. Quando uma afirmação depende de execução, a evidência está
indicada; quando depende só da leitura do código, isso também está dito.

---

## 1. Estrutura do repositório

```text
utron-jarvis/
├── .github/workflows/jarvis-validation.yml   CI (Linux 3.11/3.13, cena 3D real, Windows + instalação do ZIP)
├── README.md, README-SEGURANCA.md            apresentação e aviso de segurança
├── SEGURANCA_BACKUP/                         manifesto do snapshot de segurança (feito pelo autor em 29/10)
├── JARVIS_FINAL.zip                          pacote de entrega antigo (versionado; desatualizado em relação ao HEAD)
└── ULTRON/                                   a aplicação (o nome da pasta é da primeira identidade)
    ├── main.py, TEST_JARVIS.py, TEST_ULTRON.py
    ├── *.bat                                 instalar, iniciar, atualizar, diagnosticar (Windows)
    ├── requirements*.txt
    ├── ultron/                               pacote Python (206 módulos, 46 244 linhas)
    │   ├── core/          núcleo: NeuralCore, Event Bus, estado, ciclo de vida, workers, orquestrador, métricas
    │   ├── cognition/     intenção, contexto, decisão, planejamento, raciocínio, objetivos, procedência
    │   ├── agent/         execução, autonomia/autorização, permissões, verificação, recuperação
    │   ├── skills/        102 ações registradas (aplicativos, arquivos, janelas, navegador, sistema, memória…)
    │   ├── memory/        banco SQLite único, memórias de trabalho/episódica/semântica/procedural, backup
    │   ├── secondbrain/   memória pessoal: registros, lembretes, consultas, captura
    │   ├── graph/         grafo de conceitos persistente
    │   ├── models/        roteador de modelos, Ollama (local), OpenAI (opcional), perfis, consumo
    │   ├── voice/         áudio, reconhecimento (Vosk), ativação, síntese (Piper/SAPI), prosódia, DSP, sincronização labial
    │   ├── audio/         sons da interface e da TARDIS (sintetizados)
    │   ├── hud/           interface Qt (plataforma, páginas, tema, ORBE, configurações) e a cena 3D (Three.js)
    │   ├── tardis/        motor de tarefas da TARDIS (analisadores determinísticos)
    │   ├── perception/    sensores (janelas, processos, sistema, tela, OCR, visão, arquivos, rede, dispositivos)
    │   ├── network/       inventário passivo da rede local
    │   ├── personality/   identidade, persona (JARVIS/ULTRON), estilo de resposta, perfil de voz
    │   ├── remote/        agente de saída para a WEB ORB
    │   ├── platform/, config/, health/, privacy/, proactive/, imagination/, plugins/, world/
    ├── gateway/                              serviço separado da WEB ORB (aiohttp, Docker, Caddy)
    ├── tests/                                39 arquivos de teste (10 568 linhas), dublês de Ollama/OpenAI
    ├── tools/                                benchmarks, gerador de tokens, gerador do pacote, gerador de comandos
    ├── assets/                               modelos Vosk (254 MB) e voz Piper (61 MB), versionados
    └── docs/                                 benchmarks (JSON), capturas, inventário do original
```

### 1.1 Tamanho e composição

| Item | Quantidade | Como foi medido |
|---|---|---|
| Módulos Python do pacote `ultron` | 206 arquivos, 46 244 linhas | `find ultron -name '*.py'` + `wc -l` |
| Maiores subsistemas (linhas) | interface `hud` 14 607; `skills` 4 560; `core` 3 312; `voice` 3 255; `secondbrain` 2 663 | idem, por pasta |
| Cena 3D (JavaScript próprio, sem a biblioteca) | 13 arquivos, 4 305 linhas | `wc -l web/js/*.js` |
| Gateway da WEB ORB (Python + JS) | ~1 070 linhas | idem |
| Testes | 39 arquivos `test_*.py`, 10 568 linhas, **471 casos** | `TEST_JARVIS.py` (HEAD `bf070f6`) |
| Ações (skills) registradas | 102 | `COMANDOS_JARVIS.md` (gerado do registro) |
| Tipos de evento do Event Bus | 89 | `ultron/core/events.py` |
| Tabelas do banco | 27 + 1 índice de texto completo FTS5 (esquema v7) | `CREATE TABLE` em `memory/store.py`, `secondbrain/store.py`, `tardis/store.py`, `models/usage.py` |
| Arquivos versionados | 409 | `git ls-files` |
| Marcadores `TODO/FIXME/XXX` no pacote | 3 | `grep` |

## 2. Tecnologias e dependências

| Camada | Tecnologia | Papel | Obrigatória? |
|---|---|---|---|
| Linguagem | Python 3.11 (recomendado) e 3.13 (testado) | todo o núcleo | sim |
| Interface | PySide6 6.8 (Qt Widgets) | janela, páginas, bandeja, ORBE | não: sem ela há o modo console |
| Cena 3D | QtWebEngine + Three.js r170 (MIT, embutido) + WebGL 2 | holograma, ORBE 3D, TARDIS | não: há reserva 2D |
| Modelo de linguagem | Ollama local (`qwen2.5:3b`, visão `qwen2.5vl:3b`) | respostas, planejamento, ferramentas | não: respostas determinísticas continuam |
| Modelo na nuvem | OpenAI (Responses API) | opcional, com autorização e limite de gasto | não |
| Reconhecimento de fala | Vosk (Kaldi) — modelos `small-pt-0.3` e `pt-fb-v0.1.1` | fala → texto, offline | não |
| Síntese de fala | Piper (`pt_BR-faber-medium`, VITS) + SAPI (pyttsx3) como reserva | texto → fala, offline | não |
| Áudio | sounddevice (PortAudio), PyAudio opcional | microfone e saída | não |
| Armazenamento | SQLite em modo WAL, migrações versionadas, FTS5 | memória, lembretes, grafo, auditoria | sim |
| Cálculo | NumPy | DSP da voz, sincronização labial, geometria | sim |
| Sistema (Windows) | psutil, pywin32, pywinauto, pycaw, mss, Pillow, pyautogui, send2trash, keyring | percepção e ações no Windows | por recurso |
| Rede remota | aiohttp (gateway), websockets (agente), segno (QR) | WEB ORB | não |
| Implantação do gateway | Docker, Docker Compose, Caddy (HTTPS automático) | publicação | não |
| Qualidade | unittest/pytest, pyflakes, compileall, GitHub Actions | testes e CI | — |

## 3. Arquitetura identificada

O detalhamento, com diagramas, está em [`ARQUITETURA.md`](ARQUITETURA.md). Em resumo:

* **Núcleo único.** `NeuralCore` (`ultron/core/neural_core.py`) constrói e liga todos os componentes; a
  ordem de início e parada é controlada pelo `LifecycleManager`. Toda entrada (texto, voz, interface, WEB
  ORB) entra por `submit()` ou `run_skill()`.
* **Comunicação por eventos.** Um Event Bus com fila limitada distribui 89 tipos de evento; um estado
  global estruturado (`StateStore`) publica só os campos alterados. A interface é **leitora** desses
  dois canais — não tem estado próprio do sistema.
* **Fluxo cognitivo.** `Orchestrator`: comando → intenção → decisão → objetivo → plano → skill → execução
  → verificação → (recuperação) → resultado → memória.
* **Execução controlada.** Um único `ExecutionEngine`; política de autonomia (risco × reversibilidade ×
  origem), permissões por categoria (consultar, configurar, executar programas, arquivos, apagar dados) e
  um gerenciador de autorizações com uma pendência por vez.
* **Persistência única.** Um banco SQLite (`%LOCALAPPDATA%\ULTRON\ultron.sqlite3`) com migrações
  idempotentes; backup pela API do SQLite.
* **Concorrência.** Workers nomeados por fila (`ai`, `voice`, `memory`, `actions`…), agendador,
  cancelamento cooperativo; a thread da interface não faz E/S.

## 4. Banco de dados e memória

* **Tabelas (27 + índice FTS5 `sb_fts`):** `episodes`, `facts`, `preferences`, `procedures`, `goals`, `graph_nodes`,
  `graph_edges`, `sb_records`, `sb_reminders`, `sb_fired`, `sb_notifications`, `sb_history`,
  `sb_relations`, `session_notes`, `project_notes`, `tardis_tasks`, `activity`, `audit`, `automations`,
  `creations`, `images`, `model_usage`, `network_devices`, `meta`, `schema_version` e duas tabelas
  inertes de um módulo removido (§9).
* **Modelos de memória:** trabalho (volátil), episódica (o que foi tentado e o resultado), semântica
  (fatos), procedural (como fazer), preferências, memória pessoal (Second Brain: compromissos,
  lembretes, anotações) e grafo de conceitos.
* **Salvaguardas verificadas por teste:** textos com aparência de segredo (senha, token, cartão) são
  recusados antes de gravar; banco danificado interrompe o início com mensagem clara sem tocar no
  arquivo; banco somente leitura não derruba a conversa.

## 5. Interfaces

| Interface | Implementação | Situação |
|---|---|---|
| Plataforma desktop | Qt: páginas JARVIS (F1), TARDIS (F2), ATIVIDADES (F5), CONFIGURAÇÕES (F6), DIAGNÓSTICOS (F3/F7) | testada em modo *offscreen* e no CI do Windows |
| Cena 3D | Three.js em QtWebEngine: holograma de corpo inteiro com esqueleto e *skinning* na GPU, ORBE 3D, sala da TARDIS, cabine externa | verificada com WebGL por software (llvmpipe/SwiftShader); **GPU real não verificada** |
| ORBE compacta | janela flutuante que reaproveita a mesma cena | testada |
| Modo console | `START_JARVIS.bat --console` | testado no CI do Windows |
| Bandeja do sistema | `QSystemTrayIcon` | código presente; notificação nativa do Windows não verificada em hardware |
| WEB ORB | gateway + site + agente de saída | verificada localmente de ponta a ponta; **não publicada** |

## 6. Testes e integração contínua

* `TEST_JARVIS.py` executa 39 módulos de teste; resultado no HEAD `bf070f6`: **471 testes, 0 falhas,
  1 pulado** em Python 3.13 e 3.11 (registro da sessão de 2026-11-03), repetido nesta auditoria
  (ver `TESTES.md`).
* Dublês declarados: Ollama e OpenAI (servidores HTTP locais), microfone, Lixeira, cofre de credenciais,
  falhas injetadas (disco cheio, banco somente leitura). Componentes **reais** nos testes: núcleo, SQLite
  em arquivo, Event Bus, workers, Qt *offscreen*, Piper → Vosk com os modelos do repositório, gateway
  aiohttp real.
* CI (`jarvis-validation.yml`): Linux 3.11/3.13 (suíte, cena 3D real sob Xvfb, verificações estáticas,
  pacote ZIP extraído e testado) e Windows (suíte, estáticos, pacote, instalação pelo `INSTALL_JARVIS.bat`
  e scripts documentados). Última execução: [61](https://github.com/JLeoBRx/utron-jarvis/actions/runs/41648219272),
  `bf070f6`, **aprovada**. A anterior (60, `75e33aa`) falhou por um import sem uso (pyflakes), corrigido.
* Cobertura de linhas medida pela última vez na Fase 7 (2026-11-01): **75 %**. Não foi remedida depois
  dos acréscimos de novembro.

## 7. Scripts de inicialização, instalação e atualização

| Script | Função |
|---|---|
| `INSTALL_JARVIS.bat` | instala Python 3.11 e dependências num `.venv`, oferece o Ollama; não apaga dados |
| `START_JARVIS.bat` | inicia a interface; `--console`, `--stop`, `--status`, `--diagnose`, `--voice-test` |
| `ATUALIZAR_JARVIS.bat` | atualiza dependências preservando dados |
| `DIAGNOSTICO_JARVIS.bat` | diagnóstico por etapas (componentes, saúde, voz) |
| `CONFIGURAR_OPENAI.bat` | guarda a chave no Gerenciador de Credenciais do Windows |
| `INSTALL_ULTRON.bat`, `START_ULTRON.bat` | atalhos da identidade anterior, mantidos por compatibilidade |

## 8. Histórico e evolução (fonte: `git log`)

| Período | Commits | Marco |
|---|---|---|
| 07/10/2026 | `53e5a31` | **JARVIS original** do autor: 131 arquivos Python (26 196 linhas, 38 % em cópias de backup), 46 documentos de fase. O caminho principal (`START_JARVIS.bat`) quebrava antes de abrir a interface; o caminho que funcionava era `Abrir_JARVIS.bat` → `jarvis_hud.py` |
| 08/10 | `e0b6769`…`910c922` | Reconstrução como **ULTRON**: núcleo neural, cognição, agente, voz, HUD; o original sai da árvore (fica no histórico) |
| 12/10 | `9957499`…`6f73c2b` | desempenho medido, Second Brain, inteligência de rede |
| 19–20/10 | `1b4b8e2`…`1faf7d5` | identidade **JARVIS**: auditoria, voz diagnosticável, TARDIS (memória espacial), desempenho medido (CPU em repouso −44 %), autonomia escopada, pacote de entrega |
| 21–22/10 | `a725f56`…`d16c9d1` | **JARVIS ULTIMATE**: recuperação do original no núcleo, permissões por categoria, rosto 3D com boca sincronizada, TARDIS com rotor ligado ao estado real; módulo do robô (hoje removido) |
| 29–30/10 | `fe1d5c1`…`fd5fb06` (autor) | snapshot de segurança, CI em duas versões do Python e no Windows, endurecimento do pacote ZIP, `.gitignore` de dados sensíveis |
| 01–02/11 | `8c01d70`…`34f1fa0` | Fase 7 (testes de segurança, falhas, transições; **10 defeitos reais** achados e corrigidos), Fase 8 (modo console, diagnóstico por etapas, correções achadas pelo CI do Windows), **central 3D** (Three.js) |
| 02–03/11 | `4f540b1`…`bf070f6` | Operação Phoenix (remoção do robô, holograma androide, Protocolo ULTRON, perfis de inteligência com custo e consentimento) e Aprimoramentos 1–6 (ULTRON operador, prosódia, sons da TARDIS, holograma humanoide, WEB ORB) |

**Autoria.** 94 commits: 46 do autor (`JLeoBRx`), 46 de um assistente de programação por IA (`Claude`),
trabalhando sob as instruções do autor, e 2 de um processo automático de construção. Essa informação
precisa constar do TCC (ver `docs/academic`): a banca deve saber como o código foi produzido.

### 8.1 Problemas técnicos marcantes da evolução (com o commit que resolveu)

| Problema | Causa | Correção |
|---|---|---|
| O original não abria pelo script principal | métodos inexistentes chamados no início (`goal_manager`) | reconstrução do núcleo (`e0b6769`) |
| Observador do original nunca rodava | `NameError` engolido a cada ciclo | substituído pelo `PerceptionEngine` com erros visíveis |
| Interface não abria no Windows | `state_cache` usado antes de criado | `8417b29`, modo console como reserva |
| Scripts `.bat` perdiam a entrada do usuário | `chcp` consumia a entrada redirecionada | `cd9e7f3`, confirmado por sondas no CI do Windows |
| Cancelar com o modelo carregando travava | dependência do comportamento de *socket* no Windows | `746d7f7`, fila com verificação a cada 50 ms |
| Boca "aberta" depois da fala | erro de ponto flutuante na interpolação de quadros | `a1788c5` |
| Arquivos protegidos alteráveis por skills | ausência de recusa antes da autorização | Fase 7 (`8c01d70`), gancho `refuse_reason` |
| CPU alta em repouso | redesenho contínuo e verificações de rotina animando a cena | Fase D (`a706c27`): −44 % em repouso, medido |

## 9. Análise de dependências do módulo de robótica (NOCTARIO)

**Decisão de escopo (2026-11-11):** o NOCTARIO está fora do SAFRA e do TCC.

| Verificação | Resultado |
|---|---|
| Código do módulo (`ultron/noctario`, skills `noctario.*`, página, firmware ESP32, testes exclusivos, benchmark) | **removido da árvore** na Operação Phoenix (`4f540b1`, complemento `7385b99`), com manifesto em `REMOCAO_NOCTARIO.md`; continua íntegro no histórico (último commit completo: `34f1fa0`) |
| Imports, eventos, permissões, configurações, navegação, CI | nenhuma referência ativa (`grep -i noct` em `*.py`, `*.js`, `*.bat`, `*.yml`) |
| Banco de dados | a migração v6 ainda cria `noctario_runs` e `noctario_ops`. **São inertes:** nenhum código lê ou grava nelas. Ficam para manter a sequência de migrações idêntica entre bancos novos e antigos e para **não apagar dados** de quem já as usou |
| Testes | 5 asserções **negativas** confirmam a ausência (sem skills `noctario.*`, sem página, sem indicador, configuração antiga ignorada sem erro, evento antigo ignorado pelo avatar) |
| Documentos | menções apenas em documentos históricos (changelog, inventário, relatórios de fases) |

**Conclusão:** o SAFRA não tem dependência funcional do NOCTARIO. Nada precisa ser apagado; o que
restou está isolado (tabelas inertes e histórico). A partir desta fase, os documentos do SAFRA e do TCC
não tratam o robô como componente, objetivo ou integração prevista; ele aparece apenas no registro
histórico da evolução, como módulo descontinuado.

## 10. Problemas encontrados nesta auditoria

| # | Problema | Gravidade | Tratamento proposto |
|---|---|---|---|
| P1 | Três nomes convivendo: pasta/pacote/dados `ULTRON`, produto `JARVIS`, agora `SAFRA` | média (confusão, não defeito) | tabela de correspondência; identificadores internos mantidos; tudo o que o usuário vê passa a SAFRA |
| P2 | 25 documentos Markdown na raiz de `ULTRON/`, com sobreposição (três documentos de arquitetura) e partes desatualizadas (`TEST_REPORT.md` ainda cita 404 testes e o robô) | média | `docs/` passa a ser a documentação canônica; os antigos ficam como históricos, com aviso |
| P3 | `JARVIS_FINAL.zip` versionado na raiz, gerado em 20/10 e desatualizado | baixa | não apagar sem autorização; registrar como artefato histórico; o pacote atual é gerado pelo CI |
| P4 | Modelos de voz (315 MB) versionados no Git | baixa | manter (instalação offline depende deles); registrar o custo |
| P5 | A palavra "Jarvis" não existe no vocabulário dos modelos Vosk pt; o reconhecedor a transcreve como "aves", "aviso", "a vez" (medido em outubro) | alta para a interação por voz | a troca para "Safra" (palavra do português) é uma hipótese de melhora **a medir** (`docs/research`) |
| P6 | Cores literais fora dos tokens (ex.: 54 em `theme.py`, 54 em `room.js`) | baixa | a nova identidade concentra as cores nos tokens |
| P7 | O Protocolo ULTRON usa vermelho como assinatura; com o SAFRA vermelho, as duas identidades se confundiriam | média | o ULTRON recebe outra assinatura visual (decisão registrada no relatório técnico) |
| P8 | Desempenho 3D medido apenas com renderização por software; nunca com GPU real | média para o TCC | protocolo de medição no computador do autor |
| P9 | Qualidade da voz nunca avaliada por ouvintes; recuperação de memória nunca medida quantitativamente; reconhecimento nunca medido com voz humana | alta para o TCC | protocolos experimentais com métricas (`docs/research`) |
| P10 | WEB ORB nunca publicada (depende de servidor e domínio) | baixa para o TCC | tratada como componente complementar, fora das hipóteses centrais |
| P11 | Recursos dependentes de componentes externos não verificados: OCR (Tesseract), visão (modelo `qwen2.5vl`), geração de imagens (Stable Diffusion), UI Automation, notificações nativas | média | classificados como "não verificados" no inventário |
| P12 | Cobertura de testes não remedida desde 01/11 | baixa | remedir na fase de validação |

## 11. Escopo sugerido para o TCC

**Dentro do escopo (núcleo da pesquisa):** arquitetura modular centrada em um núcleo único e orientada a
eventos; processamento de comandos (regras determinísticas + modelo de linguagem local); interação por
voz offline (reconhecimento, ativação, síntese, prosódia); memória persistente; interface humanoide 3D com
sincronização labial guiada pelo áudio real; ambiente virtual TARDIS (visualização do estado e das tarefas
reais); segurança (permissões, autorizações, recusa antecipada, auditoria); diagnóstico, desempenho e
confiabilidade (isolamento de falhas, recuperação, testes automatizados, CI).

**Complementar (descrito, sem hipótese própria):** WEB ORB (acesso remoto seguro ao mesmo núcleo),
Protocolo ULTRON (troca de identidade e perfil de permissões sobre o mesmo executor), inventário passivo da
rede local, imaginação/geração.

**Fora do escopo:** NOCTARIO e qualquer integração robótica; controle de dispositivos físicos; treinamento
de modelos de IA.

## 12. Plano de transformação (resumo)

1. Auditoria e documentação (este documento, inventário, arquitetura).
2. Escopo científico, requisitos e cronograma.
3. Identidade SAFRA: nome visível, paleta vermelha, nova marca, holograma, ORBE, TARDIS e WEB ORB, com
   palavra de ativação "Safra" e compatibilidade com "Jarvis"; identificadores internos preservados.
4. Instrumentos de medição e protocolos experimentais; medições possíveis neste ambiente, rotuladas.
5. TCC e relatório técnico, com exportação para DOCX e PDF.

Cada etapa termina com a suíte de testes executada e um commit próprio.

## 13. Estrutura dos documentos

```text
ULTRON/docs/
├── README.md                     índice da documentação do SAFRA
├── academic/                     TCC (capítulos editáveis + TCC_SAFRA.md montado + DOCX/PDF)
├── technical/                    relatório técnico, auditoria, arquitetura, requisitos, inventário, testes, cronograma
├── diagrams/                     fontes Mermaid (.mmd) e imagens geradas
└── research/                     protocolos de validação, registro de referências verificadas, resultados (JSON)
```
