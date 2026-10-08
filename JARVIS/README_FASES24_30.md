# J.A.R.V.I.S. — FASES 24–30

## Objetivo
Integração do núcleo autônomo em um ciclo contínuo, mantendo as camadas anteriores como autoridades especializadas.

### 24 — Persistent Autonomous Loop
`autonomous_loop.py` observa continuamente. Por segurança, a promoção automática de uma percepção para missão fica DESLIGADA por padrão (`JARVIS_AUTONOMOUS_ACTIONS=0`).

### 25 — Windows Perception Integration
O loop consulta `windows_state_adapter` e `perception_engine`, combinando estado estrutural e evidência de tela quando disponíveis.

### 26 — Computer Control Integration
O controle continua em `computer_control.py`/`commands.py` e não recebe permissões novas do loop. A allowlist permanece autoridade final.

### 27 — Mission Manager
`mission_manager.py` mantém fila, prioridade, estado, resultado, cancelamento e histórico.

### 28 — Long-Running Agent
`long_running_agent.py` executa missões em background, uma por vez, usando o `autonomous_agent_runtime` existente.

### 29 — Multimodal Context
`multimodal_context.py` consolida tela, janela, Windows, voz/texto, conversa e World Model em evidência estruturada.

### 30 — Integrated Verification / Recovery
O `execution_loop.py` já fecha cada tentativa com observação ativa, verificação, comparação de estado e recovery/replan. O Runtime continua usando esse único ciclo.

## Ativação
Por padrão, o loop persistente NÃO cria missões automaticamente. Para permitir promoção automática de observações de baixo risco:

`JARVIS_AUTONOMOUS_ACTIONS=1`

Intervalo padrão: 3 segundos, configurável por `JARVIS_AUTONOMOUS_LOOP_INTERVAL`.

## Limites
- Sem shell arbitrário.
- Texto na tela não é tratado como instrução confiável.
- Ações destrutivas continuam sujeitas ao Human-in-the-Loop e às ferramentas autorizadas.
- Este pacote foi compilado e testado por smoke tests no ambiente disponível. A integração real com Windows, mouse, teclado, OCR/UI Automation e Ollama deve ser validada no Windows do usuário.
