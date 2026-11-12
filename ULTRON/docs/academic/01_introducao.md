# 1 INTRODUÇÃO

## 1.1 Contexto tecnológico

Assistentes inteligentes deixaram de ser personagens de ficção para se tornar produtos de uso diário. A
maioria deles, porém, depende de servidores remotos: a voz do usuário é enviada para a nuvem, interpretada
lá e devolvida como resposta. Esse modelo oferece grande capacidade de processamento, mas tem custos
menos visíveis — dependência de conexão, envio de dados pessoais a terceiros e pouco controle sobre o que o
assistente pode fazer no computador do usuário.

Ao mesmo tempo, três avanços tornaram viável outra abordagem. Modelos de linguagem de pequeno porte, com
poucos bilhões de parâmetros, passaram a rodar em computadores pessoais por meio de ferramentas como o
Ollama (QWEN TEAM, 2024). Reconhecedores e sintetizadores de fala de código aberto, como o Vosk — baseado no
Kaldi (POVEY et al., 2011) — e o Piper — baseado na arquitetura VITS (KIM; KONG; SON, 2021) —, funcionam sem
internet. E as bibliotecas de gráficos 3D para a web, como o Three.js sobre o WebGL, permitem desenhar
personagens animados dentro de aplicações de área de trabalho.

Juntar essas peças, porém, não é trivial. Cada uma tem seu próprio modelo de execução, consome recursos
diferentes e falha de maneiras diferentes. Um assistente que reúne todas precisa de uma **arquitetura** que
as coordene sem que a falha de uma derrube as demais, e de **mecanismos de segurança** que controlem o que
o sistema pode fazer quando um modelo de linguagem passa a propor ações no computador.

## 1.2 Motivação e histórico do projeto

Este trabalho nasceu de um projeto pessoal do autor, iniciado como um assistente chamado JARVIS. A primeira
versão registrada no repositório (outubro de 2026) reunia 131 arquivos Python, dos quais 38 % das linhas eram
cópias de segurança de versões anteriores, e o script principal de inicialização falhava antes de abrir a
interface. O sistema crescia por acréscimo de "fases": cada nova funcionalidade era um módulo novo, sem
integração com os anteriores.

Ao longo de cinco semanas de desenvolvimento intensivo, o projeto foi reconstruído em torno de um núcleo
único, recebeu testes automatizados e integração contínua, passou pelas identidades ULTRON e JARVIS e, nesta
fase, recebeu o nome definitivo **SAFRA**, com nova identidade visual. A Seção 10 descreve essa evolução.
O desenvolvimento foi feito pelo autor com o apoio de um assistente de programação baseado em inteligência
artificial, que trabalhou sob suas instruções; o histórico do repositório registra a autoria de cada
alteração (ver Seção 7.6).

A motivação para transformar o projeto em Trabalho de Conclusão de Curso é dupla: documentar com rigor as
decisões de engenharia que tornaram o sistema funcional e verificar, por meio de medições, até onde a
arquitetura adotada cumpre o que promete.

## 1.3 A proposta: o SAFRA

O SAFRA é uma plataforma inteligente modular, executada localmente em um computador pessoal com Windows, que:

* recebe pedidos em português por **voz** ou **texto** e os interpreta por regras determinísticas ou por um
  **modelo de linguagem local**;
* responde com **voz sintetizada** e com um **holograma humanoide tridimensional** cuja boca acompanha o áudio
  real da fala;
* guarda **memórias** persistentes — fatos, episódios, compromissos, lembretes — num banco de dados local;
* acompanha tarefas de análise num **ambiente virtual** chamado TARDIS, cuja sala de controle 3D reflete o
  estado real do motor de tarefas;
* executa **ações** no computador (abrir programas, organizar arquivos, registrar lembretes) sob um sistema de
  **permissões, autorizações e verificação**;
* mantém **diagnóstico** e **monitoramento** próprios e continua útil quando uma de suas partes falha.

O nome SAFRA identifica o produto; os identificadores internos do código (`ultron`, pasta de dados
`ULTRON`) foram mantidos para preservar instalações e dados existentes.

## 1.4 Organização do trabalho

O Capítulo 2 apresenta o problema de pesquisa; o 3, a hipótese; o 4, a justificativa; o 5, os objetivos. O
Capítulo 6 revisa a fundamentação teórica. O 7 descreve a metodologia, e o 8, os requisitos levantados. Os
Capítulos 9 e 10 apresentam a arquitetura e o desenvolvimento. O 11 descreve os testes e protocolos de
validação; o 12 apresenta e discute os resultados; e o 13 conclui o trabalho. Os apêndices trazem os
protocolos completos, o inventário de funcionalidades e o cronograma.
