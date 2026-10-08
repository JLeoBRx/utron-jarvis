# JARVIS — Neural Core

Esta versão restaura o cérebro central como camada executiva sobre o Observador e o agente multietapas.

Fluxo:

`OBSERVADOR -> PERCEPÇÃO -> CONTEXTO -> DECISÃO -> ROTEAMENTO -> PLANEJAMENTO -> EXECUÇÃO -> VERIFICAÇÃO -> RECUPERAÇÃO -> MEMÓRIA/RESULTADO`

O Observador não é mais o executor principal: ele entrega percepções ao `neural_core.py`. O Core cria um objetivo, evita repetição por cooldown, mantém estado, escolhe a inteligência disponível e entrega o objetivo ao `agent.py`, que continua usando a allowlist de ferramentas, confirmação para ações sensíveis e verificação.

Estados do núcleo: IDLE, PERCEIVING, CONTEXT, DECIDING, ROUTING, PLANNING, EXECUTING, VERIFYING, RECOVERY, WAITING, DONE e ERROR.

O HUD pode consumir os eventos `neural` emitidos pelo Observador para representar o cérebro e suas conexões.

Esta versão não promete autonomia irrestrita: ações perigosas continuam exigindo as proteções existentes e o núcleo não possui shell livre.
