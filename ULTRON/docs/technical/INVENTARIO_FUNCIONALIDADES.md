# Inventário de funcionalidades do SAFRA

Estado do código no commit de referência `bf070f6` (início da fase SAFRA), atualizado com as mudanças e
medições da fase SAFRA (11/11/2026), e a evidência que sustenta cada classificação. Este inventário **não** confunde código existente com funcionalidade validada: o que não
tem evidência está marcado assim.

## Critérios

**Estado**

| Estado | Significado |
|---|---|
| **Funcional** | implementada e comprovada por evidência registrada (abaixo). Quando um serviço externo com protocolo padronizado (API HTTP do Ollama/OpenAI) é substituído por um dublê fiel ao protocolo, isso fica dito na coluna de evidência |
| **Parcial** | implementada, com limitação conhecida que impede parte do comportamento esperado |
| **Não verificada** | código presente, mas a parte essencial depende de hardware ou serviço que nenhum teste registrado exercitou (microfone físico, GPU, Windows interativo, Tesseract, modelo real) |
| **Em desenvolvimento** | trabalho iniciado nesta fase |
| **Planejada** | prevista no cronograma, sem código |
| **Descontinuada** | retirada do produto; preservada apenas no histórico |

**Evidência**

| Código | Tipo |
|---|---|
| **TR** | teste automatizado com componentes reais (núcleo, SQLite em arquivo, Qt *offscreen*, Piper/Vosk com os modelos do repositório, gateway aiohttp real) |
| **TD** | teste automatizado com dublê declarado (servidor Ollama/OpenAI simulado, microfone, Lixeira, cofre de credenciais, falha injetada) |
| **CIW** | aprovado no CI em Windows (Windows Server 2025, sem microfone, alto-falante, GPU ou área de trabalho interativa) |
| **3D** | cena 3D carregada e conferida com WebGL por **software** (llvmpipe no CI Linux; SwiftShader/Chromium nas capturas) |
| **MV** | verificação manual registrada (captura de tela, arquivo de áudio, relatório de benchmark) |
| **—** | nenhuma evidência registrada |

## 1. Núcleo e infraestrutura

| Funcionalidade | Módulo | Estado | Evidência | Observações |
|---|---|---|---|---|
| Início e parada ordenados com dependências; nenhuma thread restante ao encerrar | `core/lifecycle.py`, `core/neural_core.py` | Funcional | TR (`test_core`, `test_tardis.ShutdownTest`, `test_startup`), CIW | |
| Event Bus com fila limitada; falha de um assinante não afeta os outros | `core/event_bus.py` | Funcional | TR (`test_event_bus`) | descartes contados e avisados |
| Estado global estruturado com publicação dos campos alterados | `core/state.py` | Funcional | TR (`test_core`) | |
| Workers nomeados, agendador, cancelamento cooperativo, prazos | `core/runtime.py` | Funcional | TR + TD (`test_core`, `test_model_router`) | cancelamento com o modelo carregando corrigido no Windows (`746d7f7`) |
| Instância única; `--status`, `--stop` | `platform/single_instance.py`, `platform/control.py` | Funcional | TR (`test_integrity`, `test_cli`), CIW | |
| Modo console | `console.py` | Funcional | TR, CIW (`START_JARVIS.bat --console`) | |
| Diagnóstico por etapas (`--diagnose`) | `diagnose.py` | Funcional | TR (`test_cli`, `test_startup`), CIW | |
| Monitor de saúde (CPU, RAM, disco, modelos, voz, interface) | `health/monitor.py` | Funcional | TR | GPU: leitura não verificada |
| Métricas de desempenho (quadros, atraso do laço, latências) | `core/metrics.py` | Funcional | TR, MV (`PERFORMANCE_REPORT.md`) | |
| Configurações validadas, migração de versões, cópia do arquivo ilegível | `config/settings.py` | Funcional | TR (`test_failures`, `test_original_recovery`) | |
| Plugins | `plugins/` | Funcional | TR (`test_plugins`) | |
| Instalação e atualização no Windows | `INSTALL_JARVIS.bat`, `ATUALIZAR_JARVIS.bat` | Funcional | CIW (instalação a partir do ZIP extraído) | máquina física do usuário não verificada |
| Início automático com o Windows | `platform/autostart.py` | Não verificada | — | `winreg` não exercitado; desligado por padrão |
| Bandeja do sistema e notificação nativa | `hud/controller.py` | Não verificada | — | o ícone existe; a notificação do Windows depende de sessão interativa |

## 2. Processamento de comandos e inteligência

| Funcionalidade | Módulo | Estado | Evidência | Observações |
|---|---|---|---|---|
| Intenção por regras determinísticas em português | `cognition/intent_engine.py` | Funcional | TR (`test_core`, `test_original_recovery`, `test_ultron_protocol`, `test_intelligence`) | |
| Fluxo comando → intenção → decisão → plano → execução → verificação → resposta | `core/orchestrator.py` | Funcional | TR + TD (`test_transitions`, `test_planner`) | |
| Respostas e uso de ferramentas pelo modelo local | `cognition/reasoning_engine.py`, `models/ollama_client.py` | Funcional | TD (Ollama simulado, protocolo HTTP real) | qualidade das respostas com o modelo real **não medida** |
| O modelo só executa ferramentas oferecidas no pedido | `cognition/reasoning_engine.py` | Funcional | TD (`test_security`) | |
| Perfis de inteligência, roteamento por tarefa, limite de gasto, consentimento para nuvem | `models/profiles.py`, `router.py`, `usage.py` | Funcional | TD (`test_intelligence`, `test_model_router`) | |
| Provedor OpenAI | `models/openai_provider.py` | Funcional | TD (`test_openai_provider`) | API real não usada (sem chave; exige autorização) |
| Procedência de cada resposta (memória, ação, modelo, inferência) | `cognition/provenance.py` | Funcional | TR (`test_intelligence`) | |
| Objetivos persistentes com estados formais | `cognition/goal_manager.py` | Funcional | TR | |
| Inteligência proativa (sugere, não age) | `proactive/intelligence.py` | Funcional | TR (`test_executor`: origem proativa nunca autoriza sozinha) | |
| Imaginação (cenários, mundos, modo sonho) | `imagination/` | Funcional | TD (`test_imagination`) | geração com modelo real não medida |
| Geração de imagens | `imagination/image_pipeline.py` | Não verificada | — | depende de Stable Diffusion local |

## 3. Interação por voz

| Funcionalidade | Módulo | Estado | Evidência | Observações |
|---|---|---|---|---|
| Captura do microfone (sounddevice/PyAudio, reamostragem para 16 kHz) | `voice/audio.py` | Não verificada | TD | sem microfone em nenhum ambiente de teste |
| Reconhecimento offline (Vosk, pt-BR) | `voice/stt.py`, `voice/processor.py` | Funcional (com fala sintetizada) | TR (Piper → Vosk com os modelos do repositório) | voz humana **não medida** |
| Palavra de ativação "Safra" (e "Jarvis" aceita), formas fortes/fracas, calibração | `voice/wake_word.py`, `voice/calibrate.py` | Parcial | TR, PV-01 | com voz sintética, "Safra" ativou em 2–4 % (ouvida como "faça") e "Jarvis" em 17–18 %; ativação indevida ≤ 0,5 %. Exige calibração; voz humana ainda não medida |
| Proteção contra autoescuta e janela de continuação | `voice/processor.py` | Funcional | TR + TD | |
| Síntese neural (Piper, `pt_BR-faber-medium`) com perfil de voz | `voice/tts.py`, `voice/dsp.py` | Funcional | TR (`test_jarvis_voice`, `test_voice`), MV (amostras WAV) | reprodução em alto-falante não verificada; qualidade percebida não avaliada por ouvintes |
| Prosódia (pausas, ritmo, normalização de números, horas e valores) | `voice/prosody.py` | Funcional | TR (`test_voice_prosody`) | |
| Voz alternativa SAPI | `voice/tts.py` | Não verificada | — | só no Windows com sessão de áudio |
| Diagnóstico de voz em 8 etapas | `voice/diagnostics.py` | Funcional (etapas lógicas) | TR + TD, CIW | etapa do microfone físico não verificada |
| Sincronização labial guiada pelo áudio real | `voice/lipsync.py` | Funcional | TR (`test_lipsync`) | correspondência perceptual (atraso áudio–boca) **não medida** |

## 4. Memória persistente

| Funcionalidade | Módulo | Estado | Evidência | Observações |
|---|---|---|---|---|
| Banco único SQLite (WAL), migrações v1–v7 idempotentes | `memory/store.py` | Funcional | TR (`test_memory`, `test_integrity`) | |
| Memórias de trabalho, episódica, semântica, procedural e preferências | `memory/*` | Funcional | TR (`test_memory`) | |
| Recuperação unificada de memória para o contexto | `memory/retrieval.py`, `cognition/context_engine.py` | Parcial | TR, PV-03 | medida (nov/2026): perguntas lexicais 100 % (após corrigir 3 defeitos), **paráfrases 45 %** (abaixo da meta de 80 %) |
| Memória pessoal: registros, busca sem acentos (FTS5), perguntas respondidas só com o que está salvo | `secondbrain/` | Funcional | TR (`test_second_brain`) | |
| Lembretes persistentes, sem duplicação, aviso de lembretes perdidos | `secondbrain/reminders.py` | Funcional | TR (relógio controlado) | |
| Recusa de segredos antes de gravar | `memory/store.py`, `secondbrain/service.py` | Funcional | TR | |
| Backup, restauração e exportação | `memory/backup.py`, `app.py` | Funcional | TR (`test_cli`, `test_failures`) | |
| Grafo de conceitos persistente | `graph/` | Funcional | TR | |
| Modelo do mundo persistente | `world/world_model.py` | Funcional | TR (`test_world_model`) | |

## 5. Execução, segurança e permissões

| Funcionalidade | Módulo | Estado | Evidência | Observações |
|---|---|---|---|---|
| Executor único: validação de argumentos, prazo, classificação de erros, auditoria | `agent/execution.py` | Funcional | TR (`test_executor`) | |
| Permissões por categoria (permitir/confirmar/bloquear) com pisos | `agent/permissions.py` | Funcional | TR (`test_permissions`) | |
| Autorização: uma pendência, expirar = negar, autorização permanente escopada | `agent/autonomy.py` | Funcional | TR (`test_executor`, `test_security`) | |
| Recusa antecipada de pastas protegidas (sistema, inicialização, programa, dados) | `skills/filesystem`, `agent/execution.py` | Funcional | TR (`test_security`) | |
| Exclusão só pela Lixeira; cópias de segurança nunca sobrescritas | `skills/filesystem` | Funcional | TD (Lixeira falsa) | |
| Verificação independente do efeito | `agent/verification.py` | Funcional | TR (`test_verifier`) | |
| Recuperação com tentativas limitadas | `agent/recovery.py` | Funcional | TR (`test_recovery`) | |
| Histórico de atividades | `core/activity.py`, `hud/activity_page.py` | Funcional | TR (`test_activity`) | |
| Código sem shell, `eval`, `exec`, `pickle`; TLS nunca desligado | todo o pacote | Funcional | TR (varredura em `test_security`) | |
| Credenciais apenas no cofre do sistema | `platform/credentials.py` | Funcional | TD (cofre falso) | Gerenciador de Credenciais real não verificado |
| Modo privacidade (microfone e captura fechados) | `privacy/` | Funcional | TR | |
| Ações no Windows (aplicativos, janelas, UI Automation, volume, mídia, teclado) | `skills/applications`, `windows`, `system`, `audio` | Não verificada | TD | precisam de sessão Windows interativa |
| Isolamento de falhas (banco danificado, somente leitura, modelo que quebra, sensor que falha) | vários | Funcional | TR + TD (`test_failures`, `test_transitions`) | |

## 6. Interface

| Funcionalidade | Módulo | Estado | Evidência | Observações |
|---|---|---|---|---|
| Plataforma Qt com 5 páginas e atalhos | `hud/platform.py` | Funcional | TR (`test_platform`), CIW | |
| Conversa na página principal | `hud/conversation.py` | Funcional | TR | |
| Cena 3D: holograma de corpo inteiro (57 ossos, *skinning* na GPU), estados reais, olhar, gestos | `hud/scene3d/web/js/avatar*.js` | Funcional (WebGL por software) | 3D, TR (`test_scene3d`), MV (capturas) | **GPU real não verificada** |
| ORBE 3D e ORBE compacta flutuante | `orb.js`, `hud/orb.py` | Funcional (WebGL por software) | 3D, TR | |
| Reserva 2D quando o WebGL falha | `hud/scene3d/view.py`, `hud/avatar/` | Funcional | CIW (no Windows do CI o WebGL não abriu e a reserva funcionou, `34f1fa0`) | |
| Perfis de qualidade visual | `hud/quality.py` | Funcional | MV (`PERFORMANCE_REPORT.md`) | |
| Tema centralizado (tokens) — identidade SAFRA | `hud/design/tokens.json`, `palette.py`, `theme.py` | Funcional | TR (`DesignTokensTest`), MV (capturas) | folhas de estilo do Qt geradas da paleta; cores literais restantes são de materiais físicos (latão, madeira da cabine) |
| Sons da interface | `audio/neural_audio.py` | Funcional (geração) | TR | reprodução não verificada |

## 7. Ambiente virtual TARDIS

| Funcionalidade | Módulo | Estado | Evidência | Observações |
|---|---|---|---|---|
| Motor de tarefas (fila, prazos, cancelamento, persistência, modo do rotor) | `tardis/engine.py` | Funcional | TR (`test_tardis_logic`) | |
| Analisadores determinísticos (diagnóstico, telemetria medida, organização, planejamento sem executar) | `tardis/analyzers/` | Funcional | TR | |
| Sala de controle 3D (console, rotor, colunas, mobiliário) ligada a tarefas reais | `room.js`, `tardis_room/` | Funcional (WebGL por software) | 3D, TR (`test_tardis_room`), MV | GPU real não verificada |
| Cabine externa e transição pela porta | `exterior.js` | Funcional (WebGL por software) | 3D, MV | |
| Arquivo (memória espacial navegável) | `hud/tardis.py` | Funcional | TR (`test_tardis`) | |
| Sons originais da TARDIS, substituíveis por arquivos autorizados | `audio/tardis_sfx.py` | Funcional (geração) | TR (`test_tardis_sfx`) | reprodução não verificada |

## 8. Identidades e acesso remoto (complementares)

| Funcionalidade | Módulo | Estado | Evidência | Observações |
|---|---|---|---|---|
| Protocolo ULTRON: identidade alternativa reversível e perfil `ULTRON_OPERATOR` sobre o mesmo executor | `hud/ultron_protocol.py`, `personality/persona.py`, `agent/permissions.py` | Funcional | TR (`test_ultron_protocol`) | |
| Tecla de emergência para restaurar | `hud/controller.py` | Funcional | TR | atalho da aplicação (não global do sistema) |
| WEB ORB: gateway, pareamento por QR com confirmação, agente de saída, mesmo núcleo | `gateway/`, `remote/agent.py` | Funcional (local) | TR (`test_web_orb`), MV (Chromium em tamanho de celular, imagem Docker executada) | **não publicada** |
| Inventário passivo da rede local | `network/` | Funcional (lógica) | TD (`test_network`) | rede física não verificada |

## 9. Percepção

| Funcionalidade | Módulo | Estado | Evidência | Observações |
|---|---|---|---|---|
| Sensores de processos e sistema | `perception/processes.py`, `system.py` | Funcional | TR (psutil) | |
| Sensores de janelas e dispositivos | `perception/windows.py`, `devices.py` | Não verificada | TD | Win32 |
| Captura de tela, OCR e visão | `perception/screen.py`, `ocr.py`, `vision.py` | Não verificada | TD | Tesseract e modelo de visão ausentes |
| Fusão de percepção | `perception/fusion.py` | Funcional | TR | |

## 10. Descontinuadas e planejadas

| Funcionalidade | Estado | Evidência / referência |
|---|---|---|
| NOCTARIO (robô seguidor de linha: firmware ESP32, Bluetooth, skills, painel) | **Descontinuada — fora do escopo do SAFRA e do TCC** | removida em `4f540b1`/`7385b99`; manifesto `REMOCAO_NOCTARIO.md`; análise de dependências em `AUDITORIA_INICIAL.md` §9 |
| HUB 2D antigo (cérebro desenhado em QPainter como vista principal) | Descontinuada como vista principal; mantida como vista alternativa e reserva | `hud/brain_view.py` |
| Identidade visual azul/ciano do JARVIS | Substituída nesta fase pela identidade SAFRA | `RELATORIO_TECNICO.md` |
| Medições no computador de referência (voz humana, modelo real, GPU, atraso áudio × tela, 8 h) | Planejada (protocolos e instrumentos prontos; ambiente C já medido) | `docs/research/PROTOCOLOS_DE_VALIDACAO.md` |
| Publicação da WEB ORB | Planejada (depende de servidor e domínio do autor) | `WEB_ORB.md` |

## Resumo

| Estado | Itens |
|---|---|
| Funcional | 68 |
| Parcial | 2 |
| Não verificada | 8 |
| Planejada | 2 |
| Descontinuada ou substituída | 3 |
| **Total** | **83** |

No início da fase (commit `bf070f6`) eram 84 itens: 68 funcionais, 2 parciais, 8 não verificados, 1 em
desenvolvimento, 2 planejados e 3 descontinuados. As mudanças da fase: a palavra de ativação "Safra" foi
implementada (fundida ao item da ativação por voz, que continua parcial pelas medições), o tema centralizado
passou a funcional e a recuperação de memória passou a parcial depois de medida (PV-03).

Das 68 funcionais, várias dependem de dublê para um serviço externo ou foram conferidas só com WebGL por
software; a coluna de evidência diz qual. Contagem feita por script sobre as tabelas acima.

O padrão é claro: **a lógica do sistema está amplamente verificada por testes automatizados; o que falta
verificar é a fronteira com o hardware e com os serviços externos** — microfone, alto-falante, GPU, sessão
interativa do Windows e modelos reais. É exatamente essa fronteira que os protocolos experimentais do TCC
precisam cobrir.
