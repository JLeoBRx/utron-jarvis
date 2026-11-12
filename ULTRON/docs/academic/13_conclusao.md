# 13 CONCLUSÃO

Este trabalho investigou como integrar, num computador pessoal e com processamento predominantemente local,
processamento inteligente de comandos, interação por voz, memória persistente, uma interface humanoide 3D com
sincronização labial e um ambiente virtual de acompanhamento de tarefas, mantendo a independência dos módulos, o
controle das ações e um desempenho adequado. Para isso, o SAFRA foi desenvolvido, documentado e submetido a
testes automatizados e a protocolos experimentais.

## 13.1 Resposta ao problema de pesquisa

A resposta proposta — e implementada — é uma **arquitetura de núcleo único orientada a eventos**, na qual o
núcleo concentra estado, memória e execução, e os demais subsistemas se comunicam por um barramento de eventos e
por um estado global publicado por campos alterados; e uma **cadeia de controle das ações** (recusa antecipada de
alvos protegidos, permissões por categoria, política de autonomia, autorização explícita, verificação do efeito e
auditoria) pela qual passa toda ação, venha ela de uma regra, de um modelo de linguagem, da interface ou do acesso
remoto.

As quatro questões específicas foram respondidas da seguinte forma, com as evidências disponíveis até aqui:

* **Q1 — Independência funcional:** a falha ou a ausência de um subsistema **não** interrompeu o núcleo nos testes
  de injeção de falhas (banco danificado e somente leitura, modelo que cai, sensor com erro, assinante do barramento
  que falha), na falta da interface gráfica (modo console) e na falta de WebGL (vista 2D, verificada no CI do
  Windows); a execução contínua de 30 minutos não teve falhas.
* **Q2 — Controle das ações:** sim, é possível dar ao sistema capacidade de agir sem executar ações indevidas
  dentro dos cenários medidos: 11 de 11 tentativas foram bloqueadas sem efeito colateral, com os controles
  positivos funcionando, e a suíte de segurança confirmou as demais proteções.
* **Q3 — Desempenho:** a arquitetura em si custa pouco — milissegundos para comandos determinísticos e cerca de
  11 ms de sobrecarga no caminho do modelo. O desempenho percebido depende do modelo de linguagem e da GPU, ainda
  não medidos no computador de referência.
* **Q4 — Coerência multimodal:** os estados exibidos derivam de eventos reais (verificado por testes de transição)
  e, no cálculo, a boca do holograma acompanha a energia do áudio dentro de um quadro de 10 ms e fecha em todos os
  silêncios. O atraso entre o som e a imagem na tela ainda não foi medido.

## 13.2 Avaliação da hipótese

Pelo critério definido no Capítulo 3:

| Condição | Situação | Evidência |
|---|---|---|
| H1 — Isolamento de falhas | **atendida** (ambiente C e CI) | `test_failures`, `test_transitions`, modo console, reserva 2D no CI do Windows, PV-07 |
| H2 — Controle das ações | **atendida** | PV-06 (11/11 e 4/4), `test_security` (17 testes) |
| H3 — Desempenho | **parcialmente avaliada**: RNF01 atendida; RNF02, RNF03 (completa) e RNF04 aguardam o ambiente R | PV-02, PV-04 |
| H4 — Coerência multimodal | **parcialmente avaliada**: estados reais e alinhamento do cálculo verificados; atraso de apresentação não medido | `test_transitions`, PV-05 (etapa A) |

Como H1 e H2 foram atendidas e H3 e H4 ainda não puderam ser avaliadas por completo, **a hipótese está, até o
momento, parcialmente sustentada**. A avaliação final depende das rodadas no computador de referência previstas
para março e maio de 2027; elas podem levar a hipótese a "sustentada" ou mantê-la "parcialmente sustentada", mas
não alteram as condições H1 e H2, que dependem da arquitetura e já foram verificadas.

## 13.3 Contribuições

* Uma arquitetura documentada, com diagramas tirados do código real, para assistentes locais que combinam voz,
  memória, interface 3D e execução de ações.
* Uma cadeia de controle de ações aplicada a um agente com modelo de linguagem, com protocolo de medição que
  inclui controles positivos.
* Um conjunto de instrumentos reproduzíveis (`tools/experimentos`) que registram, em cada resultado, o ambiente e
  o que foi real e o que foi simulado.
* Um registro honesto de resultados negativos: a nova palavra de ativação não foi mais bem reconhecida com voz
  sintética, e a busca lexical não entende paráfrases — além de três defeitos encontrados pelas próprias medições.
* O relato de um desenvolvimento assistido por IA com responsabilidades e autoria registradas.

## 13.4 Limitações

As medições de voz usaram uma única voz sintética; as de interface, renderização por software; as de resposta,
inferência simulada. Os conjuntos de teste de memória e segurança são pequenos e foram escritos pelo autor. O
sistema foi avaliado por um único usuário; não houve avaliação de usabilidade com outras pessoas.

## 13.5 Trabalhos futuros

1. **Rodadas no computador de referência** (PV-01B com voz humana, PV-02 com o modelo real, PV-04 com GPU, PV-05B
   com gravação em vídeo, PV-07 de 8 horas), conforme o cronograma.
2. **Palavra de ativação:** calibração guiada na primeira execução; se "Safra" continuar com reconhecimento baixo
   com voz humana, escolher outra palavra com base em medição.
3. **Recuperação semântica local** para atender às paráfrases (meta RNF09), mantendo a recuperação lexical como
   explicação do resultado.
4. **Avaliação de usabilidade** com voluntários, se a instituição permitir.

Depois do congelamento de funcionalidades (maio de 2027), apenas correções e instrumentação entram no sistema; o
foco passa a ser medir, analisar e escrever.
