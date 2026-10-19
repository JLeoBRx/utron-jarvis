"""Monitor das conexões de rede do próprio JARVIS.

Lista as conexões do processo atual (via psutil), classifica em locais/externas e registra
cada destino externo observado. Também lista portas em escuta (serviços expostos) — o
JARVIS não deve ter nenhuma. O status do firewall do Windows é lido, nunca alterado.
"""
from __future__ import annotations

import ipaddress
import os
import re
import sys
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any

from ..platform import system

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


def classify(ip: str) -> str:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return "unknown"
    if addr.is_loopback:
        return "loopback"
    if addr.is_private or addr.is_link_local:
        return "lan"
    if addr.is_multicast or addr.is_unspecified:
        return "local"
    return "external"


@dataclass
class ExternalPeer:
    ip: str
    port: int
    first_seen: float
    last_seen: float
    count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConnectionMonitor:
    def __init__(self, pid: int | None = None):
        self.pid = pid or os.getpid()
        self._lock = threading.Lock()
        self._external: dict[tuple[str, int], ExternalPeer] = {}
        self.last_scan: dict[str, Any] = {}

    def _connections(self) -> list:
        if psutil is None:
            return []
        proc = psutil.Process(self.pid)
        getter = getattr(proc, "net_connections", None) or getattr(proc, "connections")
        try:
            return getter(kind="inet")
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return []

    def scan(self) -> dict[str, Any]:
        now = time.time()
        conns = self._connections()
        listening, local, external = [], 0, []
        for c in conns:
            if c.status == "LISTEN":
                listening.append({"address": c.laddr.ip if c.laddr else "", "port": c.laddr.port if c.laddr else 0,
                                  "exposed": bool(c.laddr and classify(c.laddr.ip) not in ("loopback",))})
                continue
            if not c.raddr:
                continue
            kind = classify(c.raddr.ip)
            if kind == "external":
                external.append({"ip": c.raddr.ip, "port": c.raddr.port, "status": c.status})
                with self._lock:
                    key = (c.raddr.ip, c.raddr.port)
                    peer = self._external.get(key)
                    if peer is None:
                        self._external[key] = ExternalPeer(c.raddr.ip, c.raddr.port, now, now)
                    else:
                        peer.last_seen = now
                        peer.count += 1
            else:
                local += 1
        self.last_scan = {"timestamp": now, "listening": listening, "local_connections": local,
                          "external_now": external, "available": psutil is not None}
        return self.last_scan

    def external_log(self) -> list[dict[str, Any]]:
        with self._lock:
            return [p.to_dict() for p in sorted(self._external.values(), key=lambda p: -p.last_seen)]


def parse_firewall(text: str) -> dict[str, bool]:
    """``netsh advfirewall show allprofiles state`` → {perfil: ligado}."""
    profiles: dict[str, bool] = {}
    current = None
    for line in text.splitlines():
        header = re.match(r"^\s*(?:Configurações do Perfil|Perfil)\s+(.+?)\s*:?\s*$|^\s*(\w+) Profile Settings", line, re.I)
        if header:
            current = (header.group(1) or header.group(2) or "").strip(" :").lower()
            continue
        state = re.match(r"^\s*(?:Estado|State)\s+(\w+)", line, re.I)
        if state and current:
            profiles[current] = state.group(1).upper() in ("LIGADO", "ON", "ATIVADO")
            current = None
    return profiles


def firewall_status() -> dict[str, Any]:
    if sys.platform != "win32":
        return {"available": False, "profiles": {}}
    result = system.run(["netsh", "advfirewall", "show", "allprofiles", "state"], timeout=8)
    profiles = parse_firewall(result.stdout) if result.ok else {}
    return {"available": bool(profiles), "profiles": profiles,
            "all_on": bool(profiles) and all(profiles.values())}
