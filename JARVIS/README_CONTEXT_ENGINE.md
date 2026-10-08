# JARVIS — Fase 4: Context Engine + Intent Engine

Esta fase mantém o Observador/Perception Engine e adiciona uma camada temporal de compreensão.

Fluxo:

`percepção → contexto temporal → intenção → Neural Core → agente`

O Context Engine reúne janela ativa, atividade, erro, OCR/UI já filtrados e histórico curto.
O Intent Engine faz inferência conservadora: só transforma uma percepção em objetivo acionável quando há evidência suficiente.

A inferência não executa ferramentas. O Neural Core continua responsável por decidir quando iniciar o agente, e o agente continua responsável pela execução, verificação e recuperação.
