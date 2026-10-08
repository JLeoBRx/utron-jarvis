# J.A.R.V.I.S. — Fase 4: Action Engine

A Fase 4 adiciona uma camada de execução orientada a alvo para Windows.

## Fluxo

1. O agente descreve o alvo (`execute_ui_action`).
2. JARVIS tenta localizar o elemento por UI Automation.
3. Se não houver UI Automation, tenta OCR.
4. Exige alvo único.
5. Confere se a janela/processo continua sendo o mesmo.
6. Executa somente a ação registrada.
7. Registra evidência no Context State.

## Segurança

`ALLOW_AUTONOMOUS_UI_CLICKS = False` por padrão.

Portanto, localizar um botão não significa que JARVIS pode clicar nele sem confirmação. Para uma futura política autônoma, a opção poderá ser habilitada deliberadamente, mantendo as validações de alvo único e janela em primeiro plano.

Não há shell, CMD, PowerShell ou execução arbitrária nesta camada.

## Hierarquia de percepção

**UI Automation → OCR → coordenadas**.

A camada atual usa coordenadas apenas quando um alvo já foi localizado de maneira estruturada. Ela não escolhe coordenadas arbitrárias por conta própria.
