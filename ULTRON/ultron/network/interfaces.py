"""Interfaces de rede, gateway, DNS, Wi-Fi e rotas.

Somente leitura. Cada coletor usa a fonte nativa do sistema e devolve ``None``/lista vazia
quando a informação não existe — nada é estimado.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from ..platform import system

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

IS_WINDOWS = sys.platform == "win32"


@dataclass
class Interface:
    name: str
    is_up: bool
    mac: str = ""
    ipv4: list = field(default_factory=list)       # [{"address", "netmask", "prefix", "network"}]
    ipv6: list = field(default_factory=list)
    speed_mbps: int = 0
    mtu: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mac_family() -> int:
    if psutil is None:
        return -1
    return getattr(psutil, "AF_LINK", -1)


def list_interfaces() -> list[Interface]:
    if psutil is None:
        return []
    stats = psutil.net_if_stats()
    result = []
    for name, addrs in psutil.net_if_addrs().items():
        st = stats.get(name)
        iface = Interface(name=name, is_up=bool(st and st.isup), speed_mbps=int(getattr(st, "speed", 0) or 0),
                          mtu=int(getattr(st, "mtu", 0) or 0))
        for addr in addrs:
            if addr.family == socket.AF_INET:
                entry = {"address": addr.address, "netmask": addr.netmask or ""}
                try:
                    net = ipaddress.IPv4Network(f"{addr.address}/{addr.netmask}", strict=False)
                    entry.update(prefix=net.prefixlen, network=str(net))
                except (ValueError, TypeError):
                    pass
                iface.ipv4.append(entry)
            elif addr.family == socket.AF_INET6:
                iface.ipv6.append({"address": addr.address.split("%")[0], "netmask": addr.netmask or ""})
            elif addr.family == _mac_family() or (addr.address and re.fullmatch(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", addr.address)):
                iface.mac = normalize_mac(addr.address)
        result.append(iface)
    return result


def normalize_mac(mac: str) -> str:
    digits = re.sub(r"[^0-9A-Fa-f]", "", str(mac or ""))
    if len(digits) != 12:
        return ""
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2)).upper()


# ------------------------------------------------------------------ gateway
def parse_proc_net_route(text: str) -> list[dict[str, Any]]:
    """Rotas IPv4 de ``/proc/net/route`` (endereços em hexadecimal little-endian)."""
    routes = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 8:
            continue
        try:
            dest = socket.inet_ntoa(bytes.fromhex(parts[1])[::-1])
            gateway = socket.inet_ntoa(bytes.fromhex(parts[2])[::-1])
            mask = socket.inet_ntoa(bytes.fromhex(parts[7])[::-1])
            flags = int(parts[3], 16)
            metric = int(parts[6])
        except (ValueError, OSError):
            continue
        routes.append({"interface": parts[0], "destination": dest, "gateway": gateway, "netmask": mask,
                       "metric": metric, "up": bool(flags & 0x1)})
    return routes


def parse_windows_route_print(text: str) -> list[dict[str, Any]]:
    """Tabela de ``route print -4``: Destino, Máscara, Gateway, Interface, Métrica."""
    routes = []
    pattern = re.compile(r"^\s*(\d+\.\d+\.\d+\.\d+)\s+(\d+\.\d+\.\d+\.\d+)\s+(\S+)\s+(\d+\.\d+\.\d+\.\d+)\s+(\d+)\s*$")
    for line in text.splitlines():
        match = pattern.match(line)
        if match:
            dest, mask, gateway, iface_ip, metric = match.groups()
            routes.append({"destination": dest, "netmask": mask,
                           "gateway": gateway if re.match(r"\d+\.\d+\.\d+\.\d+", gateway) else "",
                           "interface": iface_ip, "metric": int(metric), "up": True})
    return routes


def routing_table() -> list[dict[str, Any]]:
    if IS_WINDOWS:
        result = system.run(["route", "print", "-4"], timeout=6)
        return parse_windows_route_print(result.stdout) if result.ok else []
    try:
        with open("/proc/net/route", encoding="ascii") as handle:
            return parse_proc_net_route(handle.read())
    except OSError:
        return []


def default_gateway(routes: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    routes = routes if routes is not None else routing_table()
    defaults = [r for r in routes if r.get("destination") == "0.0.0.0" and r.get("netmask") == "0.0.0.0"
                and r.get("gateway") and r["gateway"] != "0.0.0.0"]
    if not defaults:
        return None
    best = min(defaults, key=lambda r: r.get("metric", 0))
    return {"ip": best["gateway"], "interface": best.get("interface", ""), "metric": best.get("metric", 0)}


# ------------------------------------------------------------------ DNS
_PS_DNS = (
    "$ErrorActionPreference='Stop';"
    "Get-DnsClientServerAddress -AddressFamily IPv4 | Where-Object { $_.ServerAddresses } | "
    "Select-Object InterfaceAlias,ServerAddresses | ConvertTo-Json -Compress"
)


def parse_resolv_conf(text: str) -> list[str]:
    servers = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver" and parts[1] not in servers:
            servers.append(parts[1])
    return servers


def parse_ipconfig_dns(text: str) -> list[str]:
    """Servidores DNS no ``ipconfig /all`` (pt-BR "Servidores DNS" ou en "DNS Servers")."""
    servers: list[str] = []
    capturing = False
    for line in text.splitlines():
        if re.search(r"(Servidores DNS|DNS Servers)", line, re.I):
            capturing = True
            line = line.split(":", 1)[-1]
        elif capturing and not re.match(r"^\s+\d", line):
            capturing = False
        if capturing:
            for ip in re.findall(r"\d+\.\d+\.\d+\.\d+", line):
                if ip not in servers:
                    servers.append(ip)
    return servers


def dns_servers() -> list[str]:
    if IS_WINDOWS:
        result = system.powershell(_PS_DNS, timeout=12)
        if result.ok and result.stdout.strip():
            try:
                data = json.loads(result.stdout)
                items = data if isinstance(data, list) else [data]
                servers: list[str] = []
                for item in items:
                    addrs = item.get("ServerAddresses") or []
                    for ip in (addrs if isinstance(addrs, list) else [addrs]):
                        if ip and ip not in servers:
                            servers.append(str(ip))
                if servers:
                    return servers
            except ValueError:
                pass
        fallback = system.run(["ipconfig", "/all"], timeout=8)
        return parse_ipconfig_dns(fallback.stdout) if fallback.ok else []
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as handle:
            return parse_resolv_conf(handle.read())
    except OSError:
        return []


# ------------------------------------------------------------------ Wi-Fi
def parse_netsh_wlan(text: str) -> dict[str, Any] | None:
    info: dict[str, Any] = {}
    for raw in text.splitlines():
        key, sep, value = raw.partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "ssid" and value:
            info["ssid"] = value
        elif key == "bssid":
            info["bssid"] = normalize_mac(value) or value
        elif key in ("sinal", "signal"):
            match = re.search(r"(\d+)\s*%", value)
            if match:
                info["signal"] = int(match.group(1))
        elif key in ("tipo de rádio", "tipo de radio", "radio type"):
            info["radio"] = value
        elif key in ("canal", "channel"):
            info["channel"] = value
        elif key in ("autenticação", "autenticacao", "authentication"):
            info["auth"] = value
        elif key in ("taxa de recepção (mbps)", "taxa de recepcao (mbps)", "receive rate (mbps)"):
            info["rx_mbps"] = value
    return info if info.get("ssid") else None


def wifi_info() -> dict[str, Any] | None:
    if IS_WINDOWS:
        result = system.run(["netsh", "wlan", "show", "interfaces"], timeout=6)
        return parse_netsh_wlan(result.stdout) if result.ok else None
    if system.which("nmcli"):
        result = system.run(["nmcli", "-t", "-f", "active,ssid,signal,bssid", "dev", "wifi"], timeout=6, encoding="utf-8")
        for line in result.stdout.splitlines():
            parts = line.replace("\\:", "\x00").split(":")
            if parts and parts[0] == "yes" and len(parts) >= 3:
                return {"ssid": parts[1], "signal": int(parts[2]) if parts[2].isdigit() else None,
                        "bssid": normalize_mac(parts[3].replace("\x00", ":")) if len(parts) > 3 else ""}
    return None


# ------------------------------------------------------------------ retrato completo
def is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.is_private and not addr.is_loopback and not addr.is_link_local


def primary(interfaces: list[Interface], gateway: dict[str, Any] | None) -> dict[str, Any] | None:
    candidates = [i for i in interfaces if i.is_up and i.ipv4]
    if gateway:
        gw = ipaddress.ip_address(gateway["ip"])
        for iface in candidates:
            for entry in iface.ipv4:
                network = entry.get("network")
                if network and gw in ipaddress.IPv4Network(network):
                    return {"name": iface.name, "ipv4": entry["address"], "netmask": entry.get("netmask", ""),
                            "subnet": network, "prefix": entry.get("prefix"), "mac": iface.mac,
                            "ipv6": [x["address"] for x in iface.ipv6][:4], "speed_mbps": iface.speed_mbps}
    for iface in candidates:
        for entry in iface.ipv4:
            if not entry["address"].startswith(("127.", "169.254.")):
                return {"name": iface.name, "ipv4": entry["address"], "netmask": entry.get("netmask", ""),
                        "subnet": entry.get("network", ""), "prefix": entry.get("prefix"), "mac": iface.mac,
                        "ipv6": [x["address"] for x in iface.ipv6][:4], "speed_mbps": iface.speed_mbps}
    return None


def snapshot(*, include_dns: bool = True, include_wifi: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    interfaces = list_interfaces()
    routes = routing_table()
    gateway = default_gateway(routes)
    snap = {
        "timestamp": time.time(),
        "hostname": socket.gethostname(),
        "interfaces": [i.to_dict() for i in interfaces],
        "primary": primary(interfaces, gateway),
        "gateway": gateway,
        "dns": dns_servers() if include_dns else [],
        "wifi": wifi_info() if include_wifi else None,
        "routes": routes[:40],
        "psutil": psutil is not None,
    }
    snap["online"] = bool(snap["primary"])
    snap["collect_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return snap


def signature(snap: dict[str, Any]) -> tuple:
    """Assinatura para detectar mudanças relevantes de rede."""
    primary_ = snap.get("primary") or {}
    wifi = snap.get("wifi") or {}
    gateway = snap.get("gateway") or {}
    return (primary_.get("name"), primary_.get("ipv4"), gateway.get("ip"), wifi.get("ssid"),
            tuple(snap.get("dns") or ()))
