# J.A.R.V.I.S. — camada de autonomia contextual

## O que mudou

O modo **OBSERVADOR** deixou de ser apenas um monitor de sugestões. Quando a visão local encontra uma situação claramente útil e com confiança suficiente, ela pode entregar o contexto ao `agent.py`.

Fluxo:

1. captura temporária em memória;
2. análise local pelo Ollama Vision;
3. filtro de conteúdo sensível e prompt injection na tela;
4. criação de objetivo operacional;
5. planejamento multietapas pelo agente;
6. execução somente por ferramentas registradas;
7. verificação após cada ação;
8. recuperação quando uma ação falha;
9. confirmação para ações protegidas;
10. conclusão falada e registrada no histórico.

## Proteções

- sem shell, CMD, PowerShell ou execução de código livre;
- allowlist de ferramentas;
- confirmação para ações de maior risco;
- limite de etapas e chamadas;
- cancelamento pelo botão PARAR TAREFA;
- pausa do agente quando a automação é pausada;
- cooldown contra repetição do mesmo plano;
- observação visual suspensa enquanto o agente trabalha;
- exclusão de janelas/conteúdo sensível já prevista no Observador.

## Visão estruturada

Foi incluído `vision.py`, que fornece interfaces para:

- OCR opcional (`pytesseract` + Tesseract);
- UI Automation opcional (`pywinauto`);
- localização de elementos;
- clique em alvo único somente depois da confirmação;
- inspeção visual pelo Ollama local.

Esses recursos são opcionais. Sem eles, o JARVIS continua funcionando com as ferramentas básicas.

## Limitação desta entrega

A implementação foi validada por análise estática e compilação Python. O runtime real de Windows, microfone, PySide6, Ollama e drivers de automação não foi executado neste ambiente Linux.


## Fase Neural Core — cérebro restaurado
- `neural_core.py` virou o orquestrador central do fluxo autônomo.
- O Observador entrega percepções ao Core em vez de chamar o agente diretamente.
- O Core mantém contexto, objetivo, estados, cooldown, roteamento e ciclo de execução/verificação/recuperação.
- O `agent.py` permanece como executor multietapas com allowlist e confirmações.

## Fase 14 — Action Selection / Tool Intelligence
- Adicionado `action_selector.py` para ranquear ferramentas candidatas por objetivo/contexto.
- Integrado ao `execution_loop.py` como orientação antes de cada missão.
- Neural Core passa o contexto atual ao Execution Loop.
- A seleção não substitui a allowlist nem as confirmações existentes.
