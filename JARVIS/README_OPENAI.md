# JARVIS + OpenAI

Esta versão integra o núcleo cognitivo do JARVIS à OpenAI usando a **Responses API**.

## 1. Chave

Não coloque a chave dentro do código. No Windows PowerShell:

```powershell
setx OPENAI_API_KEY "SUA_CHAVE_AQUI"
```

Feche e abra o terminal/JARVIS depois de usar `setx`.

## 2. Provedor

Por padrão:

- `JARVIS_AI_PROVIDER=openai`
- modelo: `gpt-5.6-sol`

Para voltar ao cérebro local:

```powershell
setx JARVIS_AI_PROVIDER "ollama"
```

Para escolher outro modelo disponível na sua conta:

```powershell
setx JARVIS_OPENAI_MODEL "gpt-5.6-sol"
```

## 3. O que a integração faz

O JARVIS usa a OpenAI para:

- conversa e interpretação;
- planejamento de tarefas;
- chamadas das ferramentas allowlisted;
- análise visual quando o Observador precisa entender uma tela;
- pesquisa na web quando o modelo julgar necessária, usando a ferramenta de web search da OpenAI.

As ferramentas de controle continuam sendo executadas **localmente pelo JARVIS**. A OpenAI decide qual ferramenta estruturada usar; ela não recebe shell, CMD ou PowerShell como ferramenta livre.

A chave não é enviada para o Ollama.

## 4. Fallback

Se `JARVIS_AI_PROVIDER=openai` e a API estiver indisponível, o núcleo tenta o Ollama local para manter o sistema operacional.

## 5. Privacidade

Ao usar OpenAI, o conteúdo que o JARVIS enviar à API deixa de ser exclusivamente local. Em particular, uma imagem de tela enviada para análise visual pode ser transmitida à API. O modo Observador continua com os filtros locais de conteúdo sensível, mas isso não transforma a integração em processamento exclusivamente local.

## 6. Custo

A API é faturada separadamente do uso normal do ChatGPT. Consulte a página oficial de preços antes de deixar o Observador fazendo chamadas frequentes.

## Atalho no Windows

Você também pode executar `configurar_openai.bat`. Ele grava `OPENAI_API_KEY` no ambiente do usuário e seleciona OpenAI como cérebro. Depois execute `python testar_openai.py` para testar a conexão.

**Importante:** a chave da API não é a senha da sua conta e não deve ser publicada, enviada pelo chat ou colocada no GitHub.

## Web

A pesquisa web está ligada por padrão (`JARVIS_OPENAI_WEB_SEARCH=1`). Para desligar:

```powershell
setx JARVIS_OPENAI_WEB_SEARCH "0"
```

A pesquisa web tem cobrança própria na API além dos tokens, conforme a tabela oficial de preços.
