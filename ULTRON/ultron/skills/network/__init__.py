"""Skills de rede: estado, inventário, varredura autorizada, diagnóstico, ping, apelidos/notas,
verificação de conectividade de um aparelho, relatório e página oficial do roteador.

Tudo restrito à sub-rede privada deste computador. Abrir a administração do roteador é
"administração de dispositivo de rede" e sempre exige autorização específica.
"""
from __future__ import annotations

import ipaddress
import socket
import time
import webbrowser
from pathlib import Path

from ...network import discovery, oui
from ...network.inventory import InventoryError
from ..base import Risk, Skill, SkillContext, SkillResult, VerificationResult, check, schema, string

STALE_SCAN = 15 * 60          # inventário mais velho que isso ganha leitura passiva antes de listar


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
    description = ("Listar os dispositivos da rede local (nome, IP, MAC, fabricante, estado observado: presente, "
                   "ausente ou desconhecido). Atualiza o inventário por leitura passiva quando está antigo.")
    inputs = schema({"status": string(10, enum=["online", "present", "absent", "offline", "unknown", "all",
                                                "trusted", "untrusted"]),
                     "text": string(80)})
    risk = Risk.LOW

    def execute(self, ctx, status: str = "present", text: str = "") -> SkillResult:
        net = self._net(ctx)
        status = {"present": "online", "offline": "absent"}.get(status, status)
        notes, evidence = [], ["fonte: inventário local"]
        discovery_on = bool(getattr(ctx.settings, "network_discovery", True)) if ctx.settings is not None else True
        last = max(float(net.last_scan.get("timestamp") or 0), float(net.last_passive or 0))
        if discovery_on and time.time() - last > STALE_SCAN:
            refreshed = net.passive_refresh()                   # sem tráfego novo: lê a tabela de vizinhos
            if refreshed.get("error"):
                notes.append(f"Leitura da rede indisponível: {refreshed['error']}.")
            elif not refreshed.get("skipped"):
                evidence.append("leitura passiva da tabela de vizinhos agora")
            if net.inventory.count(status=None) == 0 and not refreshed.get("error"):
                scanned = net.scan(cancel=ctx.cancel)
                if scanned.get("error"):
                    notes.append(f"Varredura indisponível: {scanned['error']}.")
                elif not scanned.get("skipped"):
                    evidence.append(f"varredura de {scanned.get('network')}")
        elif not discovery_on:
            notes.append("Descoberta automática desativada; mostrando o inventário salvo.")
        trusted = {"trusted": True, "untrusted": False}.get(status)
        devices = net.inventory.devices(status=None if status in ("all", "trusted", "untrusted") else status,
                                        trusted=trusted, text=text)
        if not devices:
            empty = "Nenhum dispositivo no inventário." if net.inventory.count(status=None) == 0 else \
                "Nenhum dispositivo nesse filtro."
            return SkillResult(True, " ".join([empty] + notes), evidence, {"devices": [], "notes": notes})
        body = net.inventory_text(status if status in ("online", "absent", "unknown") else "all")
        if status in ("trusted", "untrusted") or text:
            body = f"{len(devices)} dispositivo(s): " + "; ".join(f"{d.name} ({d.ip}, {d.state_label})"
                                                                   for d in devices[:12]) + "."
        limits = " Inventário pode estar incompleto: aparelhos que bloqueiam ping e estão ociosos podem não aparecer."
        return SkillResult(True, body + limits + (" " + " ".join(notes) if notes else ""), evidence,
                           {"devices": [d.to_dict() for d in devices], "counts": net.inventory.counts(),
                            "notes": notes})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.9, [check("read", True, "inventário persistente lido")])


class DeviceUpdate(_NetSkill):
    name = "network.device_update"
    description = "Dar apelido, escrever notas ou marcar um dispositivo da rede como conhecido/confiável."
    inputs = schema({"ref": string(80), "alias": {"type": "string", "maxLength": 60, "minLength": 0},
                     "notes": {"type": "string", "maxLength": 1000, "minLength": 0}, "trusted": {"type": "boolean"}},
                    ("ref",))
    risk = Risk.LOW

    def execute(self, ctx, ref: str, alias: str | None = None, notes: str | None = None,
                trusted: bool | None = None) -> SkillResult:
        try:
            device = self._net(ctx).update_device(ref, alias=alias, notes=notes, trusted=trusted)
        except InventoryError as exc:
            return SkillResult(False, error=str(exc), error_kind="NOT_FOUND" if "nenhum" in str(exc) else
                               "INVALID_ARGUMENT")
        changes = [k for k, v in (("apelido", alias), ("notas", notes), ("confiável", trusted)) if v is not None]
        return SkillResult(True, f"Dispositivo {device['name']} ({device['ip']}) atualizado: {', '.join(changes) or 'nada'}.",
                           [device["key"]], {"key": device["key"], "alias": alias, "notes": notes, "trusted": trusted})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        device = ctx.network.inventory.get(result.data["key"])
        checks = [check("exists", device is not None, "dispositivo no inventário")]
        if device is not None:
            for field in ("alias", "trusted"):
                if result.data.get(field) is not None:
                    expected = result.data[field] if field != "alias" else " ".join(result.data[field].split())[:60]
                    checks.append(check(field, getattr(device, field) == expected, f"{field} gravado"))
        return VerificationResult.from_checks(checks)


class CheckDevice(_NetSkill):
    name = "network.check_device"
    description = ("Verificar a conectividade de UM dispositivo do inventário (ping e tabela de vizinhos). "
                   "Sem resposta não prova que saiu da rede.")
    inputs = schema({"ref": string(80)}, ("ref",))
    risk = Risk.LOW
    timeout = 20.0

    def execute(self, ctx, ref: str) -> SkillResult:
        try:
            result = self._net(ctx).check_device(ref)
        except InventoryError as exc:
            return SkillResult(False, error=str(exc), error_kind="PERMISSION_ERROR" if "fora" in str(exc) else "NOT_FOUND")
        device = result["device"]
        return SkillResult(True, f"{device['name']} ({device['ip']}): {result['verdict']}.", [result["verdict"]],
                           {"key": device["key"], "at": result["at"], "alive": result["alive"],
                            "neighbor": result["neighbor"]})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        device = ctx.network.inventory.get(result.data["key"])
        recorded = device is not None and abs(float(device.last_check.get("at", 0)) - result.data["at"]) < 1
        return VerificationResult.from_checks([check("check_recorded", recorded, "resultado registrado no inventário")])


class ExportInventory(_NetSkill):
    name = "network.export"
    description = "Gerar um relatório local do inventário da rede (Markdown, CSV ou JSON)."
    inputs = schema({"format": string(4, enum=["md", "csv", "json"])})
    risk = Risk.LOW

    def execute(self, ctx, format: str = "md") -> SkillResult:
        path = self._net(ctx).export(format)
        return SkillResult(True, f"Relatório salvo em {path}.", [str(path)], {"path": str(path)})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        path = Path(result.data["path"])
        return VerificationResult.from_checks([check("file_written", path.is_file() and path.stat().st_size > 0,
                                                     f"{path.name} existe")])


class OpenRouterAdmin(_NetSkill):
    name = "network.open_admin"
    description = ("Abrir no navegador a página oficial de administração do roteador (gateway da rede local). "
                   "Não faz login nem altera nada; exige autorização.")
    inputs = schema({})
    risk = Risk.LOW
    sensitive = "network_admin"

    def describe_action(self, args):
        return "abrir a página de administração do roteador no navegador"

    def execute(self, ctx, **_) -> SkillResult:
        try:
            url = self._net(ctx).admin_url()
        except InventoryError as exc:
            return SkillResult(False, error=str(exc), error_kind="NOT_FOUND")
        if not webbrowser.open(url, new=2):
            return SkillResult(False, error="o sistema não abriu o navegador", error_kind="APPLICATION_ERROR")
        return SkillResult(True, f"Abrindo {url} no navegador. O login e qualquer alteração ficam com você, na "
                                 "interface oficial do fabricante.", [url], {"url": url})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("UNCONFIRMED", 0.5, [check("browser_requested", True, result.data["url"])],
                                  [result.data["url"]], "o navegador foi acionado; a página não é observável daqui")


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
        summary = (f"Varredura de {result['network']}: {result['online']} dispositivo(s) presente(s), "
                   f"{result['new']} novo(s), {result.get('unknown', 0)} sem resposta agora, "
                   f"{result.get('absent', 0)} ausente(s), em {result['seconds']} s.")
        if not result.get("ping_available"):
            summary += " Ping indisponível; usei apenas a tabela de vizinhos."
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


SKILLS = (NetworkStatus, NetworkDevices, NetworkScan, NetworkDiagnose, Ping, UpdateVendorDatabase, DeviceUpdate,
          CheckDevice, ExportInventory, OpenRouterAdmin)
