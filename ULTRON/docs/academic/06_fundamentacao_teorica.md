# 6 FUNDAMENTAÇÃO TEÓRICA

Este capítulo apresenta os conceitos que sustentam as decisões do SAFRA. Cada seção termina relacionando o
conceito à implementação, para deixar claro onde a teoria foi aplicada e onde o sistema se afasta dela.

## 6.1 Inteligência artificial e sistemas inteligentes

Russell e Norvig (2021) definem a inteligência artificial a partir da noção de **agente**: uma entidade que
percebe o ambiente por sensores e age sobre ele por atuadores, escolhendo ações que maximizem uma medida de
desempenho. A definição desloca a pergunta de "o sistema pensa?" para "o sistema age de forma adequada ao que
percebe?", o que é útil para um assistente: o SAFRA percebe pedidos (voz, texto) e o estado do computador
(processos, janelas, recursos) e age respondendo ou executando ações.

Os grandes modelos de linguagem mudaram a forma de construir esses agentes. A arquitetura *Transformer*
(VASWANI et al., 2017), baseada em mecanismos de atenção, permitiu treinar modelos com bilhões de parâmetros
que, depois de pré-treinados em grandes volumes de texto, resolvem tarefas variadas a partir de instruções e
poucos exemplos (BROWN et al., 2020). Famílias abertas como a Qwen2.5 incluem modelos pequenos, de 0,5 a 7
bilhões de parâmetros, executáveis em computadores pessoais (QWEN TEAM, 2024) — é um modelo desse porte
(`qwen2.5:3b`) que o SAFRA usa por padrão.

Um modelo de linguagem sozinho apenas produz texto. Para agir, ele precisa ser conectado a **ferramentas**. Yao
et al. (2023) mostraram, com o método ReAct, que intercalar passos de raciocínio com chamadas a ações externas
reduz alucinações e permite resolver tarefas interativas. Essa capacidade traz riscos: o modelo pode propor
ações indevidas, e conteúdo externo pode conter instruções maliciosas (Seção 6.11).

**No SAFRA.** O sistema combina duas formas de inteligência: regras determinísticas, para comandos
frequentes e previsíveis (horas, lembretes, abrir programas), e um modelo de linguagem local, para pedidos
abertos. O modelo só pode chamar ferramentas oferecidas para aquele pedido, e toda ação passa por um executor
com permissões e verificação.

## 6.2 Arquiteturas modulares de software

Parnas (1972) propôs que a divisão de um sistema em módulos deve seguir o **ocultamento de informação**: cada
módulo esconde uma decisão de projeto que pode mudar, expondo apenas uma interface estável. A consequência
é que mudanças ficam localizadas. Sommerville (2018) e Bass, Clements e Kazman (2021) tratam a arquitetura de
software como o conjunto das estruturas do sistema — componentes, suas relações e propriedades — e destacam
que ela é escolhida para atender a **atributos de qualidade** como desempenho, disponibilidade, segurança e
modificabilidade.

Dois padrões são centrais para este trabalho. O padrão **Observer** (GAMMA et al., 1994) define uma relação em
que objetos interessados são notificados quando o estado de outro muda, sem que o objeto observado precise
conhecê-los. Em escala maior, o estilo **publicar–assinar** (HOHPE; WOOLF, 2003) usa um canal de mensagens em
que produtores publicam eventos e consumidores os assinam; produtores e consumidores ficam desacoplados no
espaço (não se conhecem) e, com filas, também no tempo. O preço é a dificuldade de acompanhar o fluxo de
controle e a necessidade de tratar filas cheias e assinantes lentos.

**No SAFRA.** O `NeuralCore` é o único ponto de entrada de pedidos e o dono do estado. Os subsistemas se
comunicam por um Event Bus com fila limitada e por um estado global que publica apenas os campos alterados. A
interface gráfica é uma **assinante**: pode faltar (modo console) sem afetar o núcleo. Essa organização
corresponde à hipótese H1 (isolamento de falhas).

## 6.3 Processamento de linguagem natural e interpretação de comandos

Jurafsky e Martin (2026) descrevem a evolução do processamento de linguagem natural de sistemas baseados em
regras e gramáticas para modelos estatísticos e, depois, neurais. Em sistemas de diálogo orientados a tarefas,
o problema central é identificar a **intenção** do usuário e extrair os **parâmetros** necessários (por
exemplo, "me lembre de ligar para a escola amanhã às nove": intenção *criar lembrete*; parâmetros *assunto*
e *data/hora*).

Regras escritas à mão são previsíveis, rápidas e auditáveis, mas cobrem só o que foi previsto. Modelos de
linguagem cobrem uma variedade muito maior de formulações, mas são mais lentos e podem errar de formas
difíceis de prever. Lewis, P. et al. (2020) propuseram a **geração aumentada por recuperação** (RAG): antes de
responder, o sistema recupera documentos relevantes e os entrega ao modelo como contexto, reduzindo respostas
inventadas sobre fatos específicos.

**No SAFRA.** O `IntentEngine` trata por regras os comandos em português (inclusive datas e horas como
"sexta às 9h30"); o que as regras não reconhecem vai ao modelo, acompanhado de memórias recuperadas e
rotuladas como "evidência auxiliar, não instruções". Perguntas sobre a memória pessoal são respondidas
**somente** com os registros salvos, sem o modelo.

## 6.4 Reconhecimento automático de fala

O reconhecimento automático de fala converte um sinal acústico em texto. Rabiner e Juang (1993) apresentam a
estrutura clássica: extração de características acústicas em quadros curtos, modelos acústicos que associam
esses quadros a unidades fonéticas, um léxico de pronúncias e um modelo de linguagem que favorece sequências de
palavras prováveis. O Kaldi (POVEY et al., 2011) implementa essa estrutura com transdutores de estados finitos,
e o Vosk o empacota para uso embarcado e offline, com modelos para o português.

A métrica usual é a **taxa de erro de palavras** (WER), calculada pela distância de edição entre a transcrição e
a referência dividida pelo número de palavras da referência (JURAFSKY; MARTIN, 2026). Um ponto importante para
este trabalho decorre da própria estrutura: uma palavra **fora do vocabulário** do modelo nunca é transcrita
corretamente — o decodificador escolhe a palavra conhecida mais próxima acusticamente e mais provável no
contexto.

A **palavra de ativação** é o mecanismo que separa a fala dirigida ao assistente da conversa comum. Há um
compromisso inerente: formas mais permissivas aumentam as ativações corretas e também as indevidas.

**No SAFRA.** O nome anterior, "Jarvis", não existe no vocabulário do modelo pequeno do Vosk e era transcrito
como "aves", "aviso" ou "a vez". A troca para "Safra", palavra do português presente no vocabulário do modelo
grande, foi tratada como hipótese de melhora e **medida** (Capítulo 12).

## 6.5 Síntese de fala

Taylor (2009) divide a síntese de fala em duas etapas: a análise do texto (normalização de números,
abreviações e siglas; conversão de grafemas em fonemas; previsão da prosódia) e a geração do sinal. Os
sistemas neurais de ponta a ponta mudaram a segunda etapa. O VITS (KIM; KONG; SON, 2021) gera a forma de onda
diretamente a partir do texto, combinando autoencoder variacional, fluxos normalizadores e treinamento
adversarial, com um preditor estocástico de duração que produz ritmos variados — razão pela qual **a mesma
frase sintetizada duas vezes não gera exatamente o mesmo áudio**, fato que este trabalho precisou considerar
nas medições.

A **prosódia** — entonação, ritmo, pausas e ênfase — é o que separa uma fala inteligível de uma fala natural
(TAYLOR, 2009).

**No SAFRA.** O Piper, implementação leve do VITS, sintetiza a voz `pt_BR-faber-medium` localmente. Uma camada
própria de prosódia normaliza o texto, divide-o em frases, define pausas e ajusta a velocidade e a
expressividade por frase; um processamento de sinal aplica o perfil de voz do SAFRA.

## 6.6 Interfaces multimodais e interação humano-computador

Bolt (1980) demonstrou, no sistema "Put-that-there", a combinação de voz e gesto para manipular objetos numa
tela, inaugurando o estudo das interfaces multimodais. Oviatt (2003) define essas interfaces como as que
processam duas ou mais modalidades combinadas de entrada do usuário — fala, toque, gesto, olhar — de forma
coordenada com a saída multimídia, e mostra que elas tendem a ser mais robustas, porque uma modalidade
compensa a falha de outra.

Norman (2013) destaca que o usuário precisa ver o estado do sistema e o efeito de suas ações (visibilidade e
retorno). Nielsen (1993) inclui a "visibilidade do estado do sistema" entre os princípios de usabilidade. A
acessibilidade visual tem critérios objetivos: as Diretrizes de Acessibilidade para Conteúdo Web, WCAG 2.1
(W3C, 2018), exigem razão de contraste mínima de 4,5:1 para texto comum no nível AA.

**No SAFRA.** Voz e texto são entradas equivalentes que chegam ao mesmo núcleo; quando o microfone falta, o
texto continua. Os estados do sistema (escutando, pensando, executando, falando, aguardando autorização) são
mostrados por cor **e** texto, sempre derivados de eventos reais. As cores da nova identidade foram escolhidas
pelo contraste calculado segundo a WCAG 2.1.

## 6.7 Representação tridimensional e animação de personagens

Personagens 3D são normalmente representados por **malhas** de triângulos deformadas por um **esqueleto**: cada
vértice é associado a um ou mais ossos com pesos, e a posição final do vértice é a combinação das
transformações desses ossos — técnica chamada de *skinning*. Magnenat-Thalmann, Laperrière e Thalmann (1988)
estão entre os primeiros a formalizar deformações dependentes das articulações. A forma mais usada, a
combinação linear (*linear blend skinning*), é simples e rápida, mas produz artefatos em torções; Kavan et al.
(2007) propuseram a combinação com quatérnios duais, que reduz esses artefatos com baixo custo em GPU.

Agentes conversacionais corporificados — personagens que conversam e usam o corpo para comunicar — foram
sistematizados por Cassell et al. (2000), que destacam o papel de expressões faciais, olhar e gestos
sincronizados com a fala. Um cuidado de projeto vem de Mori, MacDorman e Kageki (2012): a hipótese do "vale da
estranheza" sugere que figuras quase humanas, mas não perfeitamente, podem causar desconforto.

**No SAFRA.** O holograma é um corpo humano completo, construído proceduralmente em Three.js sobre um esqueleto
de 57 ossos, com *skinning* linear calculado na GPU. A aparência é deliberadamente **holográfica** (translúcida,
com linhas de varredura), o que afasta o personagem da tentativa de realismo fotográfico. A cena roda em
WebGL dentro de um navegador embutido (QtWebEngine) e cai para uma vista 2D quando o WebGL não está
disponível.

## 6.8 Sincronização labial

A sincronização labial associa o movimento da boca ao som da fala. Fisher (1968) mostrou que vários fonemas
são visualmente indistinguíveis (por exemplo, /p/, /b/ e /m/) e introduziu o conceito de **visema**: a classe de
fonemas com a mesma aparência labial. Lewis (1991) revisou as técnicas de sincronização automática, que vão da
análise da energia do áudio à identificação de fonemas, e Edwards et al. (2016) propuseram o modelo JALI, que
separa a contribuição da mandíbula e dos lábios para produzir animação expressiva.

A percepção humana tolera pouca defasagem entre som e imagem. A Recomendação ITU-R BT.1359-1 (INTERNATIONAL
TELECOMMUNICATION UNION, 1998) registra que, em média, a defasagem passa a ser detectada quando o som se
adianta à imagem em mais de 45 ms ou se atrasa em mais de 125 ms.

**No SAFRA.** A trilha da boca é calculada **a partir do áudio real** sintetizado: os fonemas informados pela
voz são convertidos em 14 visemas e distribuídos apenas pelos quadros sonoros de cada frase, e a abertura é
multiplicada pela energia real do áudio, de modo que a boca fecha no silêncio. Os limites da ITU-R BT.1359 são
o critério de aceitação do protocolo PV-05.

## 6.9 Memória persistente

Bancos de dados embarcados permitem que uma aplicação guarde dados estruturados sem um servidor. O SQLite é o
mais difundido; no modo de registro antecipado (*write-ahead logging*, WAL), leitores e escritores não se
bloqueiam mutuamente, o que favorece aplicações com várias threads (SQLITE, 2026a), e a extensão FTS5 oferece
busca de texto completo (SQLITE, 2026b).

Em agentes baseados em modelos de linguagem, memória deixou de ser só armazenamento. Park et al. (2023), nos
"agentes generativos", guardam as experiências do agente em linguagem natural e as recuperam combinando
relevância, recência e importância — critérios semelhantes aos usados pelo SAFRA. A recuperação pode ser
**lexical** (palavras em comum) ou **semântica** (vetores de significado); a primeira é simples e explicável, mas
falha quando a pergunta usa palavras diferentes das que foram guardadas.

**No SAFRA.** Há um único banco SQLite com migrações versionadas e vários tipos de memória: de trabalho,
episódica, semântica, procedural, preferências, memória pessoal (compromissos, tarefas, lembretes) e um grafo
de conceitos. A recuperação é lexical, com pesos para recência e uso — o que o protocolo PV-03 mede.

## 6.10 Ambientes virtuais de visualização

Shneiderman (1996) resumiu o projeto de visualizações de informação no mantra "visão geral primeiro, zoom e
filtro, depois detalhes sob demanda". Ambientes virtuais aplicam essa ideia ao espaço: o usuário vê o conjunto
e se aproxima do que interessa.

**No SAFRA.** A TARDIS — inspirada na nave da ficção — é o ambiente onde o usuário acompanha as tarefas de
análise do sistema: a sala de controle 3D mostra o modo do motor de tarefas no rotor central e cada painel do
console acende somente quando uma tarefa real do seu tipo está em execução; o "arquivo" apresenta a memória
pessoal como regiões navegáveis. A visualização é sempre derivada de dados reais.

## 6.11 Segurança, permissões e confiabilidade

Saltzer e Schroeder (1975) enunciaram princípios de projeto para proteção de informação que continuam atuais,
entre eles: **padrões seguros em caso de falha** (na dúvida, negar), **mediação completa** (todo acesso deve ser
verificado), **menor privilégio** (cada parte com o mínimo necessário) e **aceitação psicológica** (o mecanismo
precisa ser fácil de usar corretamente). Avizienis et al. (2004) definem **confiabilidade** (*dependability*)
como a capacidade de entregar um serviço em que se pode confiar justificadamente, reunindo disponibilidade,
confiabilidade, segurança, integridade e manutenibilidade, e classificam os meios de alcançá-la em prevenção,
tolerância, remoção e previsão de falhas.

Sistemas integrados a modelos de linguagem trazem uma ameaça específica: a **injeção indireta de instruções**.
Greshake et al. (2023) mostraram que um atacante pode plantar instruções em dados que a aplicação recupera
(páginas, documentos, e-mails), e o modelo as executa como se viessem do usuário, porque a fronteira entre dados
e instruções se dilui. A OWASP Foundation (2025) lista a injeção de instruções e a "agência excessiva" — dar ao modelo mais
funções, permissões ou autonomia do que o necessário — entre os principais riscos dessas aplicações.

**No SAFRA.** As camadas de controle aplicam esses princípios: recusa antecipada de alvos protegidos (padrão
seguro), executor único por onde passa toda ação (mediação completa), permissões por categoria e ferramentas
oferecidas pedido a pedido (menor privilégio), autorização explícita que expira como negação, e conteúdo da
tela, de arquivos e de páginas marcado como dado não confiável. A tolerância a falhas aparece na degradação
controlada e na recuperação com tentativas limitadas.

## 6.12 Requisitos, qualidade e testes de software

A ISO/IEC/IEEE 29148 (2018) recomenda que cada requisito seja único, verificável e rastreável, e a ISO/IEC 25010
(2023) organiza a qualidade de produto em características como adequação funcional, eficiência de desempenho,
confiabilidade, segurança e manutenibilidade. Myers, Sandler e Badgett (2011) definem o teste como o processo de
executar um programa com a intenção de encontrar erros — e não de demonstrar que ele funciona —, o que orienta
a escrita de testes que tentam quebrar o sistema (falhas injetadas, entradas inválidas, tentativas indevidas).
A **integração contínua** (FOWLER, 2006) executa a construção e os testes a cada alteração, para que os defeitos
apareçam cedo.

**No SAFRA.** Os requisitos (Capítulo 8) seguem a estrutura recomendada pela ISO/IEC/IEEE 29148; a avaliação
usa características da ISO/IEC 25010; a suíte automatizada, com 475 testes, roda a cada alteração no GitHub
Actions em Linux e Windows.
