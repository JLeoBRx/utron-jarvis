"""Memória de trabalho: o que está acontecendo agora.

Fica só na RAM, com capacidade limitada e expiração. Itens com saliência alta são
candidatos à consolidação em memória episódica.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class WorkingItem:
    kind: str                     # input | response | perception | action | result | insight
    content: str
    salience: float = 0.5
    data: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    ttl: float = 900.0
    consolidated: bool = False

    @property
    def expired(self) -> bool:
        return time.time() - self.timestamp > self.ttl

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class WorkingMemory:
    def __init__(self, capacity: int = 64):
        self._items: deque[WorkingItem] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def add(self, kind: str, content: str, *, salience: float = 0.5, ttl: float = 900.0, **data: Any) -> WorkingItem:
        item = WorkingItem(kind, str(content)[:2000], max(0.0, min(1.0, salience)), data, ttl=ttl)
        with self._lock:
            self._items.append(item)
        return item

    def recent(self, limit: int = 12, kinds: tuple[str, ...] | None = None) -> list[WorkingItem]:
        with self._lock:
            items = [i for i in self._items if not i.expired and (kinds is None or i.kind in kinds)]
        return items[-limit:]

    def salient(self, threshold: float = 0.7) -> list[WorkingItem]:
        with self._lock:
            return [i for i in self._items if i.salience >= threshold and not i.consolidated]

    def mark_consolidated(self, items: list[WorkingItem]) -> None:
        with self._lock:
            for item in items:
                item.consolidated = True

    def purge(self) -> int:
        with self._lock:
            before = len(self._items)
            kept = [i for i in self._items if not i.expired]
            self._items.clear()
            self._items.extend(kept)
            return before - len(kept)

    def dialogue(self, limit: int = 8) -> list[dict[str, str]]:
        """Histórico curto de conversa no formato de mensagens do modelo."""
        messages = []
        for item in self.recent(limit * 2, ("input", "response")):
            role = "user" if item.kind == "input" else "assistant"
            messages.append({"role": role, "content": item.content})
        return messages[-limit:]

    def summary(self, limit: int = 8) -> str:
        parts = [f"[{i.kind}] {i.content[:160]}" for i in self.recent(limit)]
        return " | ".join(parts)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
