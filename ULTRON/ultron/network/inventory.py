"""Inventário persistente de dispositivos da rede local."""
from __future__ import annotations

import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from ..memory.store import Database
from . import oui

_KIND_HINTS = (
    (re.compile(r"printer|impressora|epson|brother|canon|hp[-_ ]?(?:laser|office|deskjet)|kyocera|xerox", re.I), "printer"),
    (re.compile(r"android|iphone|galaxy|redmi|xiaomi|motorola|moto[- ]g|pixel", re.I), "phone"),
    (re.compile(r"ipad|tablet|tab[- ]?s", re.I), "tablet"),
    (re.compile(r"\btv\b|chromecast|roku|fire[- ]?stick|bravia|webos|tizen|smart[- ]?tv", re.I), "media"),
    (re.compile(r"esp[-_]?\w*|tasmota|shelly|sonoff|tuya|wled|smart[- ]?plug", re.I), "iot"),
    (re.compile(r"nas|synology|qnap|truenas", re.I), "storage"),
    (re.compile(r"desktop|laptop|notebook|pc-|-pc\b|workstation|macbook|imac", re.I), "computer"),
)


@dataclass
class Device:
    key: str
    ip: str
    mac: str
    hostname: str
    vendor: str
    kind: str
    status: str
    first_seen: float
    last_seen: float
    latency_ms: float | None

    def label(self) -> str:
        names = {"router": "Roteador", "this_computer": "Este computador", "printer": "Impressora",
                 "phone": "Celular", "tablet": "Tablet", "media": "Mídia/TV", "iot": "IoT",
                 "storage": "Armazenamento", "computer": "Computador", "virtual_machine": "Máquina virtual",
                 "raspberry_pi": "Raspberry Pi"}
        base = self.hostname or names.get(self.kind, "Desconhecido")
        return f"{self.ip} {base}"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["label"] = self.label()
        return data


def infer_kind(ip: str, mac: str, hostname: str, vendor: str, *, gateway: str = "", own_ip: str = "") -> str:
    if ip == own_ip:
        return "this_computer"
    if ip == gateway:
        return "router"
    if vendor in ("VMware", "Oracle VirtualBox", "Microsoft Hyper-V", "Parallels", "Xen", "QEMU/KVM"):
        return "virtual_machine"
    if vendor == "Raspberry Pi":
        return "raspberry_pi"
    haystack = f"{hostname} {vendor}"
    for pattern, kind in _KIND_HINTS:
        if pattern.search(haystack):
            return kind
    return "unknown"


class NetworkInventory:
    def __init__(self, db: Database):
        self.db = db

    def merge_scan(self, scan: dict[str, Any], *, gateway: str = "", own_ip: str = "") -> dict[str, list[Device]]:
        """Funde o resultado de uma descoberta. Devolve dispositivos novos, online e offline."""
        now = time.time()
        seen_keys = set()
        new, online = [], []
        known = {d.key: d for d in self.devices()}
        for host in scan.get("hosts", []):
            ip, mac = host["ip"], host.get("mac") or ""
            key = mac or f"ip:{ip}"
            if not mac:
                legacy = next((d for d in known.values() if d.ip == ip), None)   # dispositivo já conhecido por MAC
                if legacy:
                    key, mac = legacy.key, legacy.mac
            seen_keys.add(key)
            vendor = oui.vendor(mac) if mac else ""
            hostname = host.get("hostname") or (known[key].hostname if key in known else "")
            kind = infer_kind(ip, mac, hostname, vendor, gateway=gateway, own_ip=own_ip)
            status = "online" if host.get("alive") or "arp" in (host.get("methods") or ()) else "unknown"
            first = known[key].first_seen if key in known else now
            self.db.execute(
                "INSERT INTO network_devices(key,ip,mac,hostname,vendor,kind,status,first_seen,last_seen,latency_ms) "
                "VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET ip=excluded.ip, mac=excluded.mac, "
                "hostname=excluded.hostname, vendor=excluded.vendor, kind=excluded.kind, status=excluded.status, "
                "last_seen=excluded.last_seen, latency_ms=excluded.latency_ms",
                (key, ip, mac, hostname, vendor, kind, status, first, now, host.get("latency_ms")))
            device = Device(key, ip, mac, hostname, vendor, kind, status, first, now, host.get("latency_ms"))
            online.append(device)
            if key not in known:
                new.append(device)
        offline = []
        for key, device in known.items():
            if key not in seen_keys and device.status != "offline":
                self.db.execute("UPDATE network_devices SET status='offline' WHERE key=?", (key,))
                device.status = "offline"
                offline.append(device)
        return {"new": new, "online": online, "offline": offline}

    def devices(self, *, status: str | None = None) -> list[Device]:
        if status:
            rows = self.db.query("SELECT * FROM network_devices WHERE status=? ORDER BY ip", (status,))
        else:
            rows = self.db.query("SELECT * FROM network_devices ORDER BY ip")
        devices = [Device(r["key"], r["ip"], r["mac"], r["hostname"], r["vendor"], r["kind"], r["status"],
                          r["first_seen"], r["last_seen"], r["latency_ms"]) for r in rows]
        devices.sort(key=lambda d: tuple(int(x) for x in d.ip.split(".")) if re.fullmatch(r"[\d.]+", d.ip) else (999,))
        return devices

    def count(self, status: str | None = "online") -> int:
        if status:
            row = self.db.one("SELECT COUNT(*) FROM network_devices WHERE status=?", (status,))
        else:
            row = self.db.one("SELECT COUNT(*) FROM network_devices")
        return int(row[0]) if row else 0
