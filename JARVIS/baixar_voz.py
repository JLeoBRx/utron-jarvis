"""Baixa a voz pt-BR do Piper (modelo + configuração) para a pasta voices/."""
import os
import urllib.request

BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/"
FILES = ("pt_BR-faber-medium.onnx", "pt_BR-faber-medium.onnx.json")
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")

os.makedirs(DEST, exist_ok=True)
for name in FILES:
    target = os.path.join(DEST, name)
    if os.path.isfile(target) and os.path.getsize(target) > 0:
        print("Já existe:", name)
        continue
    print("Baixando", name, "...")
    try:
        urllib.request.urlretrieve(BASE + name, target)
    except Exception as exc:
        if os.path.exists(target):
            os.remove(target)
        raise SystemExit(f"Falhou ({exc}). Baixe manualmente no repositório rhasspy/piper-voices "
                         f"(pasta pt/pt_BR/faber/medium) e coloque em: {DEST}")
print("Pronto. Reinicie o JARVIS.")
