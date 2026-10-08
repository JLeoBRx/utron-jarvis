import threading
import time
import unittest

import helpers

from ultron.core.event_bus import EventBus
from ultron.core.events import EventType

assert helpers.ROOT.is_dir()          # helpers isola dados e caminhos antes do import do ULTRON


class EventBusTest(unittest.TestCase):
    def test_sync_delivery_before_start(self):
        bus = EventBus()
        seen = []
        bus.subscribe(EventType.SYSTEM_BOOT, lambda e: seen.append(threading.current_thread().name))
        bus.publish(EventType.SYSTEM_BOOT, {"v": 1})
        self.assertEqual(seen, [threading.current_thread().name])

    def test_async_delivery_after_start_does_not_block_publisher(self):
        bus = EventBus()
        bus.start()
        try:
            gate = threading.Event()
            seen = []

            def slow(event):
                gate.wait(2)
                seen.append(event.get("n"))

            bus.subscribe(EventType.LOG, slow)
            started = time.perf_counter()
            for n in range(5):
                bus.publish(EventType.LOG, {"n": n})
            self.assertLess(time.perf_counter() - started, 0.5, "publicar não pode esperar o assinante")
            gate.set()
            self.assertTrue(bus.wait_idle(3))
            self.assertEqual(seen, [0, 1, 2, 3, 4], "ordem de entrega preservada")
        finally:
            bus.stop()

    def test_handler_error_is_isolated(self):
        bus = EventBus()
        seen = []

        def broken(event):
            raise RuntimeError("falha proposital")

        bus.subscribe(EventType.LOG, broken)
        bus.subscribe(EventType.LOG, lambda e: seen.append(e.id))
        bus.publish(EventType.LOG, {})
        self.assertEqual(len(seen), 1)
        self.assertEqual(bus.stats.handler_errors, 1)

    def test_type_filter_wildcard_and_unsubscribe(self):
        bus = EventBus()
        typed, every = [], []
        sub = bus.subscribe([EventType.WAKE_WORD, EventType.VOICE_RECEIVED], lambda e: typed.append(e.type))
        bus.subscribe(None, lambda e: every.append(e.type))
        bus.publish(EventType.WAKE_WORD)
        bus.publish(EventType.LOG)
        sub.unsubscribe()
        bus.publish(EventType.VOICE_RECEIVED)
        self.assertEqual(typed, [EventType.WAKE_WORD])
        self.assertEqual(every, [EventType.WAKE_WORD, EventType.LOG, EventType.VOICE_RECEIVED])

    def test_history_and_stats(self):
        bus = EventBus(history=3)
        for _ in range(5):
            bus.publish(EventType.LOG)
        self.assertEqual(len(bus.history(10)), 3)
        self.assertEqual(bus.stats.published, 5)
        self.assertEqual(bus.stats.by_type["LOG"], 5)

    def test_queue_overflow_drops_instead_of_blocking(self):
        bus = EventBus(max_queue=2)
        gate = threading.Event()
        bus.subscribe(EventType.LOG, lambda e: gate.wait(2))
        bus.start()
        try:
            started = time.perf_counter()
            for _ in range(20):
                bus.publish(EventType.LOG)
            self.assertLess(time.perf_counter() - started, 0.5)
            self.assertGreater(bus.stats.dropped, 0)
        finally:
            gate.set()
            bus.stop()

    def test_events_are_immutable_records(self):
        bus = EventBus()
        event = bus.publish(EventType.LOG, {"a": 1}, source="teste")
        self.assertEqual(event.to_dict()["type"], "LOG")
        self.assertEqual(event.source, "teste")
        with self.assertRaises(Exception):
            event.source = "outro"          # dataclass congelada


if __name__ == "__main__":
    unittest.main()
