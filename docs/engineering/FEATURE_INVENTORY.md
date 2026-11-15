# Inventário de funcionalidades

Data: 14/11/2026. Base: código do legado em `ULTRON/` no commit `470359f` e o inventário anterior
(`ULTRON/docs/technical/INVENTARIO_FUNCIONALIDADES.md`, 83 itens com a evidência de cada um).

## Como ler

**Estado no legado** — três marcas independentes:

| Marca | Significado |
|---|---|
| I | implementada no código |
| T | coberta por teste automatizado que passa |
| R | validada em ambiente real (Windows do autor), com registro |

Nenhuma funcionalidade tem a marca **R**: não há registro de validação no Windows real. Isso não quer dizer que
não funcionem lá; quer dizer que não há evidência guardada.

**Destino na nova versão:**

| Destino | Significado |
|---|---|
| Portar | reimplementar nos novos limites de módulo, levando os testes como especificação |
| Redesenhar | manter o propósito, refazer a solução |
| Novo | não existe no legado |
| Adiar | fora do caminho crítico; os dados são preservados; decisão revista depois do núcleo pronto |
| Descartar | não entra na nova versão; motivo registrado |

**Fase** é a da missão (1 a 12). Na nova versão, cada funcionalidade passará por quatro estados registrados
separadamente: planejada → implementada → testada → validada em ambiente real.

## 1. Núcleo (`core`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Barramento de eventos com fila limitada; falha de assinante isolada | `core/event_bus.py` | I T | Portar | 4 |
| Estado global estruturado, publicado por mudança | `core/state.py` | I T | Portar | 4 |
| Início e parada ordenados com dependências | `core/lifecycle.py` | I T | Redesenhar: inicialização em etapas, serviços opcionais sob demanda | 4 |
| *Workers*, agendador, cancelamento, prazos | `core/runtime.py` | I T | Redesenhar sobre tarefas assíncronas, com limite de concorrência | 4 |
| Orquestrador: pedido → intenção → plano → execução → verificação → resposta | `core/orchestrator.py` | I T | Portar | 4 |
| Configurações validadas, com migração e cópia de segurança | `config/settings.py` | I T | Redesenhar com modelos Pydantic; importar as existentes | 2, 4 |
| Instância única; `--status`, `--stop` | `platform/single_instance.py` | I T | Portar | 10 |
| Modo console e linha de comando | `console.py`, `app.py` | I T | Portar (cliente da API) | 4 |
| Logs | `app.py` (texto) | I | Redesenhar: estruturados, com correlação | 2 |

## 2. Inteligência (`intelligence`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Intenção por regras determinísticas em português | `cognition/intent_engine.py` | I T | Portar, dividindo a classe de 685 linhas por domínio | 4 |
| Raciocínio com ferramentas oferecidas por pedido | `cognition/reasoning_engine.py` | I T | Portar sobre o gateway de IA | 5 |
| Planejamento de tarefas em passos | `cognition/planner_engine.py` | I T | Portar | 7 |
| Procedência de cada resposta | `cognition/provenance.py` | I T | Portar | 4 |
| Objetivos persistentes | `cognition/goal_manager.py` | I T | Portar | 6 |
| Motor de análise (consulta, planejamento, organização, rotinas, telemetria, diagnóstico) que só propõe ações | `tardis/engine.py`, `analyzers/` | I T | Portar com nome próprio ("Análises") | 6 |
| Identidade e tom do assistente | `personality/` | I T | Redesenhar para a identidade SAFRA | 4 |
| Proatividade (sugere, não age) | `proactive/` | I T | Adiar | — |
| Imaginação, modo sonho | `imagination/` | I T | Adiar | — |
| Geração de imagens | `imagination/image_pipeline.py` | I | Adiar | — |
| Modelo do mundo | `world/world_model.py` | I T | Adiar (dados importados) | — |

## 3. Gateway de IA (`ai_gateway`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Cliente do modelo local (Ollama) | `models/ollama_client.py` | I T (simulado) | Portar como provedor | 5 |
| Provedor remoto (OpenAI) | `models/openai_provider.py` | I T (simulado) | Portar como provedor | 5 |
| Perfis e roteamento por tarefa | `models/profiles.py`, `router.py` | I T | Redesenhar: roteamento por privacidade, latência, custo, disponibilidade, capacidade e contexto | 5 |
| Consentimento para nuvem e limite mensal de gasto | `models/` | I T | Portar | 5 |
| Registro de consumo (só números) | tabela `model_usage` | I T | Portar; acrescentar métricas p50/p95/p99 e tempo até o primeiro token | 5 |
| Contrato único de provedor, *fallback*, prazo e cancelamento uniformes | — | — | Novo | 5 |
| Resposta em fluxo (*streaming*) até a interface | parcial (eventos de progresso) | I | Redesenhar | 5 |
| Descarregar modelos locais ociosos | — | — | Novo | 5 |

## 4. Memória (`memory`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Memórias episódica, semântica, procedural, de preferências, de trabalho | `memory/*` | I T | Portar | 6 |
| Recuperação para o contexto | `memory/retrieval.py` | I T (lexical 100 %, paráfrase 45 %) | Redesenhar a recuperação por significado; manter a lexical | 6 |
| Memória pessoal: registros, lembretes, busca sem acentos, lixeira, histórico | `secondbrain/` | I T | Portar | 6 |
| Respostas só com o que está salvo | `secondbrain/queries.py` | I T | Portar | 6 |
| Lembretes no horário, sem duplicação, aviso dos perdidos | `secondbrain/reminders.py` | I T | Portar | 6 |
| Recusa de segredos antes de gravar | `memory/store.py`, `secondbrain/` | I T | Portar | 6 |
| Grafo de conceitos | `graph/` | I T | Portar (dados importados) | 6 |
| Exportação da memória pessoal | `app.py --export` | I T | Portar | 6 |
| Conversas e mensagens como entidades | — (só atividades e episódios) | — | Novo | 6 |

## 5. Projetos (`projects`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Notas, decisões e parâmetros por projeto | `tardis/store.py`, tabela `project_notes` | I T | Portar | 6 |
| Registros do tipo "projeto" na memória pessoal | `secondbrain/` | I T | Portar como projetos | 6 |
| Projeto como entidade que liga conversas, memórias, tarefas e atividades; contexto ativo | — | — | Novo | 6 |

## 6. Comunicação (`communication`, `api`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Chamadas diretas da interface ao núcleo | `hud/controller.py` | I | Descartar: substituídas pela API | — |
| Ponte da cena 3D (`window.JARVIS`, QWebChannel) | `hud/scene3d/` | I T | Descartar | — |
| Agente de saída para acesso remoto | `remote/agent.py` | I T (local) | Redesenhar sobre o contrato da API; desligado por padrão | 10–11 |
| Gateway remoto com pareamento por código, anti-CSRF, limite de tentativas | `gateway/` | I T (local) | Redesenhar: as defesas viram parte de `security`; o serviço é reavaliado na fase de publicação | 11 |
| API HTTP e WebSocket com contrato versionado | — | — | Novo (especificado em `ULTRON/docs/especificacao/CONTRATO_V1.md`) | 2, 4 |

## 7. Voz (`voice`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Captura do microfone com reamostragem | `voice/audio.py` | I | Portar | 6 |
| Reconhecimento offline em português (Vosk) | `voice/stt.py` | I T (fala sintetizada) | Portar atrás de interface de provedor | 6 |
| Palavra de ativação com calibração | `voice/wake_word.py` | I T (acerto de 2–4 % com voz sintética) | Redesenhar: só "Safra"; avaliar alternativa de detecção | 6 |
| Tecla de atalho global para falar | — | — | Novo | 10 |
| Sem autoescuta; janela de continuação; interrupção | `voice/processor.py` | I T | Portar | 6 |
| Síntese neural local (Piper) com perfil de voz | `voice/tts.py`, `dsp.py` | I T | Portar atrás de interface de provedor | 6 |
| Prosódia: números, horas, valores, siglas | `voice/prosody.py` | I T | Portar | 6 |
| Voz alternativa do Windows (SAPI) | `voice/tts.py` | I | Portar | 6 |
| Diagnóstico de voz em 8 etapas | `voice/diagnostics.py` | I T | Portar | 6 |
| Nível de áudio da fala (energia) | parte de `voice/lipsync.py` | I T | Portar (anima o símbolo) | 6 |
| Movimento da boca do avatar | `voice/lipsync.py` | I T | Descartar: não há rosto | — |
| Sons da interface | `audio/neural_audio.py` | I T | Adiar | — |

## 8. Ferramentas e segurança (`tools`, `security`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Executor único: validação, prazo, classificação de erro, auditoria | `agent/execution.py` | I T | Portar | 7 |
| Permissões por categoria, com pisos | `agent/permissions.py` | I T | Portar | 7 |
| Autorização: uma pendência, expirar é negar, concessão permanente escopada | `agent/autonomy.py` | I T | Portar | 7 |
| Verificação independente do efeito | `agent/verification.py` | I T | Portar | 7 |
| Recuperação com tentativas limitadas | `agent/recovery.py` | I T | Portar | 7 |
| Pastas protegidas recusadas antes de pedir autorização; exclusão só pela Lixeira | `skills/filesystem` | I T | Portar | 7 |
| Sem shell, `eval`, `exec`, `pickle`; TLS nunca desligado | todo o pacote | I T | Manter como regra, com teste | 2 |
| Credenciais só no cofre do sistema | `platform/credentials.py` | I T (simulado) | Portar | 7 |
| Modo privacidade | `privacy/` | I T | Portar | 7 |
| 102 habilidades (aplicativos, janelas, arquivos, sistema, navegador, desenvolvimento, rede, memória, visão…) | `skills/` | I T (parte simulada) | Portar por grupos, começando pelas que não dependem do Windows | 7, 10 |
| Perfil de autonomia ampliada | `ULTRON_OPERATOR` em `agent/permissions.py` | I T | Portar como "Modo Operador", com prazo obrigatório | 7 |
| Plugins do usuário | `plugins/` | I T | Adiar: interface de extensão redefinida depois | — |
| Usuários, perfis, permissões por papel, sessões, bloqueio por tentativas | — | — | Novo | 2, 9 |
| Chave de idempotência para pedidos com efeito | — | — | Novo | 4 |

## 9. Monitoramento (`monitoring`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Histórico de atividades | `core/activity.py` | I T | Portar | 4 |
| Monitor de saúde (CPU, memória, disco, modelos, voz) | `health/monitor.py` | I T | Portar | 4 |
| Métricas internas (laço, filas, latências) | `core/metrics.py` | I T | Redesenhar com percentis e exportação | 4 |
| Diagnóstico por etapas | `diagnose.py` | I T | Portar | 4 |
| Telemetria só com valores medidos | `tardis/analyzers/telemetry.py` | I T | Portar | 4 |

## 10. Plataforma e armazenamento (`platform`, `storage`)

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Banco SQLite único com migrações | `memory/store.py` | I T | Redesenhar: camada de acesso isolada, migrações versionadas com retorno | 2 |
| Backup verificado, diário; restauração conferida | `memory/backup.py` | I T | Portar | 2, 6 |
| Banco danificado ou só leitura não derruba o sistema | vários | I T | Portar | 4 |
| Início automático com o Windows | `platform/autostart.py` | I T (simulado) | Redesenhar na casca do desktop | 10 |
| Bandeja e avisos nativos | `hud/controller.py` | I | Redesenhar na casca do desktop | 10 |
| Sensores de janelas, processos, dispositivos | `perception/` | I T | Adiar; quando voltar, por eventos e não por sondagem | — |
| Captura de tela, OCR, visão | `perception/screen.py`, `ocr.py` | I T (simulado) | Adiar | — |
| Observador (acompanha o que o usuário faz, com pausa) | `perception/`, `privacy/` | I T | Adiar | — |
| Inventário passivo da rede local | `network/` | I T (simulado) | Adiar | — |
| Instalação e atualização por `.bat` | scripts | I T (CI) | Redesenhar: instalador e atualização verificada | 10–11 |

## 11. Interfaces

| Funcionalidade | Legado | Estado | Destino | Fase |
|---|---|:-:|---|:-:|
| Plataforma Qt de 5 páginas | `hud/platform.py` e páginas | I T | Redesenhar em React: interface operacional | 3, 10 |
| Conversa, autorização pendente, atividades, configurações, diagnósticos | `hud/` | I T | Redesenhar | 3, 10 |
| Janela compacta flutuante | `hud/orb.py` | I T | Redesenhar na casca | 10 |
| Design system por *tokens* | `hud/design/tokens.json` | I T | Redesenhar com a paleta definida | 3 |
| Símbolo abstrato do assistente | — | — | Novo | 3 |
| Holograma humanoide 3D; avatar 2D com rosto | `hud/scene3d/`, `hud/avatar/` | I T | **Descartar**: a identidade não admite 3D nem rosto | — |
| Sala de controle e cabine temáticas; sons temáticos | `hud/tardis*`, `audio/tardis_sfx.py` | I T | **Descartar**: elementos de obra de terceiros | — |
| Persona alternativa com nome de personagem; ativação ocasional | `hud/ultron_protocol.py`, `personality/persona.py` | I T | **Descartar**: personagem de terceiros; o perfil de autonomia fica (seção 8) | — |
| Perfis de qualidade 3D, detecção de GPU, reserva 2D | `hud/quality.py`, `scene3d/view.py` | I T | **Descartar**: não há mais 3D | — |
| Site remoto da "ORBE" | `gateway/.../static/` | I T (local) | **Descartar**: substituído pela interface operacional | — |

## 12. Legado do legado

| Funcionalidade | Legado | Estado | Destino |
|---|---|:-:|---|
| Importação do "JARVIS original" (banco, automações, modelos) | `platform/models_import.py`, `memory/` | I T | **Descartar**: os dados já estão no banco atual, que é a origem da nova importação |
| Migração de configurações v1 → v3 | `config/settings.py` | I T | **Descartar** depois da importação: a nova versão lê a v3 |
| Tabelas de um módulo de robótica removido | migração v6 | I | **Descartar**; conteúdo exportado e conferido antes |

## 13. Novo: portal público e painel administrativo

Nada disto existe no legado. Situação em 15/11/2026 na coluna da direita (I implementado, T testado; nada validado em produção).

| Funcionalidade | Fase |
|---|:-:|
| Portal público: início, sobre, funcionalidades, IA, segurança, atualizações, documentação, downloads, perguntas frequentes, contato, privacidade, termos | 8 → **I T** (Fase 2); galeria e página de arquitetura: pendentes |
| Página inicial configurável (título, seções, ordem, destaques, rodapé) | **I T** (Fase 2) |
| CMS: páginas com rascunho, publicação, despublicação, agendamento, *slug*, SEO, pré-visualização e histórico | **I T** (Fase 2), exceto agendamento |
| CMS: notícias, atualizações, artigos, funcionalidades, perguntas frequentes, galeria, documentação, *links*, contato | notícias com categorias, perguntas frequentes (blocos), *links* e contato: **I T**; galeria e seções de documentação: pendentes |
| Gerenciador de mídia com validação de tipo e tamanho, nomes seguros, texto alternativo, categorias | **I T** (Fase 2) |
| Downloads: versões, plataforma, canal (estável, beta, experimental), notas, integridade do arquivo | cadastro **I T**; arquivos e publicação: bloqueados até a decisão de licença |
| Usuários administrativos: entrada, saída, recuperação de acesso, papéis, sessões, histórico de ações, bloqueio por tentativas | **I T** (Fase 2) |
| Separação entre conteúdo público e dados privados, conferida no servidor | **I T** (Fase 2) |
| Infraestrutura: ambientes, contêineres, banco para uso concorrente, mídia, backups, CI/CD, retorno de versão | 11 |

## 14. Resumo

| Destino | Itens |
|---|---:|
| Portar | 48 |
| Redesenhar | 20 |
| Novo | 18 (9 no núcleo, 9 no portal e no painel administrativo) |
| Adiar | 10 |
| Descartar | 11 |
| Manter como regra de código | 1 |
| **Total** | **108** |

Os itens adiados não perdem dados: as tabelas correspondentes são importadas e ficam disponíveis para quando a
funcionalidade voltar.
