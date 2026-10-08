"""PERCEPTION ENGINE — agenda os sensores, publica eventos e alimenta o World Model.

A percepção nunca executa ações. Ela observa, registra evidência e informa.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from ..core.events import EventType
from .audio import AudioSensor
from .base import Percept, Sensor
from .devices import DeviceSensor
from .filesystem import FilesystemSensor
from .fusion import PerceptionFusion
from .microphone import MicrophoneSensor
from .network import NetworkSensor
from .ocr import OCRSensor
from .processes import ProcessSensor
from .screen import ScreenSensor
from .system import SystemSensor
from .vision import VisionSensor
from .windows import WindowSensor

log = logging.getLogger("ultron.perception")


class PerceptionEngine:
    name = "perception"

    def __init__(self, *, settings_getter: Callable[[], Any], runtime, bus, state, world, memory=None,
                 router=None, network=None, hud_probe: Callable[[], bool] | None = None,
                 mic_probe: Callable[[], dict] | None = None):
        s = settings_getter()
        self._settings = settings_getter
        self.runtime = runtime
        self.bus = bus
        self.state = state
        self.world = world
        self.memory = memory
        self._lock = threading.Lock()
        self.foreground: dict = {}
        self._last_fused_key = None
        self._last_fuse = 0.0
        self._last_screen_event = 0.0

        self.window_sensor = WindowSensor(s.window_interval, on_change=self._on_window_change, on_hung=self._on_hung)
        self.process_sensor = ProcessSensor(s.process_interval, on_ended=self._on_process_ended,
                                            extra_important=self._known_processes)
        self.system_sensor = SystemSensor(s.system_interval, world=world)
        self.screen_sensor = ScreenSensor(3.0, foreground=lambda: dict(self.foreground),
                                          hud_covering=hud_probe or (lambda: False),
                                          excluded=lambda: tuple(self._settings().excluded_apps),
                                          enabled=lambda: bool(self._settings().screen_observation))
        self.vision_sensor = VisionSensor(self.screen_sensor, router, interval=s.vision_interval,
                                          enabled=lambda: bool(self._settings().screen_observation)) if router else None
        self.ocr_sensor = OCRSensor(self.screen_sensor.capture_now)
        self.audio_sensor = AudioSensor(s.device_interval)
        self.microphone_sensor = MicrophoneSensor(mic_probe or (lambda: {}), 1.0)
        self.filesystem_sensor = FilesystemSensor(self._watch_dirs, s.filesystem_interval)
        self.network_sensor = NetworkSensor(network, s.network_interval) if network is not None else None
        self.device_sensor = DeviceSensor(s.device_interval, on_change=self._on_device_change)
        self.fusion = PerceptionFusion(memory_probe=self._memory_probe)

    # ------------------------------------------------------------ ciclo de vida
    @property
    def sensors(self) -> list[Sensor]:
        items = [self.window_sensor, self.process_sensor, self.system_sensor, self.screen_sensor,
                 self.vision_sensor, self.ocr_sensor, self.audio_sensor, self.microphone_sensor,
                 self.filesystem_sensor, self.network_sensor, self.device_sensor]
        return [s for s in items if s is not None]

    def start(self) -> None:
        for sensor in self.sensors:
            self.runtime.scheduler.every(f"sense:{sensor.name}", sensor.interval,
                                         lambda s=sensor: self.run_sensor(s), worker=sensor.worker,
                                         initial_delay=0.2 if sensor.worker == "perception" else 2.0)

    def stop(self) -> None:
        for sensor in self.sensors:
            self.runtime.scheduler.set_enabled(f"sense:{sensor.name}", False)

    def health(self) -> dict:
        statuses = {s.name: s.status for s in self.sensors}
        failing = [n for n, st in statuses.items() if st == "ERROR"]
        return {"status": "WARN" if failing else "OK",
                "detail": f"{sum(1 for st in statuses.values() if st == 'OK')} sensores ativos"
                          + (f"; com erro: {', '.join(failing)}" if failing else ""),
                "data": statuses}

    def sensor_report(self) -> list[dict]:
        return [s.describe() for s in self.sensors]

    def apply_settings(self, settings) -> None:
        mapping = {"windows": settings.window_interval, "processes": settings.process_interval,
                   "system": settings.system_interval, "vision": settings.vision_interval,
                   "filesystem": settings.filesystem_interval, "network": settings.network_interval,
                   "devices": settings.device_interval, "audio": settings.device_interval}
        for sensor in self.sensors:
            if sensor.name in mapping:
                sensor.interval = mapping[sensor.name]
                self.runtime.scheduler.set_interval(f"sense:{sensor.name}", sensor.interval)

    # ------------------------------------------------------------ execução de sensores
    def run_sensor(self, sensor: Sensor) -> Percept | None:
        percept = sensor.poll()
        if percept is not None:
            try:
                self._handle(sensor, percept)
            except Exception:
                log.exception("falha ao processar percepção de %s", sensor.name)
        return percept

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        self.bus.publish(event_type, payload, source="perception")

    def _handle(self, sensor: Sensor, percept: Percept) -> None:
        self.fusion.ingest(percept)
        data = percept.data
        source = percept.source
        if source == "window":
            fg = data.get("foreground") or {}
            self.foreground = fg
            self.state.update(_source="perception", current_application=fg.get("application", ""),
                              current_window=fg.get("title", "")[:200])
            self.world.update("user_context", {"application": fg.get("application", ""),
                                               "process": fg.get("process", ""), "window": fg.get("title", "")[:200],
                                               "focus_seconds": data.get("focus_seconds"),
                                               "idle_seconds": data.get("idle_seconds")},
                              source="windows", confidence=percept.confidence, merge=True)
            if data.get("windows"):
                self.world.update("windows", {"open": [{k: w.get(k) for k in ("title", "process", "pid", "minimized", "hung")}
                                                       for w in data["windows"][:40]]},
                                  source="windows", confidence=percept.confidence)
        elif source == "process":
            self.state.update(_source="perception", current_processes=[p["name"] for p in data.get("top_cpu", [])[:6]])
            self.world.update("processes", {"count": data.get("count"), "important": data.get("important", []),
                                            "top_memory": [p["name"] for p in data.get("top_memory", [])[:6]]},
                              source="processes", confidence=1.0)
        elif source == "system":
            self.state.update(_source="perception", telemetry={k: data.get(k) for k in
                                                               ("cpu", "ram", "ram_used_gb", "ram_total_gb", "gpu",
                                                                "battery", "uptime_s", "disks")})
        elif source == "screen":
            if data.get("captured") and data.get("changed") and time.time() - self._last_screen_event > 2.0:
                self._last_screen_event = time.time()
                self._emit(EventType.SCREEN_CHANGED, delta=data.get("delta"), application=data.get("application"))
        elif source == "vision":
            if not data.get("discarded"):
                self.state.update(_source="perception", vision_state={
                    "active": True, "model": data.get("model"), "app": data.get("app"),
                    "activity": data.get("activity"), "summary": data.get("summary"),
                    "error_visible": data.get("error_visible"), "at": percept.timestamp})
                self.world.update("user_context", {"activity": data.get("activity", ""),
                                                   "screen_summary": data.get("summary", "")},
                                  source="vision", confidence=percept.confidence, merge=True)
                if data.get("injection"):
                    log.warning("texto na tela tentou instruir o assistente; tratado como dado")
            self._emit(EventType.VISION_UPDATED, **{k: data.get(k) for k in
                                                    ("app", "activity", "summary", "error_visible", "error_text",
                                                     "confidence", "model", "discarded", "injection")})
        elif source == "ocr":
            self._emit(EventType.OCR_UPDATED, lines=len(data.get("lines", [])), errors=data.get("errors", [])[:5])
        elif source == "filesystem":
            for change in data.get("changes", []):
                self._emit(EventType.FILESYSTEM_CHANGED, **change)
            for project in data.get("projects", []):
                self.world.upsert_item("projects", project["path"], project, source="filesystem")
                if self.memory is not None:
                    try:
                        node = self.memory.graph.add_node("PROJECT", project["name"], {"path": project["path"]})
                        if project.get("language") and project["language"] != "desconhecida":
                            lang = self.memory.graph.add_node("CONCEPT", project["language"].split("/")[0])
                            self.memory.graph.connect(node.id, lang.id, "DEPENDS", delta=0.02)
                    except (ValueError, KeyError):
                        pass
        elif source == "device":
            summary = data.get("summary", {})
            self.world.update("peripherals", {k: v[:12] for k, v in summary.items()}, source="devices", confidence=1.0)
            self.state.update(_source="perception", device_state={k: len(v) for k, v in summary.items()})
        elif source == "audio":
            self.world.update("peripherals", {"audio_inputs": [d["name"] for d in data.get("inputs", [])][:8],
                                              "audio_outputs": [d["name"] for d in data.get("outputs", [])][:8],
                                              "default_input": data.get("default_input"),
                                              "default_output": data.get("default_output")},
                              source="audio", confidence=1.0, merge=True)
        if source in ("vision", "ocr", "window", "process", "filesystem", "network"):
            self._maybe_fuse()

    def _maybe_fuse(self) -> None:
        now = time.time()
        if now - self._last_fuse < 1.0:
            return
        self._last_fuse = now
        context = self.fusion.fuse()
        top = context.get("top")
        key = (top["kind"], top["description"]) if top else None
        if top and top["confidence"] >= 0.5 and key != self._last_fused_key:
            self._emit(EventType.PERCEPTION_FUSED, **context)
        self._last_fused_key = key

    # ------------------------------------------------------------ callbacks dos sensores
    def _on_window_change(self, previous: dict, current: dict) -> None:
        self._emit(EventType.WINDOW_CHANGED, title=current.get("title", "")[:200], process=current.get("process", ""),
                   application=current.get("application", ""))
        if previous.get("process") != current.get("process"):
            self._emit(EventType.APPLICATION_CHANGED, previous=previous.get("application", ""),
                       application=current.get("application", ""), process=current.get("process", ""))
            app = current.get("application")
            if app:
                self.world.upsert_item("applications", (current.get("process") or app).lower(),
                                       {"name": app, "process": current.get("process", "")}, source="windows")
                if self.memory is not None:
                    try:
                        node = self.memory.graph.add_node("APPLICATION", app, {"process": current.get("process", "")})
                        self.memory.graph.activate([node.id], reason="focus", reinforce=False)
                    except ValueError:
                        pass

    def _on_hung(self, window: dict) -> None:
        self._emit(EventType.APPLICATION_HUNG, application=window.get("application", ""),
                   process=window.get("process", ""), pid=window.get("pid"), hwnd=window.get("hwnd"),
                   title=window.get("title", "")[:160])

    def _on_process_ended(self, info: dict) -> None:
        self._emit(EventType.PROCESS_ENDED, name=info.get("name"), pid=info.get("pid"),
                   runtime_s=info.get("runtime_s"))

    def _on_device_change(self, change: str, device: dict) -> None:
        self._emit(EventType.DEVICE_DETECTED, change=change, name=device.get("name"),
                   category=device.get("category"), origin="peripheral")
        if change == "added" and self.memory is not None:
            try:
                self.memory.graph.add_node("DEVICE", device.get("name", "Dispositivo"),
                                           {"category": device.get("category")})
            except ValueError:
                pass

    # ------------------------------------------------------------ auxiliares
    def _known_processes(self) -> set:
        apps = self.world.get("applications")
        return {str(v.get("process", "")).lower() for v in apps.values() if v.get("process")}

    def _watch_dirs(self) -> list[str]:
        dirs = list(self._settings().watch_dirs)
        projects = self.world.get("projects")
        recent = sorted(projects.values(), key=lambda p: -p.get("last_seen", 0))[:6]
        dirs += [p["path"] for p in recent if p.get("path")]
        return list(dict.fromkeys(dirs))

    def _memory_probe(self, text: str) -> list[str]:
        if self.memory is None:
            return []
        try:
            return [r.text for r in self.memory.retriever.search(text, limit=2, min_score=0.45)
                    if r.kind == "episode"]
        except Exception:
            return []

    # ------------------------------------------------------------ sob demanda
    def inspect_screen(self, question: str) -> dict:
        if self.vision_sensor is None:
            raise RuntimeError("visão indisponível: roteador de modelos ausente")
        return self.vision_sensor.inspect(question)

    def read_screen_text(self) -> Percept:
        percept = self.ocr_sensor.read_screen()
        self._handle(self.ocr_sensor, percept)
        return percept

    def context(self) -> dict:
        return self.fusion.fuse()
