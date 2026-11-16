# SAFRA

Plataforma inteligente integrada: um assistente que roda no computador do usuário, com interface operacional,
e um portal público com painel administrativo. Projeto de conclusão de curso técnico em Desenvolvimento de
Sistemas, com conclusão prevista para 2027.

O repositório está em **reconstrução integral**. Há duas coisas aqui:

| Pasta | O que é | Situação |
|---|---|---|
| `backend/`, `apps/`, `packages/`, `desktop/`, `tests/`, `scripts/`, `docs/` | a **nova geração** (4.x): dois serviços independentes, o **SAFRA Assistant** (local) e o **SAFRA Portal** (site público e CMS) | Portal e painel administrativo implementados e testados; Assistant com fundação, modelo de dados e API mínima; casca do desktop em prova de conceito |
| `ULTRON/` | o **legado** (3.0.0): o aplicativo que funciona hoje | preservado, executável e intocado até a nova versão ser validada |

## Por onde começar

- O que foi decidido e por quê: [`docs/decisions/ARCHITECTURE_DECISIONS.md`](docs/decisions/ARCHITECTURE_DECISIONS.md)
- Para onde o projeto vai: [`docs/architecture/TARGET_ARCHITECTURE.md`](docs/architecture/TARGET_ARCHITECTURE.md)
- O plano, fase a fase: [`docs/engineering/MIGRATION_PLAN.md`](docs/engineering/MIGRATION_PLAN.md)
- Índice de toda a documentação: [`docs/README.md`](docs/README.md)
- Backend novo: [`backend/README.md`](backend/README.md)
- Relatório da Fase 2: [`docs/engineering/PHASE_2_REPORT.md`](docs/engineering/PHASE_2_REPORT.md)

## Usar o SAFRA hoje

A versão utilizável continua sendo o legado: instalação e uso em
[`ULTRON/README_JARVIS.md`](ULTRON/README_JARVIS.md) (`ULTRON\INSTALL_SAFRA.bat`, `ULTRON\START_SAFRA.bat`).
A nova geração ainda não substitui nenhuma função do aplicativo.

## Executar a nova geração em desenvolvimento

Python 3.11 ou mais novo e Node.js 22. Os dois serviços sobem separados, cada um com o seu banco; nenhum precisa
do outro.

```text
pip install -e backend/foundation -e "backend/assistant[dev]" -e "backend/portal[dev]"

safra-assistant --check                 Assistant: valida, migra o banco privado e informa a saúde
safra-assistant                         Assistant: API em http://127.0.0.1:47800

cd apps/admin && npm ci && npm run build && cd ../..    compila o painel administrativo
safra-portal create-admin --email voce@exemplo.com --name "Seu Nome"     cria a primeira conta (pede a senha)
safra-portal                            Portal: site em http://127.0.0.1:47900, painel em /admin/
```

Testes: ver [`docs/README.md`](docs/README.md#como-repetir-o-que-foi-medido-e-testado).

## Estado declarado

Nada da nova geração foi validado no Windows do autor nem publicado na internet; o CI roda em Linux e Windows.
Cada documento distingue o que está planejado, implementado, testado e validado.
