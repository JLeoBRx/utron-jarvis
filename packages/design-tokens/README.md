# Design tokens

`tokens.json` é a **fonte única** da identidade visual do SAFRA: cores (as sete definidas pelo autor mais as
derivadas para acessibilidade), medidas, raios, fontes e tempos de movimento. Também lista os pares de cor em uso
e o contraste mínimo de cada um.

```text
python packages/design-tokens/build.py          gera tokens.css no Portal e no painel
python packages/design-tokens/build.py --check  falha se algum tokens.css estiver desatualizado
```

`tests/workspace/test_design_tokens.py` confere o contraste de todos os pares e a sincronia dos arquivos gerados.
As fontes são nomeadas por pilha: nenhuma fonte é distribuída com o projeto enquanto o inventário de licenças não
registrar a licença do arquivo.
