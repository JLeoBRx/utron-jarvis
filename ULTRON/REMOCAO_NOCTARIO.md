# Manifesto — remoção do Noctário do JARVIS (Operação Phoenix, Fase A)

O Noctário (robô seguidor de linha) saiu do produto JARVIS. Tudo continua no **histórico do Git** (o último
commit com o módulo completo é `34f1fa0`); nada foi apagado da pasta de dados do usuário
(`%LOCALAPPDATA%\ULTRON`).

## Arquivos removidos do repositório

| Arquivo | O que era |
|---|---|
| `ultron/noctario/__init__.py`, `protocol.py`, `service.py`, `simulator.py`, `store.py`, `transport.py` | serviço do robô: protocolo NOCT/1, transporte Bluetooth (RFCOMM/COM), simulador, registro de voltas |
| `ultron/skills/noctario/__init__.py` | as skills `noctario.*` (conectar, partida, parada, parâmetros, telemetria, calibração…) |
| `ultron/hud/noctario_page.py` | a página NOCTÁRIO |
| `firmware/noctario/` (inteiro: `src/main.cpp`, `noct_core.cpp/.h`, `platformio.ini`, `README.md`, `PROTOCOLO_NOCT1.md`, `test/host/*`) | firmware ESP32 e testes do núcleo em C++ |
| `tests/test_noctario.py`, `tests/test_noctario_firmware.py` | testes exclusivos |
| `tools/benchmark_noctario.py`, `docs/benchmarks/noctario_fase6.json` | medição exclusiva |

## Funcionalidades desativadas / integrações retiradas

| Onde | O que saiu |
|---|---|
| Navegação | página NOCTÁRIO e o atalho **F4** (os outros atalhos não mudaram) |
| Barra superior | indicador NOCTÁRIO (conexão/estado do robô) |
| Atalho global | **F12** (parada de emergência do robô) |
| NeuralCore | `NoctarioService`, registro no ciclo de vida, verificação de saúde `NOCTARIO`, parada de emergência direta por voz, "pare" com o robô andando |
| Intenções de voz/texto | todas as regras do robô (conectar, partida, parar, parâmetros, telemetria, sensores…) e "abra o noctário" |
| Permissões | a categoria **comandos ao robô** e as categorias sensíveis `robot_motion`/`robot_config` |
| Configurações | seção NOCTÁRIO e os campos `noctario_*` (um `settings.json` antigo com essas chaves continua abrindo: chaves desconhecidas são ignoradas e somem na próxima gravação) |
| TARDIS | o painel **TELEMETRIA** foi mantido e passou a medir o **próprio JARVIS** (processo, latência real dos modelos e das respostas, interface, Event Bus e workers); o DIAGNÓSTICO deixou de consultar o robô |
| Rosto/avatar | eventos `NOCTARIO_*` (link perdido, alerta) não existem mais |
| Diagnóstico (`--diagnose`) | a etapa "Noctário" |
| Atividades | o tipo/origem "Noctário" nos filtros |
| Dependências | `pyserial` (usado só pela porta COM do robô) |
| CI | os jobs "Noctario host C++ tests" e "Noctario ESP32 firmware compile" |
| Documentação de usuário | a seção do Noctário no `README_JARVIS.md` (seções renumeradas), exemplos de voz, tabela de atalhos; `COMANDOS_JARVIS.md` regenerado (102 ações) |

## O que foi preservado de propósito

* **Banco SQLite**: a migração v6 (tabelas `noctario_runs` e `noctario_ops`) continua no código para que
  bancos novos e antigos tenham o mesmo esquema; os dados já gravados nessas tabelas **não foram apagados** e
  simplesmente não são mais lidos.
* **Histórico**: `CHANGELOG_JARVIS.md` e os relatórios de fases anteriores (`INVENTARIO_JARVIS_ORIGINAL.md`,
  `ARQUITETURA_ULTIMATE.md`, rascunhos da Fase 8) mantêm as menções ao Noctário como registro do que existiu;
  serão revistos na entrega final da Operação Phoenix.
* Autorizações permanentes antigas de categorias do robô ficam no arquivo do usuário e são ignoradas.

## Complemento (revisão durante a Fase C)

Uma nova varredura (`grep -i noct` fora de `assets/` e dos documentos históricos) achou menções que tinham
escapado da primeira passada; todas eram texto, nenhuma era código ativo:

| Onde | O que era | Agora |
|---|---|---|
| `TEST_JARVIS.py` | `pyserial` listado como dependência ("Noctário pela porta COM") | removido da lista |
| `ultron/diagnose.py` | "Noctário" na lista de etapas dependentes (nenhuma etapa com esse nome existia mais) | removido |
| `ultron/hud/settings_page.py` | RESTAURAR PADRÕES dizia manter o "endereço do Noctário" | texto corrigido |
| `ultron/hud/tardis_room/page.py` | descrição dos painéis TELEMETRIA e DIAGNÓSTICO e exemplos dos campos | telemetria do sistema; exemplos novos |
| `ultron/skills/tardis`, `ultron/skills/assistant` | exemplos nas descrições das ferramentas (vão para o modelo e para `COMANDOS_JARVIS.md`) | exemplos novos; `COMANDOS_JARVIS.md` regenerado |
| `ultron/hud/avatar/states.py`, `ultron/core/activity.py`, `ultron/tardis/analyzers/__init__.py`, `ultron/memory/store.py` | comentários | atualizados |
| `RECURSOS_EXTERNOS.md` | seção "5. Noctário (robô)" e duas menções | removidas |
| `SEGURANCA_E_BACKUP.md` | duas regras de bancada do robô | removidas |
| `tests/test_original_recovery.py` | exemplo de nota de sessão | exemplo novo |
