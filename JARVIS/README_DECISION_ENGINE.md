# JARVIS — Fase 5: Decision Engine + Goal Manager

O Neural Core agora separa quatro perguntas:

1. **O que estou vendo?** — Perception Engine
2. **O que isso significa?** — Context/Intent Engine
3. **Devo fazer alguma coisa?** — Decision Engine
4. **Qual é o objetivo acompanhado pelo agente?** — Goal Manager

Decisões possíveis:

- `observe`: continuar observando sem interromper.
- `ask`: pedir autorização/decisão ao usuário.
- `act`: entregar o objetivo ao agente multietapas.
- `ignore`: bloquear a intervenção, inclusive diante de conteúdo sensível ou instruções não confiáveis na tela.

A decisão não executa ferramentas. O agente continua responsável pela execução, allowlist, confirmações, verificação e recuperação.
