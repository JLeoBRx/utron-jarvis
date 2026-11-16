# 7 METODOLOGIA

## 7.1 Classificação da pesquisa

Segundo os critérios de Gil (2017) e de Prodanov e Freitas (2013), este trabalho é:

* **quanto à natureza, pesquisa aplicada** — busca gerar conhecimento para a solução de um problema concreto
  (integrar subsistemas inteligentes num computador pessoal);
* **quanto aos objetivos, exploratória e descritiva** — explora um problema pouco documentado no contexto de
  sistemas locais e descreve as características do sistema construído;
* **quanto aos procedimentos, pesquisa experimental com desenvolvimento de protótipo** — o objeto (o SAFRA) é
  construído, as variáveis são controladas nos experimentos (palavra de ativação, nível de ruído, tipo de
  pergunta, cenário de segurança) e os efeitos são medidos; complementada por **pesquisa bibliográfica**;
* **quanto à abordagem, predominantemente quantitativa** — os resultados são medidas (taxas, tempos,
  proporções), com análise qualitativa das falhas e das decisões de engenharia.

## 7.2 Etapas

| Etapa | Atividades | Produtos |
|---|---|---|
| 1 Pesquisa bibliográfica | levantamento de livros, artigos e documentação técnica sobre os temas do Capítulo 6; registro de verificação de cada referência | Capítulo 6; `docs/research/REFERENCIAS_VERIFICADAS.md` |
| 2 Auditoria do sistema existente | leitura do código, histórico do Git, execução da suíte de testes, consulta ao CI | `AUDITORIA_INICIAL.md`, `INVENTARIO_FUNCIONALIDADES.md` |
| 3 Levantamento de requisitos | engenharia reversa do sistema existente + objetivos da fase SAFRA; requisitos com identificador, prioridade, critério e verificação | Capítulo 8, `REQUISITOS.md` |
| 4 Modelagem da arquitetura | diagramas desenhados a partir do código (camadas, componentes, fluxos, armazenamento, falhas) | Capítulo 9, `docs/diagrams` |
| 5 Implementação | evolução incremental em ciclos curtos (alteração → testes → integração contínua → registro) | código, Capítulo 10 |
| 6 Integração | testes de integração com o núcleo real; cena 3D real sob servidor X virtual; CI em Linux e Windows | Capítulo 11 |
| 7 Testes individuais e integrados | suíte automatizada (unidade, integração, falhas, segurança, interface) | Capítulo 11 |
| 8 Coleta de dados | protocolos PV-01 a PV-07 (Apêndice A), executados no ambiente de desenvolvimento e, nas etapas que exigem hardware, no computador de referência | `docs/research/resultados/*.json` |
| 9 Análise | estatística descritiva, intervalos de confiança, comparação com as metas dos requisitos não funcionais e com a hipótese | Capítulo 12 |

## 7.3 Ciclo de desenvolvimento

O desenvolvimento seguiu ciclos curtos e verificáveis: (1) definir a alteração e o critério de aceitação; (2)
implementar; (3) executar a suíte automatizada completa (em Python 3.13 e 3.11); (4) enviar ao repositório e
executar a integração contínua (Linux 3.11/3.13 com a cena 3D real e Windows com instalação a partir do pacote);
(5) registrar o que mudou, o que foi verificado e o que não foi. Quando um teste falhava, a causa era corrigida
no código ou, se a suposição do teste estivesse errada, no próprio teste — e as duas situações eram
registradas. Nenhum teste foi desativado para obter aprovação.

## 7.4 Instrumentos e critérios de avaliação

| Instrumento | O que mede | Critério |
|---|---|---|
| Suíte automatizada (`TEST_JARVIS.py`, 39 módulos de teste) | comportamento funcional, falhas injetadas, segurança, interface (Qt *offscreen*) | 100 % aprovados em cada versão (CA01) |
| Integração contínua (GitHub Actions) | o mesmo em Linux e Windows, cena 3D real, instalação a partir do pacote | execução aprovada no commit entregue |
| `tools/experimentos/pv01…pv07` | métricas experimentais (Quadro 1 do Apêndice A) | metas RNF01–RNF16 |
| `tools/benchmark.py`, `benchmark_scene3d.py` | desempenho da interface | RNF03–RNF05 |
| Revisão dos dados brutos | consistência, valores extremos, rótulos real × simulado | — |

As métricas e as metas estão no Capítulo 8 (requisitos não funcionais) e os procedimentos completos, no
Apêndice A. Proporções são apresentadas com intervalo de confiança de Wilson a 95 %; tempos, com média,
desvio-padrão, mediana, percentil 95 e intervalo de confiança da média.

## 7.5 Ambientes de medição

Duas condições são distinguidas em todos os resultados:

* **Ambiente C (contêiner de desenvolvimento):** Linux, 4 processadores virtuais, 15 GB de memória, sem GPU,
  sem microfone e sem alto-falante. Mede o que não depende de hardware de áudio e vídeo (lógica, núcleo,
  memória, segurança, cálculo da sincronização) e verifica os instrumentos. O WebGL roda por software.
* **Ambiente R (computador de referência do autor):** Windows, GPU, microfone e alto-falante. Necessário para
  voz humana, modelo de linguagem real, desempenho gráfico e atraso de apresentação áudio × imagem. As rodadas
  oficiais estão previstas no cronograma para março e maio de 2027.

Cada arquivo de resultado registra o ambiente e lista explicitamente o que foi **real** e o que foi
**simulado**. Resultados de um ambiente não são apresentados como se fossem do outro.

## 7.6 Uso de inteligência artificial no desenvolvimento

O código do SAFRA foi desenvolvido pelo autor com o apoio de um assistente de programação baseado em
inteligência artificial (Claude Code). O assistente produziu grande parte do código e da documentação a partir
de instruções, requisitos e decisões do autor; o histórico do repositório registra a autoria de cada alteração
(46 commits do autor, 46 do assistente e 2 automáticos até 03/11/2026). As decisões de escopo, de identidade e
de prioridade, a definição dos requisitos e a aprovação de cada etapa foram do autor. Este registro é feito em
nome da transparência acadêmica; a forma de declarar o uso dessas ferramentas deve seguir as orientações da
instituição.

## 7.7 Aspectos éticos

As medições com voz humana (PV-01, etapa B) envolvem gravações de pessoas. Elas só serão feitas com termo de
consentimento, se a instituição permitir; as gravações não são versionadas e podem ser apagadas após a extração
dos resultados. Nenhum experimento lê ou altera dados pessoais reais: todos usam pastas temporárias.
