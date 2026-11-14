# Documentação do SAFRA — nova geração

Situação em 14/11/2026: **Fase 1 concluída; Fase 2 em andamento.** A documentação do legado e do TCC da fase
anterior continua em `ULTRON/docs/`.

| Pasta | Documento | Conteúdo | Situação |
|---|---|---|---|
| `architecture/` | [`LEGACY_AUDIT.md`](architecture/LEGACY_AUDIT.md) | diagnóstico do legado, problemas, dados a preservar | feito |
| | [`TARGET_ARCHITECTURE.md`](architecture/TARGET_ARCHITECTURE.md) | quatro ambientes, dois serviços, módulos, estrutura de pastas | feito |
| `engineering/` | [`FEATURE_INVENTORY.md`](engineering/FEATURE_INVENTORY.md) | cada funcionalidade e o seu destino | feito |
| | [`MIGRATION_PLAN.md`](engineering/MIGRATION_PLAN.md) | riscos, 12 fases, critérios de aprovação, cronograma | feito |
| `decisions/` | [`ARCHITECTURE_DECISIONS.md`](decisions/ARCHITECTURE_DECISIONS.md) | 19 decisões, com alternativas e situação | feito; 2 propostas e 3 abertas |
| `performance/` | [`BASELINE.md`](performance/BASELINE.md) | linha de base medida do legado; metas da nova versão | feito |
| | `data/` | dados brutos das medições | — |
| `security/` | — | matriz de permissões, modelo de ameaças | Fase 2 |
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
python scripts/perf/legacy_baseline.py          linha de base do legado (ambiente do legado)
cd backend && pip install -e ".[dev]" && pytest  testes da nova geração
cd ULTRON && python TEST_JARVIS.py               testes do legado
```
