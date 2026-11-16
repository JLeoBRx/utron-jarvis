"""Sensor de sistema: SO, CPU, GPU, RAM, armazenamento e energia."""
from __future__ import annotations

import json
import platform
import shutil
import sys
import time

from ..platform import system, win32
from .base import Percept, Sensor, SensorUnavailable

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

_PS_GPU = ("$ErrorActionPreference='Stop';Get-CimInstance Win32_VideoController | "
           "Select-Object Name,AdapterRAM,DriverVersion | ConvertTo-Json -Compress")


def cpu_name() -> str:
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                return str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
        except OSError:
            pass
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or ""


def gpu_static() -> list[dict]:
    gpus: list[dict] = []
    exe = shutil.which("nvidia-smi")
    if exe:
        result = system.run([exe, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"],
                            timeout=4, encoding="utf-8")
        for line in result.stdout.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3 and parts[0]:
                gpus.append({"name": parts[0], "memory_mb": int(float(parts[1] or 0)), "driver": parts[2],
                             "source": "nvidia-smi"})
    if not gpus and sys.platform == "win32":
        result = system.powershell(_PS_GPU, timeout=15)
        if result.ok and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                for item in data if isinstance(data, list) else [data]:
                    if item.get("Name"):
                        gpus.append({"name": item["Name"], "memory_mb": int((item.get("AdapterRAM") or 0) / 1048576),
                                     "driver": item.get("DriverVersion") or "", "source": "wmi"})
            except ValueError:
                pass
    return gpus


def gpu_utilization() -> float | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    result = system.run([exe, "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"], timeout=3,
                        encoding="utf-8")
    try:
        return max(0.0, min(1.0, float(result.stdout.splitlines()[0]) / 100.0)) if result.ok else None
    except (ValueError, IndexError):
        return None


class SystemSensor(Sensor):
    name = "system"
    kind = "telemetry"

    def __init__(self, interval: float = 2.0, *, world=None):
        super().__init__(interval)
        self._world = world
        self._static: dict | None = None
        self._gpu_checked = 0.0
        self._net_last: tuple[float, int, int] | None = None     # (instante, bytes recebidos, bytes enviados)

    def available(self) -> tuple[bool, str]:
        return (True, "") if psutil is not None else (False, "psutil não instalado")

    def static_info(self) -> dict:
        if self._static is None:
            vm = psutil.virtual_memory()
            disks = []
            for part in psutil.disk_partitions(all=False):
                if part.fstype and "cdrom" not in part.opts:
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                    except (PermissionError, OSError):
                        continue
                    disks.append({"mount": part.mountpoint, "fs": part.fstype,
                                  "total_gb": round(usage.total / 1e9, 1)})
            self._static = {
                "os": f"{platform.system()} {platform.release()}",
                "os_version": platform.version(),
                "machine": platform.machine(),
                "hostname": platform.node(),
                "cpu_name": cpu_name(),
                "cpu_physical": psutil.cpu_count(logical=False),
                "cpu_logical": psutil.cpu_count(logical=True),
                "ram_total_gb": round(vm.total / 1024 ** 3, 1),
                "gpus": gpu_static(),
                "storage": disks[:12],
                "python": platform.python_version(),
                "boot_time": psutil.boot_time(),
            }
            gpus = self._static["gpus"]
            self._static["gpu_name"] = gpus[0]["name"] if gpus else ""
        return self._static

    def net_rate(self, *, now: float | None = None, counters=None) -> dict:
        """Taxa real de download/upload (bytes/s) entre duas leituras — como a telemetria do JARVIS original.
        Sem leitura anterior (ou sem suporte), devolve None: nunca um valor inventado."""
        try:
            io = counters if counters is not None else psutil.net_io_counters()
        except Exception:
            io = None
        now = time.monotonic() if now is None else now
        if io is None:
            return {"net_rx_bps": None, "net_tx_bps": None}
        rx, tx = int(io.bytes_recv), int(io.bytes_sent)
        last, self._net_last = self._net_last, (now, rx, tx)
        if last is None or now - last[0] <= 0 or rx < last[1] or tx < last[2]:
            return {"net_rx_bps": None, "net_tx_bps": None}
        dt = now - last[0]
        return {"net_rx_bps": round((rx - last[1]) / dt), "net_tx_bps": round((tx - last[2]) / dt)}

    def sense(self) -> Percept:
        if psutil is None:
            raise SensorUnavailable("psutil não instalado")
        static = self.static_info()
        vm = psutil.virtual_memory()
        data = {
            "cpu": psutil.cpu_percent(interval=None) / 100.0,
            "ram": vm.percent / 100.0,
            "ram_used_gb": round(vm.used / 1024 ** 3, 2),
            "ram_total_gb": static["ram_total_gb"],
            "gpu": gpu_utilization(),
            "disks": [],
            "uptime_s": time.time() - static["boot_time"],
        }
        for disk in static["storage"]:
            try:
                usage = psutil.disk_usage(disk["mount"])
                data["disks"].append({"mount": disk["mount"], "used": usage.percent / 100.0,
                                      "free_gb": round(usage.free / 1e9, 1)})
            except OSError:
                continue
        battery = None
        try:
            batt = psutil.sensors_battery()
            if batt is not None:
                battery = {"percent": batt.percent, "plugged": bool(batt.power_plugged)}
        except Exception:
            battery = None
        if battery is None:
            status = win32.power_status()
            if status and status["has_battery"]:
                battery = {"percent": status["percent"], "plugged": status["plugged"]}
        data["battery"] = battery
        data.update(self.net_rate())
        if self._world is not None:
            # Somente dados estáveis vão ao World Model (carga instantânea fica no estado/telemetria).
            disks = [{"mount": d["mount"], "used": round(d["used"], 2), "free_gb": round(d["free_gb"])}
                     for d in data["disks"]]
            power = {"percent": int(battery["percent"] // 5 * 5), "plugged": battery["plugged"]} if battery else None
            self._world.update("computer", {**{k: v for k, v in static.items() if k != "boot_time"},
                                            "disks": disks, "battery": power},
                               source="system", confidence=1.0)
        return Percept("system", "telemetry", data, 1.0)
