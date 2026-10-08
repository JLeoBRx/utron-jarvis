# JARVIS — Observador

Esta versão integra o modo **OBSERVADOR** ao JARVIS existente.

## O que foi alterado

- `copilot.py`: novo modo `observer`, com observação contínua e assistência falada relevante.
- `commands.py`: comandos de voz como `Jarvis, ative o Observador`, `desative o Observador`, `pause o Observador` e pedidos naturais como acompanhar o computador/programação.
- `jarvis_hud.py`: modo OBSERVADOR disponível na barra da HUD.
- O Observador não abre navegador/Bloco de Notas automaticamente.
- O Observador não fala a cada clique. Há detecção de mudança, cooldown e limites de chamadas.
- Continua respeitando exclusões e filtros de conteúdo sensível existentes.

## Como usar

1. Inicie o JARVIS normalmente.
2. Diga: **"Jarvis, ative o Observador."**
3. Minimize a HUD se ela estiver cobrindo a tela.
4. Trabalhe normalmente. O JARVIS observará o contexto autorizado e falará quando identificar algo realmente útil.
5. Para parar: **"Jarvis, desative o Observador."**

Também é possível selecionar **OBSERVADOR** na barra de automação da HUD.

## Teste realizado neste ambiente

Foi feita compilação sintática (`py_compile`) dos módulos Python entregues. O controle real do Windows, PySide6, microfone e Ollama não podem ser executados neste ambiente Linux; esses pontos precisam ser validados no Windows do usuário.


## Camada AGENTE AUTÔNOMO

O modo **OBSERVADOR** agora pode entregar uma percepção de alta confiança ao `agent.py`. O fluxo passa a ser:

**percepção visual → contexto → planejamento multietapas → ferramenta → verificação → recuperação → conclusão**.

O agente usa a mesma allowlist do projeto. Não existe shell/CMD/PowerShell livre. Ferramentas que exigem confirmação continuam exigindo confirmação. O agente pode usar `inspect_screen`, OCR/UI Automation quando disponíveis, pesquisar arquivos, abrir caminhos, digitar, teclado, mouse e outras ferramentas já registradas.

Para evitar loops, o mesmo contexto não dispara novamente por 120 segundos e a visão é suspensa enquanto o agente está trabalhando. O botão **PARAR TAREFA** também solicita o cancelamento do agente autônomo.

### Dependências opcionais

`vision.py` funciona sem OCR/UI Automation instalados, mas para localização estruturada de controles você pode instalar `pytesseract` + Tesseract OCR e/ou `pywinauto`. Se não estiverem instalados, o JARVIS simplesmente informa que o recurso visual estruturado está indisponível.

### Importante

A camada é deliberadamente limitada por allowlists e confirmações. Ela não é um executor irrestrito de comandos do Windows. O ambiente desta geração não executou o JARVIS no Windows; foram feitas validações estáticas de sintaxe/estrutura.
