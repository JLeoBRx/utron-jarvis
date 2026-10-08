"""NETWORK INTELLIGENCE — integra a rede ao World Model, ao Neural Graph e ao estado.

* ``refresh()`` (periódico): interfaces, gateway, DNS, Wi-Fi → ``NETWORK_CHANGED`` quando
  algo relevante muda;
* ``scan()`` (periódico, se habilitado): descoberta autorizada → inventário →
  ``DEVICE_DETECTED`` para dispositivos novos (após a primeira varredura de referência);
* ``diagnose()``: diagnóstico sob demanda.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from ..core.events import EventType
from . import diagnostics, discovery, interfaces, oui
from .inventory import NetworkInventory

log = logging.getLogger("ultron.network")


class NetworkIntelligence:
    name = "network"

    def __init__(self, *, db, settings_getter: Callable[[], Any], bus=None, state=None, world=None,
                 graph=None, privacy=None):
        self.inventory = NetworkInventory(db)
        self._settings = settings_getter
        self._bus = bus
        self._state = state
        self._world = world
        self._graph = graph
        self._privacy = privacy
        self._lock = threading.Lock()
        self._scan_lock = threading.Lock()
        self.snapshot: dict[str, Any] = {}
        self._signature: tuple | None = None
        self.last_scan: dict[str, Any] = {}
        self.last_diagnosis: dict[str, Any] = {}
        self.scans = 0

    # ------------------------------------------------------------ ciclo de vida
    def start(self) -> None:
        self.refresh()

    def stop(self) -> None:
        pass

    def health(self) -> dict:
        primary = self.snapshot.get("primary")
        if not self.snapshot:
            return {"status": "UNKNOWN", "detail": "sem leitura"}
        if not primary:
            return {"status": "WARN", "detail": "sem interface ativa"}
        return {"status": "OK", "detail": f"{primary['name']} {primary['ipv4']}"}

    def _emit(self, event_type: EventType, **payload: Any) -> None:
        if self._bus is not None:
            self._bus.publish(event_type, payload, source="network")

    # ------------------------------------------------------------ estado da rede
    def refresh(self) -> dict[str, Any]:
        snap = interfaces.snapshot()
        signature = interfaces.signature(snap)
        with self._lock:
            previous = self._signature
            self.snapshot = snap
            self._signature = signature
        changed = previous is not None and previous != signature
        self._publish(snap)
        if changed:
            self._emit(EventType.NETWORK_CHANGED, before=list(previous or ()), after=list(signature),
                       primary=snap.get("primary"), gateway=snap.get("gateway"), wifi=snap.get("wifi"),
                       online=bool(snap.get("online", False)))
        return snap

    def _publish(self, snap: dict[str, Any]) -> None:
        primary = snap.get("primary") or {}
        gateway = (snap.get("gateway") or {}).get("ip", "")
        devices = {d.key: {"ip": d.ip, "mac": d.mac, "hostname": d.hostname, "vendor": d.vendor,
                           "kind": d.kind, "status": d.status, "last_seen": d.last_seen}
                   for d in self.inventory.devices()}
        online = sum(1 for d in devices.values() if d["status"] == "online")
        summary = {
            "hostname": snap.get("hostname"), "interface": primary.get("name", ""),
            "ipv4": primary.get("ipv4", ""), "ipv6": primary.get("ipv6", []), "mac": primary.get("mac", ""),
            "subnet": primary.get("subnet", ""), "gateway": gateway, "dns": snap.get("dns", []),
            "wifi": snap.get("wifi"), "online": snap.get("online", False),
            "devices_online": online, "devices_known": len(devices),
            "last_scan": self.last_scan.get("timestamp"), "vendor_source": oui.source(),
        }
        if self._world is not None:
            self._world.update("network", {**summary, "interfaces": snap.get("interfaces", []),
                                           "routes": snap.get("routes", [])[:20], "devices": devices},
                               source="network", confidence=0.95)
        if self._state is not None:
            self._state.update(_source="network", network_state=summary)

    # ------------------------------------------------------------ descoberta
    def scan(self, *, cancel=None, force: bool = False) -> dict[str, Any]:
        settings = self._settings()
        if not force and not getattr(settings, "network_discovery", True):
            return {"skipped": "descoberta desativada nas configurações"}
        if not self._scan_lock.acquire(blocking=False):
            return {"skipped": "varredura já em andamento"}
        try:
            snap = self.snapshot or self.refresh()
            primary = snap.get("primary")
            result = discovery.discover(primary, max_hosts=int(getattr(settings, "discovery_max_hosts", 256)),
                                        cancel=cancel)
            gateway = (snap.get("gateway") or {}).get("ip", "")
            baseline = self.inventory.count(status=None) == 0
            merged = self.inventory.merge_scan(result, gateway=gateway, own_ip=(primary or {}).get("ipv4", ""))
            self.scans += 1
            self.last_scan = {**result, "new": len(merged["new"]), "online": len(merged["online"]),
                              "offline": len(merged["offline"])}
            for device in merged["online"]:
                self._link_device(device)
            if not baseline:
                for device in merged["new"]:
                    self._emit(EventType.DEVICE_DETECTED, ip=device.ip, mac=device.mac, hostname=device.hostname,
                               vendor=device.vendor, kind=device.kind, origin="network")
            self._publish(snap)
            return self.last_scan
        except discovery.ScopeError as exc:
            self.last_scan = {"error": str(exc), "timestamp": time.time()}
            return self.last_scan
        finally:
            self._scan_lock.release()

    def _link_device(self, device) -> None:
        if self._graph is None or device.kind == "this_computer":
            return
        try:
            node = self._graph.add_node("DEVICE", device.label(), {"ip": device.ip, "mac": device.mac,
                                                                   "kind": device.kind, "vendor": device.vendor},
                                        node_id=f"device:{device.key.lower()}")
            hub = self._graph.add_node("CONCEPT", "Rede local")
            self._graph.connect(hub.id, node.id, "RELATED", delta=0.02)
        except (ValueError, KeyError):
            pass

    # ------------------------------------------------------------ diagnóstico
    def diagnose(self, *, explicit: bool = True) -> dict[str, Any]:
        snap = self.refresh()

        def allowed(purpose: str) -> bool:
            if self._privacy is None:
                return False
            return self._privacy.allow_external(purpose, explicit=explicit).allowed

        self.last_diagnosis = diagnostics.run(snap, external_allowed=allowed)
        return self.last_diagnosis

    def describe(self) -> str:
        snap = self.snapshot or {}
        primary = snap.get("primary") or {}
        wifi = snap.get("wifi") or {}
        lines = []
        if primary:
            lines.append(f"Interface {primary.get('name')} — IP {primary.get('ipv4')} ({primary.get('subnet')}).")
        else:
            lines.append("Nenhuma interface ativa com IPv4.")
        gateway = (snap.get("gateway") or {}).get("ip")
        if gateway:
            lines.append(f"Gateway {gateway}.")
        if snap.get("dns"):
            lines.append("DNS " + ", ".join(snap["dns"][:3]) + ".")
        if wifi.get("ssid"):
            signal = f", sinal {wifi['signal']}%" if wifi.get("signal") is not None else ""
            lines.append(f"Wi-Fi {wifi['ssid']}{signal}.")
        devices = self.inventory.devices(status="online")
        if devices:
            lines.append(f"{len(devices)} dispositivos ativos: " +
                         "; ".join(d.label() + (f" ({d.vendor})" if d.vendor else "") for d in devices[:8]) + ".")
        return " ".join(lines)
