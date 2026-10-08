"""
J.A.R.V.I.S. // telemetria REAL do computador e dos módulos.

Tudo é lido localmente e em segundo plano (a HUD nunca espera por nada daqui):
  - CPU, RAM, bateria e tráfego de rede ........ psutil
  - GPU ......................................... nvidia-smi (se existir; senão None)
  - Wi-Fi (nome e sinal) ........................ netsh (Windows)
  - Ollama (online, latência, modelos) .......... GET http://localhost:11434/api/tags
  - Memórias e automações ....................... SQLite do próprio JARVIS (somente leitura)

Quando um dado não está disponível, o valor é None. A HUD mostra "N/D" em vez de inventar.

Instalação do único requisito externo:
    pip install psutil
"""
import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

try:
    import psutil
except ImportError:          # a HUD avisa "instale psutil"; nada é simulado
    psutil = None

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
HISTORY = 60                 # amostras de rede guardadas (1 por segundo)
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_lock = threading.Lock()
_started_at = time.time()
_thread = None
_stop = threading.Event()

_data = {
    "psutil_ok": psutil is not None,
    "cpu": None, "ram": None, "ram_used_gb": None, "ram_total_gb": None,
    "gpu": None, "gpu_name": None,
    "net_down": None, "net_up": None, "net_iface": None, "net_ip": None,
    "net_online": None,
    "wifi_ssid": None, "wifi_signal": None,
    "ollama_ok": None, "ollama_ms": None, "ollama_models": [],
    "battery": None, "battery_plugged": None,
    "memories": None, "automations_total": None, "automations_enabled": None,
    "host": socket.gethostname(),
}
_down_hist = deque([0.0] * HISTORY, maxlen=HISTORY)
_up_hist = deque([0.0] * HISTORY, maxlen=HISTORY)
_ollama_hist = deque(maxlen=HISTORY)


# ------------------------------------------------------------------ API pública
def start():
    """Inicia a coleta em segundo plano (idempotente)."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="jarvis-telemetria", daemon=True)
    _thread.start()


def stop():
    _stop.set()


def snapshot():
    """Cópia segura dos dados atuais (listas incluídas)."""
    with _lock:
        out = dict(_data)
        out["down_hist"] = list(_down_hist)
        out["up_hist"] = list(_up_hist)
        out["ollama_hist"] = list(_ollama_hist)
        out["ollama_models"] = list(_data["ollama_models"])
    out["uptime"] = time.time() - _started_at
    return out


def _set(**values):
    with _lock:
        _data.update(values)


# ------------------------------------------------------------------ coletores
def _sample_system():
    if psutil is None:
        return
    cpu = psutil.cpu_percent(interval=None) / 100.0
    mem = psutil.virtual_memory()
    values = {
        "cpu": max(0.0, min(1.0, cpu)),
        "ram": max(0.0, min(1.0, mem.percent / 100.0)),
        "ram_used_gb": mem.used / 1024 ** 3,
        "ram_total_gb": mem.total / 1024 ** 3,
    }
    try:
        battery = psutil.sensors_battery()
    except Exception:
        battery = None
    if battery is not None:
        values["battery"] = battery.percent
        values["battery_plugged"] = bool(battery.power_plugged)
    else:
        values["battery"] = None
        values["battery_plugged"] = None
    _set(**values)


def _active_interfaces():
    """Interfaces ativas com IPv4 que não seja loopback: {nome: ip}."""
    result = {}
    stats = psutil.net_if_stats()
    for name, addrs in psutil.net_if_addrs().items():
        st = stats.get(name)
        if st is None or not st.isup:
            continue
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith(("127.", "169.254.")):
                result[name] = addr.address
                break
    return result


class _NetState:
    last_time = None
    last = {}


def _sample_network():
    if psutil is None:
        return
    now = time.monotonic()
    ifaces = _active_interfaces()
    counters = psutil.net_io_counters(pernic=True)
    rx = tx = 0
    current = {}
    for name in ifaces:
        c = counters.get(name)
        if c is not None:
            current[name] = (c.bytes_recv, c.bytes_sent)
    down = up = 0.0
    if _NetState.last_time is not None:
        dt = max(0.2, now - _NetState.last_time)
        for name, (r, s) in current.items():
            prev = _NetState.last.get(name)
            if prev is not None:
                rx += max(0, r - prev[0])
                tx += max(0, s - prev[1])
        down, up = rx / dt, tx / dt
    _NetState.last_time, _NetState.last = now, current

    main = None
    if ifaces:
        main = max(ifaces, key=lambda n: sum(current.get(n, (0, 0))))
    with _lock:
        _down_hist.append(down)
        _up_hist.append(up)
    _set(net_down=down, net_up=up, net_iface=main,
         net_ip=ifaces.get(main) if main else None,
         net_online=bool(ifaces))


def _sample_gpu():
    exe = shutil.which("nvidia-smi")
    if not exe:
        _set(gpu=None, gpu_name=None)
        return
    out = subprocess.run(
        [exe, "--query-gpu=utilization.gpu,name", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=3, creationflags=_NO_WINDOW,
    )
    line = (out.stdout or "").strip().splitlines()
    if out.returncode != 0 or not line:
        _set(gpu=None, gpu_name=None)
        return
    util, _, name = line[0].partition(",")
    _set(gpu=max(0.0, min(1.0, float(util.strip()) / 100.0)), gpu_name=name.strip())


def _sample_wifi():
    if os.name != "nt":
        return
    out = subprocess.run(["netsh", "wlan", "show", "interfaces"], capture_output=True,
                         timeout=4, creationflags=_NO_WINDOW)
    text = out.stdout.decode("cp850", errors="replace")
    if out.returncode != 0 or not text.strip():
        _set(wifi_ssid=None, wifi_signal=None)
        return
    ssid = signal = None
    for raw in text.splitlines():
        key, _, value = raw.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "ssid" and value:
            ssid = value
        elif key in ("sinal", "signal"):
            match = re.search(r"(\d+)\s*%", value)
            if match:
                signal = int(match.group(1))
    _set(wifi_ssid=ssid, wifi_signal=signal if ssid else None)


def _sample_ollama():
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(OLLAMA_TAGS_URL, timeout=1.5) as response:
            body = json.loads(response.read().decode("utf-8"))
        ms = (time.perf_counter() - started) * 1000.0
        models = [m.get("name", "") for m in body.get("models", [])]
        with _lock:
            _ollama_hist.append(ms)
        _set(ollama_ok=True, ollama_ms=ms, ollama_models=models)
    except Exception:
        _set(ollama_ok=False, ollama_ms=None, ollama_models=[])


def _db_path():
    root = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(root, "JARVIS", "assistant.sqlite3")


def _sample_database():
    path = _db_path()
    if not os.path.isfile(path):
        _set(memories=None, automations_total=None, automations_enabled=None)
        return
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=1)
    try:
        memories = connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        total, enabled = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(CASE WHEN enabled=1 THEN 1 ELSE 0 END),0) FROM automations"
        ).fetchone()
        _set(memories=int(memories), automations_total=int(total), automations_enabled=int(enabled))
    finally:
        connection.close()


def _safe(fn):
    try:
        fn()
    except Exception:
        pass            # um coletor falhar não derruba os outros; o valor antigo permanece


def _runner(fn, period):
    """Cada coletor roda na própria thread: um lento (Ollama fora do ar, netsh) não atrasa os outros."""
    while not _stop.is_set():
        _safe(fn)
        _stop.wait(period)


def _loop():
    if psutil is not None:
        psutil.cpu_percent(interval=None)    # a primeira leitura é descartada pelo psutil
    schedule = [          # (função, período em segundos)
        (_sample_system, 1.0),
        (_sample_network, 1.0),
        (_sample_gpu, 3.0),
        (_sample_wifi, 10.0),
        (_sample_ollama, 5.0),
        (_sample_database, 10.0),
    ]
    for fn, period in schedule[1:]:
        threading.Thread(target=_runner, args=(fn, period), name=f"jarvis-{fn.__name__}",
                         daemon=True).start()
    _runner(*schedule[0])
