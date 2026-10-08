# J.A.R.V.I.S. — Fase 8: Voice & Conversational Engine

## Objetivo

Transformar a voz em uma interface contínua, com wake-word, janela curta de continuação e interrupção da fala (barge-in).

## Comportamento

1. O usuário diz **"JARVIS"** e o sistema acorda.
2. Após uma resposta, existe uma janela curta de aproximadamente 14 segundos para continuar a conversa sem repetir a wake-word.
3. Dizer **"pare"**, **"cancelar"** ou equivalente interrompe a fala e solicita o cancelamento do agente quando houver tarefa em andamento.
4. A janela expira e a wake-word volta a ser exigida.
5. O motor conversacional não executa ferramentas e não altera permissões; ele somente administra o diálogo de voz.

## Arquitetura

`microfone → Vosk → ConversationEngine → backend.process_command → agente/orquestrador → TTS`

O TTS continua usando Piper quando disponível e pyttsx3 como fallback.

## Observação

A implementação continua dependente do ambiente Windows e dos componentes locais já utilizados pelo projeto: Vosk, PyAudio, Piper/pyttsx3 e Ollama. A validação feita no ambiente de desenvolvimento é estática (`AST`/`py_compile`); microfone, drivers e áudio precisam ser testados no Windows.
