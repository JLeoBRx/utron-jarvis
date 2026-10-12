"""PERFORMANCE MONITOR — métricas reais de desempenho do ULTRON.

Séries de tempo (janelas limitadas, sem crescimento ilimitado) e contadores, alimentados
por quem mede de verdade:

* ``ui.frame`` (pintura do HUB), ``ui.lag`` (atraso do laço de eventos da interface),
  ``ui.event_delay`` (evento publicado → tratado na interface);
* ``model.request`` (chamada completa ao modelo) e ``model.inference`` (tempo de inferência
  informado pelo próprio Ollama, separado do tempo de rede/fila/carga);
* ``request`` (pedido do usuário → resposta final);
* ``perception.<sensor>`` (duração de cada leitura de sensor);

mais amostras do processo (CPU, memória), filas e workers, exceções e eventos do Event Bus.
Nada aqui é estimado: uma série sem amostras aparece vazia.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable

WINDOW = 512                 # amostras mantidas por série


def percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0}
    ordered = sorted(values)

    def pct(p: float) -> float:
        return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]

    return {"n": len(ordered), "mean": sum(ordered) / len(ordered), "p50": pct(50), "p95": pct(95),
            "p99": pct(99), "max": ordered[-1]}


class _ErrorCounter(logging.Handler):
    """Conta registros de erro do ULTRON (sem guardar texto que possa conter dados sensíveis)."""

    def __init__(self, monitor: "PerformanceMonitor"):
        super().__init__(level=logging.ERROR)
        self._monitor = monitor

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("ultron"):
            self._monitor.count("log.errors")
            self._monitor.note_error(f"{record.name}: {record.levelname}"
                                     + (f" ({record.exc_info[0].__name__})" if record.exc_info and record.exc_info[0]
                                        else ""))


class PerformanceMonitor:
    name = "metrics"

    def __init__(self, *, bus=None, runtime=None, clock: Callable[[], float] = time.time):
        self._bus = bus
        self._runtime = runtime
        self._clock = clock
        self._lock = threading.Lock()
        self._series: dict[str, deque] = {}
        self._counters: dict[str, int] = {}
        self._gauges: dict[str, Any] = {}
        self._errors: deque = deque(maxlen=20)
        self._process: dict[str, Any] = {}
        self._cpu_primed = False
        self._log_handler: _ErrorCounter | None = None

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        if self._log_handler is None:
            self._log_handler = _ErrorCounter(self)
            logging.getLogger("ultron").addHandler(self._log_handler)
        self.sample_process()

    def stop(self) -> None:
        if self._log_handler is not None:
            logging.getLogger("ultron").removeHandler(self._log_handler)
            self._log_handler = None

    def health(self) -> dict:
        lag = self.stats("ui.lag")
        if lag.get("n", 0) >= 10 and lag["p95"] > 0.25:
            return {"status": "WARN", "detail": f"interface com atraso p95 {lag['p95'] * 1000:.0f} ms"}
        return {"status": "OK", "detail": "medindo" if not lag.get("n") else f"atraso p95 {lag['p95'] * 1000:.0f} ms"}

    # ------------------------------------------------------------ registro
    def record(self, series: str, seconds: float) -> None:
        if seconds is None or seconds < 0:
            return
        with self._lock:
            target = self._series.get(series)
            if target is None:
                target = self._series[series] = deque(maxlen=WINDOW)
            target.append(float(seconds))

    def count(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + int(amount)

    def gauge(self, name: str, value: Any) -> None:
        with self._lock:
            self._gauges[name] = value

    def note_error(self, text: str) -> None:
        with self._lock:
            self._errors.append({"at": self._clock(), "text": str(text)[:160]})

    def timer(self, series: str) -> "_Timer":
        return _Timer(self, series)

    # ------------------------------------------------------------ leitura
    def stats(self, series: str) -> dict[str, float]:
        with self._lock:
            values = list(self._series.get(series, ()))
        return percentiles(values)

    def sample_process(self) -> dict[str, Any]:
        """CPU e memória do processo do ULTRON (psutil). Chamado pelo agendador, nunca pela interface."""
        try:
            import psutil
            proc = psutil.Process()
            cpu = proc.cpu_percent(None)
            info = proc.memory_info()
            sample = {"cpu_percent": round(cpu, 1) if self._cpu_primed else None,
                      "rss_mb": round(info.rss / 2 ** 20, 1), "threads": proc.num_threads(),
                      "system_cpu_percent": psutil.cpu_percent(None) if self._cpu_primed else None,
                      "at": self._clock()}
            self._cpu_primed = True
        except Exception as exc:                          # psutil ausente: informa, não inventa
            sample = {"error": f"{type(exc).__name__}: {exc}"[:120], "at": self._clock()}
        with self._lock:
            self._process = sample
        return sample

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            series = {name: percentiles(list(values)) for name, values in self._series.items()}
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            errors = list(self._errors)
            process = dict(self._process)
        out: dict[str, Any] = {"series": series, "counters": counters, "gauges": gauges, "errors": errors,
                               "process": process, "at": self._clock()}
        if self._runtime is not None:
            workers = self._runtime.status()
            out["workers"] = {name: {"alive": w["alive"], "pending": w["pending"], "current": w["current"],
                                     "failed": w["failed"]} for name, w in workers.items()}
            out["queued"] = sum(w["pending"] for w in workers.values())
            out["workers_alive"] = sum(1 for w in workers.values() if w["alive"])
            out["worker_failures"] = sum(w["failed"] for w in workers.values())
            try:
                out["scheduler"] = self._runtime.scheduler.jobs()
            except Exception:
                pass
        if self._bus is not None:
            stats = self._bus.stats
            out["bus"] = {"published": stats.published, "delivered": stats.delivered, "dropped": stats.dropped,
                          "handler_errors": stats.handler_errors, "queued": self._bus.queue_size()}
        out["exceptions"] = (counters.get("log.errors", 0) + out.get("worker_failures", 0)
                             + out.get("bus", {}).get("handler_errors", 0))
        return out


class _Timer:
    def __init__(self, monitor: PerformanceMonitor, series: str):
        self._monitor, self._series = monitor, series
        self._started = 0.0

    def __enter__(self) -> "_Timer":
        self._started = time.perf_counter()
        return self

    def __exit__(self, *exc) -> None:
        self._monitor.record(self._series, time.perf_counter() - self._started)
