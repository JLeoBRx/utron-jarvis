# Testes entre serviços

Os testes de cada pacote ficam junto dele (`backend/*/tests`). Aqui ficam os que olham para **mais de um pacote**:

| Pasta | O que confere |
|---|---|
| `isolation/` | o SAFRA Assistant e o SAFRA Portal não se conhecem: sem importações cruzadas, sem rotas em comum, sem banco, sessão, credencial ou configuração compartilhados; cada um sobe e funciona sem o outro instalado |
| `workspace/` | regras do repositório inteiro: contraste e sincronia dos *tokens* de design, ausência de nomes de terceiros e de segredos, legado não importado |

```text
pip install -e backend/foundation -e backend/assistant -e backend/portal pytest httpx
pytest tests
```
