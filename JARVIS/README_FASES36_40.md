# J.A.R.V.I.S. — FASES 36–40

## 36 — Neural HUD 2.0
`neural_hud_engine.py` mantém o estado visual do cérebro e módulos ativos. A HUD usa eventos reais do Neural Core para energizar conexões.

## 37 — Voice Pipeline
`voice_pipeline.py` controla estado de escuta/fala, interrupção e fala proativa sem substituir o backend de voz existente.

## 38 — Live State
`live_hud_state.py` oferece snapshots thread-safe para estado vivo de Windows, World Model, voz e runtime.

## 39 — Skill Visualization
`skill_visualizer.py` transforma Skills registradas em módulos visuais. Skills não ganham autorização de execução.

## 40 — Proactive Voice Policy
`proactive_voice.py` aplica cooldown a mensagens proativas e gera uma formulação curta no tom JARVIS.

### Princípio
O HUD é uma projeção do estado do cérebro. Nenhum desses módulos executa ferramentas ou concede permissões.

### Validação
Smoke tests são determinísticos e não dependem de Windows, PySide6, microfone, display ou Ollama real. Runtime Windows ainda requer validação na máquina do usuário.
