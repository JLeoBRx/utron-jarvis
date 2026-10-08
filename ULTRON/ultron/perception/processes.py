"""Sensor de processos: carga, processos relevantes e encerramentos."""
from __future__ import annotations

import time
from typing import Callable

from .base import Percept, Sensor

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

# Processos que, ao encerrarem, merecem atenção (ferramentas de trabalho do usuário).
IMPORTANT = {
    "code.exe", "code", "devenv.exe", "pycharm64.exe", "idea64.exe", "python.exe", "pythonw.exe", "python3",
    "python", "node.exe", "node", "java.exe", "java", "ollama.exe", "ollama", "ollama app.exe",
    "chrome.exe", "msedge.exe", "firefox.exe", "winword.exe", "excel.exe", "powerpnt.exe",
    "windowsterminal.exe", "obs64.exe", "spotify.exe", "discord.exe", "steam.exe",
}


class ProcessSensor(Sensor):
    name = "processes"
    kind = "structural"

    def __init__(self, interval: float = 5.0, *, on_ended: Callable[[dict], None] | None = None,
                 extra_important: Callable[[], set] | None = None):
        super().__init__(interval)
        self._on_ended = on_ended
        self._extra = extra_important
        self._watched: dict[int, dict] = {}
        self._self_pid = None

    def available(self) -> tuple[bool, str]:
        return (True, "") if psutil is not None else (False, "psutil não instalado")

    def sense(self) -> Percept:
        import os
        self._self_pid = self._self_pid or os.getpid()
        important = set(IMPORTANT)
        if self._extra:
            try:
                important |= {x.lower() for x in self._extra()}
            except Exception:
                pass
        procs = []
        current: dict[int, dict] = {}
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_info", "create_time", "status"]):
            info = proc.info
            name = (info.get("name") or "").strip()
            if not name or info["pid"] in (0, 4):
                continue
            mem = info.get("memory_info")
            entry = {"pid": info["pid"], "name": name, "cpu": float(info.get("cpu_percent") or 0.0),
                     "mem_mb": round((mem.rss if mem else 0) / 1048576, 1), "status": info.get("status") or "",
                     "started": info.get("create_time") or 0.0}
            procs.append(entry)
            if name.lower() in important and info["pid"] != self._self_pid:
                current[info["pid"]] = entry
        ended = []
        now = time.time()
        for pid, entry in self._watched.items():
            if pid not in current and now - entry.get("started", now) > 10:
                ended.append({**entry, "ended_at": now, "runtime_s": round(now - entry.get("started", now), 1)})
        self._watched = current
        if self._on_ended:
            for item in ended:
                self._on_ended(item)
        top_cpu = sorted(procs, key=lambda p: -p["cpu"])[:8]
        top_mem = sorted(procs, key=lambda p: -p["mem_mb"])[:8]
        return Percept("process", "structural", {
            "count": len(procs), "top_cpu": top_cpu, "top_memory": top_mem,
            "important": sorted({p["name"] for p in current.values()}), "ended": ended}, 1.0)
