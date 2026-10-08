# J.A.R.V.I.S. — Fase 2: Context State

Esta fase transforma observações isoladas em um **estado contextual estruturado**.

## O que foi adicionado

- `context_state.py`: mantém o estado recente do computador sem armazenar screenshots.
- Janela e processo em primeiro plano.
- Atividade e resumo identificados pela visão local.
- Erro visível e texto do erro.
- Confiança da percepção.
- Estado da tela: mudança/estabilidade.
- Controles conhecidos da janela via UI Automation, quando `pywinauto` estiver disponível.
- OCR continua sob demanda; não é executado continuamente em cada ciclo.
- Histórico curto de eventos contextuais.
- Persistência local em `context_state.json`.
- `get_context` foi adicionada à allowlist do agente para que o próprio JARVIS possa consultar seu contexto estruturado.
- O Observador passa o contexto estruturado ao orquestrador e ao agente.
- A HUD mostra aplicação/atividade atuais quando o modo OBSERVADOR está ativo.

## Arquitetura

```text
Tela
  ↓
Observador
  ↓
Visão local
  ↓
Context State
  ├── aplicação
  ├── janela
  ├── atividade
  ├── erro
  ├── confiança
  ├── controles
  └── histórico curto
          ↓
      Orquestrador
          ↓
        Agent
```

## Segurança

O Context State não salva imagens. A visão continua local. Conteúdo sensível continua sujeito aos filtros do Observador. Texto encontrado na tela continua sendo tratado como dado, não como instrução.

## Próxima fase

A próxima evolução natural é conectar o Context State a um **perception loop** mais rico: mudanças incrementais de UI, OCR sob demanda, detecção de editor/terminal/browser e comparação entre estados para descobrir exatamente o que mudou antes de decidir uma ação.
