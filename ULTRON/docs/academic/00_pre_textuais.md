<!-- CAPA — preencha os campos entre colchetes; não invente dados. -->
<div class="capa">

**[NOME DA INSTITUIÇÃO DE ENSINO]**

**[CURSO TÉCNICO EM DESENVOLVIMENTO DE SISTEMAS]**

**[NOME COMPLETO DO AUTOR]**

&nbsp;

&nbsp;

**SAFRA: DESENVOLVIMENTO E AVALIAÇÃO DE UMA PLATAFORMA INTELIGENTE MULTIMODAL COM ARQUITETURA MODULAR E INTERFACE HUMANOIDE TRIDIMENSIONAL**

&nbsp;

&nbsp;

[CIDADE]

2027

</div>

<!-- quebra de página -->

<!-- FOLHA DE ROSTO -->
<div class="folha-de-rosto">

**[NOME COMPLETO DO AUTOR]**

&nbsp;

**SAFRA: DESENVOLVIMENTO E AVALIAÇÃO DE UMA PLATAFORMA INTELIGENTE MULTIMODAL COM ARQUITETURA MODULAR E INTERFACE HUMANOIDE TRIDIMENSIONAL**

&nbsp;

> Trabalho de Conclusão de Curso apresentado ao [Curso Técnico em Desenvolvimento de Sistemas] da
> [Nome da Instituição], como requisito parcial para a obtenção do título de [Técnico em Desenvolvimento de
> Sistemas].
>
> Orientador(a): [Nome do(a) orientador(a)]
>
> Coorientador(a): [se houver]

&nbsp;

[CIDADE]

2027

</div>

<!-- quebra de página -->

## RESUMO

O trabalho investiga como integrar, em um computador pessoal e com processamento predominantemente local,
processamento inteligente de comandos, interação por voz, memória persistente, uma interface humanoide
tridimensional com sincronização labial e um ambiente virtual de acompanhamento de tarefas, de modo que esses
subsistemas operem coordenados por um núcleo central sem perder a independência funcional, o controle das ações
e um desempenho adequado à interação. Trata-se de pesquisa aplicada, com desenvolvimento experimental de um
protótipo, o SAFRA. A arquitetura proposta concentra estado, memória e execução em um núcleo único e faz os
demais subsistemas se comunicarem por eventos; as ações no computador passam por recusa antecipada de alvos
protegidos, permissões por categoria, autorização explícita, verificação do efeito e auditoria. O protótipo,
escrito em Python com interface Qt e cena 3D em Three.js, usa modelo de linguagem, reconhecimento e síntese de
fala executados localmente. A validação combinou 475 testes automatizados, executados em integração contínua
em Linux e Windows, e protocolos experimentais. No ambiente de desenvolvimento, todas as 11 tentativas de ação
indevida foram bloqueadas sem efeito colateral, com os 4 controles funcionando; o núcleo respondeu a comandos
determinísticos com percentil 95 de 9 ms; a boca do holograma acompanhou a energia do áudio com defasagem
mediana de 0 ms e fechou em todos os silêncios; e uma execução de 30 minutos não apresentou falhas nem deixou
processos pendentes. Os experimentos também mostraram limitações: a recuperação lexical de memória acertou 90 %
das perguntas com as mesmas palavras do fato e só 40 % das paráfrases, e, com voz sintética, a nova palavra de
ativação "Safra" foi reconhecida em apenas 2 a 4 % das frases, abaixo da anterior. As condições de isolamento de
falhas e de controle das ações foram atendidas; as de desempenho e de coerência multimodal dependem das
medições no computador de referência, previstas para 2027. Conclui-se, até aqui, que a hipótese está
parcialmente sustentada.

**Palavras-chave:** assistente inteligente; arquitetura orientada a eventos; interação por voz; interface
humanoide; segurança de agentes.

<!-- quebra de página -->

## ABSTRACT

This work investigates how to integrate, on a personal computer and with predominantly local processing,
intelligent command processing, voice interaction, persistent memory, a three-dimensional humanoid interface with
lip synchronization and a virtual environment for following tasks, so that these subsystems work in coordination
through a central core without losing functional independence, control over actions and adequate performance
for interaction. It is applied research with the experimental development of a prototype, SAFRA. The proposed
architecture keeps state, memory and execution in a single core and makes the other subsystems communicate
through events; actions on the computer go through early refusal of protected targets, per-category permissions,
explicit authorization, effect verification and auditing. The prototype, written in Python with a Qt interface
and a Three.js 3D scene, uses a language model, speech recognition and speech synthesis that run locally.
Validation combined 475 automated tests, run in continuous integration on Linux and Windows, with experimental
protocols. In the development environment, all 11 improper action attempts were blocked with no side effects,
while the 4 controls worked; the core answered deterministic commands with a 95th percentile of 9 ms; the
hologram's mouth followed the audio energy with a median offset of 0 ms and closed in every silence; and a
30-minute run showed no failures and left no pending threads. The experiments also showed limitations: lexical
memory retrieval answered 90 % of the questions that reused the words of the stored fact but only 40 % of the
paraphrases, and, with a synthetic voice, the new wake word "Safra" was recognized in only 2 to 4 % of the
sentences, below the previous one. The fault-isolation and action-control conditions were met; the performance
and multimodal-coherence conditions depend on measurements on the reference computer, scheduled for 2027. So far,
the hypothesis is partially supported.

**Keywords:** intelligent assistant; event-driven architecture; voice interaction; humanoid interface; agent
security.

<!-- quebra de página -->

<!-- sumário -->

