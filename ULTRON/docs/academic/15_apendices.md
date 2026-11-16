# APÊNDICE A — PROTOCOLOS DE VALIDAÇÃO EXPERIMENTAL

<!-- incluir: ../research/PROTOCOLOS_DE_VALIDACAO.md | a partir de: ## 0. Regras gerais | nivel: 2 | numerar: A -->

# APÊNDICE B — INVENTÁRIO DE FUNCIONALIDADES

<!-- incluir: ../technical/INVENTARIO_FUNCIONALIDADES.md | a partir de: ## Critérios | nivel: 2 | numerar: B -->

# APÊNDICE C — CRONOGRAMA ATÉ A CONCLUSÃO

<!-- incluir: ../technical/CRONOGRAMA.md | a partir de: ## 1. Princípios | nivel: 2 | numerar: C -->

# APÊNDICE D — ARQUIVOS DE DADOS E COMO REPRODUZIR

Todos os resultados citados no Capítulo 12 estão em `docs/research/resultados/` (JSON com dados brutos,
ambiente e a lista do que foi real e simulado). Para reproduzir no ambiente de desenvolvimento:

```text
python TEST_JARVIS.py                                         # suíte automatizada
python tools/experimentos/pv01_ativacao.py --rotulo meu-pc     # PV-01 (voz sintética)
python tools/experimentos/pv02_latencia.py --rotulo meu-pc     # PV-02 (com --ollama URL para o modelo real)
python tools/experimentos/pv03_memoria.py --rotulo meu-pc      # PV-03
python tools/experimentos/pv04_interface.py --rotulo meu-pc    # PV-04 (precisa de tela; no Linux, xvfb-run -a)
python tools/experimentos/pv05_sincronizacao.py --rotulo meu-pc  # PV-05 etapa A
python tools/experimentos/pv06_seguranca.py --rotulo meu-pc    # PV-06
python tools/experimentos/pv07_estabilidade.py --minutos 480 --rotulo meu-pc   # PV-07
```

O repositório está em `JLeoBRx/utron-jarvis`; a versão analisada neste texto é identificada pelo commit
registrado em cada arquivo de resultado.
