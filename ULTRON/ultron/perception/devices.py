"""Sensor de periféricos: câmera, microfone, alto-falantes, teclado, mouse, USB, Bluetooth...

* Windows: ``Get-PnpDevice -PresentOnly`` (script fixo, somente leitura);
* Linux: ``/sys/class/video4linux``, ``/proc/asound/cards``, ``/proc/bus/input/devices``,
  ``/sys/bus/usb/devices``.

A primeira leitura vira referência; dispositivos que aparecem ou somem depois disso
geram eventos.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Callable

from ..platform import system
from .base import Percept, Sensor, SensorUnavailable

_PS_PNP = (
    "$ErrorActionPreference='Stop';"
    "Get-PnpDevice -PresentOnly | Where-Object { $_.Class -in "
    "@('Camera','Image','AudioEndpoint','Keyboard','Mouse','USB','Bluetooth','Printer','Monitor','DiskDrive','MEDIA') }"
    " | Select-Object Class,FriendlyName,Status,InstanceId | ConvertTo-Json -Compress"
)

_MIC_RE = re.compile(r"micro|microphone|mic\b|headset|entrada|input", re.I)
_SPK_RE = re.compile(r"alto-falante|speaker|fone|headphone|sa[ií]da|output|hdmi|realtek.*audio", re.I)


def categorize(cls: str, name: str) -> str:
    cls = (cls or "").lower()
    if cls in ("camera", "image"):
        return "camera"
    if cls == "audioendpoint":
        if _MIC_RE.search(name):
            return "microphone"
        if _SPK_RE.search(name):
            return "speakers"
        return "audio"
    return {"keyboard": "keyboard", "mouse": "mouse", "usb": "usb", "bluetooth": "bluetooth",
            "printer": "printer", "monitor": "monitor", "diskdrive": "storage", "media": "audio"}.get(cls, "other")


def parse_pnp_json(text: str) -> list[dict]:
    data = json.loads(text)
    items = data if isinstance(data, list) else [data]
    devices = []
    for item in items:
        name = str(item.get("FriendlyName") or "").strip()
        if not name:
            continue
        devices.append({"id": str(item.get("InstanceId") or name), "name": name,
                        "category": categorize(str(item.get("Class") or ""), name),
                        "status": str(item.get("Status") or "")})
    return devices


def parse_proc_input(text: str) -> list[dict]:
    devices, name, handlers = [], "", ""
    for line in text.splitlines() + [""]:
        if line.startswith("N: Name="):
            name = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("H: Handlers="):
            handlers = line.split("=", 1)[1]
        elif not line.strip() and name:
            if "kbd" in handlers and "mouse" not in handlers and re.search(r"keyboard|teclado", name, re.I):
                devices.append({"id": f"input:{name}", "name": name, "category": "keyboard", "status": "OK"})
            elif "mouse" in handlers:
                devices.append({"id": f"input:{name}", "name": name, "category": "mouse", "status": "OK"})
            name, handlers = "", ""
    return devices


def _linux_devices() -> list[dict]:
    devices: list[dict] = []
    for node in sorted(Path("/sys/class/video4linux").glob("video*")):
        try:
            name = (node / "name").read_text().strip()
            devices.append({"id": f"v4l:{node.name}", "name": name, "category": "camera", "status": "OK"})
        except OSError:
            continue
    try:
        for line in Path("/proc/asound/cards").read_text().splitlines():
            match = re.match(r"\s*(\d+)\s+\[[^\]]+\]:\s*(.+)", line)
            if match:
                devices.append({"id": f"alsa:{match.group(1)}", "name": match.group(2).strip(),
                                "category": "audio", "status": "OK"})
    except OSError:
        pass
    try:
        devices.extend(parse_proc_input(Path("/proc/bus/input/devices").read_text()))
    except OSError:
        pass
    for node in sorted(Path("/sys/bus/usb/devices").glob("*")):
        product = node / "product"
        if product.is_file():
            try:
                name = product.read_text().strip()
                vendor = (node / "manufacturer").read_text().strip() if (node / "manufacturer").is_file() else ""
                devices.append({"id": f"usb:{node.name}", "name": f"{vendor} {name}".strip(),
                                "category": "usb", "status": "OK"})
            except OSError:
                continue
    return devices


def list_devices() -> list[dict]:
    if sys.platform == "win32":
        result = system.powershell(_PS_PNP, timeout=25)
        if not result.ok:
            raise SensorUnavailable(f"PnP indisponível: {result.stderr.strip()[:160]}")
        return parse_pnp_json(result.stdout) if result.stdout.strip() else []
    if sys.platform.startswith("linux"):
        return _linux_devices()
    raise SensorUnavailable("inventário de periféricos não suportado neste sistema")


class DeviceSensor(Sensor):
    name = "devices"
    kind = "structural"

    def __init__(self, interval: float = 30.0, *, on_change: Callable[[str, dict], None] | None = None,
                 lister: Callable[[], list[dict]] | None = None):
        super().__init__(interval)
        self._on_change = on_change
        self._lister = lister or list_devices
        self._known: dict[str, dict] | None = None

    def sense(self) -> Percept:
        devices = self._lister()
        current = {d["id"]: d for d in devices}
        added, removed = [], []
        if self._known is not None:
            added = [d for k, d in current.items() if k not in self._known]
            removed = [d for k, d in self._known.items() if k not in current]
            if self._on_change:
                for d in added:
                    self._on_change("added", d)
                for d in removed:
                    self._on_change("removed", d)
        self._known = current
        summary: dict[str, list[str]] = {}
        for d in devices:
            summary.setdefault(d["category"], []).append(d["name"])
        return Percept("device", "structural", {"devices": devices, "summary": summary,
                                                "added": added, "removed": removed}, 1.0)
