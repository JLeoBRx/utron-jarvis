"""Descoberta de dispositivos na rede local AUTORIZADA.

Escopo e limites (não negociáveis):

* somente a sub-rede IPv4 **privada** da interface principal do próprio computador;
* no máximo ``max_hosts`` endereços (padrão 256; sub-redes maiores são reduzidas ao /24
  do próprio IP);
* métodos passivos ou de rotina de administração: tabela ARP/vizinhos do sistema, ``ping``
  de um único pacote e DNS reverso;
* sem varredura de portas, sem exploração, sem interceptação.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..platform import system
from .interfaces import is_private, normalize_mac

IS_WINDOWS = sys.platform == "win32"


@dataclass
class Host:
    ip: str
    mac: str = ""
    hostname: str = ""
    alive: bool = False
    latency_ms: float | None = None
    methods: tuple = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScopeError(ValueError):
    """O alvo está fora da rede local autorizada."""


def authorized_scope(primary: dict[str, Any] | None, *, max_hosts: int = 256) -> ipaddress.IPv4Network:
    if not primary or not primary.get("ipv4"):
        raise ScopeError("sem interface de rede ativa")
    ip = primary["ipv4"]
    if not is_private(ip):
        raise ScopeError(f"{ip} não é um endereço privado; descoberta não autorizada")
    subnet = primary.get("subnet") or f"{ip}/24"
    network = ipaddress.IPv4Network(subnet, strict=False)
    if network.num_addresses - 2 > max_hosts:
        network = ipaddress.IPv4Network(f"{ip}/24", strict=False)
    if not network.is_private:
        raise ScopeError(f"{network} não é uma rede privada")
    return network


# ------------------------------------------------------------------ tabela ARP / vizinhos
def parse_arp_windows(text: str) -> dict[str, str]:
    table = {}
    for match in re.finditer(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5})\s+(\w+)", text):
        ip, mac, _kind = match.groups()
        mac = normalize_mac(mac)
        if mac and mac != "FF:FF:FF:FF:FF:FF" and not mac.startswith("01:00:5E"):
            table[ip] = mac
    return table


def parse_proc_net_arp(text: str) -> dict[str, str]:
    table = {}
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and parts[2] != "0x0":
            mac = normalize_mac(parts[3])
            if mac and mac != "00:00:00:00:00:00":
                table[parts[0]] = mac
    return table


def parse_ip_neigh(text: str) -> dict[str, str]:
    table = {}
    for line in text.splitlines():
        match = re.match(r"(\d+\.\d+\.\d+\.\d+)\s+.*lladdr\s+([0-9a-fA-F:]{17})\s+(\w+)", line)
        if match and match.group(3) not in ("FAILED", "INCOMPLETE"):
            table[match.group(1)] = normalize_mac(match.group(2))
    return table


def neighbor_table() -> dict[str, str]:
    if IS_WINDOWS:
        result = system.run(["arp", "-a"], timeout=8)
        return parse_arp_windows(result.stdout) if result.ok else {}
    table: dict[str, str] = {}
    try:
        with open("/proc/net/arp", encoding="ascii") as handle:
            table.update(parse_proc_net_arp(handle.read()))
    except OSError:
        pass
    if system.which("ip"):
        result = system.run(["ip", "neigh"], timeout=5, encoding="utf-8")
        if result.ok:
            table.update(parse_ip_neigh(result.stdout))
    return table


# ------------------------------------------------------------------ ping
_LATENCY_RE = re.compile(r"(?:tempo|time)[=<]\s*([\d.,]+)\s*ms", re.I)


def parse_ping_latency(text: str) -> float | None:
    match = _LATENCY_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:
        return None


def ping(ip: str, *, timeout_ms: int = 700) -> tuple[bool, float | None]:
    ipaddress.ip_address(ip)                       # valida: nunca texto livre no comando
    if IS_WINDOWS:
        args = ["ping", "-n", "1", "-w", str(int(timeout_ms)), ip]
    else:
        args = ["ping", "-c", "1", "-W", str(max(1, round(timeout_ms / 1000))), "-n", ip]
    result = system.run(args, timeout=timeout_ms / 1000 + 3)
    if result.returncode == 127:
        raise FileNotFoundError("comando ping indisponível")
    latency = parse_ping_latency(result.stdout)
    # No Windows "Host de destino inacessível" retorna 0; só conta resposta com tempo/TTL.
    alive = result.ok and (latency is not None or "ttl=" in result.stdout.lower())
    return alive, latency


def reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, UnicodeError):
        return ""


# ------------------------------------------------------------------ varredura
def discover(primary: dict[str, Any] | None, *, max_hosts: int = 256, workers: int = 32,
             timeout_ms: int = 700, resolve_names: bool = True, deadline_s: float = 90.0,
             cancel=None, progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    network = authorized_scope(primary, max_hosts=max_hosts)
    hosts = [str(h) for h in network.hosts()][:max_hosts]
    started = time.monotonic()
    found: dict[str, Host] = {}
    ping_available = True
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 64)), thread_name_prefix="ultron-ping") as pool:
        futures = {pool.submit(ping, ip, timeout_ms=timeout_ms): ip for ip in hosts}
        done = 0
        try:
            for future in as_completed(futures, timeout=deadline_s):
                if cancel is not None and getattr(cancel, "cancelled", False):
                    break
                ip = futures[future]
                done += 1
                try:
                    alive, latency = future.result()
                except FileNotFoundError:
                    ping_available = False
                    alive, latency = False, None
                except Exception:
                    alive, latency = False, None
                if alive:
                    found[ip] = Host(ip, alive=True, latency_ms=latency, methods=("icmp",))
                if progress and done % 16 == 0:
                    progress(done, len(hosts))
        except TimeoutError:
            pass
        finally:
            for future in futures:
                future.cancel()
    for ip, mac in neighbor_table().items():
        try:
            if ipaddress.ip_address(ip) not in network:
                continue
        except ValueError:
            continue
        host = found.get(ip) or Host(ip)
        host.mac = mac
        host.methods = tuple(sorted(set(host.methods) | {"arp"}))
        found[ip] = host
    own_ip = primary.get("ipv4") if primary else None
    if own_ip and own_ip in map(str, network.hosts()):
        own = found.get(own_ip) or Host(own_ip, alive=True)
        own.mac = own.mac or (primary.get("mac") or "")
        own.alive = True
        own.methods = tuple(sorted(set(own.methods) | {"self"}))
        found[own_ip] = own
    if resolve_names and found:
        with ThreadPoolExecutor(max_workers=16, thread_name_prefix="ultron-rdns") as pool:
            futures = {pool.submit(reverse_dns, ip): ip for ip in found}
            try:
                for future in as_completed(futures, timeout=10):
                    try:
                        found[futures[future]].hostname = future.result()
                    except Exception:
                        pass
            except TimeoutError:
                pass
    return {"network": str(network), "scanned": len(hosts), "ping_available": ping_available,
            "hosts": sorted((h.to_dict() for h in found.values()),
                            key=lambda h: tuple(int(x) for x in h["ip"].split("."))),
            "seconds": round(time.monotonic() - started, 2), "timestamp": time.time()}
