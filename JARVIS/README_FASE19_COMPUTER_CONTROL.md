# J.A.R.V.I.S. — Fase 19: Computer Control Layer

A Fase 19 cria uma camada unificada de controle físico do computador.

## Objetivo

Separar o raciocínio do agente da implementação de mouse, teclado, janelas e abertura de aplicativos.

Fluxo:

```text
Neural Core
  -> Planner / Action Selector
  -> Computer Control Layer
  -> commands.py (allowlist)
  -> Windows / desktop
  -> Perception / Verification
```

## Segurança

`computer_control.py` **não substitui** a allowlist e não adiciona shell, CMD ou PowerShell livres.
A autoridade final continua em `commands.py`.

O módulo possui `dry_run=True` para que o Planner possa testar a forma de uma ação sem tocar no computador.

## Capacidades

- mouse
- teclado
- rolagem
- janela ativa
- abertura de aplicativos permitidos
- espera controlada

## Limitação desta sessão

O código foi compilado e os testes estruturais foram executados em ambiente Linux. O controle físico real de Windows precisa ser validado na máquina Windows do JARVIS.
