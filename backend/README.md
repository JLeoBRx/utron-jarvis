# Backend do SAFRA

Três pacotes Python instaláveis separadamente:

| Pasta | Pacote | O que é |
|---|---|---|
| `foundation/` | `safra_foundation` | biblioteca de base: erros, logs, configuração, banco, migrações, backup, senhas, saúde, base web. Sem domínio e sem estado |
| `assistant/` | `safra` | **SAFRA Assistant**: roda no computador do usuário, banco privado, API só em 127.0.0.1 |
| `portal/` | `safra_portal` | **SAFRA Portal**: site público e CMS, em servidor próprio, com banco próprio |

Os dois serviços dependem da biblioteca de base e **não se conhecem**: não há importação, rota, banco, sessão,
credencial nem configuração em comum. `tests/isolation` (na raiz) confere isso, inclusive subindo cada serviço
num processo em que o outro não pode ser importado.

```text
pip install -e backend/foundation -e "backend/assistant[dev]" -e "backend/portal[dev]"
(cd backend/foundation && pytest) ; (cd backend/assistant && pytest) ; (cd backend/portal && pytest) ; pytest tests
```
