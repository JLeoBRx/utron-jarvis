"""HEALTH MONITOR — CPU, RAM, GPU, DISCO, OLLAMA, VOZ, VISÃO, REDE, MEMÓRIA e HUD.

Cada verificação devolve ``{"status", "detail", "value"}`` com status:

* ``OK``          — funcionando;
* ``WARN``        — funcionando com degradação (carga alta, recurso desativado);
* ``FAIL``        — deveria funcionar e não funciona;
* ``UNAVAILABLE`` — recurso opcional ausente (com o motivo).

Os recursos da máquina são medidos aqui; os módulos do JARVIS são consultados por
*probes* registradas pelo Neural Core. Nenhuma verificação pode travar o monitor: cada
uma tem tempo limite e erro vira ``FAIL`` com a causa.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable

from ..config import paths
from ..core.events import EventType

log = logging.getLogger("ultron.health")

ORDER = ("CPU", "RAM", "GPU", "DISK", "OLLAMA", "VOICE", "VISION", "NETWORK", "MEMORY", "HUD")
SEVERITY = {"OK": 0, "UNAVAILABLE": 1, "UNKNOWN": 1, "WARN": 2, "FAIL": 3}
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def _result(status: str, detail: str = "", value: Any = None) -> dict[str, Any]:
    return {"status": status, "detail": detail, "value": value}


def check_cpu() -> dict[str, Any]:
    import psutil
    load = psutil.cpu_percent(interval=None)
    cores = psutil.cpu_count(logical=True) or 0
    status = "WARN" if load >= 90 else "OK"
    return _result(status, f"{load:.0f}% de {cores} núcleos lógicos", round(load, 1))


def check_ram() -> dict[str, Any]:
    import psutil
    mem = psutil.virtual_memory()
    status = "FAIL" if mem.percent >= 96 else "WARN" if mem.percent >= 88 else "OK"
    return _result(status, f"{mem.used / 1024 ** 3:.1f} de {mem.total / 1024 ** 3:.1f} GB ({mem.percent:.0f}%)",
                   round(mem.percent, 1))


def check_disk(path: str | None = None) -> dict[str, Any]:
    target = path or str(paths.data_dir())
    usage = shutil.disk_usage(target)
    free_gb = usage.free / 1024 ** 3
    percent = usage.used / usage.total * 100 if usage.total else 0.0
    status = "FAIL" if free_gb < 1 else "WARN" if free_gb < 5 or percent >= 95 else "OK"
    return _result(status, f"{free_gb:.1f} GB livres ({percent:.0f}% usado)", round(percent, 1))


_gpu_name_cache: dict[str, str] = {}


def _gpu_name_windows() -> str:
    if "name" not in _gpu_name_cache:
        name = ""
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command",
                                  "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name"],
                                 capture_output=True, text=True, timeout=6, creationflags=_NO_WINDOW)
            name = out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
        _gpu_name_cache["name"] = name
    return _gpu_name_cache["name"]


def check_gpu(model_probe: Callable[[], list[dict]] | None = None) -> dict[str, Any]:
    """NVIDIA via nvidia-smi (uso, memória, temperatura). Também informa quanto do modelo
    carregado no Ollama está na GPU (``/api/ps``), quando disponível."""
    offload = ""
    if model_probe is not None:
        try:
            running = model_probe() or []
            if running:
                frac = max(m.get("gpu_fraction", 0.0) for m in running)
                offload = f"; modelo carregado {frac:.0%} na GPU"
        except Exception:
            pass
    smi = shutil.which("nvidia-smi")
    if smi:
        try:
            out = subprocess.run([smi, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                                  "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3,
                                 creationflags=_NO_WINDOW)
            line = (out.stdout.strip().splitlines() or [""])[0]
            name, util, used, total, temp = [x.strip() for x in line.split(",")]
            util_v, temp_v = float(util), float(temp)
            status = "WARN" if temp_v >= 85 or float(used) / max(1.0, float(total)) >= 0.97 else "OK"
            return _result(status, f"{name}: {util_v:.0f}% uso, {float(used) / 1024:.1f}/{float(total) / 1024:.1f} GB, "
                                   f"{temp_v:.0f}°C{offload}", util_v)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            return _result("WARN", f"nvidia-smi falhou: {exc}{offload}")
    if sys.platform == "win32":
        name = _gpu_name_windows()
        if name:
            return _result("UNAVAILABLE", f"{name}: sem telemetria de uso (nvidia-smi ausente){offload}")
    return _result("UNAVAILABLE", f"telemetria de GPU indisponível{offload}")


class HealthMonitor:
    name = "health"

    def __init__(self, *, bus=None, state=None, probes: dict[str, Callable[[], dict]] | None = None,
                 model_probe: Callable[[], list[dict]] | None = None, check_timeout: float = 4.0):
        self._bus = bus
        self._state = state
        self._probes: dict[str, Callable[[], dict]] = dict(probes or {})
        self._model_probe = model_probe
        self._timeout = check_timeout
        self._lock = threading.Lock()
        self.last: dict[str, Any] = {}
        self.history: list[dict] = []           # (instante, geral) — para tendência
        self._previous_overall = ""
        self._previous_signature: tuple = ()

    def register(self, name: str, probe: Callable[[], dict]) -> None:
        with self._lock:
            self._probes[name.upper()] = probe

    def unregister(self, name: str) -> None:
        with self._lock:
            self._probes.pop(name.upper(), None)

    def start(self) -> None:
        try:
            import psutil
            psutil.cpu_percent(interval=None)      # primeira leitura de CPU serve de referência
        except ImportError:
            pass

    def stop(self) -> None:
        pass

    def health(self) -> dict:
        return {"status": "OK", "detail": f"geral: {self.last.get('overall', 'n/d')}"}

    # ------------------------------------------------------------ verificação
    def _run(self, fn: Callable[[], dict]) -> dict[str, Any]:
        box: dict[str, Any] = {}

        def runner() -> None:
            try:
                box["value"] = fn()
            except Exception as exc:  # o erro vira resultado
                box["error"] = exc

        thread = threading.Thread(target=runner, daemon=True, name="ultron-health-check")
        thread.start()
        thread.join(self._timeout)
        if thread.is_alive():
            return _result("FAIL", f"verificação excedeu {self._timeout:.0f}s")
        if "error" in box:
            exc = box["error"]
            if isinstance(exc, ImportError):
                return _result("UNAVAILABLE", f"dependência ausente: {exc}")
            return _result("FAIL", f"{type(exc).__name__}: {exc}")
        value = box.get("value") or {}
        status = str(value.get("status", "UNKNOWN")).upper()
        return _result(status if status in SEVERITY else "UNKNOWN", str(value.get("detail", "")), value.get("value"))

    def check_all(self) -> dict[str, Any]:
        started = time.perf_counter()
        builtin: dict[str, Callable[[], dict]] = {
            "CPU": check_cpu, "RAM": check_ram, "DISK": check_disk,
            "GPU": lambda: check_gpu(self._model_probe),
        }
        with self._lock:
            probes = dict(self._probes)
        checks: dict[str, dict] = {}
        for name in ORDER:
            fn = builtin.get(name) or probes.get(name)
            checks[name] = self._run(fn) if fn else _result("UNAVAILABLE", "não registrado")
        for name, fn in probes.items():            # verificações extras (plugins)
            if name not in checks:
                checks[name] = self._run(fn)
        worst = max(checks.values(), key=lambda c: SEVERITY.get(c["status"], 1))["status"]
        overall = "FAIL" if worst == "FAIL" else "WARN" if worst == "WARN" else "OK"
        report = {"overall": overall, "timestamp": time.time(), "checks": checks,
                  "seconds": round(time.perf_counter() - started, 3), "pid": os.getpid()}
        with self._lock:
            self.last = report
            self.history.append({"t": report["timestamp"], "overall": overall})
            del self.history[:-120]
        if self._state is not None:
            self._state.update(_source="health", health=report)
        problems = {k: v["detail"] for k, v in checks.items() if v["status"] in ("WARN", "FAIL")}
        # "mudou" = o estado geral OU o conjunto de verificações com problema mudou; a verificação
        # de rotina que só confirma o mesmo quadro não é tratada como novidade pelos hubs
        signature = (overall, tuple(sorted((k, checks[k]["status"]) for k in problems)))
        if self._bus is not None:
            self._bus.publish(EventType.HEALTH_UPDATED, {"overall": overall,
                                                         "changed": signature != self._previous_signature,
                                                         "problems": problems},
                              source="health")
        if overall != self._previous_overall and self._previous_overall:
            log.info("saúde geral: %s → %s", self._previous_overall, overall)
        self._previous_overall = overall
        self._previous_signature = signature
        return report


def format_report(report: dict[str, Any]) -> str:
    lines = [f"SAÚDE GERAL: {report.get('overall', '?')}  ({report.get('seconds', 0):.2f}s)"]
    for name, check in report.get("checks", {}).items():
        lines.append(f"  {name:<8} {check['status']:<12} {check.get('detail', '')}")
    return "\n".join(lines)
