# J.A.R.V.I.S. — Fase 3: Perception Engine

A terceira fase conecta o Observador ao Neural Core por uma camada de percepção contextual.

## Fluxo

`Tela → Observador visual → Perception Engine → Neural Core → Agente`

A percepção combina:

- processo/janela em foco;
- classificação visual já feita pelo Ollama;
- OCR opcional (pytesseract/Tesseract);
- UI Automation opcional (pywinauto);
- mudança de contexto;
- histórico curto.

A camada **não executa ações**. Ela somente produz evidência estruturada para o cérebro.

## Privacidade

Se a visão marcar a tela como sensível ou detectar instruções destinadas à IA, o enriquecimento OCR/UI é interrompido. Termos que parecem credenciais, senhas, tokens, chaves ou dados bancários também são filtrados da evidência estruturada.

## Dependências opcionais

Sem OCR/UI Automation instalados, o JARVIS continua funcionando com a percepção visual local existente.

- `pytesseract` + Tesseract OCR: texto da interface.
- `pywinauto`: elementos nativos do Windows.

O próximo estágio pode usar essa evidência para melhorar a decisão autônoma e o roteamento de inteligência.
