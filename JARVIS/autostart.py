"""
Liga/desliga a abertura automática do JARVIS ao entrar no Windows
(chave HKCU\\...\\Run, sem precisar de administrador).

Use SEMPRE de dentro do .venv, para gravar o python do ambiente certo:
    python autostart.py on
    python autostart.py off
    python autostart.py status
"""
import os
import sys
import winreg

KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "JARVIS"


def command():
    here = os.path.dirname(os.path.abspath(__file__))
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")   # sem janela de console
    if os.path.exists(pyw):
        py = pyw
    return f'"{py}" "{os.path.join(here, "jarvis_hud.py")}" --boot'


def is_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as key:
            return bool(winreg.QueryValueEx(key, NAME)[0])
    except FileNotFoundError:
        return False


def enable():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, NAME, 0, winreg.REG_SZ, command())
    print("Inicialização automática ATIVADA:\n ", command())


def disable():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, NAME)
        print("Inicialização automática DESATIVADA.")
    except FileNotFoundError:
        print("Já estava desativada.")


def status():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            print("ATIVADA:", winreg.QueryValueEx(k, NAME)[0])
    except FileNotFoundError:
        print("DESATIVADA.")


def check():
    """Diagnóstico: confere se a inicialização automática vai funcionar."""
    here = os.path.dirname(os.path.abspath(__file__))
    cmd = command()
    interpreter = cmd.split('"')[1]
    print("Comando:", cmd)
    print("Python existe:", os.path.exists(interpreter), "| .venv:", "venv" in interpreter.lower())
    for name in ("jarvis_hud.py", "backend.py", "commands.py"):
        print(f"{name}:", os.path.exists(os.path.join(here, name)))
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY) as k:
            registered = winreg.QueryValueEx(k, NAME)[0]
        print("Registrado:", "sim" + ("" if registered == cmd else " (DESATUALIZADO: rode 'python autostart.py on')"))
    except FileNotFoundError:
        print("Registrado: não")
    try:
        import urllib.request
        import json
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]
        print("Ollama: respondendo | modelos:", ", ".join(names) or "nenhum")
    except Exception as exc:
        print("Ollama: NÃO respondeu agora:", exc)
    try:
        import pyaudio
        audio = pyaudio.PyAudio()
        print("Microfones:")
        for i in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(i)
            if int(info["maxInputChannels"]) > 0:
                print(f"  [{i}] {info['name']}")
        audio.terminate()
    except Exception as exc:
        print("PyAudio falhou:", exc)


if __name__ == "__main__":
    {"on": enable, "off": disable, "status": status, "check": check}.get(
        sys.argv[1] if len(sys.argv) > 1 else "status", status)()
