"""Event Bus interno do ULTRON.

* ``publish`` nunca bloqueia quem publica: o evento entra numa fila e uma thread
  despachante entrega aos assinantes.
* Antes de ``start()`` (boot, testes) a entrega é síncrona.
* A exceção de um assinante é registrada e contada, mas não afeta os demais.
* A fila é limitada: em sobrecarga extrema, eventos são descartados e contados
  (nunca há travamento da origem).
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .events import Event, EventType

log = logging.getLogger("ultron.bus")

Handler = Callable[[Event], None]


@dataclass
class Subscription:
    bus: "EventBus"
    types: frozenset | None
    handler: Handler
    name: str
    active: bool = True
    delivered: int = 0
    errors: int = 0

    def unsubscribe(self) -> None:
        self.bus.unsubscribe(self)


@dataclass
class BusStats:
    published: int = 0
    delivered: int = 0
    dropped: int = 0
    handler_errors: int = 0
    by_type: dict = field(default_factory=dict)


class EventBus:
    def __init__(self, *, max_queue: int = 20000, history: int = 600):
        self._subs: list[Subscription] = []
        self._lock = threading.RLock()
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._history: deque[Event] = deque(maxlen=history)
        self._thread: threading.Thread | None = None
        self._running = threading.Event()
        self._idle = threading.Event()
        self._idle.set()
        self._pending = 0
        self._sync_depth = threading.local()
        self.stats = BusStats()

    # ------------------------------------------------------------ assinaturas
    def subscribe(self, types: EventType | Iterable[EventType] | None, handler: Handler,
                  *, name: str = "") -> Subscription:
        if isinstance(types, EventType):
            kinds = frozenset({types})
        elif types is None:
            kinds = None
        else:
            kinds = frozenset(types)
        sub = Subscription(self, kinds, handler, name or getattr(handler, "__qualname__", "handler"))
        with self._lock:
            self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            sub.active = False
            if sub in self._subs:
                self._subs.remove(sub)

    # ------------------------------------------------------------ publicação
    def publish(self, type_: EventType, payload: dict | None = None, *, source: str = "") -> Event:
        event = Event(type_, dict(payload or {}), source)
        with self._lock:
            self.stats.published += 1
            self.stats.by_type[type_.value] = self.stats.by_type.get(type_.value, 0) + 1
            self._history.append(event)
            running = self._running.is_set()
            if running:
                self._pending += 1
                self._idle.clear()
        if not running:
            self._deliver_sync(event)
            return event
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            with self._lock:
                self.stats.dropped += 1
                self._pending -= 1
                if self._pending <= 0:
                    self._idle.set()
            log.warning("fila do Event Bus cheia; evento %s descartado", type_.value)
        return event

    def emit(self, type_: EventType, source: str = "", **payload) -> Event:
        return self.publish(type_, payload, source=source)

    # ------------------------------------------------------------ entrega
    def _targets(self, event: Event) -> list[Subscription]:
        with self._lock:
            return [s for s in self._subs if s.active and (s.types is None or event.type in s.types)]

    def _call(self, sub: Subscription, event: Event) -> None:
        try:
            sub.handler(event)
            sub.delivered += 1
            with self._lock:
                self.stats.delivered += 1
        except Exception:
            sub.errors += 1
            with self._lock:
                self.stats.handler_errors += 1
            log.exception("assinante %s falhou ao tratar %s", sub.name, event.type.value)

    def _deliver_sync(self, event: Event) -> None:
        depth = getattr(self._sync_depth, "value", 0)
        if depth > 16:  # proteção contra recursão infinita de eventos
            log.error("recursão de eventos interrompida em %s", event.type.value)
            return
        self._sync_depth.value = depth + 1
        try:
            for sub in self._targets(event):
                self._call(sub, event)
        finally:
            self._sync_depth.value = depth

    def _run(self) -> None:
        while self._running.is_set() or not self._queue.empty():
            try:
                event = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                for sub in self._targets(event):
                    self._call(sub, event)
            finally:
                with self._lock:
                    self._pending -= 1
                    if self._pending <= 0:
                        self._pending = 0
                        self._idle.set()

    # ------------------------------------------------------------ controle
    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._running.set()
            self._thread = threading.Thread(target=self._run, name="ultron-event-bus", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._running.clear()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        self._thread = None
        self._idle.set()

    @property
    def running(self) -> bool:
        return self._running.is_set()

    def queue_size(self) -> int:
        return self._queue.qsize()

    def wait_idle(self, timeout: float = 2.0) -> bool:
        """Aguarda a fila esvaziar (usado em testes e no desligamento)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._idle.wait(0.05) and self._queue.empty():
                return True
        return self._queue.empty()

    def history(self, limit: int = 50, types: Iterable[EventType] | None = None) -> list[Event]:
        with self._lock:
            items = list(self._history)
        if types is not None:
            wanted = set(types)
            items = [e for e in items if e.type in wanted]
        return items[-max(1, int(limit)):]

    def subscribers(self) -> list[str]:
        with self._lock:
            return [s.name for s in self._subs]
