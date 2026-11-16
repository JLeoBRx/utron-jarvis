"""Diagnóstico de rede: gateway, latência, DNS e conectividade.

Testes locais (gateway) sempre podem rodar. Testes que saem da rede local (DNS público,
conectividade com a internet) passam pela política de privacidade.
"""
from __future__ import annotations

import socket
import statistics
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .discovery import ping

INTERNET_PROBES = (("1.1.1.1", 443), ("8.8.8.8", 53))
DNS_PROBE_NAME = "example.com"


@dataclass
class CheckResult:
    name: str
    status: str                  # OK | FAIL | DEGRADED | SKIPPED | UNAVAILABLE
    detail: str = ""
    latency_ms: float | None = None
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_gateway(gateway_ip: str | None, *, count: int = 3) -> CheckResult:
    if not gateway_ip:
        return CheckResult("gateway", "FAIL", "nenhum gateway padrão configurado")
    latencies, lost = [], 0
    try:
        for _ in range(count):
            alive, latency = ping(gateway_ip, timeout_ms=900)
            if alive:
                if latency is not None:
                    latencies.append(latency)
            else:
                lost += 1
    except FileNotFoundError:
        return CheckResult("gateway", "UNAVAILABLE", "comando ping indisponível neste sistema")
    loss = lost / count
    if loss >= 1.0:
        return CheckResult("gateway", "FAIL", f"gateway {gateway_ip} não respondeu", data={"loss": loss})
    avg = statistics.mean(latencies) if latencies else None
    status = "OK" if loss == 0 and (avg is None or avg < 50) else "DEGRADED"
    detail = f"gateway {gateway_ip} respondeu" + (f" em {avg:.1f} ms" if avg is not None else "")
    if loss:
        detail += f"; perda de {loss:.0%}"
    return CheckResult("gateway", status, detail, avg, {"loss": loss, "samples": latencies})


def check_dns(servers: list[str], *, allowed: bool) -> CheckResult:
    if not allowed:
        return CheckResult("dns", "SKIPPED", "consulta externa bloqueada pelo modo local",
                           data={"servers": servers})
    started = time.perf_counter()
    try:
        socket.getaddrinfo(DNS_PROBE_NAME, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        return CheckResult("dns", "FAIL", f"resolução de nomes falhou: {exc}", data={"servers": servers})
    ms = (time.perf_counter() - started) * 1000
    return CheckResult("dns", "OK" if ms < 300 else "DEGRADED", f"resolução de nomes em {ms:.0f} ms", ms,
                       {"servers": servers})


def check_internet(*, allowed: bool, timeout: float = 3.0) -> CheckResult:
    if not allowed:
        return CheckResult("internet", "SKIPPED", "teste externo bloqueado pelo modo local")
    errors = []
    for host, port in INTERNET_PROBES:
        started = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=timeout):
                ms = (time.perf_counter() - started) * 1000
            return CheckResult("internet", "OK" if ms < 150 else "DEGRADED", f"conectividade confirmada ({host})",
                               ms, {"probe": f"{host}:{port}"})
        except OSError as exc:
            errors.append(f"{host}: {exc}")
    return CheckResult("internet", "FAIL", "sem conectividade externa", data={"errors": errors})


def run(snapshot: dict[str, Any], *, external_allowed: Callable[[str], bool]) -> dict[str, Any]:
    gateway = (snapshot.get("gateway") or {}).get("ip")
    primary = snapshot.get("primary")
    checks = [
        CheckResult("interface", "OK" if primary else "FAIL",
                    f"{primary['name']} {primary['ipv4']}" if primary else "nenhuma interface ativa com IPv4"),
        check_gateway(gateway),
        check_dns(snapshot.get("dns") or [], allowed=external_allowed("teste de DNS")),
        check_internet(allowed=external_allowed("teste de conectividade")),
    ]
    statuses = [c.status for c in checks if c.status not in ("SKIPPED", "UNAVAILABLE")]
    incomplete = [c.name for c in checks if c.status in ("SKIPPED", "UNAVAILABLE")]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "DEGRADED" in statuses:
        overall = "DEGRADED"
    else:
        overall = "PARTIAL" if incomplete else "OK"
    return {"overall": overall, "checks": [c.to_dict() for c in checks], "incomplete": incomplete,
            "timestamp": time.time()}
