"""Limite de frequência em memória (janela deslizante). Vale para UM processo; com várias instâncias, o limite
precisa ir para o *proxy* ou para um armazenamento comum (registrado em PORTAL_THREAT_MODEL.md)."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    def __init__(self, max_events: int, window_seconds: float, *, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = 50_000) -> None:
        self.max_events, self.window, self._clock, self._max_keys = max_events, window_seconds, clock, max_keys
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Registra um evento. ``False`` se ``key`` já passou do limite na janela."""
        now = self._clock()
        with self._lock:
            if len(self._events) > self._max_keys:                 # não deixa a memória crescer sem limite
                self._prune(now)
            events = self._events[key]
            while events and now - events[0] > self.window:
                events.popleft()
            if len(events) >= self.max_events:
                return False
            events.append(now)
            return True

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def _prune(self, now: float) -> None:
        for key in [k for k, events in self._events.items() if not events or now - events[-1] > self.window]:
            del self._events[key]
