"""Skills de rede: estado, dispositivos, varredura autorizada, diagnóstico e ping."""
from __future__ import annotations

import ipaddress
import socket

from ...network import discovery, oui
from ..base import Risk, Skill, SkillContext, SkillResult, VerificationResult, check, schema, string


class _NetSkill(Skill):
    category = "network"

    def _net(self, ctx: SkillContext):
        if ctx.network is None:
            raise RuntimeError("inteligência de rede indisponível")
        return ctx.network


class NetworkStatus(_NetSkill):
    name = "network.status"
    description = "Informar interface, IP, gateway, DNS, Wi-Fi e dispositivos conhecidos."
    inputs = schema({})
    risk = Risk.NONE

    def execute(self, ctx, **_) -> SkillResult:
        net = self._net(ctx)
        net.refresh()
        return SkillResult(True, net.describe(), ["leitura das interfaces do sistema"], {"snapshot": net.snapshot})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.95, [check("read", True, "dados lidos do sistema operacional")])


class NetworkDevices(_NetSkill):
    name = "network.devices"
    description = "Listar dispositivos conhecidos da rede local (IP, MAC, nome, fabricante, estado)."
    inputs = schema({"status": string(8, enum=["online", "offline", "all"])})
    risk = Risk.NONE

    def execute(self, ctx, status: str = "online") -> SkillResult:
        devices = self._net(ctx).inventory.devices(status=None if status == "all" else status)
        if not devices:
            return SkillResult(True, "Nenhum dispositivo registrado. Execute uma varredura da rede local.", [],
                               {"devices": []})
        lines = [f"{d.ip} {d.hostname or d.kind}{f' — {d.vendor}' if d.vendor else ''}{f' [{d.mac}]' if d.mac else ''}"
                 for d in devices[:30]]
        return SkillResult(True, f"{len(devices)} dispositivo(s): " + "; ".join(lines), ["fonte: inventário local"],
                           {"devices": [d.to_dict() for d in devices]})

    def verify(self, ctx, args, result):
        return VerificationResult("VERIFIED", 0.9, [check("read", True, "inventário persistente")])


class NetworkScan(_NetSkill):
    name = "network.scan"
    description = "Varrer a rede local autorizada (sub-rede privada deste computador) e atualizar o inventário."
    inputs = schema({})
    risk = Risk.LOW
    timeout = 150.0

    def execute(self, ctx, **_) -> SkillResult:
        result = self._net(ctx).scan(cancel=ctx.cancel, force=True)
        if result.get("error"):
            return SkillResult(False, error=result["error"], error_kind="NETWORK_ERROR")
        if result.get("skipped"):
            return SkillResult(False, error=result["skipped"], error_kind="BUSY")
        summary = (f"Varredura de {result['network']}: {result['online']} dispositivo(s) ativo(s), "
                   f"{result['new']} novo(s), em {result['seconds']} s.")
        if not result.get("ping_available"):
            summary += " Ping indisponível; usei apenas a tabela ARP."
        return SkillResult(True, summary, [f"{result['scanned']} endereços examinados"], result)

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        count = ctx.network.inventory.count(status=None)
        return VerificationResult.from_checks([check("inventory_updated", count > 0,
                                                     f"{count} dispositivo(s) no inventário")])


class NetworkDiagnose(_NetSkill):
    name = "network.diagnose"
    description = "Diagnosticar conectividade: interface, gateway, DNS e internet."
    inputs = schema({})
    risk = Risk.LOW
    timeout = 60.0

    def execute(self, ctx, **_) -> SkillResult:
        report = self._net(ctx).diagnose(explicit=True)
        lines = [f"{c['name']}: {c['status']} — {c['detail']}" for c in report["checks"]]
        return SkillResult(True, f"Diagnóstico de rede: {report['overall']}. " + " | ".join(lines),
                           [c["detail"] for c in report["checks"]], report)

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.9, [check("diagnosed", True, f"resultado {result.data['overall']}")])


class Ping(_NetSkill):
    name = "network.ping"
    description = "Medir a latência até um endereço IP ou nome de host."
    inputs = schema({"host": string(253)}, ("host",))
    risk = Risk.LOW

    def execute(self, ctx, host: str) -> SkillResult:
        if not all(c.isalnum() or c in ".-:" for c in host):
            return SkillResult(False, error="host inválido", error_kind="INVALID_ARGUMENT")
        try:
            ip = str(ipaddress.ip_address(host))
        except ValueError:
            try:
                ip = socket.gethostbyname(host)
            except OSError as exc:
                return SkillResult(False, error=f"não consegui resolver {host}: {exc}", error_kind="NETWORK_ERROR")
        if not ipaddress.ip_address(ip).is_private and ctx.privacy is not None:
            decision = ctx.privacy.allow_external("ping", ip, explicit=True)
            if not decision.allowed:
                return SkillResult(False, error=decision.reason, error_kind="PERMISSION_ERROR")
        try:
            alive, latency = discovery.ping(ip, timeout_ms=1500)
        except FileNotFoundError:
            return SkillResult(False, error="comando ping indisponível", error_kind="UNSUPPORTED")
        if not alive:
            return SkillResult(True, f"{host} não respondeu ao ping.", [ip], {"ip": ip, "alive": False})
        return SkillResult(True, f"{host} respondeu" + (f" em {latency:.0f} ms." if latency is not None else "."), [ip],
                           {"ip": ip, "alive": True, "latency_ms": latency})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.9, [check("measured", True, result.result)])


class UpdateVendorDatabase(_NetSkill):
    name = "network.update_vendors"
    description = "Baixar a base oficial de fabricantes (IEEE OUI). Conexão externa sob autorização."
    inputs = schema({})
    risk = Risk.LOW
    expose_to_llm = False
    timeout = 90.0

    def execute(self, ctx, **_) -> SkillResult:
        allowed = ctx.privacy.allow_external("base de fabricantes IEEE", oui.IEEE_URL, explicit=True).allowed \
            if ctx.privacy else False
        try:
            count = oui.update_database(allowed=allowed)
        except PermissionError as exc:
            return SkillResult(False, error=str(exc), error_kind="PERMISSION_ERROR")
        except Exception as exc:
            return SkillResult(False, error=f"falha ao baixar a base: {exc}", error_kind="NETWORK_ERROR")
        return SkillResult(True, f"Base de fabricantes atualizada ({count} prefixos).", [oui.IEEE_URL], {"count": count})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult.from_checks([check("vendor_source", oui.source() == "ieee", f"fonte: {oui.source()}")])


SKILLS = (NetworkStatus, NetworkDevices, NetworkScan, NetworkDiagnose, Ping, UpdateVendorDatabase)
