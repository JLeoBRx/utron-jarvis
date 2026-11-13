# Documentação do SAFRA

O SAFRA é a plataforma inteligente modular desenvolvida neste repositório (identidades anteriores: JARVIS
e ULTRON). Esta pasta reúne a documentação **canônica** do projeto e do Trabalho de Conclusão de Curso.
Os documentos na raiz de `ULTRON/` (`ARCHITECTURE_*.md`, `TEST_REPORT.md`, relatórios de fases…) são
**registros históricos** das fases anteriores: continuam válidos como evidência do que foi feito na época,
mas o estado atual está aqui.

## Onde está cada coisa

| Pasta / arquivo | Conteúdo |
|---|---|
| [`academic/`](academic/) | o TCC: capítulos editáveis em Markdown (`NN_*.md`) e o documento montado `TCC_SAFRA.md` (gerado — edite os capítulos) |
| [`export/`](export/) | versões DOCX (editáveis no Word/LibreOffice) e PDF do TCC e do relatório técnico |
| [`technical/RELATORIO_TECNICO.md`](technical/RELATORIO_TECNICO.md) | relatório técnico de desenvolvimento e evolução (engenharia) |
| [`technical/AUDITORIA_TRANSFORMACAO_SAFRA.md`](technical/AUDITORIA_TRANSFORMACAO_SAFRA.md) | **auditoria da transformação em SAFRA (13/11/2026)**: diagnóstico, mapas, riscos, arquitetura proposta, plano e decisões que aguardam aprovação |
| [`technical/AUDITORIA_INICIAL.md`](technical/AUDITORIA_INICIAL.md) | auditoria do repositório antes da fase SAFRA (histórico, para o TCC da fase anterior) |
| [`technical/INVENTARIO_FUNCIONALIDADES.md`](technical/INVENTARIO_FUNCIONALIDADES.md) | cada funcionalidade com estado e evidência |
| [`technical/ARQUITETURA.md`](technical/ARQUITETURA.md) | arquitetura com diagramas |
| [`technical/REQUISITOS.md`](technical/REQUISITOS.md) | requisitos funcionais, não funcionais, de segurança e critérios de aceitação |
| [`technical/TESTES.md`](technical/TESTES.md) | estratégia de testes, comandos, ambientes e resultados |
| [`technical/CRONOGRAMA.md`](technical/CRONOGRAMA.md) | cronograma mensal até a entrega em 2027 |
| [`technical/CHANGELOG.md`](technical/CHANGELOG.md) | marcos de versão (o detalhe fica em `../CHANGELOG_JARVIS.md`) |
| [`diagrams/`](diagrams/) | diagramas (fontes Mermaid em `src/`, imagens SVG/PNG) |
| [`research/`](research/) | protocolos de validação experimental, registro das referências verificadas, resultados das medições (`resultados/`, com índice) |
| `benchmarks/`, `capturas/`, `inventario/` | evidências das fases anteriores (medições, capturas, inventário do original) |

## Gerar diagramas e documentos

```bash
# diagramas (precisa de Node 18+ e do Playwright com Chromium)
mkdir -p /tmp/mmd && cd /tmp/mmd && npm init -y && npm install mermaid@11.4.1 playwright
node <repo>/ULTRON/docs/diagrams/render.js <repo>/ULTRON/docs/diagrams/src <repo>/ULTRON/docs/diagrams \
     /tmp/mmd/node_modules/mermaid/dist/mermaid.min.js

# TCC e relatório técnico em DOCX e PDF (precisa de pandoc, python-docx e Node com Playwright)
python tools/montar_documentos.py            # --so-md: só monta docs/academic/TCC_SAFRA.md
```

## Nomes e compatibilidade

| O que | Nome |
|---|---|
| Produto, interface, voz, documentos | **SAFRA** |
| Pasta do código, pacote Python, pasta de dados, banco | `ULTRON/`, `ultron`, `%LOCALAPPDATA%\ULTRON`, `ultron.sqlite3` (mantidos para não quebrar instalações e dados) |
| Scripts do Windows | `START_JARVIS.bat`, `INSTALL_JARVIS.bat`… (mantidos) e os atalhos `START_SAFRA.bat`, `INSTALL_SAFRA.bat`, `ATUALIZAR_SAFRA.bat`, `DIAGNOSTICO_SAFRA.bat` |
| Identidade alternativa | Protocolo ULTRON (evento de identidade reversível) |
