import os
import sys
from openai_provider import ResponsesProvider, OpenAIProviderError

print("J.A.R.V.I.S. // TESTE OPENAI")
print("Modelo:", os.environ.get("JARVIS_OPENAI_MODEL", "gpt-5.6-sol"))
if not ResponsesProvider.available():
    print("ERRO: OPENAI_API_KEY não está definida.")
    sys.exit(2)

try:
    provider = ResponsesProvider()
    answer = provider.text(
        "Responda apenas: conexão estabelecida.",
        system="Você é um teste de conectividade. Seja objetivo."
    )
    print("Resposta:", answer)
    print("OPENAI: ONLINE")
except OpenAIProviderError as exc:
    print("OPENAI: FALHA")
    print(exc)
    sys.exit(1)
