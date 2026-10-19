"""NETWORK INTELLIGENCE — integra a rede ao World Model, ao Neural Graph e ao estado.

* ``refresh()`` (periódico): interfaces, gateway, DNS, Wi-Fi → ``NETWORK_CHANGED`` quando
  algo relevante muda;
* ``scan()`` (periódico, se habilitado): descoberta autorizada → inventário →
  ``DEVICE_DETECTED`` para dispositivos novos (após a primeira varredura de referência) e
  ``NETWORK_INVENTORY_UPDATED`` com contagens, métodos e limitações;
* ``passive_refresh()``: só lê as tabelas de vizinhos (sem enviar pacotes);
* ``update_device()`` / ``check_device()``: apelido, notas, "confiável" e verificação de
  conectividade de UM aparelho do segmento autorizado (``DEVICE_UPDATED``);
* ``admin_url()``: página de administração do roteador (gateway privado do próprio segmento);
* ``export()``: relatório local (Markdown, CSV ou JSON);
* ``diagnose()``: diagnóstico sob demanda.

Gerenciar aparelhos de terceiros fabricantes exige integração oficial configurada; sem ela o
JARVIS só observa e abre a interface oficial — não promete controle universal.
"""
from __future__ import annotations

import ipaddress
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..core.events import EventType
from . import diagnostics, discovery, interfaces, oui
from .inventory import STATES, InventoryError, NetworkInventory

LIMITATIONS = (
    "A descoberta cobre apenas a sub-rede privada deste computador (no máximo 256 endereços).",
    "Aparelhos que bloqueiam ping e não conversaram recentemente com este computador podem não aparecer.",
    "MACs aleatórios (privacidade de celulares) impedem identificar o fabricante.",
    "Ausência de resposta não prova que o aparelho saiu da rede; 'ausente' exige varreduras seguidas.",
    "A presença de um aparelho não identifica a pessoa que o usa.",
    "Administrar roteadores e outros aparelhos exige a interface oficial ou integração do fabricante.",
)

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
        self.last_passive = 0.0

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
        devices = {d.key: {"ip": d.ip, "mac": d.mac, "hostname": d.hostname, "vendor": d.vendor, "name": d.name,
                           "kind": d.kind, "status": d.status, "last_seen": d.last_seen, "trusted": d.trusted,
                           "confidence": d.confidence}
                   for d in self.inventory.devices()}
        counts = self.inventory.counts()
        online = counts["online"]
        summary = {
            "hostname": snap.get("hostname"), "interface": primary.get("name", ""),
            "ipv4": primary.get("ipv4", ""), "ipv6": primary.get("ipv6", []), "mac": primary.get("mac", ""),
            "subnet": primary.get("subnet", ""), "gateway": gateway, "dns": snap.get("dns", []),
            "wifi": snap.get("wifi"), "online": snap.get("online", False),
            "devices_online": online, "devices_known": len(devices), "devices_absent": counts["absent"],
            "devices_unknown": counts["unknown"], "devices_trusted": counts["trusted"],
            "devices_untrusted_online": counts["untrusted_online"],
            "last_scan": self.last_scan.get("timestamp"), "last_passive": self.last_passive or None,
            "scan_error": self.last_scan.get("error", ""), "limitations": self.last_scan.get("limitations", []),
            "discovery_enabled": bool(getattr(self._settings(), "network_discovery", True)),
            "vendor_source": oui.source(),
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
                                        cancel=cancel, ssdp=bool(getattr(settings, "network_ssdp", False)))
            gateway = (snap.get("gateway") or {}).get("ip", "")
            baseline = self.inventory.count(status=None) == 0
            merged = self.inventory.merge_scan(result, gateway=gateway, own_ip=(primary or {}).get("ipv4", ""))
            self.scans += 1
            self.last_scan = {**result, "new": len(merged["new"]), "online": len(merged["online"]),
                              "unknown": len(merged["unknown"]), "absent": len(merged["absent"]),
                              "offline": len(merged["absent"])}
            for device in merged["online"]:
                self._link_device(device)
            if not baseline:
                for device in merged["new"]:
                    self._emit(EventType.DEVICE_DETECTED, ip=device.ip, mac=device.mac, hostname=device.hostname,
                               vendor=device.vendor, kind=device.kind, origin="network")
            self._publish(snap)
            self._inventory_event("scan", merged)
            return self.last_scan
        except discovery.ScopeError as exc:
            self.last_scan = {"error": str(exc), "timestamp": time.time(),
                              "limitations": [f"descoberta indisponível: {exc}"]}
            self._publish(self.snapshot or {})
            self._inventory_event("scan", None, error=str(exc))
            return self.last_scan
        finally:
            self._scan_lock.release()

    def passive_refresh(self) -> dict[str, Any]:
        """Atualiza presença lendo só as tabelas de vizinhos do sistema (sem tráfego novo)."""
        if not self._scan_lock.acquire(blocking=False):
            return {"skipped": "varredura em andamento"}
        try:
            snap = self.snapshot or self.refresh()
            primary = snap.get("primary")
            result = discovery.discover(primary, passive=True, resolve_names=False)
            gateway = (snap.get("gateway") or {}).get("ip", "")
            merged = self.inventory.merge_scan(result, gateway=gateway, own_ip=(primary or {}).get("ipv4", ""))
            self.last_passive = time.time()
            self._publish(snap)
            self._inventory_event("passive", merged)
            return {**result, "online": len(merged["online"]), "new": len(merged["new"])}
        except discovery.ScopeError as exc:
            return {"error": str(exc)}
        finally:
            self._scan_lock.release()

    def _inventory_event(self, source: str, merged: dict | None, *, error: str = "") -> None:
        counts = self.inventory.counts()
        self._emit(EventType.NETWORK_INVENTORY_UPDATED, source=source, counts=counts, error=error,
                   new=[d.to_dict() for d in (merged or {}).get("new", [])][:20],
                   limitations=self.last_scan.get("limitations", []) if source == "scan" else [],
                   timestamp=time.time())

    # ------------------------------------------------------------ dispositivos
    def scope(self) -> ipaddress.IPv4Network | None:
        try:
            primary = (self.snapshot or {}).get("primary")
            return discovery.authorized_scope(primary, max_hosts=int(getattr(self._settings(), "discovery_max_hosts", 256)))
        except discovery.ScopeError:
            return None

    def in_scope(self, ip: str) -> bool:
        network = self.scope()
        try:
            return network is not None and ipaddress.ip_address(ip) in network
        except ValueError:
            return False

    def update_device(self, ref: str, *, alias: str | None = None, notes: str | None = None,
                      trusted: bool | None = None) -> dict[str, Any]:
        device = self.inventory.find(ref)
        device = self.inventory.update(device.key, alias=alias, notes=notes, trusted=trusted)
        self._emit(EventType.DEVICE_UPDATED, device=device.to_dict(), change="edited")
        self._publish(self.snapshot or {})
        return device.to_dict()

    def check_device(self, ref: str) -> dict[str, Any]:
        """Verificação de conectividade de UM aparelho do segmento autorizado (ping + vizinhos).

        Sem resposta NÃO significa desconectado: o resultado diz exatamente o que foi observado."""
        device = self.inventory.find(ref)
        if not self.in_scope(device.ip):
            raise InventoryError(f"{device.ip} está fora da rede local autorizada; verificação não executada")
        try:
            alive, latency = discovery.ping(device.ip, timeout_ms=1200)
            if not alive:
                alive, latency = discovery.ping(device.ip, timeout_ms=1200)
            ping_ok = True
        except FileNotFoundError:
            alive, latency, ping_ok = False, None, False
        neighbor = discovery.neighbor_table().get(device.ip, "")
        same_mac = bool(neighbor) and (not device.mac or neighbor == device.mac)
        if alive:
            verdict = "respondeu ao ping" + (f" em {latency:.0f} ms" if latency is not None else "")
        elif same_mac:
            verdict = "não respondeu ao ping, mas está na tabela de vizinhos do sistema (provavelmente presente)"
        elif not ping_ok:
            verdict = "ping indisponível neste sistema; presença não verificada"
        else:
            verdict = ("não respondeu agora; isso não prova que saiu da rede (pode estar dormindo ou "
                       "bloqueando ping)")
        result = {"at": time.time(), "alive": alive, "latency_ms": latency, "neighbor": same_mac,
                  "ping_available": ping_ok, "verdict": verdict}
        self.inventory.record_check(device.key, result)
        if alive or same_mac:
            self.inventory.merge_scan({"hosts": [{"ip": device.ip, "mac": device.mac or neighbor, "alive": alive,
                                                  "latency_ms": latency,
                                                  "methods": (["icmp"] if alive else []) + (["arp"] if same_mac else [])}],
                                       "network": device.segment, "interface": device.interface, "passive": True},
                                      gateway=(self.snapshot.get("gateway") or {}).get("ip", ""),
                                      own_ip=((self.snapshot.get("primary") or {}).get("ipv4", "")))
        updated = self.inventory.get(device.key) or device
        self._emit(EventType.DEVICE_UPDATED, device=updated.to_dict(), change="checked", check=result)
        return {"device": updated.to_dict(), **result}

    def admin_url(self) -> str:
        """Página de administração do roteador: http://<gateway> — só gateway privado do próprio segmento."""
        snap = self.snapshot or self.refresh()
        gateway = (snap.get("gateway") or {}).get("ip", "")
        if not gateway:
            raise InventoryError("gateway não identificado nesta rede")
        if not interfaces.is_private(gateway) or not self.in_scope(gateway):
            raise InventoryError(f"o gateway {gateway} não é um endereço privado da rede local autorizada")
        return f"http://{gateway}/"

    def export(self, fmt: str = "md", *, directory: Path | None = None) -> Path:
        from ..config import paths
        fmt = fmt if fmt in ("md", "csv", "json") else "md"
        folder = Path(directory) if directory else paths.data_dir() / "exports"
        folder.mkdir(parents=True, exist_ok=True)
        snap = self.snapshot or {}
        primary = snap.get("primary") or {}
        meta = {"Rede": primary.get("subnet", "—"), "Interface": primary.get("name", "—"),
                "Gateway": (snap.get("gateway") or {}).get("ip", "—"),
                "Última varredura": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.last_scan["timestamp"]))
                if self.last_scan.get("timestamp") else "nenhuma nesta sessão",
                "Fonte de fabricantes": oui.source(), "Limitações": " ".join(LIMITATIONS)}
        path = folder / f"rede-{time.strftime('%Y%m%d-%H%M%S')}.{fmt}"
        path.write_text(self.inventory.export(fmt, meta=meta), encoding="utf-8")
        return path

    def inventory_text(self, status: str = "online", *, limit: int = 12) -> str:
        devices = self.inventory.devices(status=None if status == "all" else status)
        counts = self.inventory.counts()
        if not counts["total"]:
            return "Nenhum dispositivo no inventário ainda."
        label = {"online": "presente(s)", "absent": "ausente(s)", "unknown": "em estado desconhecido",
                 "all": "no inventário"}.get(status, "")
        parts = []
        for d in devices[:limit]:
            extra = d.vendor if d.vendor and d.vendor not in d.name else ""
            parts.append(f"{d.name} ({d.ip}{', ' + extra if extra else ''}){'' if d.trusted else ' [não marcado como conhecido]'}")
        text = f"{len(devices)} dispositivo(s) {label}: " + "; ".join(parts) + ("…" if len(devices) > limit else "") + "."
        if status == "online" and (counts["unknown"] or counts["absent"]):
            text += f" Além disso: {counts['unknown']} desconhecido(s), {counts['absent']} ausente(s)."
        return text

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
            lines.append(f"{len(devices)} dispositivo(s) presente(s): " +
                         "; ".join(d.label() + (f" ({d.vendor})" if d.vendor else "") for d in devices[:8]) + ".")
        return " ".join(lines)

    @staticmethod
    def states() -> dict[str, str]:
        return dict(STATES)
