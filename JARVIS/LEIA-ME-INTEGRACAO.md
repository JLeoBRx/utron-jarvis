# JARVIS — integração de HUD e monitoramento proativo

## O que foi integrado

- HUD não volta automaticamente ao estado ocioso após um período sem interação.
- Botão flutuante `J`, sempre no topo, que pode ser arrastado; clique oculta/restaura a janela.
- Monitoramento proativo com captura temporária da tela e análise pelo modelo de visão configurado no Ollama.
- Modos `desativado`, `assistente` e `supervisionado`. Os dois últimos produzem sugestões; **nenhum executa ações automaticamente nesta versão**.
- Pausar, retomar e interromper o monitor; intervalo configurável (30 a 3600 s); histórico local limitado aos últimos 100 registros.
- Exclusões por trechos do título da janela ativa. Separe vários termos por vírgula (ex.: `banco, senha, WhatsApp Web`).
- Indicador textual do estado no tooltip do ícone da bandeja.

## Instalação / execução

1. Extraia o ZIP para uma pasta normal, por exemplo `C:\JARVIS`.
2. Use o mesmo ambiente Python em que o JARVIS original já funcionava.
3. Confirme que as dependências do projeto estão instaladas. Para o monitor proativo, são necessárias `pyautogui` e `Pillow`; a interface requer `PySide6`. O backend também precisa das dependências e modelos de voz/Ollama já usados pelo seu projeto.
4. Inicie o Ollama e confirme que o modelo de visão definido em `config.py` está instalado e aceita imagens.
5. Execute `python Jarvis.py` (ou o ponto de entrada que você já usa no seu projeto).
6. Abra o menu da bandeja e selecione **Monitoramento proativo...** para configurar.

## Privacidade e segurança

- A captura é feita em memória, reduzida e enviada ao endpoint local configurado no Ollama; o monitor não grava a imagem em disco.
- A exclusão de janela é baseada no título da janela em primeiro plano. Ela não é um bloqueio por aplicativo/processo e não substitui desligar o monitor em telas sensíveis.
- O texto visível na tela é tratado como conteúdo não confiável. O monitor não obedece instruções que apareçam em imagens.
- Sugestões são exibidas no HUD e registradas no histórico em memória. Não há cliques, digitação, envio de mensagens, compras, exclusão de arquivos ou execução de comandos por conta própria.
- `Interromper` sinaliza o encerramento do worker. Uma chamada ao Ollama que já esteja em andamento pode terminar antes de a thread encerrar; o botão não cancela à força uma requisição em andamento.

## Validação e limites

Os arquivos Python foram compilados para verificar sintaxe e o monitor foi exercitado com um teste local de ciclo, resposta `SEM_SUGESTAO` e sinalização de parada. Isso não equivale a um teste integral em Windows: a captura real, o dispositivo de áudio, o Ollama e a interação gráfica precisam ser confirmados na máquina de destino.

O modo supervisionado está deliberadamente limitado à revisão humana das sugestões. Para automatizar ações com confirmação, é necessário definir explicitamente quais ferramentas podem ser chamadas, quais são de risco e como a aprovação do usuário será coletada; isso não foi presumido nem implementado como execução arbitrária.

## Primeira etapa: agente visual de tarefas

Foi adicionado `visual_agent.py` e a ferramenta `visual_computer_task`. Ao receber uma tarefa que exige interação visual, o agente pode observar a tela, escolher uma ação de interface, executá-la e observar novamente. O modelo visual usado é o `OLLAMA_VISION_MODEL` configurado no `config.py`.

Esta é uma primeira implementação experimental, não uma cópia das capacidades fictícias do JARVIS. O ciclo é limitado a 12 passos por chamada. Ações sensíveis ou incertas devem parar e pedir orientação; não há digitação de credenciais nem execução de comandos de terminal. O fail-safe do PyAutoGUI continua ativo: mover o mouse para o canto superior esquerdo interrompe a automação. Como a interpretação visual pode errar, acompanhe a tela durante os testes e comece com tarefas simples e reversíveis.

Para testar, inicie Ollama com o modelo de visão instalado e peça ao JARVIS uma tarefa simples de interface, por exemplo abrir uma página e localizar uma informação. O teste real depende do Windows, da resolução, do modelo instalado e das permissões locais.
