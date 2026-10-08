import os
import config
import intelligence_router

# Local é o padrão.
config.OPENAI_ENABLED = False
os.environ.pop("OPENAI_API_KEY", None)
r = intelligence_router.decide("corrija o erro do projeto")
assert r.route == "OLLAMA_LOCAL"

# Sem chave, mesmo habilitado, não pode usar remoto.
config.OPENAI_ENABLED = True
r = intelligence_router.decide("desenvolva e implemente uma solução complexa")
assert r.route == "OLLAMA_LOCAL"

# Com chave, missão complexa pode usar remoto.
os.environ["OPENAI_API_KEY"] = "test-only-placeholder"
r = intelligence_router.decide("investigue, analise, corrija e implemente a solução do projeto")
assert r.route == "OPENAI"

print("Fase 9 OK")
