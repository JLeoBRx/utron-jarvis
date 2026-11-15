# safra_foundation — biblioteca de base

Código comum ao **SAFRA Assistant** e ao **SAFRA Portal**: formato de erro, logs estruturados, leitura de
configuração, motor do banco, migrações, backup e restauração, guarda de senhas, *tokens*, verificação de saúde e
a base das aplicações web.

É uma biblioteca: **não tem domínio, não tem banco, não tem rotas, não guarda estado**. Os dois serviços a
instalam, mas nenhum deles conhece o outro. Compartilhar esta biblioteca não cria comunicação entre os serviços.

```text
pip install -e ".[dev]" && pytest
```
