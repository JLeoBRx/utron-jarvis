# J.A.R.V.I.S. // FASE 20 — WINDOWS STATE ADAPTER

Camada somente-leitura que traduz sinais estruturais do Windows para o World Model.

## O que fornece

- janela ativa;
- título da janela;
- PID;
- nome do processo quando a permissão do Windows permite;
- posição/tamanho da janela;
- visibilidade/minimização;
- lista limitada de janelas visíveis;
- comparação entre dois snapshots.

## Princípios

- não executa ações;
- não fecha/abre/move janelas;
- não altera processos;
- não usa shell, PowerShell ou CMD;
- fora do Windows, declara indisponibilidade em vez de inventar estado.

## Próxima integração

O próximo passo é alimentar o `world_model.py` com esse snapshot em ciclos controlados, correlacionando estado estrutural com percepção visual/OCR.
