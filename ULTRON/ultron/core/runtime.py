"""Infraestrutura de execução concorrente do JARVIS.

Separação de threads exigida pelo projeto:

* ``ui``        — thread do Qt (fora deste módulo; apenas desenha);
* ``ai``        — inferência, planejamento e execução de objetivos (serial);
* ``vision``    — análise visual (chamadas lentas ao modelo de visão);
* ``voice``     — síntese de fala (a captura do microfone tem thread própria);
* ``network``   — interfaces, diagnóstico e descoberta;
* ``memory``    — consolidação e persistência;
* ``perception``— sensores leves.

Garantias: filas com limite, *timeouts*, cancelamento cooperativo, tentativas limitadas
e agendamento periódico sem acúmulo (uma execução por vez por tarefa).
"""
from __future__ import annotations

import itertools
import logging
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger("ultron.runtime")


class CancelledError(RuntimeError):
    """A operação foi cancelada cooperativamente."""


class CancellationToken:
    def __init__(self, parent: "CancellationToken | None" = None):
        self._event = threading.Event()
        self._parent = parent
        self.reason = ""

    def cancel(self, reason: str = "cancelado") -> None:
        self.reason = reason
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set() or (self._parent is not None and self._parent.cancelled)

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError(self.reason or (self._parent.reason if self._parent else "cancelado"))

    def wait(self, timeout: float) -> bool:
        """Espera até ``timeout`` ou cancelamento. Devolve True se cancelado."""
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            if self.cancelled:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._event.wait(min(remaining, 0.1))

    def child(self) -> "CancellationToken":
        return CancellationToken(self)


@dataclass(order=True)
class _Job:
    priority: int
    seq: int
    fn: Callable = None  # type: ignore[assignment]
    args: tuple = ()
    kwargs: dict = None  # type: ignore[assignment]
    future: Future = None  # type: ignore[assignment]
    name: str = ""


class Worker:
    """Thread dedicada com fila de prioridade (menor número = mais urgente)."""

    def __init__(self, name: str, *, max_queue: int = 256):
        self.name = name
        self._queue: queue.PriorityQueue = queue.PriorityQueue(maxsize=max_queue)
        self._seq = itertools.count()
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self.current: str = ""
        self.processed = 0
        self.failed = 0
        self.last_activity = 0.0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._running.set()
        self._thread = threading.Thread(target=self._loop, name=f"ultron-{self.name}", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._running.clear()
        try:
            self._queue.put_nowait(_Job(-1, next(self._seq)))  # acorda a thread
        except queue.Full:
            pass
        if self._thread is not None:
            self._thread.join(timeout)

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def submit(self, fn: Callable, *args: Any, priority: int = 50, name: str = "", **kwargs: Any) -> Future:
        future: Future = Future()
        job = _Job(priority, next(self._seq), fn, args, kwargs, future, name or getattr(fn, "__name__", "job"))
        try:
            self._queue.put_nowait(job)
        except queue.Full:
            future.set_exception(RuntimeError(f"fila do worker {self.name} cheia"))
        return future

    def pending(self) -> int:
        return self._queue.qsize()

    def _loop(self) -> None:
        while self._running.is_set():
            try:
                job = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if job.fn is None:
                continue
            if not job.future.set_running_or_notify_cancel():
                continue
            self.current = job.name
            self.last_activity = time.time()
            try:
                result = job.fn(*job.args, **(job.kwargs or {}))
                job.future.set_result(result)
                self.processed += 1
            except BaseException as exc:
                self.failed += 1
                job.future.set_exception(exc)
                if not isinstance(exc, CancelledError):
                    log.exception("tarefa %s falhou no worker %s", job.name, self.name)
            finally:
                self.current = ""
                self.last_activity = time.time()


@dataclass
class _Periodic:
    name: str
    worker: str
    fn: Callable
    interval: float
    next_run: float
    running: bool = False
    runs: int = 0
    errors: int = 0
    enabled: bool = True


class Scheduler:
    """Agenda tarefas periódicas em workers, sem sobrepor execuções da mesma tarefa."""

    def __init__(self, pool: "WorkerPool"):
        self._pool = pool
        self._jobs: dict[str, _Periodic] = {}
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def every(self, name: str, interval: float, fn: Callable, *, worker: str = "perception",
              initial_delay: float = 0.0) -> None:
        with self._lock:
            self._jobs[name] = _Periodic(name, worker, fn, max(0.05, float(interval)),
                                         time.monotonic() + max(0.0, initial_delay))

    def set_interval(self, name: str, interval: float) -> None:
        with self._lock:
            if name in self._jobs:
                self._jobs[name].interval = max(0.05, float(interval))

    def set_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            if name in self._jobs:
                self._jobs[name].enabled = bool(enabled)

    def trigger(self, name: str) -> None:
        """Antecipa a próxima execução de uma tarefa."""
        with self._lock:
            if name in self._jobs:
                self._jobs[name].next_run = 0.0

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ultron-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(2.0)

    def jobs(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {n: {"interval": j.interval, "runs": j.runs, "errors": j.errors,
                        "running": j.running, "enabled": j.enabled} for n, j in self._jobs.items()}

    def _loop(self) -> None:
        while not self._stop.wait(0.05):
            now = time.monotonic()
            with self._lock:
                due = [j for j in self._jobs.values() if j.enabled and not j.running and now >= j.next_run]
                for job in due:
                    job.running = True
                    job.next_run = now + job.interval
            for job in due:
                self._dispatch(job)

    def _dispatch(self, job: _Periodic) -> None:
        def run() -> None:
            try:
                job.fn()
                job.runs += 1
            except Exception:
                job.errors += 1
                log.exception("tarefa periódica %s falhou", job.name)
            finally:
                job.running = False

        future = self._pool.submit(job.worker, run, priority=80, name=job.name)
        if future.done() and future.exception() is not None:
            job.running = False


class WorkerPool:
    NAMES = ("ai", "vision", "voice", "network", "memory", "perception", "imagination")

    def __init__(self, names: tuple[str, ...] = NAMES):
        self.workers = {name: Worker(name) for name in names}
        self.scheduler = Scheduler(self)

    def start(self) -> None:
        for worker in self.workers.values():
            worker.start()
        self.scheduler.start()

    def stop(self) -> None:
        self.scheduler.stop()
        for worker in self.workers.values():
            worker.stop(1.0)

    def submit(self, worker: str, fn: Callable, *args: Any, priority: int = 50, name: str = "",
               **kwargs: Any) -> Future:
        target = self.workers.get(worker)
        if target is None:
            raise KeyError(f"worker desconhecido: {worker}")
        return target.submit(fn, *args, priority=priority, name=name, **kwargs)

    def status(self) -> dict[str, dict[str, Any]]:
        return {name: {"alive": w.alive, "pending": w.pending(), "current": w.current,
                       "processed": w.processed, "failed": w.failed}
                for name, w in self.workers.items()}


def run_with_timeout(fn: Callable, timeout: float, *args: Any, **kwargs: Any) -> Any:
    """Executa ``fn`` em thread auxiliar e desiste após ``timeout`` segundos.

    Threads Python não podem ser mortas: em caso de timeout a thread é abandonada
    (daemon) e ``TimeoutError`` é levantado para o chamador seguir em frente.
    """
    result: dict[str, Any] = {}
    done = threading.Event()

    def target() -> None:
        try:
            result["value"] = fn(*args, **kwargs)
        except BaseException as exc:
            result["error"] = exc
        finally:
            done.set()

    threading.Thread(target=target, name=f"timeout-{getattr(fn, '__name__', 'fn')}", daemon=True).start()
    if not done.wait(timeout):
        raise TimeoutError(f"{getattr(fn, '__name__', 'operação')} excedeu {timeout:.1f}s")
    if "error" in result:
        raise result["error"]
    return result.get("value")


@dataclass
class RetryPolicy:
    """Tentativas limitadas com espera exponencial. Nunca repete indefinidamente."""

    max_attempts: int = 3
    base_delay: float = 0.5
    max_delay: float = 8.0
    factor: float = 2.0

    def delays(self):
        delay = self.base_delay
        for _ in range(max(0, self.max_attempts - 1)):
            yield min(self.max_delay, delay)
            delay *= self.factor

    def run(self, fn: Callable[[int], Any], *, retry_on: tuple = (Exception,),
            token: CancellationToken | None = None) -> Any:
        attempt = 0
        delays = list(self.delays())
        while True:
            attempt += 1
            if token is not None:
                token.raise_if_cancelled()
            try:
                return fn(attempt)
            except retry_on:
                if attempt >= self.max_attempts:
                    raise
                pause = delays[attempt - 1] if attempt - 1 < len(delays) else self.max_delay
                if token is not None:
                    if token.wait(pause):
                        token.raise_if_cancelled()
                else:
                    time.sleep(pause)
