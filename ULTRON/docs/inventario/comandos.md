# Inventário de comandos — J.A.R.V.I.S. original × plataforma atual (`ultron`)

**Escopo.** Original: `53e5a31:JARVIS (git archive 53e5a31 JARVIS)` (citado como `commands.py:L`, `backend.py:L`, `copilot.py:L`…). Atual: `ULTRON` (citado como `ultron/…:L`). O repositório não foi alterado (snapshot de arquivos/tamanhos/mtimes antes e depois: idêntico).

**Fluxo real do original** (HUD `jarvis_hud.py:2759` e voz `backend.py:898-907`) → `backend.process_command` (`backend.py:805-837`): 1º `commands.handle` (roteador regex), 2º automação por frase exata, 3º agente LLM `ask_agent` (Ollama `qwen2.5:3b`, 32 ferramentas). Nenhum comando ou ferramenta existia só nas cópias `*_BACKUP_*`, `*_ANTES_*` ou `_backup_antes_do_copilot/` (diff das regex e das definições de ferramentas: os backups são subconjuntos — faltam neles apenas as rotas do Observador).

**Como foi verificado** (scripts em `(scripts de verificação da auditoria, fora do repositório) `):
- `run_original.py` carrega o `commands.py` original com stubs (`stubs/pyautogui.py`, `stubs/pyperclip.py`, `stubs/copilot.py`) e substitui todas as funções de ação (abrir, fechar, energia, PowerShell, navegador…) por registradores — **nada é executado de verdade**; registra a linha do `return` de `handle()`, a ação chamada e a confirmação pendente. Resultados: `original_results.json`, `original_phrases_extra.json`, `original_phrases_edge.json`. `run_original_confirm.py` testa “sim/não/expiração”.
- `run_current.py` roda `IntentEngine.classify` + `DecisionEngine` atuais, valida os argumentos na skill e calcula a decisão de autonomia (origem `user`, nível padrão `balanced`). Resultados: `current_results.json`, `current_phrases_extra.json`, `current_phrases_edge.json`.
- `run_automations.py` cria automações com o `automation.py` original (LOCALAPPDATA temporário), dispara-as, importa o banco com o `legacy_import` atual e tenta executá-las no `ExecutionEngine` atual.
- Limite: execução em Linux. Os efeitos reais no Windows (PowerShell/WinRT, `taskkill`, `LockWorkStation`, pycaw, janelas) **não** foram executados; “funcional” = caminho de código completo e sem stub, com a rota confirmada no harness.

**Critério de status.** PRESERVADO = as alternativas explícitas da regex original continuam reconhecidas, com efeito equivalente (variações livres que só casavam por regex frouxa ficam anotadas em “observação”). PARCIAL = o efeito existe, mas alguma alternativa explícita não é reconhecida, ou o comportamento foi reduzido. AUSENTE = sem equivalente.

**Confirmação no atual.** `AutonomyPolicy.decide` (`ultron/agent/autonomy.py:74-95`): risco none/low → executa; medium → executa para pedido direto; high/critical → pede autorização (timeout padrão de 30 s, `ultron/config/settings.py:106`; no original eram 12 s, `commands.py:33`).

---

## 1) Comandos do original

| # | Frases de exemplo (casam na regex original) | Ação/ferramenta (original) | Confirmação (original) | Funcional? (evidência) | Atual: intent/skill obtido | Status | Observação |
|---|---|---|---|---|---|---|---|
| 1 | “ative o Observador”, “ligue o modo observador”, “observador”, “modo observador” | `copilot.activate_observer()` → modo OBSERVER: percepção contínua da tela por modelo de visão, assistência falada e tarefas agênticas autônomas via `neural_core` | não | Sim — `commands.py:1069-1072`; `copilot.py:264-266, 280-299, 777-802` | “ative o Observador”, “ligue o modo observador”, “ativar observador” → `control` {screen_observation: true} (`intent_engine.py:139-140`; `neural_core.py:502-505`). “observador” e “modo observador” sozinhos → `unknown` (vai ao LLM) | PARCIAL | Frases exatas “observador”/“modo observador” não são reconhecidas. O efeito atual liga a configuração `screen_observation` (sensores de tela/visão + insights proativos que só sugerem, `neural_core.py:525-530`), sem execução autônoma de tarefas. O padrão atual é ligado (`settings.py:86`); o original sempre iniciava desativado (`copilot.py:45`). |
| 2 | “acompanhe o que eu fizer no computador”, “me ajude com o código”, “fique me acompanhando na tela”, “me ajude no pc” | `copilot.activate_observer()` | não | Sim — `commands.py:1073-1076` | todas → `unknown` (LLM) | PARCIAL | O efeito existe via “ative o observador”, mas nenhuma destas frases é reconhecida. No original a regex era ampla: qualquer “me ajude … pc/tela/programa” ligava o Observador. |
| 3 | “desative o observador”, “desligue o observador”, “pare o observador”, “parar observador” | `copilot.deactivate_observer()` | não | Sim — `commands.py:1077-1080`; `copilot.py:269-273` | “desative/desligue/desligar observador” → `control` {screen_observation: false} (`intent_engine.py:141-142`). “pare o observador”, “parar observador” → `unknown` | PARCIAL | Os verbos “pare/parar” são alternativas explícitas na regex original e não são reconhecidos (a regex atual exige “pare de”). |
| 4 | “pause o observador”, “pausar observador” | `copilot.pause()`: suspende capturas, descarta resultados em voo e pausa o agente (`agent.pause()`) | não | Sim — `commands.py:1081-1084`; `copilot.py:302-319` | `unknown` (LLM) | AUSENTE | Não existe pausa nem retomada de observação ou de tarefa em andamento. Só há ligar/desligar `screen_observation` ou “cancelar”. |
| 5 | “retome o observador”, “retomar observador” | `copilot.resume()` | não | Sim — `commands.py:1085-1088`; `copilot.py:322-335` | `unknown` | AUSENTE | Idem ao item 4. |
| 6 | “cancelar desligamento”, “cancele o reinício”, “cancela o desligamento” | `shutdown /a` | não | Sim — `commands.py:1089-1090, 350-352` | `command` → `system.power` {action: cancel}, risco low → executa (`intent_engine.py:292-293`; `skills/system/__init__.py:96-105`) | PRESERVADO | — |
| 7 | “o que você pode fazer”, “ajuda”, “o que você consegue fazer” | resposta fixa `HELP` | não | Sim — `commands.py:1091-1092, 1032-1035` | `response` com template `help` (`intent_engine.py:134-135`; `core/orchestrator.py:159-168`) | PRESERVADO | O texto atual inclui o número de skills. Nos dois, `\bajuda\b` casa em qualquer posição (“me ajuda a abrir o chrome” devolve a ajuda). |
| 8 | “que horas são” | resposta com a hora | não | Sim — `commands.py:1093-1094` | `response` (`intent_engine.py:129-130`) | PRESERVADO | — |
| 9 | “que dia é hoje”, “qual a data de hoje” | resposta com a data | não | Sim — `commands.py:1095-1097` | `response` (`intent_engine.py:131-133`) | PRESERVADO | — |
| 10 | “desligar”, “desligar assistente”, “encerrar jarvis” (frase exata) | só responde “Encerrando, senhor.” | não | **Stub**: `commands.py:1098-1099` só devolve texto, e nenhum código trata essa resposta (grep em `backend.py` e `jarvis_hud.py`) | “encerrar jarvis” → `command` → `app.close` {name: jarvis} (`intent_engine.py:558-560`), risco high → pede autorização e depois falharia (“não há processo conhecido”, `skills/applications/__init__.py:220-222`). “desligar”/“desligar assistente” → `unknown` | AUSENTE | O original não encerrava nada. No atual, “encerrar jarvis” gera um pedido de autorização inútil. |
| 11 | “desligue o computador”, “desligar o pc”, “desliga o pc” | `shutdown /s /t 15` | **sim** (12 s) | Sim — `commands.py:1101-1102, 335-347` | `system.power` {shutdown}, risco critical → autorização (`intent_engine.py:294-295`; `skills/system/__init__.py:88-111`) | PRESERVADO | Mesmo comando (15 s, cancelável). |
| 12 | “reinicie o computador”, “reiniciar o pc agora”, “reinicia o pc” | `shutdown /r /t 15` | sim | Sim — `commands.py:1103-1104` | `system.power` {restart} → autorização (`intent_engine.py:296-297`) | PRESERVADO | O atual exige verbo + “(o) computador/pc” juntos: “reinicie agora o computador” casava no original e vira `unknown`. |
| 13 | “suspender o computador”, “hibernar” | `rundll32 powrprof.dll,SetSuspendState 0,1,0` | sim | Sim — `commands.py:1105-1106` | `system.power` {sleep} → autorização (`intent_engine.py:298-299`) | PRESERVADO | O atual também aceita “suspenda”/“hiberne”. |
| 14 | “sair da conta”, “fazer logoff”, “encerrar sessão” | `shutdown /l` | sim | Sim — `commands.py:1107-1108` | `system.power` {logoff} → autorização (`intent_engine.py:300-301`) | PRESERVADO | O atual também aceita “encerrar a sessão”, que não casava no original. |
| 15 | “bloquear”, “bloquear o computador” | `LockWorkStation` | não | Sim — `commands.py:1109-1110, 329-332` | `system.lock`, risco medium → executa sem perguntar (`intent_engine.py:302-303`; `skills/system/__init__.py:114-123`) | PRESERVADO | O original casava `\bbloquear\b` em qualquer frase (“bloquear o site” bloqueava o PC). O atual usa fullmatch: aceita “bloqueie o computador”, mas “bloquear a tela” e “bloquear o computador agora” → `unknown`. |
| 16 | “desligue o wi-fi”, “ligue o bluetooth”, “ative o modo avião”, “desative o modo avião”, “desligar o uaifai”, “ativar o blutufe” | `control_radio` (PowerShell + WinRT Radio) | **sim quando desliga um rádio** (desligar Wi-Fi/Bluetooth ou ativar o modo avião) | Sim — `commands.py:1112-1119, 923-933, 521-540` | `system.radio`, mesma regex. Desligar → high → autorização; ligar → low → executa (`intent_engine.py:304-310`; `skills/system/__init__.py:144-185`) | PRESERVADO | — |
| 17 | “brilho para cinquenta por cento”, “aumente o brilho”, “diminua o brilho”, “brilho máximo”, “brilho” | `control_brightness` via WMI (±15 ou set 5-100); “brilho” sozinho → pede o nível | não | Sim — `commands.py:1121-1137, 912-921, 564-569` | `system.brightness` {set 50 / up / down / set 100}; “brilho” → `response` pedindo o nível (`intent_engine.py:311-323`) | PRESERVADO | O atual trata qualquer número como `set` (o original exigia “para/em/a/no/ao”). |
| 18 | “como está a bateria”, “status do sistema”, “situação do sistema” | `system_status` (bateria, Wi-Fi, Bluetooth, brilho) | não | Sim — `commands.py:1139-1140, 593-618` | `system.status` (`intent_engine.py:324-325`; `skills/system/__init__.py:218-256`) | PRESERVADO | O atual acrescenta “estado do sistema” e um fallback via psutil. |
| 19 | “abra a pasta C:\Users\…\Documentos” | `os.startfile` (exige pasta existente) | não | Sim — `commands.py:1142-1147` | `fs.open` {path}, low (`intent_engine.py:470-472`; `skills/filesystem/__init__.py:119-140`) | PRESERVADO | Nos dois, o caminho precisa ser dito ou digitado por extenso; na prática é um comando de texto. |
| 20 | “abra o arquivo relatorio.txt”, “abra o arquivo setup.exe” | `os.startfile` | **sim se a extensão for executável** (.exe, .bat, .ps1…) | Sim — `commands.py:1149-1157, 993` | `fs.open`; executável → high → autorização (`skills/filesystem/__init__.py:125-130`) | PRESERVADO | A lista atual de extensões inclui também .lnk, .jar e .sh. |
| 21 | “crie uma pasta Projetos”, “criar pasta Teste” | `os.makedirs` | não | Sim — `commands.py:1159-1162` (o harness criou a pasta) | `fs.create_folder`, low (`intent_engine.py:476-478`; `skills/filesystem/__init__.py:143-160`) | PRESERVADO | — |
| 22 | “renomear relatorio.txt para relatorio_final.txt” | `os.rename`/`os.replace` | sim | Sim — `commands.py:1164-1175` | `fs.move` {source, destination}, high → autorização (`intent_engine.py:485-487`; `skills/filesystem/__init__.py:320-343`) | PRESERVADO | O atual recusa se o destino existir; o original sobrescrevia com `os.replace` após a confirmação. |
| 23 | “mova o arquivo relatorio.txt para Documentos” | `shutil.move` | sim | Sim — `commands.py:1177-1184` | `fs.move` → autorização (`intent_engine.py:488-490`) | PRESERVADO | O atual aceita também “a pasta”. |
| 24 | “copie o arquivo relatorio.txt para copia.txt” | `_copy_path` | **sim só se o destino existir** (sobrescrita) | Sim — `commands.py:1186-1195, 369-385` | `fs.copy`: medium → executa; destino existente → high → autorização (`skills/filesystem/__init__.py:279-317`) | PRESERVADO | A sobrescrita difere: o original apagava o destino (com `rmtree` se fosse pasta); o atual copia para dentro da pasta e cria backup `.ultron.bak` do arquivo existente. |
| 25 | “exclua o arquivo relatorio.txt”, “apague a pasta X” | `send2trash` (Lixeira; fallback via `SHFileOperationW`) | sim | Sim — `commands.py:1197-1202, 388-412`. Porém “apague **a** pasta X” não casava (a regex só aceita “o”) e ia para o LLM | `fs.delete`, critical → autorização (`intent_engine.py:494-496`; `skills/filesystem/__init__.py:346-370`) | PRESERVADO | O atual exige o módulo send2trash (está no requirements, sem fallback ctypes) e recusa raiz, perfil e caminhos com até 2 partes (ex.: `C:\Temp`). |
| 26 | “procure o arquivo relatorio em Documentos”, “procurar arquivo orçamento” | `_find_files` (até 5 arquivos; raiz padrão = home) | não | Sim — `commands.py:1204-1208, 415-429` | `fs.search` {name, root}, none (`intent_engine.py:497-502`; `skills/filesystem/__init__.py:59-95`) | PRESERVADO | O atual devolve até 20 resultados, inclui pastas, ignora AppData/Windows/node_modules e tem limite de 25 s. |
| 27 | “abra o site g1.globo.com” | `webbrowser.open` (só http/https, sem credenciais) | não | Sim — `commands.py:1210-1213, 153-168` | `web.open_url` (`intent_engine.py:510-512`; `skills/browser/__init__.py:19-58`) | PRESERVADO | Mesma validação de URL. |
| 28 | “abra https://www.python.org”, “abra www.python.org” | `webbrowser.open` | não | Sim — `commands.py:1215-1218` | `web.open_url` (`intent_engine.py:513-515`) | PRESERVADO | — |
| 29 | “abra o youtube”, “abrir google” | abre youtube.com ou google.com | não | Sim — `commands.py:1220-1223` | `web.open_url` (`intent_engine.py:516-518`) | PRESERVADO | — |
| 30 | “youtube”, “google.com” (frase sozinha) | abre o site | não | Sim — `commands.py:1225-1227` | `unknown` (LLM) | PARCIAL | No atual só funciona com verbo (“abra o youtube”). |
| 31 | “feche a janela”, “fechar janela atual”, “feche esta janela” | Alt+F4 | sim | Sim — `commands.py:1229-1233` | `window.close`, high → autorização (`intent_engine.py:528-529`; `skills/windows/__init__.py:83-104`) | PRESERVADO | O atual fecha via API (não Alt+F4) e recusa quando a janela ativa é o próprio JARVIS. |
| 32 | “minimize a janela” | Win+↓ | não | Sim — `commands.py:1235-1236` | `window.state` {minimize} (`intent_engine.py:530-531`) | PRESERVADO | O atual aceita também “minimiza”. |
| 33 | “maximize a janela”, “maximizar janela” | Win+↑ | não | Sim — `commands.py:1237-1238` | `window.state` {maximize} (`intent_engine.py:532-533`) | PRESERVADO | — |
| 34 | “minimizar tudo”, “mostrar a área de trabalho” | Win+D | não | Sim — `commands.py:1239-1240` | `window.show_desktop` (`intent_engine.py:536-537`) | PRESERVADO | — |
| 35 | “trocar de janela”, “próxima janela” | Alt+Tab | não | Sim — `commands.py:1241-1242` | `input.press_key` {alt+tab} (`intent_engine.py:538-539`) | PRESERVADO | O atual acrescenta “vá para <app>” (`window.switch`). |
| 36 | “pesquise sobre receitas de bolo”, “pesquise músicas do Queen no youtube”, “busque previsão do tempo” | `search` no Google ou YouTube | não | Sim — `commands.py:1244-1249, 257-263` | `web.search` {query, site} (`intent_engine.py:519-524`; `skills/browser/__init__.py:61-73`) | PRESERVADO | — |
| 37 | “abra o bloco de notas”, “abrir calculadora”, “inicie o spotify”, “abra o navegador”, “abra o vs code”, “abra configurações”, “lance o discord” | `open_app` (só os 22 nomes de `APPS`) | não | Sim — `commands.py:1251-1256, 222-244, 39-62`. Fora da lista → “Não tenho o aplicativo X configurado.” | `app.open` {name}, low (`intent_engine.py:546-557`; `skills/applications/__init__.py:124-171`) | PRESERVADO | Ampliado: catálogo + índice do menu Iniciar (“abra o whatsapp” tenta abrir; o original recusava, e o `app_index.py` original não era importado por nenhum módulo). “abra as configurações” passou a funcionar. “lançar” (com ç) não casa em nenhum dos dois. |
| 38 | “feche o spotify”, “fechar o chrome”, “feche o navegador”, “feche a calculadora” | `taskkill /IM <processo>` (só nomes de `PROCS`) | sim | Sim — `commands.py:1258-1263, 247-254, 64-84` | `app.close`, high → autorização (`intent_engine.py:558-560`; `skills/applications/__init__.py:210-246`) | PRESERVADO | “navegador”: o original fechava o **msedge.exe** (`commands.py:69`) embora abrisse o Chrome; o atual fecha o Chrome. O atual também fecha Gerenciador de Tarefas e Configurações (o original recusava). |
| 39 | “aumente o volume”, “volume mais alto”, “volume maior” | tecla volumeup ×5 | não | Sim — `commands.py:1265-1266, 355-366` | `audio.volume` {up} (`intent_engine.py:564-565`; `skills/audio/__init__.py:25-59`) | PRESERVADO | O atual verifica o nível via pycaw. |
| 40 | “diminua o volume”, “abaixe o volume” | tecla volumedown ×5 | não | Sim — `commands.py:1267-1268` | `audio.volume` {down} (`intent_engine.py:566-567`) | PRESERVADO | — |
| 41 | “mudo”, “silenciar”, “silencie” | tecla volumemute | não | Sim — `commands.py:1269-1270` | `audio.volume` {mute} (`intent_engine.py:568-569`) | PRESERVADO | “silêncio”: o original silenciava o sistema; o atual trata como **cancelar** (`CANCEL_WORDS`, `intent_engine.py:30-32`). |
| 42 | “próxima música”, “próxima faixa” | tecla nexttrack | não | Sim — `commands.py:1271-1272` | `audio.media` {next} (`intent_engine.py:570-571`) | PRESERVADO | — |
| 43 | “música anterior” | tecla prevtrack | não | Sim — `commands.py:1273-1274` | `audio.media` {previous} (`intent_engine.py:572-573`) | PRESERVADO | — |
| 44 | “pausar”, “pausa”, “continuar”, “retomar”, “tocar música”, “pausa a música” | tecla playpause | não | Sim — `commands.py:1275-1276` (casa a substring em qualquer posição) | “pausar”, “tocar música”, “pausa a música”, “continuar a música” → `audio.media` {play_pause} (`intent_engine.py:574-576`). “continuar”, “retomar”, “pausa” sozinhos e “retomar a música” → `unknown` | PARCIAL | As alternativas explícitas “continuar”, “retomar” e “pausa” sozinhas não são reconhecidas. O original tinha falsos positivos (“continuar a tarefa” apertava play/pause). |
| 45 | “mova o mouse para 500, 300”, “mover cursor 100 200” | `moveTo` (valida os limites da tela) | não | Sim — `commands.py:1278-1284` | `input.move_mouse` {x, y} (`intent_engine.py:580-582`) | PRESERVADO | Nos dois só valem dígitos; números por extenso do Vosk não casam. |
| 46 | “duplo clique”, “clique duplo” | `doubleClick` | não | Sim — `commands.py:1286-1287` | `input.click` {double}, medium → executa (`intent_engine.py:583-584`) | PRESERVADO | — |
| 47 | “clique com o botão direito”, “clique direito” | `click(button=right)` | não | Sim — `commands.py:1288-1289` | `input.click` {right} (`intent_engine.py:585-586`) | PRESERVADO | — |
| 48 | “clique”, “clique esquerdo”, “clicar com botão esquerdo” | clique esquerdo na posição atual | não | Sim — `commands.py:1290-1291` | “clique”, “clique esquerdo” → `input.click` {left} (`intent_engine.py:587-588`). “clicar com botão esquerdo” → `unknown`. “clique no botão OK” → `vision.click_element` {description: OK}, high → autorização | PARCIAL | A alternativa explícita “clicar com botão esquerdo” foi perdida. Em “clique no X”, o original clicava na posição atual ignorando o alvo; o atual localiza o alvo (melhoria, mas o efeito é outro). |
| 49 | “rolar para baixo”, “descer a página” | `scroll(-3)` | não | Sim — `commands.py:1292-1293`. Provavelmente ineficaz no Windows: o pyautogui 0.9.54 passa o valor bruto a `mouse_event(MOUSEEVENTF_WHEEL)` (`_pyautogui_win.py:539`); como 120 = 1 entalhe, 3 ≈ 1/40 de entalhe (não testado em Windows) | `input.scroll` {down, 3} (`intent_engine.py:589-590`) | PRESERVADO | O atual usa amount×120 (`skills/automation/__init__.py:154`) e aceita “role para baixo”, que não casava no original. |
| 50 | “rolar para cima”, “subir a página” | `scroll(3)` | não | Idem ao item 49 — `commands.py:1294-1295` | `input.scroll` {up, 3} (`intent_engine.py:591-592`) | PRESERVADO | Idem ao item 49. |
| 51 | “digite olá mundo”, “escreva bom dia a todos” | cola via área de transferência + Ctrl+V | não (pela voz não havia checagem de terminal; só a ferramenta do agente checava, `commands.py:827-828`) | Sim — `commands.py:1297-1299, 318-321` | `input.type_text` {text}: medium → executa; terminal ativo → high → autorização (`intent_engine.py:593-595`; `skills/automation/__init__.py:41-76`) | PRESERVADO | O atual restaura a área de transferência; limite de 1000 caracteres. O pyperclip não está no requirements atual, mas vem como dependência transitiva (pyautogui → MouseInfo → pyperclip, conferido no setup.py dos pacotes). |
| 52 | “aperte enter”, “pressione esc”, “aperte espaço”, “aperte ctrl+c”, “aperte control+v”, “pressione alt+tab”, “aperte windows+d”, “enter”, “alt+tab”, “aperte delete”, “apagar”, “excluir” | `press`/`hotkey` (listas `KEYS`/`HOTKEYS`); Delete, “apagar” e “excluir” → tecla Delete | **sim para Delete** | Sim — `commands.py:1301-1309, 85-93` | “aperte enter/esc/espaço/ctrl+c/alt+tab/win+d” → `input.press_key`, low. “aperte delete” → high → autorização (`intent_engine.py:596-598`; `skills/automation/__init__.py:79-105`). “aperte control+v”, “control+c” e “windows+d” → `input.press_key`, mas a **validação recusa** (“tecla fora da lista permitida”). “enter”, “alt+tab”, “esc”, “tab”, “ctrl+v”, “apagar”, “excluir” e “delete” sozinhos → `unknown` | PARCIAL | Faltam: os aliases `control+…` e `windows+d` em `HOTKEYS` (`skills/automation/__init__.py:22-25`); tecla ou atalho dito sem verbo; “apagar”/“excluir” como tecla Delete. O atual ganhou setas, Home/End, F5, Ctrl+Z/S/F/T/W etc. |
| 53 | “tecla windows”, “tecla win”, “aperte windows” | `press('win')` | não | Sim — `commands.py:1310-1311` | “aperte/pressione windows” → `input.press_key` {windows}. “tecla windows”/“tecla win” → `unknown` | PARCIAL | As formas “tecla windows/win” (alternativas explícitas) não são reconhecidas. |
| 54 | “tire um print”, “captura de tela”, “screenshot” | `pyautogui.screenshot` salvo em `~/Pictures/Jarvis/captura_*.png` | não | Sim — `commands.py:1313-1314, 266-271` | `vision.screenshot`, low → executa (`intent_engine.py:461-462`; `skills/vision/__init__.py:193-217`) | PARCIAL | O atual recusa a captura quando a janela em foco é o próprio JARVIS (a HUD roda no mesmo processo: `app.py:323-330`; `perception/screen.py:112-126, 166-172`), ou quando há janela “sensível” ou app excluído. Um comando digitado na HUD tende a ser recusado (conclusão por leitura de código, não testado em Windows). A skill não é exposta ao LLM. “printscreen” sozinho não casa; o original casava a substring “print”, inclusive em “sprint”. |
| 55 | “Jarvis” sozinho (também “javis”, “ja vis”) | ativa a escuta e responde “Sim, senhor.” (texto vazio → “Ouvindo, senhor.”) | — | Sim — `backend.py:184-207, 1050-1061`; `commands.py:1060-1061` | Texto “Jarvis” → `response` “Estou ouvindo.” (`intent_engine.py:91-95`). Voz → WakeWordDetector + “Sim, senhor?”/“Pois não?” (`neural_core.py:682-687`; `voice/processor.py:144`) | PRESERVADO | “Jarvis, abra o bloco de notas” → `app.open` nos dois. |
| 56 | “sim”, “confirmo” / “não”, “cancelar”, “cancela” (com confirmação pendente) | executa ou cancela a ação pendente (expira em 12 s; qualquer outra frase descarta a pendência) | — | Sim — `commands.py:1047-1058, 114-123`. No harness, “feche o spotify” + “sim” → `close_app`; “não” → cancelada; após expirar, “sim” → não tratado | `AuthorizationManager.handle_reply` (YES/NO/ALWAYS, `agent/autonomy.py:104-127, 311-319`; `neural_core.py:388-399`), timeout de 30 s | PRESERVADO | Ampliado: “sim, sempre” cria autorização permanente com escopo (24 h) para ações low/medium reversíveis. |
| 57 | “cancelar”, “pare”, “para tudo”, “abortar”, “esquece”, “esqueça” (com o agente em execução) | aborta o plano do agente | — | Sim — `backend.py:864-865, 889-907` | `cancel` (`CANCEL_WORDS`, `intent_engine.py:30-32, 100-101`) → `NeuralCore.cancel` (`neural_core.py:382-387, 423-436`) | PRESERVADO | O atual também interrompe a fala e cancela autorizações. “esqueça” (que o original tinha como “esqueca”) não está em `CANCEL_WORDS` → `unknown`. |
| 58 | frase exata cadastrada (ex.: “modo foco”) | executa a ferramenta allowlisted da automação | conforme a ferramenta | Sim — `backend.py:773-802, 824` (detalhes na seção 3) | `command` com `source=automation` (`intent_engine.py:102-106`) | PARCIAL | Automações novas funcionam. As **automações importadas do banco original ficam inexecutáveis** e não há como pausar ou reativar automações (seção 3). |
| 59 | qualquer outra frase (perguntas, pedidos de várias etapas) | `ask_agent`: Ollama `qwen2.5:3b` com as 32 ferramentas (seção 2), até 10 passos e 12 chamadas | conforme a ferramenta | Sim — `backend.py:652-770, 805-837` | `unknown` → rota `agentic` (`cognition/decision_engine.py:52-54`). Pergunta sem verbo de ação → resposta direta; senão agente com as 12 skills mais “relevantes” (`core/orchestrator.py:171-180, 234`; `skills/registry.py:70-89`), até 8 passos e 10 chamadas (`settings.py:65-66`) | PRESERVADO | O original sempre oferecia todas as ferramentas; o atual oferece um subconjunto de 12 escolhido por palavra-chave. A seleção não foi verificada em Windows, porque `relevant()` filtra skills indisponíveis no Linux. |

---

## 2) Ferramentas do agente (LLM) no original

Há dois conjuntos de ferramentas no original:
- **Caminho de conversa (principal):** `backend.ask_agent` usa `AGENT_TOOL_DEFINITIONS = commands.TOOL_DEFINITIONS (25) + MEMORY_TOOL_DEFINITIONS (7)` (`backend.py:418-438`).
- **Caminho agêntico do Observador:** `copilot._start_agentic_task` → `neural_core.observe` → `autonomous_core` → `autonomous_agent_runtime` → `execution_loop.run` → `agent.run` (`execution_loop.py:60`; `agent.py:126`). Ele usa `tools.DEFINITIONS = commands.TOOL_DEFINITIONS + EXTRA_DEFINITIONS (16)` (`tools.py:36-75`), com 9 nomes novos; os outros 7 reimplementam as ferramentas de memória e automação com `memory.py`/`automation.py`.

Todas usam JSON Schema com `additionalProperties: false`. Shell, CMD, PowerShell e Python livres são proibidos (`config.py:71-74`).

| # | Ferramenta (original) | Parâmetros | O que faz / confirmação (original) | Onde (original) | Equivalente atual (skill, arquivo:linha) | Status | Observação |
|---|---|---|---|---|---|---|---|
| 1 | `open_app` | name ∈ APPS (22 nomes) | abre um app do catálogo | `commands.py:683-684, 763-768` | `app.open` (`skills/applications/__init__.py:124`) | PRESERVADO | Sem enum: aceita qualquer nome (catálogo + menu Iniciar). |
| 2 | `search_web` | query ≤300; site ∈ {google, youtube} | pesquisa | `commands.py:685-687, 770-776` | `web.search` (`skills/browser/__init__.py:61`) | PRESERVADO | — |
| 3 | `open_url` | url | abre http/https sem credenciais | `commands.py:688, 778-781` | `web.open_url` (`skills/browser/__init__.py:44`) | PRESERVADO | — |
| 4 | `control_volume` | direction ∈ {up, down, mute} | 5 toques de tecla ou mudo | `commands.py:689-690, 783-789` | `audio.volume` (`skills/audio/__init__.py:25`) | PRESERVADO | — |
| 5 | `control_media` | action ∈ {play_pause, next, previous} | tecla de mídia | `commands.py:691-692, 791-797` | `audio.media` (`skills/audio/__init__.py:62`) | PRESERVADO | — |
| 6 | `control_window` | action ∈ {minimize, maximize, switch, close} | atalhos; **close pede confirmação** (Alt+F4) | `commands.py:693-694, 799-808` | `window.state` (`skills/windows/__init__.py:51`), `window.close` (`:83`, high → autorização), `window.switch` (`:28`, exige alvo) ou `input.press_key` alt+tab | PRESERVADO | Dividida em várias skills. |
| 7 | `move_mouse` | x, y (inteiros dentro da tela) | move o cursor | `commands.py:695-696, 831-837` | `input.move_mouse` (`skills/automation/__init__.py:108`) | PRESERVADO | — |
| 8 | `mouse_click` | button ∈ {left, right, double} | clique; **sempre pede confirmação** | `commands.py:697-698, 839-845` | `input.click` (`skills/automation/__init__.py:130`): medium e irreversível; com origem agent no nível balanced → autorização (`agent/autonomy.py:92-95`) | PRESERVADO | No nível `autonomous` (perfil developer, `config/profiles.py:45-48`), clica sem perguntar. |
| 9 | `scroll` | direction ∈ {up, down}; amount 1-10 | rolagem | `commands.py:699-701, 847-852` | `input.scroll` (`skills/automation/__init__.py:146`), amount 1-15 | PRESERVADO | — |
| 10 | `take_screenshot` | — | salva um PNG | `commands.py:702, 854-856` | `vision.screenshot` (`skills/vision/__init__.py:193`) com **`expose_to_llm=False`** | PARCIAL | O LLM não pode chamá-la; só por comando direto. |
| 11 | `inspect_screen` | question ≤300 | captura em memória + `qwen2.5vl:3b` | `commands.py:703-704`; tratada em `backend.py:708-725` e `tools.py:99-108` | `vision.inspect_screen` (`skills/vision/__init__.py:74`) | PRESERVADO | Tem bloqueios de privacidade (HUD/JARVIS em foco, janela sensível). |
| 12 | `search_files` | name; root opcional | busca até 5 arquivos | `commands.py:705-706, 862-866` | `fs.search` (`skills/filesystem/__init__.py:59`) | PRESERVADO | — |
| 13 | `open_path` | path | abre arquivo ou pasta; **executável → confirmação** | `commands.py:707, 868-876` | `fs.open` (`skills/filesystem/__init__.py:119`) | PRESERVADO | — |
| 14 | `create_folder` | path | cria pasta | `commands.py:708, 878-882` | `fs.create_folder` (`skills/filesystem/__init__.py:143`) | PRESERVADO | — |
| 15 | `move_path` | source, destination | move; **confirmação** | `commands.py:709-710, 884-892` | `fs.move` (`skills/filesystem/__init__.py:320`), high | PRESERVADO | — |
| 16 | `copy_path` | source, destination | copia; **confirmação se o destino existe** | `commands.py:711-712, 893-896` | `fs.copy` (`skills/filesystem/__init__.py:279`) | PRESERVADO | — |
| 17 | `delete_path` | path | envia à Lixeira; **confirmação** | `commands.py:713-714, 898-903` | `fs.delete` (`skills/filesystem/__init__.py:346`), critical | PRESERVADO | — |
| 18 | `close_app` | name ∈ PROCS | `taskkill /IM`; **confirmação** | `commands.py:715-716, 905-910` | `app.close` (`skills/applications/__init__.py:210`), high | PRESERVADO | — |
| 19 | `power_control` | action ∈ {shutdown, restart, sleep, logoff} | energia; **sempre pede confirmação** | `commands.py:717-718, 947-954` | `system.power` (`skills/system/__init__.py:88`) com **`expose_to_llm=False`** | PARCIAL | Só por comando direto; o LLM não pode chamá-la. |
| 20 | `control_brightness` | action ∈ {up, down, set}; level 5-100 | brilho via WMI | `commands.py:719-721, 912-921` | `system.brightness` (`skills/system/__init__.py:188`) | PRESERVADO | — |
| 21 | `control_radio` | radio ∈ {wifi, bluetooth, airplane}; state ∈ {on, off} | rádios; **confirmação ao desligar** | `commands.py:722-724, 923-933` | `system.radio` (`skills/system/__init__.py:144`) | PRESERVADO | — |
| 22 | `system_status` | — | bateria, rádios e brilho | `commands.py:725, 935-937` | `system.status` (`skills/system/__init__.py:218`) | PRESERVADO | — |
| 23 | `type_text` | text ≤500 | cola o texto; **confirmação se houver terminal ativo** | `commands.py:726-727, 824-829` | `input.type_text` (`skills/automation/__init__.py:41`) | PRESERVADO | — |
| 24 | `press_key` | key ∈ KEYS ∪ HOTKEYS ∪ {delete} | tecla ou atalho; **Delete e Enter em terminal → confirmação** | `commands.py:728-729, 810-822` | `input.press_key` (`skills/automation/__init__.py:79`) | PRESERVADO | Sem os aliases `control+…` e `windows+d`; com mais teclas que o original. |
| 25 | `wait_seconds` | seconds 1-10 | espera | `commands.py:730-731, 939-945` | `system.wait` (`skills/system/__init__.py:126`), 1-15 | PRESERVADO | — |
| 26 | `remember_fact` | subject ≤80; fact ≤500 | grava na tabela SQLite `memories` | `backend.py:419-421, 516-525` (também `tools.py:37-39` → `memory.py:137-148`) | `memory.remember` (`skills/memory/__init__.py:8`) | PRESERVADO | — |
| 27 | `recall_facts` | query ≤120 | LIKE, até 5 resultados | `backend.py:422-423, 528-539` | `memory.recall` (`skills/memory/__init__.py:30`) | PRESERVADO | Busca mais ampla (fatos, episódios, procedimentos, conceitos). |
| 28 | `forget_fact` | subject | apaga um fato; **confirmação falada** | `backend.py:424-425, 624-629` | `memory.forget` (`skills/memory/__init__.py:48`), high | PRESERVADO | — |
| 29 | `set_personality` | style ∈ PERSONALITIES | só aceita “jarvis” (personalidade travada, `config.py:29`) | `backend.py:426-427, 482-496` | — nenhum | AUSENTE | Inócua no original. |
| 30 | `create_automation` | name ≤60; trigger ≤100; tool_name na allowlist de 7; arguments | cria automação por frase exata | `backend.py:428-433, 581-595` | `automation.create` (`skills/automation/__init__.py:163`), allowlist de 8 skills (`:159-160`) | PARCIAL | Não aceita captura de tela; acrescenta `network.status` e `diagnostics.system_report`. |
| 31 | `list_automations` | — | lista as automações | `backend.py:434, 598-605` | `automation.list` (`skills/automation/__init__.py:190`) | PRESERVADO | — |
| 32 | `delete_automation` | name | remove; **confirmação falada** | `backend.py:435-436, 643-648` | `automation.delete` (`skills/automation/__init__.py:209`), high | PRESERVADO | — |
| 33 | `get_profile` | — | lê perfil e preferências | `tools.py:46, 139-142` | — sem skill; as preferências entram no contexto do prompt (`cognition/context_engine.py:67-80`) | PARCIAL | Não há ferramenta explícita. |
| 34 | `set_preference` | name ∈ {profile_name, city, language, address_me_as}; value ≤200 | grava preferência | `tools.py:47-49, 143-147` | `memory.set_preference` (`skills/memory/__init__.py:68`), lista ampliada (`memory/preference_memory.py:8-16`) | PRESERVADO | — |
| 35 | `add_session_note` | note ≤300 | anota contexto da sessão | `tools.py:50-51, 148-152` | — nenhum (a tabela `session_notes` existe em `memory/store.py:92`, mas nada grava nela) | AUSENTE | — |
| 36 | `read_audit` | limit 1-20 | lê a auditoria local | `tools.py:52-53, 153-156` | — sem skill; a auditoria só aparece no painel da HUD (`hud/panels.py:1331`) | PARCIAL | — |
| 37 | `set_automation_enabled` | name; enabled | pausa ou reativa automação | `tools.py:61-63, 166-170` | `ProceduralMemory.set_automation_enabled` (`memory/procedural_memory.py:149-151`) existe, mas nenhuma skill, intent ou HUD o chama | AUSENTE | — |
| 38 | `ocr_screen` | — | OCR via pytesseract (fora do requirements original) | `tools.py:66, 177-185` | `vision.read_text` (`skills/vision/__init__.py:105`) | PRESERVADO | — |
| 39 | `list_ui_elements` | — | UI Automation via pywinauto (fora do requirements original) | `tools.py:67, 186-194` | `vision.ui_elements` (`skills/vision/__init__.py:131`) | PRESERVADO | — |
| 40 | `locate_on_screen` | description ≤200 | localiza elemento por OCR e UIA | `tools.py:68-69, 195-200` | `vision.locate` (`skills/vision/__init__.py:148`) | PRESERVADO | — |
| 41 | `click_by_description` | description ≤200 | clica num alvo único; **confirmação** | `tools.py:70-71, 201-215` | `vision.click_element` (`skills/vision/__init__.py:166`), high | PRESERVADO | — |

**Código morto ou stub no original** (não contado): `visual_agent.py` e a ferramenta `visual_computer_task` aparecem só em `LEIA-ME-INTEGRACAO.md:38` e nunca foram registrados em nenhuma lista de ferramentas. `app_index.py` não é importado e chama `config.db_dir()`, que não existe (`app_index.py:64`; `config.py:87-95`). `computer_control.py` não é importado. O copilot tinha sua própria allowlist de sugestões (`PROACTIVE_TOOLS`, `copilot.py:96-100`, inclui `run_automation`); essas sugestões vêm do modelo de visão e não são ferramentas do agente de conversa.

---

## 3) Automações por frase exata

### 3.1 Original

- **Armazenamento:** SQLite em `%LOCALAPPDATA%\JARVIS\assistant.sqlite3` (`backend.py:442-444`), tabela `automations(name TEXT PRIMARY KEY, trigger_text TEXT NOT NULL UNIQUE, tool_name TEXT NOT NULL, arguments TEXT NOT NULL /*JSON*/, enabled INTEGER NOT NULL DEFAULT 1)` (`backend.py:465-467`). Há uma implementação duplicada com o mesmo arquivo e esquema em `memory.py:45-77` + `automation.py`, usada pelo caminho agêntico (`tools.py`).
- **Criação:** só pelo agente LLM, com a ferramenta `create_automation`. O `commands.handle` não tem regex para criar, listar ou remover automações.
- **Validação** (`backend.py:549-578` = `automation.py:25-54`):
  - `tool_name` precisa estar em `SAFE_AUTOMATION_ARGUMENTS` = {open_app, search_web, open_url, control_volume, control_media, take_screenshot, search_files} (`backend.py:132-140`; `config.py:76-84`).
  - Só argumentos permitidos, e todos os obrigatórios.
  - O app precisa estar em `APPS`; a URL precisa ser http/https sem credenciais (é normalizada); o site precisa ser google ou youtube; volume e mídia seguem os enums.
  - Limites: nome ≤60 e frase ≤100 caracteres.
- **Normalização da frase:** minúsculas, sem acentos, pontuação vira espaço, espaços colapsados (`backend.py:478-479`). Ex.: “Modo foco!” → `modo foco`.
- **Disparo:** acontece só se `commands.handle` **não** tratou o texto (`backend.py:818-827`). Exige igualdade exata com `trigger_text` e `enabled=1` (`backend.py:773-787`). Executa com `commands.execute_tool` (mesmas confirmações) e depois `verify_tool`; se não verificar, responde “A automação X terminou sem verificação…” (`backend.py:788-802`).
- **Listar e remover:** ferramentas `list_automations` e `delete_automation` (esta com confirmação falada).
- **Pausar e reativar:** só pela ferramenta `set_automation_enabled` de `tools.py`, disponível apenas no caminho agêntico do Observador.
- **Evidência executada** (`run_automations.py`, ações substituídas por registradores):
  - Criadas: `foco`/“Modo foco!”/open_app {spotify}; `noticias`/open_url; `print`/take_screenshot; `youtube`/“abra o youtube”/search_web.
  - Recusadas: delete_path (“Ação de automação não permitida”), whatsapp (“Aplicativo não configurado”) e argumento extra.
  - Disparam: “modo foco” e “MODO FOCO.”. Não disparam: “modo  foco agora” e “Jarvis, modo foco” (o texto chega cru quando digitado na HUD; pela voz, a palavra de despertar já é removida antes).
  - “abra o youtube” como gatilho fica **sombreado** pelo comando embutido (regra 29), porque `commands.handle` roda antes.

### 3.2 Atual

- **Armazenamento:** `%LOCALAPPDATA%\ULTRON\ultron.sqlite3` (`config/paths.py:33-55`), tabela `automations` com o mesmo esquema (`memory/store.py:82-87`). A coluna `tool_name` agora guarda o **nome da skill** (ex.: `app.open`).
- **Criação:** skill `automation.create` (pelo LLM; não há regra de voz). “crie uma automação…” → `unknown` → agente; nesse teste em Linux, `automation.create` estava entre as 12 skills relevantes.
  - Allowlist `SAFE_AUTOMATION_SKILLS` = {app.open, web.search, web.open_url, audio.volume, audio.media, fs.search, network.status, diagnostics.system_report} (`skills/automation/__init__.py:159-160`).
  - Os argumentos são validados pelo schema da skill alvo, e a gravação é verificada lendo de volta (`skills/automation/__init__.py:172-187`).
- **Normalização:** equivalente à do original (`memory/procedural_memory.py:117-121`).
- **Disparo:** `IntentEngine.classify` consulta as automações **antes** das regras embutidas, logo depois de remover a palavra de despertar e de checar objetivos proibidos e cancelamento (`intent_engine.py:91-106`). A origem é `automation` (`cognition/planner_engine.py:107-110`) → decisão de autonomia (low executa).
- **Listar:** “listar automações” e “quais são as automações” → `automation.list` (`intent_engine.py:448-449`); “liste as automações” → `unknown`.
- **Remover:** “remova a automação X” → `automation.delete`, high → autorização (`intent_engine.py:450-452`).
- **Pausar e reativar:** o método existe (`procedural_memory.py:149-151`), mas nada o chama.
- **Migração do banco original:** `legacy_import.py:52-57` copia `tool_name` **literalmente** (`memory/system.py:45-48` faz isso no boot, uma única vez).
  - Teste: as 4 automações criadas pelo código original foram importadas (`{'automations': 4}`). “modo foco” → `command` skill=`open_app` → `ExecutionEngine.execute` → `refused: skill 'open_app' não existe ou não é permitida` (`agent/execution.py:117-120`). O mesmo aconteceu com `search_web` e `take_screenshot`.
  - Como as automações têm prioridade sobre as regras, a automação legada “abra o youtube” passa a quebrar também o comando embutido “abra o youtube”.
  - O teste `tests/test_memory.py:98` usa `'app.open'` no banco legado de exemplo, por isso não detecta o problema. A documentação afirma que os dados do usuário não são perdidos (`ARCHITECTURE_REPORT.md:200-201`; `README_ULTRON.md:262-264`).

### 3.3 Comparação

| Aspecto | Original | Atual | Status |
|---|---|---|---|
| Armazenamento/esquema | `assistant.sqlite3`, tabela `automations` | `ultron.sqlite3`, mesmo esquema, `tool_name` = nome da skill | PRESERVADO |
| Criação (via agente) | `create_automation`, 7 ferramentas | `automation.create`, 8 skills | PARCIAL (sem captura de tela) |
| Validação | allowlist + argumentos + catálogo de apps + URL | allowlist + schema da skill alvo + URL | PRESERVADO (o app não precisa mais estar no catálogo) |
| Gatilho por frase exata/normalização | igualdade normalizada; comando embutido tem prioridade | igualdade normalizada; remove “Jarvis,”; **a automação tem prioridade** sobre o comando embutido | PRESERVADO (prioridade invertida) |
| Execução/confirmação/verificação | `execute_tool` + `verify_tool` | `ExecutionEngine` + autonomia + `VerificationEngine` | PRESERVADO |
| Listar | ferramenta do LLM | skill do LLM + frase direta | PRESERVADO |
| Remover com confirmação | ferramenta + “sim” | skill high + autorização | PRESERVADO |
| Pausar/reativar | `set_automation_enabled` (caminho agêntico) | método sem acesso | AUSENTE |
| Migração das automações existentes | — | importadas com nomes antigos e inexecutáveis | AUSENTE |

---

## 4) Resumo

**Contagem por status**

| Seção | PRESERVADO | PARCIAL | AUSENTE | Total |
|---|---|---|---|---|
| 1. Comandos (54 rotas de `commands.handle` + 5 do backend) | 46 | 10 | 3 | 59 |
| 2. Ferramentas do agente LLM | 33 | 5 | 3 | 41 |
| 3. Aspectos das automações por frase | 6 | 1 | 2 | 9 |

**Itens PARCIAL/AUSENTE e o que falta exatamente**

Comandos (seção 1):
1. **#1 Ativar Observador (PARCIAL):** “observador” e “modo observador” sozinhos vão para o LLM. O efeito atual só liga `screen_observation`, sem as tarefas agênticas autônomas do Observador, e vem ligado por padrão (o original iniciava desligado).
2. **#2 “acompanhe o que eu fizer no computador” / “me ajude com o código/pc/tela” (PARCIAL):** nenhuma frase é reconhecida; vão para o LLM.
3. **#3 Desativar Observador (PARCIAL):** “pare o observador” e “parar observador” não são reconhecidas (a regex atual exige “pare de”).
4. **#4 e #5 Pausar e retomar o Observador (AUSENTE):** não há comando nem conceito de pausa e retomada (o original pausava capturas e o agente).
5. **#10 “desligar” / “desligar assistente” / “encerrar jarvis” (AUSENTE; no original era stub que só respondia “Encerrando, senhor.”):** hoje “encerrar jarvis” vira `app.close(jarvis)`, com pedido de autorização que depois falha.
6. **#30 “youtube” / “google.com” sozinhos (PARCIAL):** exigem verbo (“abra o youtube”).
7. **#44 Play/pause (PARCIAL):** “continuar”, “retomar” e “pausa” sozinhos, e “retomar a música”, vão para o LLM.
8. **#48 Clique esquerdo (PARCIAL):** “clicar com botão esquerdo” vai para o LLM. “clique no X” virou clique por descrição (`vision.click_element`, com autorização), em vez de clicar na posição atual.
9. **#52 Teclas e atalhos (PARCIAL):**
   - Os aliases “control+c/v/a” e “windows+d” são recusados na validação.
   - Tecla ou atalho dito sem verbo (“enter”, “esc”, “tab”, “alt+tab”, “ctrl+v”, “win+d”) vai para o LLM.
   - “apagar”, “excluir” e “delete” sozinhos, como tecla Delete com confirmação, vão para o LLM.
10. **#53 “tecla windows” / “tecla win” (PARCIAL):** só “aperte/pressione windows” funciona.
11. **#54 Captura de tela (PARCIAL):** é recusada quando o JARVIS/HUD está em foco (a HUD roda no mesmo processo), em janela sensível ou em app excluído, então o comando digitado na HUD tende a falhar. A skill também não é exposta ao LLM.
12. **#58 Automações por frase (PARCIAL):** ver os itens 18 a 20.

Ferramentas do agente (seção 2):

13. **`take_screenshot` e `power_control` (PARCIAL):** existem como `vision.screenshot` e `system.power`, mas com `expose_to_llm=False`; o LLM não pode chamá-las.
14. **`create_automation` (PARCIAL):** a allowlist não inclui captura de tela.
15. **`get_profile` (PARCIAL):** não há ferramenta; o perfil só entra no contexto do prompt.
16. **`read_audit` (PARCIAL):** a auditoria só aparece no painel da HUD.
17. **AUSENTE:**
    - `set_personality` — inócua no original, onde a personalidade estava travada em “jarvis”.
    - `add_session_note` — a tabela `session_notes` existe, mas nada grava nela.
    - `set_automation_enabled` — o método existe, mas nada o chama.

Automações (seção 3):

18. **Migração (AUSENTE):** o `legacy_import` copia `tool_name` sem mapear, então as automações do banco original (open_app, search_web, open_url, control_volume, control_media, take_screenshot, search_files) são importadas, mas o `ExecutionEngine` as recusa (“skill 'open_app' não existe”).
    - Como as automações agora têm prioridade sobre as regras, uma automação legada pode também quebrar um comando embutido de mesma frase (demonstrado com “abra o youtube”).
    - Falta mapear: open_app→app.open, search_web→web.search, open_url→web.open_url, control_volume→audio.volume, control_media→audio.media, search_files→fs.search. Para take_screenshot não há skill permitida.
    - Falta também corrigir `tests/test_memory.py:98`, que usa `app.open` no banco legado de exemplo.
19. **Pausar e reativar automação (AUSENTE):** nenhuma skill, regra de voz ou controle na HUD.
20. **Criação (PARCIAL):** não aceita automação de captura de tela.

**Não verificado:** os efeitos reais no Windows (PowerShell/WinRT, taskkill, LockWorkStation, pycaw, foco de janelas); a seleção `relevant()` de 12 skills em Windows (no Linux várias skills ficam indisponíveis); o comportamento do LLM nas frases que caem em `unknown`; e a eficácia de `pyautogui.scroll(±3)` no Windows (inferida a partir do código do pyautogui 0.9.54).
