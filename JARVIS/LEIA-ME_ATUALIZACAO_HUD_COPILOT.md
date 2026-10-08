# Atualização: HUD flutuante + automação inteligente (copilot)

## Arquivos
- NOVO  `copilot.py`        — observação da tela, sugestões, modos, limites, segurança
- ALTERADO `jarvis_hud.py`  — timer de 7 s removido; botão flutuante; barra de automação; painel; avisos
- ALTERADO `backend.py`     — `_ollama_chat(options, fmt, timeout)`, `is_busy()`, `run_exclusive()`
- ALTERADO `commands.py`    — `capture_screen_image()`, `encode_image_base64()`, `foreground_info()`, `cancel_pending()`
- `_backup_antes_do_copilot/` — cópias originais de jarvis_hud.py, backend.py, commands.py
- `_testes/`                — test_copilot.py e test_hud_logica.py

## Instalação
Copie os arquivos para a pasta do JARVIS (sobrescrevendo). Dependências (já usadas no projeto):
`pip install PySide6 psutil pyautogui pillow` (+ as que você já tem: vosk, pyaudio, pyttsx3, pyperclip).
Modelo de visão: `ollama pull qwen2.5vl:3b`.

## Comportamento
- A HUD não minimiza mais sozinha (IDLE_TIMEOUT removido; Esc também não minimiza; fechar = minimizar).
- O JARVIS agora INICIA só com o botão flutuante; clique nele (ou diga "Jarvis") para abrir.
- Modo da automação sempre inicia DESATIVADO (copilot.RESTORE_MODE_ON_START = False).
- A HUD aberta cobre a tela inteira: nesse estado o copilot não observa (indicador mostra "OBSERVAÇÃO SUSPENSA").
  Para ele trabalhar, minimize a HUD.
- Ajustes em copilot.py (topo do arquivo): limites, intervalos, SPEAK_SUGGESTIONS, apps/títulos sensíveis.
