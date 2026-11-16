# 2 PROBLEMA DE PESQUISA

Assistentes inteligentes comerciais concentram o processamento em servidores remotos e oferecem ao
usuário pouco controle sobre o que é guardado e sobre o que é executado no seu computador. Ao mesmo tempo, os
componentes que permitem construir um assistente local — modelos de linguagem executáveis em computadores
pessoais, reconhecimento e síntese de fala offline, bancos de dados embarcados e bibliotecas de gráficos 3D
para a web — estão disponíveis como peças isoladas, cada uma com seu próprio modelo de execução, suas
próprias falhas e seus próprios requisitos de desempenho.

Juntar essas peças em um único sistema não é uma soma simples. Ao longo do desenvolvimento do SAFRA (e das
identidades anteriores, JARVIS e ULTRON), os problemas mais difíceis não estiveram dentro de cada componente,
mas nas fronteiras entre eles: a interface que não abria porque um estado era usado antes de existir; o
reconhecimento de voz que não conhecia o nome do próprio assistente; a fala que precisava suspender a
escuta para não ouvir a si mesma; a boca do avatar que continuava aberta depois do fim do áudio por um erro
de arredondamento; ações sobre arquivos que podiam alcançar pastas do sistema; um modelo de linguagem que
podia executar ferramentas que não lhe foram oferecidas. Esses problemas são de **integração** e de
**arquitetura**.

Dessa situação surge o problema que orienta este trabalho:

> **Como integrar, em um computador pessoal e com processamento predominantemente local, processamento
> inteligente de comandos, interação por voz, memória persistente, uma interface humanoide tridimensional com
> sincronização labial e um ambiente virtual de acompanhamento de tarefas, de modo que esses subsistemas
> operem de forma coordenada por um núcleo central, preservando a independência funcional de cada módulo, o
> controle das ações executadas no computador e um desempenho adequado à interação?**

O problema se desdobra em quatro questões específicas, que orientam os testes:

* **Q1 — Independência funcional:** a falha ou a ausência de um subsistema (voz, modelo de linguagem, cena
  3D, sensores) interrompe o funcionamento do núcleo?
* **Q2 — Controle das ações:** é possível dar ao sistema a capacidade de agir no computador sem que ações não
  autorizadas, destrutivas ou fora do escopo sejam executadas?
* **Q3 — Desempenho:** um computador pessoal, sem serviços em nuvem, sustenta tempos de resposta, de
  inicialização e de interface compatíveis com a interação?
* **Q4 — Coerência multimodal:** a fala, a animação do holograma e os estados exibidos podem derivar dos
  mesmos eventos reais, sem estados inventados e com sincronização perceptivamente aceitável entre áudio e
  boca?

**Delimitação.** O trabalho trata de um protótipo para um único usuário, em Windows 10/11, com modelos de
IA pré-treinados executados localmente. Não faz parte do problema treinar modelos, controlar dispositivos
físicos ou robôs, nem comparar o SAFRA com assistentes comerciais.
