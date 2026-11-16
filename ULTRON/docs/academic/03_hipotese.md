# 3 HIPÓTESE

Formula-se a seguinte hipótese, investigável pela implementação e pelos testes do protótipo:

> **H — Uma arquitetura modular orientada a eventos, na qual um núcleo único concentra o estado global, a
> memória persistente e a execução das ações, enquanto os demais subsistemas (voz, interface humanoide 3D,
> ambiente TARDIS e memória pessoal) atuam como serviços desacoplados que publicam e consomem eventos,
> permite integrar essas modalidades em um computador pessoal com processamento local, atendendo às quatro
> condições abaixo.**

| Condição | Enunciado verificável | Como será testada | Questão |
|---|---|---|---|
| **H1 — Isolamento de falhas** | a indisponibilidade ou a falha de um subsistema periférico não interrompe o núcleo, que continua atendendo pedidos pelas modalidades restantes | testes de injeção de falhas (banco danificado e somente leitura, modelo indisponível, cena 3D sem WebGL, sensor com erro, assinante do Event Bus que falha) | Q1 |
| **H2 — Controle das ações** | nenhuma ação fora das permissões configuradas, sem autorização exigida ou sobre alvos protegidos é executada | casos de teste de segurança (alvos protegidos, ferramentas não oferecidas ao modelo, autorização negada ou expirada, conteúdo de tela tratado como dado) — taxa de bloqueio esperada de 100 % | Q2 |
| **H3 — Desempenho** | tempos de resposta, inicialização e taxa de quadros atendem às metas RNF01–RNF05 no computador de referência | protocolos PV-02 e PV-04 | Q3 |
| **H4 — Coerência multimodal** | os estados exibidos derivam de eventos reais e a defasagem entre áudio e boca fica dentro dos limites de percepção (RNF08) | testes de transição de estados e protocolo PV-05 | Q4 |

**Critério de decisão.** A hipótese será considerada:

* **sustentada**, se H1 a H4 forem atendidas;
* **parcialmente sustentada**, se H1 e H2 (as condições arquiteturais e de segurança) forem atendidas e
  pelo menos uma entre H3 e H4 não for, ou não puder ser medida no computador de referência;
* **não sustentada**, se H1 ou H2 não forem atendidas.

A distinção reflete a natureza do trabalho: H1 e H2 dependem da arquitetura proposta; H3 e H4 dependem
também do hardware e dos modelos pré-treinados utilizados.
