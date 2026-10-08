# J.A.R.V.I.S. — NEURAL CORE 2.0

Esta é a versão consolidada do projeto.

## Iniciar
1. Instale Python 3.11.
2. Execute `INSTALAR_JARVIS.bat`.
3. Garanta que o Ollama esteja instalado e que o modelo configurado em `config.py` esteja disponível.
4. Execute `START_JARVIS.bat`.

A entrada oficial é `main.py`, que abre `jarvis_hud.py`.

## O que mudou
- Nova interface Neural HUD centrada no cérebro holográfico.
- Conexões aparecem conforme o Neural Core usa cada módulo.
- O Neural Core agora atualiza diretamente o `neural_hud_engine`.
- Voz, escuta, execução, visão, memória, skills, arquivos, Windows e web têm nós próprios.
- O HUD não é mais o painel antigo com o cérebro adicionado por cima.
- `jarvis_hud.py` é agora a interface oficial.
- Backups das interfaces antigas foram removidos desta distribuição.

## Importante
A validação feita no ambiente de desenvolvimento é de código/estrutura. O runtime de Windows, microfone, PySide6 e Ollama deve ser validado no seu PC.
