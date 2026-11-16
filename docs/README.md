# Documentação do SAFRA — nova geração

Situação em 15/11/2026: **Fase 1 concluída; Fase 2 entregue com pendências** (ver o relatório). A documentação
do legado e do TCC da fase anterior continua em `ULTRON/docs/`.

| Pasta | Documento | Conteúdo | Situação |
|---|---|---|---|
| `architecture/` | [`LEGACY_AUDIT.md`](architecture/LEGACY_AUDIT.md) | diagnóstico do legado, problemas, dados a preservar | feito |
| | [`TARGET_ARCHITECTURE.md`](architecture/TARGET_ARCHITECTURE.md) | quatro ambientes, dois serviços, módulos, estrutura de pastas | feito; atualizado na Fase 2 |
| | [`DATA_MODEL.md`](architecture/DATA_MODEL.md) | os dois bancos, com diagramas, regras e índices | feito |
| | [`DESKTOP_SHELL_POC.md`](architecture/DESKTOP_SHELL_POC.md) | prova de conceito Tauri × QtWebEngine, medida no contêiner e no Windows do CI | feito; decisão aberta |
| `engineering/` | [`PHASE_2_REPORT.md`](engineering/PHASE_2_REPORT.md) | relatório da Fase 2: o que foi feito, critérios de aceitação, resultados, pendências | feito |
| | [`FEATURE_INVENTORY.md`](engineering/FEATURE_INVENTORY.md) | cada funcionalidade e o seu destino | feito; atualizado na Fase 2 |
| | [`MIGRATION_PLAN.md`](engineering/MIGRATION_PLAN.md) | riscos, fases, critérios de aprovação, cronograma | feito; atualizado na Fase 2 |
| | [`LICENSE_INVENTORY.md`](engineering/LICENSE_INVENTORY.md) | licenças das dependências diretas e transitivas (Python, npm, Rust), obrigações e riscos | feito; a decisão de licença (AD-17) continua aberta |
| `decisions/` | [`ARCHITECTURE_DECISIONS.md`](decisions/ARCHITECTURE_DECISIONS.md) | 24 decisões, com alternativas e situação | AD-07, AD-13 e AD-17 abertas |
| `security/` | [`PORTAL_PERMISSIONS.md`](security/PORTAL_PERMISSIONS.md) | papéis, permissões e cada rota administrativa | feito; gerado do código e conferido por teste |
| | [`PORTAL_THREAT_MODEL.md`](security/PORTAL_THREAT_MODEL.md) | ameaças ao Portal, mitigação e o teste de cada uma | feito |
| | [`PORTAL_AUTHENTICATION.md`](security/PORTAL_AUTHENTICATION.md) | senhas, sessões, bloqueio e recuperação, conferidos com a OWASP | feito |
| `performance/` | [`BASELINE.md`](performance/BASELINE.md) | linha de base medida do legado; metas da nova versão | feito |
| | `data/` | dados brutos das medições (legado e cascas do desktop) | — |
| `migration/` | — | importação dos dados do legado, relatórios | Fase 6 |
| `deployment/` | — | ambientes, publicação, domínio, backup, retorno | Fase 11 |
| `user-guide/` | — | instalação, uso, administração | Fases 10–12 |
| `academic/` | — | TCC reescrito para o novo escopo | Fase 12 |

## Documentos anteriores que continuam valendo

Em `ULTRON/docs/especificacao/` (14/11/2026, antes da missão de reconstrução integral):

| Documento | Uso agora |
|---|---|
| `CONTRATO_V1.md` | base da API do SAFRA Core |
| `ESPECIFICACAO_DA_INTERFACE.md` | base do design system e do console; será estendida ao portal e ao admin |
| `REQUISITOS_SAFRA.md` | base dos requisitos; falta acrescentar portal, CMS e gateway de IA |
| `DECISOES.md`, `PLANO_DE_MIGRACAO.md` | substituídos por `decisions/` e `engineering/MIGRATION_PLAN.md` (a tabela de correspondência está no fim das decisões) |

## Como repetir o que foi medido e testado

```text
pip install -e backend/foundation -e "backend/assistant[dev]" -e "backend/portal[dev]"
(cd backend/foundation && pytest); (cd backend/assistant && pytest); (cd backend/portal && pytest); pytest tests
(cd apps/admin && npm ci && npm test && npm run build)
python scripts/e2e/portal_e2e.py                 ponta a ponta no navegador (exige o painel compilado)
python scripts/licenses/inventory.py             inventário de licenças
python desktop/measure_shell.py --help           medição das cascas do desktop
python scripts/perf/legacy_baseline.py           linha de base do legado (ambiente do legado)
cd ULTRON && python TEST_JARVIS.py               testes do legado
```
