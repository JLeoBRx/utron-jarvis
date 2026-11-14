# SAFRA

Plataforma inteligente integrada: um assistente que roda no computador do usuário, com interface operacional,
e um portal público com painel administrativo. Projeto de conclusão de curso técnico em Desenvolvimento de
Sistemas, com conclusão prevista para 2027.

O repositório está em **reconstrução integral**. Há duas coisas aqui:

| Pasta | O que é | Situação |
|---|---|---|
| `backend/`, `docs/`, `scripts/` (e, nas próximas fases, `frontend/`, `desktop/`, `infra/`) | a **nova geração** (4.x) | fundação do backend implementada e testada; o restante é plano |
| `ULTRON/` | o **legado** (3.0.0): o aplicativo que funciona hoje | preservado, executável e intocado até a nova versão ser validada |

## Por onde começar

- O que foi decidido e por quê: [`docs/decisions/ARCHITECTURE_DECISIONS.md`](docs/decisions/ARCHITECTURE_DECISIONS.md)
- Para onde o projeto vai: [`docs/architecture/TARGET_ARCHITECTURE.md`](docs/architecture/TARGET_ARCHITECTURE.md)
- O plano, fase a fase: [`docs/engineering/MIGRATION_PLAN.md`](docs/engineering/MIGRATION_PLAN.md)
- Índice de toda a documentação: [`docs/README.md`](docs/README.md)
- Backend novo: [`backend/README.md`](backend/README.md)

## Usar o SAFRA hoje

A versão utilizável continua sendo o legado: instalação e uso em
[`ULTRON/README_JARVIS.md`](ULTRON/README_JARVIS.md) (`ULTRON\INSTALL_SAFRA.bat`, `ULTRON\START_SAFRA.bat`).
A nova geração ainda não substitui nenhuma função do aplicativo.

## Estado declarado

Nada da nova geração foi validado em Windows real. Cada documento distingue o que está planejado, implementado,
testado e validado.
