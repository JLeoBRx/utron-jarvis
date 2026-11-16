"""Sensor de rede: adapta a Network Intelligence ao contrato de percepção."""
from __future__ import annotations

from .base import Percept, Sensor


class NetworkSensor(Sensor):
    name = "network"
    kind = "structural"
    worker = "network"

    def __init__(self, intelligence, interval: float = 30.0):
        super().__init__(interval)
        self.intelligence = intelligence

    def sense(self) -> Percept:
        snap = self.intelligence.refresh()
        primary = snap.get("primary") or {}
        return Percept("network", "structural", {
            "online": snap.get("online", False), "interface": primary.get("name", ""),
            "ipv4": primary.get("ipv4", ""), "subnet": primary.get("subnet", ""),
            "gateway": (snap.get("gateway") or {}).get("ip", ""), "dns": snap.get("dns", []),
            "wifi": snap.get("wifi"), "devices_online": self.intelligence.inventory.count("online"),
        }, 0.95)
