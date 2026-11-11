# RELATÓRIO TÉCNICO DE DESENVOLVIMENTO E EVOLUÇÃO DO SAFRA

## 1. Identificação

| Campo | Valor |
|---|---|
| Projeto | SAFRA — plataforma inteligente modular local (identidades anteriores: JARVIS, ULTRON) |
| Versão do aplicativo | 3.0.0 (fase SAFRA; a versão anterior, JARVIS, era 2.0.0) |
| Repositório | `JLeoBRx/utron-jarvis`, branch `claude/adoring-brahmagupta-vcejpt` |
| Commit de referência do estado inicial | `bf070f6` (2026-11-03) |
| Commits desta fase | registrados na seção 8 |
| Data de início da fase | 2026-11-11 |
| Responsável | autor do TCC (dados institucionais em `docs/academic/00_pre_textuais.md`) |
| Desenvolvimento assistido | assistente de programação por IA, sob instruções e revisão do autor |

## 2. Resumo executivo

O SAFRA é um assistente inteligente que roda no computador do usuário: recebe pedidos por voz ou texto,
responde com voz sintetizada e um holograma 3D, guarda memórias num banco local e executa ações no
computador sob um sistema de permissões e autorizações. Esta fase transforma o projeto — antes chamado
JARVIS — em objeto de um TCC técnico: (1) auditoria do estado real; (2) definição do escopo científico,
requisitos e cronograma; (3) nova identidade SAFRA; (4) instrumentos e protocolos de medição; (5) TCC e
este relatório.

**Estado no início da fase:** 206 módulos Python (46 mil linhas), cena 3D em JavaScript (4,3 mil linhas),
471 testes automatizados aprovados em Python 3.11 e 3.13 e no CI do Windows. A lógica está amplamente
verificada; a fronteira com o hardware (microfone, alto-falante, GPU, sessão interativa do Windows) e com os
modelos reais nunca foi medida. O módulo de robótica (NOCTARIO) foi descontinuado e está fora do escopo.

## 3. Estado inicial

Descrito em detalhe em [`AUDITORIA_INICIAL.md`](AUDITORIA_INICIAL.md). Pontos principais:

* arquitetura de núcleo único (`NeuralCore`) com Event Bus, estado global, executor único e banco SQLite
  único (27 tabelas, migrações v1–v7);
* identidade visual azul/ciano centralizada em tokens (`ultron/hud/design/tokens.json`), ainda com cores
  literais em alguns módulos;
* palavra de ativação "Jarvis", fora do vocabulário dos modelos de reconhecimento;
* documentação espalhada em 25 arquivos na raiz de `ULTRON/`, parte desatualizada;
* linha de base de testes neste ambiente: **471 testes, 0 falhas, 1 pulado**
  (`docs/research/resultados/linha_de_base_bf070f6.txt`).

## 4. Auditoria da arquitetura

Ver [`ARQUITETURA.md`](ARQUITETURA.md) (princípios, camadas, componentes, fluxos, armazenamento,
interface, falhas, integrações, concorrência) e os diagramas em `docs/diagrams/`.

## 5. Inventário de funcionalidades

Ver [`INVENTARIO_FUNCIONALIDADES.md`](INVENTARIO_FUNCIONALIDADES.md). Resumo (84 itens): 68 funcionais,
2 parciais, 8 não verificadas, 1 em desenvolvimento, 2 planejadas, 3 descontinuadas ou substituídas.

## 6. Problemas encontrados

Tabela P1–P12 em `AUDITORIA_INICIAL.md` §10. Os de maior impacto para o TCC:

| # | Problema | Efeito |
|---|---|---|
| P5 | "Jarvis" fora do vocabulário do reconhecedor | ativação por voz depende de calibração e de formas fracas |
| P7 | vermelho já usado como assinatura do Protocolo ULTRON | conflito com a nova identidade |
| P8, P9 | desempenho 3D, voz, memória e sincronização nunca medidos com hardware real | o TCC não pode afirmar resultados sem protocolos |

## 7. Plano de transformação

| Etapa | Conteúdo | Critério de conclusão |
|---|---|---|
| 1 | Auditoria, inventário, arquitetura e diagramas | documentos versionados; nenhum código alterado |
| 2 | Escopo científico, requisitos, cronograma | `REQUISITOS.md`, `CRONOGRAMA.md`, capítulos 2–5 do TCC |
| 3 | Identidade SAFRA | nome visível, tokens vermelhos, holograma, ORBE, TARDIS, web, palavra de ativação; identificadores internos preservados; suíte aprovada |
| 4 | Medição | ferramentas em `tools/experimentos/`, protocolos PV-01…PV-07, medições possíveis neste ambiente, rotuladas |
| 5 | TCC e relatório | capítulos completos, referências verificadas, DOCX e PDF |

## 8. Mudanças realizadas

### Etapa 1 — auditoria (commit `07fcda6`)

* Criados: `docs/README.md`, `docs/technical/AUDITORIA_INICIAL.md`, `INVENTARIO_FUNCIONALIDADES.md`,
  `ARQUITETURA.md`, `docs/diagrams/` (9 diagramas + `render.js`), `docs/research/resultados/linha_de_base_bf070f6.txt`.
* Nenhum arquivo de código alterado, movido ou removido.

### Etapa 2 — escopo, requisitos e cronograma

* Criados: `docs/technical/REQUISITOS.md` (RF01–RF37, RNF01–RNF16, RS01–RS11, RT01–RT08, CA01–CA05,
  rastreabilidade), `docs/technical/CRONOGRAMA.md` (+ diagrama `10_cronograma`), capítulos 2–5 do TCC
  (`docs/academic/02…05`), este relatório.
* Decisões: título revisado sem robótica; hipótese com quatro condições verificáveis (H1–H4) e critério
  de decisão; congelamento de funcionalidades em maio de 2027.

## 9. Testes

Ver [`TESTES.md`](TESTES.md) (atualizado ao fim de cada etapa).

## 10. Segurança e integridade

* Nenhum dado do usuário é lido ou alterado pelos testes (pastas temporárias definidas antes de qualquer
  import).
* Nenhum banco foi apagado; as tabelas do módulo descontinuado continuam no esquema.
* Backup: o estado inicial está preservado no histórico remoto (`bf070f6`) e nas branches de segurança do
  autor (`safety/backup-before-phase-7-8-20261029`, `work/phase-7-8-safe-release`), não modificadas.

## 11. Limitações

Registradas ao fim do trabalho (ver seção 13).

## 12. Próximas etapas

Ver [`CRONOGRAMA.md`](CRONOGRAMA.md).

## 13. Conclusão técnica

Redigida ao fim da fase.
