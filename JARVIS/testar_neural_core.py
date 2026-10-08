import os
import neural_core

print("J.A.R.V.I.S. // TESTE NEURAL CORE")
print("Roteamento:", neural_core.brain_status())
print("OPENAI_API_KEY:", "configurada" if os.environ.get("OPENAI_API_KEY") else "não configurada")
print("Modo:", neural_core.brain_status()["routing_mode"])
