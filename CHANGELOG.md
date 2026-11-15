# Registro de mudanças — SAFRA, nova geração

O registro do legado (até a versão 3.0.0) continua em `ULTRON/CHANGELOG_JARVIS.md`.

## 4.0.0.dev0 — em desenvolvimento

### 14/11/2026 — Fase 1 (auditoria do legado) e início da Fase 2 (fundação)

**Documentação** (`docs/`)
- Auditoria do legado, inventário de funcionalidades (108 itens com destino), linha de base de desempenho
  medida, arquitetura alvo, 19 decisões de arquitetura e plano de entregas em 12 fases.
- Instrumento de medição do legado: `scripts/perf/legacy_baseline.py`, com os dados brutos versionados.

**Backend** (`backend/`)
- Pacote `safra` com os 13 módulos do SAFRA Core e pacote `safra_portal`.
- Implementado e testado: configuração validada; erros com código estável; logs em JSON com correlação e
  mascaramento de segredos; motor do banco; migrações versionadas com retorno e backup verificado; guarda de
  senhas com scrypt; *tokens*; registro de saúde; aplicação base da API (formato único de erro, guarda de
  `Host`, cabeçalhos de segurança); rota de saúde; linha de comando `safra-core`.
- Regras de arquitetura conferidas por teste: camadas, ciclos, construções proibidas, independência do legado,
  ausência de nomes de terceiros.
- CI próprio (`.github/workflows/safra-ci.yml`): Linux e Windows, Python 3.11 e 3.13. Primeira execução
  aprovada nos quatro ambientes, no commit `f54f616`.

**Legado**
- Nenhum arquivo de `ULTRON/` foi alterado.
