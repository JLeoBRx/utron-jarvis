"""Uso de recursos medido de verdade (psutil): o processo do Assistant, o computador e o banco."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import psutil

MB = 1024 * 1024


class ResourceSampler:
    """Amostra o processo atual. A CPU é a média desde a amostra anterior (a primeira devolve 0)."""

    def __init__(self) -> None:
        self.process = psutil.Process(os.getpid())
        self.process.cpu_percent(None)
        self.started = time.time()

    def sample(self, *, data_dir: Path, database: Path | None) -> dict[str, Any]:
        with self.process.oneshot():
            memory = self.process.memory_info()
            cpu = self.process.cpu_percent(None)
            threads = self.process.num_threads()
        system = psutil.virtual_memory()
        try:
            disk = psutil.disk_usage(str(data_dir if data_dir.exists() else data_dir.anchor or "/"))
            disk_free = round(disk.free / MB)
        except OSError:
            disk_free = None
        return {
            "process": {"rss_mb": round(memory.rss / MB, 1), "cpu_percent": round(cpu, 1), "threads": threads,
                        "uptime_s": round(time.time() - self.started)},
            "system": {"cpu_count": psutil.cpu_count() or 0, "cpu_percent": round(psutil.cpu_percent(None), 1),
                       "memory_total_mb": round(system.total / MB), "memory_used_percent": round(system.percent, 1)},
            "storage": {"database_bytes": database.stat().st_size if database and database.is_file() else None,
                        "disk_free_mb": disk_free},
            "measured_at": time.time(),
        }
