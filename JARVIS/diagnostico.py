"""Diagnóstico local do JARVIS. Não altera configurações do Windows."""
import importlib.util, os, platform, sys

REQUIRED = [
    ("PySide6", "interface/HUD"),
    ("pyttsx3", "voz Windows"),
    ("pyautogui", "mouse/teclado"),
    ("pyperclip", "clipboard"),
    ("pyaudio", "microfone"),
    ("vosk", "reconhecimento de voz"),
    ("cffi", "dependência nativa do Vosk"),
    ("psutil", "telemetria"),
    ("send2trash", "lixeira"),
    ("mss", "captura de tela"),
    ("PIL", "imagens"),
    ("numpy", "voz neural opcional"),
]
print("=== J.A.R.V.I.S. — DIAGNÓSTICO ===")
print("Python:", sys.version.split()[0], platform.architecture()[0])
print("Executável:", sys.executable)
for module, purpose in REQUIRED:
    ok = importlib.util.find_spec(module) is not None
    print(f"{'OK  ' if ok else 'FALHA'} {module:12} — {purpose}")
print("\nArquivos críticos:")
for path in ("Jarvis.py", "main.py", "jarvis_hud.py", "backend.py", "commands.py", "VOSK_MODEL"):
    if path == "VOSK_MODEL":
        exists = os.path.isdir("vosk-model-small-pt-0.3")
    else:
        exists = os.path.isfile(path)
    print(f"{'OK  ' if exists else 'FALTA'} {path}")
try:
    import pyttsx3
    e = pyttsx3.init()
    print("\nTTS pyttsx3: OK")
    e.stop()
except Exception as exc:
    print("\nTTS pyttsx3: FALHA:", repr(exc))
try:
    import pyaudio
    p = pyaudio.PyAudio()
    print("PyAudio: OK — dispositivos:", p.get_device_count())
    p.terminate()
except Exception as exc:
    print("PyAudio: FALHA:", repr(exc))
