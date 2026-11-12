# RELATÓRIO TÉCNICO DE DESENVOLVIMENTO E EVOLUÇÃO DO SAFRA

## 1. Identificação

| Campo | Valor |
|---|---|
| Projeto | SAFRA — plataforma inteligente modular local (identidades anteriores: JARVIS, ULTRON) |
| Versão do aplicativo | 3.0.0 (fase SAFRA; a versão anterior, JARVIS, era 2.0.0) |
| Repositório | `JLeoBRx/utron-jarvis`, branch `claude/adoring-brahmagupta-vcejpt` |
| Commit de referência do estado inicial | `bf070f6` (2026-11-03) |
| Commits desta fase | `07fcda6` (etapa 1), `c5f8313` (2), `35a7554` (3), `456fe23` (4) e o commit da etapa 5 — ver seção 8 |
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

### Etapa 2 — escopo, requisitos e cronograma (commit `c5f8313`)

* Criados: `docs/technical/REQUISITOS.md` (RF01–RF37, RNF01–RNF16, RS01–RS11, RT01–RT08, CA01–CA05,
  rastreabilidade), `docs/technical/CRONOGRAMA.md` (+ diagrama `10_cronograma`), capítulos 2–5 do TCC
  (`docs/academic/02…05`), este relatório.
* Decisões: título revisado sem robótica; hipótese com quatro condições verificáveis (H1–H4) e critério
  de decisão; congelamento de funcionalidades em maio de 2027.

### Etapa 3 — identidade SAFRA (commit `35a7554`)

**O que mudou**

| Área | Mudança | Arquivos principais |
|---|---|---|
| Nome visível | "JARVIS" → "SAFRA" em textos da interface, voz, console, diagnóstico, mensagens de erro, prompt de identidade, site da ORBE, scripts `.bat` (só os textos), manual e README | 133 módulos (texto), `README_JARVIS.md`, `../README.md`, `*.bat` |
| Versão | 2.0.0 → **3.0.0** | `ultron/__init__.py` |
| Paleta | azul/ciano → vermelho SAFRA, bordô, preto, grafite; âmbar (atenção), laranja (falha); violeta e cromo só no ULTRON | `hud/design/tokens.json`, `hud/palette.py`, `css/tokens.css` (gerado) |
| Qt | folhas de estilo **geradas da paleta** (antes eram cores literais); cantos retos, filete vermelho nas abas | `hud/theme.py`, 9 módulos recoloridos |
| Cena 3D | holograma, roupas, cabelo, ORBE, piso, luzes, telas da TARDIS e camada de interface em vermelho; cabine externa **azul preservada** | `web/js/*.js`, `web/css/scene.css` |
| Protocolo ULTRON | vermelho → violeta e cromo (para continuar distinguível) | `ultron.js`, `theme.ULTRON_SWAPS`, `controller.py` |
| Ativação por voz | "safra" passa a ser a primeira palavra; "jarvis" continua aceita; calibração aceita as duas e recusa palavras comuns próximas ("sobra", "cifra"…) | `voice/wake_word.py`, `config/settings.py`, `cognition/intent_engine.py` |
| Configurações | migração **v2 → v3** passo a passo, com cópia `settings.jarvis-backup.json`; preferências pessoais intactas | `config/settings.py` |
| Frases de comando | "restaurar SAFRA", "encerrar o SAFRA", "status do SAFRA"… somadas às antigas | `cognition/intent_engine.py` |
| Atalhos | `START_SAFRA.bat`, `INSTALL_SAFRA.bat`, `ATUALIZAR_SAFRA.bat`, `DIAGNOSTICO_SAFRA.bat` chamam os scripts de nome antigo | novos |
| Variáveis de ambiente | `SAFRA_<CAMPO>` e `SAFRA_DATA_DIR` aceitas, além de `JARVIS_*` e `ULTRON_*` | `config/settings.py`, `config/paths.py` |
| Design system | documento reescrito para o SAFRA, com contrastes medidos | `DESIGN_SYSTEM.md` |
| Testes | +3 testes (palavra de ativação "Safra" e compatibilidade; calibração; migração v2→v3); expectativas de texto atualizadas | `tests/test_voice.py`, `tests/test_jarvis_voice.py`, outros |

**Decisões**

| ID | Decisão | Justificativa |
|---|---|---|
| D1 | Manter identificadores internos: pasta `ULTRON/`, pacote `ultron`, dados `%LOCALAPPDATA%\ULTRON`, scripts `*_JARVIS.bat`, serviço "JARVIS" no cofre de credenciais, entrada "JARVIS" do início automático, pasta `Imagens\JARVIS`, pasta `JARVIS/` do pacote ZIP, objeto `window.JARVIS` da ponte com a cena 3D, cookies da web | mudar qualquer um deles quebra instalações, chaves salvas, atalhos ou a comunicação entre Python e a página (requisito RT06) |
| D2 | Vermelho primário `#EA2840`, não `#E5233A` | o primeiro candidato dava contraste 4,44:1 sobre o fundo; o escolhido dá 4,67:1 (WCAG AA ≥ 4,5:1) |
| D3 | ULTRON em violeta e cromo | com o SAFRA vermelho, a assinatura vermelha do ULTRON deixaria as duas identidades indistinguíveis |
| D4 | Atenção em âmbar e falha em laranja | numa interface vermelha, o vermelho não pode significar erro; estados continuam com cor **e** texto |
| D5 | Nome escrito "SAFRA", sem pontos, e subtítulo "PLATAFORMA INTELIGENTE LOCAL" | "S.A.F.R.A." sugere uma sigla que não foi definida; o subtítulo antigo era a expansão de "J.A.R.V.I.S." |
| D6 | "safra" como palavra de ativação e "jarvis" mantida | "jarvis" não está no vocabulário do reconhecedor; "safra" está (modelo grande). O custo é uma palavra comum: só vale no início da frase. Efeito medido na etapa 4 |
| D7 | Cabine externa da TARDIS continua azul; interior com energia vermelha | preservar a identidade da nave pedida pelo autor |

**Problemas encontrados durante a etapa (e como foram detectados)**

A troca de nome foi feita com um script que altera só literais de texto e comentários, protegendo nomes de
variáveis de ambiente e de arquivos. Mesmo assim, ele trocou identificadores que **pareciam texto**:

| Problema | Consequência se passasse | Como foi detectado | Correção |
|---|---|---|---|
| serviço do cofre de credenciais "JARVIS" → "SAFRA" | a chave da OpenAI já salva deixaria de ser encontrada | `test_security.CredentialsTest` | revertido |
| pastas do JARVIS original (`…\JARVIS\assistant.sqlite3`, `JARVIS\assets`) | importação de dados e modelos antigos pararia | `test_original_recovery` | revertido |
| prefixo de variáveis `"JARVIS_" + campo` | configurações por ambiente ignoradas | revisão do diff | `SAFRA_` somado aos antigos |
| entrada "JARVIS" do início automático | o início automático já ligado seria tratado como "outro programa" | revisão do diff (o CI do Windows também confere essa chave) | revertido |
| `window.JARVIS` (ponte Python → página 3D) | a cena 3D abriria, mas **não receberia nenhum estado** | `test_scene3d.NativeSceneTest` com QtWebEngine real sob Xvfb (1 erro de JavaScript) | revertido |
| quebras de linha CRLF dos `.bat` viraram LF | o `cmd.exe` pode não achar os rótulos do `goto` | `test_cli.WindowsScriptsTest` | CRLF restaurado |

Lição registrada: renomear um produto exige separar **nome visível** de **identificador**; a suíte de
testes — principalmente os testes de compatibilidade e o teste da cena real — foi o que impediu as
regressões.

**Verificação:** suíte completa aprovada (474 testes, 0 falhas, 1 pulado — a cena 3D real, executada à parte
e aprovada: 24/24 com QtWebEngine e WebGL por software); pyflakes e compileall limpos; pacote ZIP validado;
capturas em `docs/capturas/safra_*.jpg`.

### Etapa 4 — instrumentos, protocolos e medições (commit `456fe23`)

**Criados:** `tools/experimentos/` (`_comum.py` e um instrumento por protocolo PV-01…PV-07, mais a análise
exploratória das formas de ativação), `docs/research/PROTOCOLOS_DE_VALIDACAO.md`,
`docs/research/REFERENCIAS_VERIFICADAS.md`, `docs/research/resultados/*.json` e `README.md`, `TESTES.md`.

**Alterados (código):**

| Arquivo | Mudança | Motivo |
|---|---|---|
| `ultron/memory/retrieval.py` | comparação por palavra inteira (com variação de plural/gênero de até 3 letras no fim); fatos e episódios sem palavra em comum não entram | PV-03: "ana" casava com "losartana", "avo" com "favorito"; bônus de recência e uso deixavam passar fatos sem relação |
| `ultron/memory/semantic_memory.py`, `episodic_memory.py` | pré-filtro sem acentos, por palavra, sobre os 5.000 registros mais recentes | PV-03: o `LIKE` do SQL comparava "medico" com "médico" e não achava o fato |
| `ultron/voice/wake_word.py` | "faça" e afins proibidas como forma forte | PV-01: o Vosk grande ouviu o "Safra" sintetizado como "faça" em 156 de 180 frases |
| `tests/test_memory.py`, `tests/test_voice.py` | testes de regressão dos itens acima | — |

**Decisões:**

| ID | Decisão | Justificativa |
|---|---|---|
| D8 | Separar ambiente C (contêiner) e R (computador de referência) em todos os resultados | o contêiner não tem GPU, microfone nem alto-falante; nada medido nele pode representar o hardware |
| D9 | Repetir cada síntese de voz e reportar intervalos de confiança | o Piper (VITS) é estocástico: a mesma frase gera áudios diferentes |
| D10 | Não adotar "faça" como forma fraca por padrão | a análise exploratória mostrou ganho (2,2 % → 88,9 %) com custo (0 → 0,9 % de indevidas), mas sobre UMA voz sintética: seria ajustar o sistema ao teste |
| D11 | Avaliar a memória "antes" e "depois" das correções e guardar os dois arquivos | permite mostrar o efeito de cada correção sem reescrever o histórico |
| D12 | Métrica de estabilidade após o aquecimento | a série de 30 min mostrou um aquecimento de ~4 min (55,6 → 70 MB) seguido de crescimento lento; a regressão sobre a série inteira (19,2 MB/h) misturava as fases |

**Problemas dos próprios instrumentos (encontrados e corrigidos antes dos resultados finais):** os tempos por
palavra do Vosk se acumulavam entre frases no PV-05 (erros de dezenas de segundos — o reconhecedor passou a ser
recriado por frase). Na revisão do código, antes das rodadas finais: o PV-02 passou a ignorar respostas parciais
de progresso e as sementes de ruído do PV-01, que dependiam de `hash()`, passaram a ser fixas.

### Etapa 5 — TCC e relatório

**Criados:** `docs/academic/00…15_*.md` (capítulos editáveis), `docs/academic/TCC_SAFRA.md` (montado),
`tools/montar_documentos.py` (monta o TCC resolvendo as inclusões dos documentos técnicos — fonte única —, gera
DOCX com estilos no padrão de trabalhos acadêmicos e PDF A4 numerado), `docs/export/` (DOCX e PDF do TCC e deste
relatório).

**Decisões:** os capítulos de requisitos, arquitetura e os apêndices **incluem** os documentos técnicos em vez
de copiá-los (uma alteração vale para os dois); campos institucionais ficam como `[campo]` editável; nenhuma
conformidade com uma edição específica da ABNT é declarada (a NBR 14724 e a NBR 6023 receberam edições novas
em 2024–2025); a referência de Cohen e Massaro (1993) foi descartada por não ter sido confirmada.

## 9. Testes

Detalhes em [`TESTES.md`](TESTES.md). Síntese:

| Momento | Resultado |
|---|---|
| Linha de base (`bf070f6`) | 471 testes, 0 falhas (contêiner); CI 61 aprovado em Linux e Windows |
| Fim da etapa 3 | 474 testes, 0 falhas; cena 3D real 24/24 |
| Fim da etapa 4 | **475 testes, 0 falhas**; pyflakes e compileall limpos; pacote ZIP validado |
| Defeitos encontrados na fase | 10 (6 da renomeação, 3 da recuperação de memória, 1 risco na calibração), todos corrigidos com teste |

## 10. Segurança e integridade

* **Dados do usuário:** nenhum teste ou experimento lê ou altera `%LOCALAPPDATA%\ULTRON`; todos usam pastas
  temporárias definidas antes de importar o pacote.
* **Compatibilidade:** pasta, pacote, banco, scripts antigos, serviço do cofre, entrada do início automático,
  pasta de imagens, pasta do ZIP e ponte `window.JARVIS` mantidos (decisão D1). A migração de configurações
  v2 → v3 guarda `settings.jarvis-backup.json` e não altera preferências pessoais; "jarvis" continua aceita.
* **Banco:** nenhuma tabela apagada (as duas do módulo descontinuado continuam inertes); nenhuma migração nova.
* **Permissões:** nenhuma regra afrouxada; a PV-06 confirmou 11/11 bloqueios com 4/4 controles.
* **Backups:** estado inicial preservado no histórico remoto (`bf070f6`) e nas branches de segurança do autor,
  não modificadas. Nada foi mesclado na `main`.

## 11. Limitações

| Limitação | Efeito no TCC | Como será tratada |
|---|---|---|
| Voz medida só com uma voz sintética | a taxa de ativação não representa a voz humana | PV-01 etapa B (voz do autor e, se permitido, de voluntários) |
| WebGL por software no contêiner | quadros/s sem valor para a meta RNF04 | PV-04 no computador de referência |
| Inferência simulada | tempo com o modelo real desconhecido | PV-02 com `--ollama` |
| Atraso áudio × tela não medido | RNF08 não avaliado | PV-05 etapa B (vídeo a 60 q/s) |
| Estabilidade de 30 min | meta é 8 h | PV-07 de 8 h |
| Recuperação lexical | paráfrases 45 % | recuperação semântica local (trabalho futuro) |
| "Safra" mal reconhecida com voz sintética | ativação abaixo do esperado | calibração; teste com voz humana; nova escolha de palavra se necessário |
| Conjuntos de teste pequenos e escritos pelo autor | generalização limitada | declarado no TCC |
| Bandeja, notificações nativas, UI Automation, SAPI, OCR, visão, início automático não verificados | itens "não verificados" no inventário | fora das hipóteses; verificação manual no Windows |

## 12. Próximas etapas

Ver [`CRONOGRAMA.md`](CRONOGRAMA.md). Prioridades até o congelamento (maio/2027): (1) validar o escopo e o título
com o orientador; (2) rodadas no computador de referência (piloto em fevereiro, oficiais em março e maio);
(3) decisão sobre a palavra de ativação com base na voz humana; (4) recuperação semântica local, se couber no
cronograma; (5) confirmar o manual de formatação da instituição.

## 13. Conclusão técnica

O SAFRA é um sistema real e funcional na sua lógica: 475 testes automatizados aprovados, CI em Linux e Windows,
arquitetura de núcleo único documentada a partir do código e camadas de segurança que bloquearam todas as
tentativas medidas sem bloquear as ações legítimas. A nova identidade foi aplicada sem quebrar instalações nem
dados — e os testes impediram seis regressões que a renomeação introduziria. As medições desta fase também
mostraram o que **não** está bom: a nova palavra de ativação não foi mais bem reconhecida com voz sintética, e a
recuperação de memória não entende paráfrases; três defeitos de memória foram encontrados e corrigidos pelas
próprias medições. O que falta para o TCC é medir a fronteira com o hardware (voz humana, GPU, modelo real,
atraso de apresentação e 8 horas de execução) no computador de referência. Com os instrumentos e protocolos
prontos, essa medição depende de tempo e do equipamento do autor, não de desenvolvimento novo.
