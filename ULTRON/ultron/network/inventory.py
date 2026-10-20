"""Inventário persistente de dispositivos da rede local.

Estados OBSERVADOS (nunca presumidos):

* ``online`` (presente) — visto nesta varredura: respondeu ao ping, está na tabela de vizinhos
  do sistema, anunciou-se por SSDP, ou é este computador;
* ``unknown`` (desconhecido) — não visto na última varredura, mas ainda sem evidência suficiente
  para dizer que saiu (um ping sem resposta não prova nada: muitos aparelhos ignoram ping ou
  dormem), ou visto em outra rede;
* ``absent`` (ausente) — não visto em ``ABSENT_AFTER`` varreduras completas seguidas do mesmo
  segmento, com métodos de observação funcionando.

Presença de um aparelho NÃO identifica uma pessoa: o inventário fala de dispositivos.
Apelido, notas e "confiável" são do usuário e nunca são sobrescritos por uma varredura.
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from ..memory.store import Database, looks_secret
from . import oui

ABSENT_AFTER = 2
STATES = {"online": "presente", "absent": "ausente", "unknown": "desconhecido"}
KIND_NAMES = {"router": "Roteador", "this_computer": "Este computador", "printer": "Impressora",
              "phone": "Celular", "tablet": "Tablet", "media": "Mídia/TV", "iot": "IoT",
              "storage": "Armazenamento", "computer": "Computador", "virtual_machine": "Máquina virtual",
              "raspberry_pi": "Raspberry Pi", "unknown": "Desconhecido"}
METHOD_NAMES = {"icmp": "ping", "arp": "tabela ARP", "ndp": "vizinhos IPv6", "self": "este computador",
                "rdns": "DNS reverso", "ssdp": "anúncio SSDP/UPnP"}
RECENT_SECONDS = 15 * 60       # "respondeu recentemente": observado diretamente nos últimos 15 min
# Classificação honesta do que se SABE de cada aparelho (derivada dos estados observados acima)
OBSERVATIONS = {
    "self": "informação do próprio computador",
    "recent": "respondeu recentemente",
    "inferred": "presença inferida — dados incompletos",
    "known": "conhecido anteriormente — não confirmado agora",
    "no_response": "sem resposta no momento",
}

_KIND_HINTS = (
    (re.compile(r"printer|impressora|epson|brother|canon|hp[-_ ]?(?:laser|office|deskjet)|kyocera|xerox", re.I), "printer"),
    (re.compile(r"android|iphone|galaxy|redmi|xiaomi|motorola|moto[- ]g|pixel", re.I), "phone"),
    (re.compile(r"ipad|tablet|tab[- ]?s", re.I), "tablet"),
    (re.compile(r"\btv\b|chromecast|roku|fire[- ]?stick|bravia|webos|tizen|smart[- ]?tv|mediarenderer", re.I), "media"),
    (re.compile(r"esp[-_]?\w*|tasmota|shelly|sonoff|tuya|wled|smart[- ]?plug", re.I), "iot"),
    (re.compile(r"nas|synology|qnap|truenas", re.I), "storage"),
    (re.compile(r"desktop|laptop|notebook|pc-|-pc\b|workstation|macbook|imac", re.I), "computer"),
    (re.compile(r"internetgatewaydevice|wlanaccesspoint|router|roteador", re.I), "router"),
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
    alias: str = ""
    notes: str = ""
    trusted: bool = False
    ipv6: list = field(default_factory=list)
    interface: str = ""
    segment: str = ""
    methods: list = field(default_factory=list)
    confidence: float = 0.0
    missed_scans: int = 0
    vendor_source: str = ""
    extra: dict = field(default_factory=dict)
    last_check: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return (self.alias or self.hostname or self.extra.get("friendly_name") or
                KIND_NAMES.get(self.kind, "Desconhecido"))

    def label(self) -> str:
        return f"{self.ip} {self.name}"

    @property
    def state_label(self) -> str:
        return STATES.get(self.status, self.status)

    @property
    def is_gateway(self) -> bool:
        return bool(self.extra.get("gateway")) or (self.kind == "router" and "self" not in self.methods
                                                   and self.extra.get("gateway") is None)

    def observation(self, now: float | None = None) -> str:
        """O que se sabe AGORA: medido diretamente há pouco, inferido, visto antes ou sem resposta."""
        now = time.time() if now is None else now
        methods = set(self.methods)
        if "self" in methods or self.kind == "this_computer":
            return "self"
        if self.status == "online" and now - (self.last_seen or 0) <= RECENT_SECONDS:
            direct = bool(methods & {"icmp", "arp", "ndp"})
            return "recent" if direct and self.confidence >= 0.7 else "inferred"
        if self.status == "absent":
            return "no_response"
        return "known"

    def missing(self) -> list[str]:
        return [label for value, label in ((self.mac, "MAC"), (self.hostname or self.extra.get("friendly_name"),
                                                                "nome na rede"), (self.vendor, "fabricante"))
                if not value]

    def administration(self) -> str:
        """Descobrir não é administrar: o que o JARVIS pode (e não pode) fazer com este aparelho."""
        if self.observation() == "self":
            return "Este computador: administrado pela sua própria conta do Windows."
        if self.is_gateway:
            return ("Gateway/roteador: a administração é só pela página oficial dele, aberta por você e com as SUAS "
                    "credenciais — o JARVIS não guarda, não testa e não adivinha senhas.")
        return "Descoberto, não administrado: o JARVIS não acessa, não controla e não altera este aparelho."

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        observation = self.observation()
        data.update(label=self.label(), name=self.name, state_label=self.state_label,
                    kind_label=KIND_NAMES.get(self.kind, self.kind),
                    method_labels=[METHOD_NAMES.get(m, m) for m in self.methods],
                    observation=observation, observation_label=OBSERVATIONS[observation],
                    missing=self.missing(), administration=self.administration(), is_gateway=self.is_gateway,
                    reliability_label=("alta" if self.confidence >= 0.9 else "média" if self.confidence >= 0.7
                                       else "baixa" if self.confidence > 0 else "sem medição"))
        return data


def infer_kind(ip: str, mac: str, hostname: str, vendor: str, *, gateway: str = "", own_ip: str = "",
               hint: str = "") -> str:
    if ip == own_ip:
        return "this_computer"
    if ip == gateway:
        return "router"
    if vendor in ("VMware", "Oracle VirtualBox", "Microsoft Hyper-V", "Parallels", "Xen", "QEMU/KVM"):
        return "virtual_machine"
    if vendor == "Raspberry Pi":
        return "raspberry_pi"
    haystack = f"{hostname} {vendor} {hint}"
    for pattern, kind in _KIND_HINTS:
        if pattern.search(haystack):
            return kind
    return "unknown"


def confidence_of(methods: set, *, has_mac: bool, has_name: bool) -> float:
    """Quão certo é que o aparelho estava presente nesta observação (não quem o usa)."""
    if "self" in methods:
        return 1.0
    score = 0.0
    if "icmp" in methods:
        score = max(score, 0.75)
    if "arp" in methods or "ndp" in methods:
        score = max(score, 0.7)
    if "ssdp" in methods:
        score = max(score, 0.7)
    if "icmp" in methods and ("arp" in methods or "ndp" in methods):
        score = 0.95
    if has_mac:
        score += 0.02
    if has_name:
        score += 0.03
    return round(min(score, 0.99), 2)


def _ip_sort(ip: str) -> tuple:
    return tuple(int(x) for x in ip.split(".")) if re.fullmatch(r"[\d.]+", ip or "") else (999,)


def _loads(text: str | None, default):
    try:
        return json.loads(text) if text else default
    except ValueError:
        return default


def _row(r) -> Device:
    keys = r.keys()

    def col(name, default):
        return r[name] if name in keys and r[name] is not None else default

    return Device(r["key"], r["ip"], r["mac"], r["hostname"], r["vendor"], r["kind"],
                  "absent" if r["status"] == "offline" else r["status"], r["first_seen"], r["last_seen"],
                  r["latency_ms"], col("alias", ""), col("notes", ""), bool(col("trusted", 0)),
                  _loads(col("ipv6", "[]"), []), col("interface", ""), col("segment", ""),
                  _loads(col("methods", "[]"), []), float(col("confidence", 0.0)), int(col("missed_scans", 0)),
                  col("vendor_source", ""), _loads(col("extra", "{}"), {}), _loads(col("last_check", "{}"), {}))


class InventoryError(ValueError):
    pass


class NetworkInventory:
    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------ varreduras
    def merge_scan(self, scan: dict[str, Any], *, gateway: str = "", own_ip: str = "") -> dict[str, list[Device]]:
        """Funde uma descoberta. Devolve dispositivos novos, presentes, não vistos (desconhecidos) e ausentes.

        Leitura passiva (``scan["passive"]``) só confirma presença: nunca conta como "não visto".
        """
        now = time.time()
        segment = str(scan.get("network") or "")
        interface = str(scan.get("interface") or "")
        passive = bool(scan.get("passive"))
        methods_ok = bool(scan.get("methods_ok", True))
        known = {d.key: d for d in self.devices()}
        seen_keys: set[str] = set()
        new, online = [], []
        vendor_source = oui.source()
        for host in scan.get("hosts", []):
            ip, mac = host["ip"], host.get("mac") or ""
            key = mac or f"ip:{ip}"
            previous = known.get(key)
            if not mac:
                legacy = next((d for d in known.values() if d.ip == ip and d.mac), None)   # já conhecido por MAC
                if legacy is not None:
                    key, mac, previous = legacy.key, legacy.mac, legacy
            elif f"ip:{ip}" in known and previous is None:
                previous = known.pop(f"ip:{ip}")                    # agora com MAC: migra apelido/notas
                self.db.execute("DELETE FROM network_devices WHERE key=?", (previous.key,))
            seen_keys.add(key)
            methods = set(host.get("methods") or ())
            extra = {**(previous.extra if previous else {}), **(host.get("extra") or {})}
            if gateway:
                extra["gateway"] = ip == gateway                     # o gateway informado pelo sistema
            vendor, source = "", ""
            if mac:
                vendor = oui.vendor(mac)
                source = "local_admin" if oui.is_locally_administered(mac) else (vendor_source if vendor else "")
            if not vendor and extra.get("manufacturer"):
                vendor, source = extra["manufacturer"], "ssdp"
            hostname = host.get("hostname") or (previous.hostname if previous else "")
            hint = " ".join(str(extra.get(k, "")) for k in ("friendly_name", "model", "device_type", "model_description"))
            kind = infer_kind(ip, mac, hostname, vendor, gateway=gateway, own_ip=own_ip, hint=hint)
            observed = bool(host.get("alive")) or bool(methods & {"arp", "ndp", "self", "ssdp"})
            status = "online" if observed else "unknown"
            ipv6 = list(dict.fromkeys(list(host.get("ipv6") or ()) + (previous.ipv6 if previous else [])))[:8]
            device = Device(key, ip, mac, hostname, vendor, kind, status,
                            previous.first_seen if previous else now, now if observed else
                            (previous.last_seen if previous else now), host.get("latency_ms"),
                            previous.alias if previous else "", previous.notes if previous else "",
                            previous.trusted if previous else kind == "this_computer", ipv6,
                            interface or (previous.interface if previous else ""),
                            segment or (previous.segment if previous else ""), sorted(methods),
                            confidence_of(methods, has_mac=bool(mac), has_name=bool(hostname)), 0, source, extra,
                            previous.last_check if previous else {})
            self._save(device)
            online.append(device)
            if previous is None:
                new.append(device)
        unknown, absent = [], []
        if not passive:
            for key, device in known.items():
                if key in seen_keys:
                    continue
                if device.segment and segment and device.segment != segment:
                    status, missed = "unknown", device.missed_scans       # outra rede: não observável daqui
                else:
                    missed = device.missed_scans + 1
                    status = "absent" if (missed >= ABSENT_AFTER and methods_ok) else "unknown"
                if status != device.status or missed != device.missed_scans:
                    self.db.execute("UPDATE network_devices SET status=?, missed_scans=? WHERE key=?",
                                    (status, missed, key))
                    device.status, device.missed_scans = status, missed
                (absent if status == "absent" else unknown).append(device)
        return {"new": new, "online": online, "unknown": unknown, "absent": absent, "offline": absent}

    def _save(self, d: Device) -> None:
        self.db.execute(
            "INSERT INTO network_devices(key,ip,mac,hostname,vendor,kind,status,first_seen,last_seen,latency_ms,"
            "alias,notes,trusted,ipv6,interface,segment,methods,confidence,missed_scans,vendor_source,extra,last_check) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET ip=excluded.ip, "
            "mac=excluded.mac, hostname=excluded.hostname, vendor=excluded.vendor, kind=excluded.kind, "
            "status=excluded.status, last_seen=excluded.last_seen, latency_ms=excluded.latency_ms, "
            "ipv6=excluded.ipv6, interface=excluded.interface, segment=excluded.segment, methods=excluded.methods, "
            "confidence=excluded.confidence, missed_scans=excluded.missed_scans, "
            "vendor_source=excluded.vendor_source, extra=excluded.extra",
            (d.key, d.ip, d.mac, d.hostname, d.vendor, d.kind, d.status, d.first_seen, d.last_seen, d.latency_ms,
             d.alias, d.notes, int(d.trusted), json.dumps(d.ipv6), d.interface, d.segment, json.dumps(d.methods),
             d.confidence, d.missed_scans, d.vendor_source, json.dumps(d.extra, ensure_ascii=False),
             json.dumps(d.last_check, ensure_ascii=False)))

    # ------------------------------------------------------------ leitura
    def devices(self, *, status: str | None = None, trusted: bool | None = None, text: str = "") -> list[Device]:
        status = {"offline": "absent", "present": "online"}.get(status or "", status)
        where, params = [], []
        if status:
            where.append("status=?" if status != "absent" else "status IN ('absent','offline')")
            if status != "absent":
                params.append(status)
        if trusted is not None:
            where.append("trusted=?")
            params.append(int(trusted))
        sql = "SELECT * FROM network_devices" + (" WHERE " + " AND ".join(where) if where else "")
        devices = [_row(r) for r in self.db.query(sql, params)]
        if text:
            needle = text.casefold()
            devices = [d for d in devices if needle in " ".join(
                (d.ip, d.mac, d.hostname, d.vendor, d.alias, d.notes, d.kind, " ".join(d.ipv6),
                 str(d.extra.get("friendly_name", "")))).casefold()]
        devices.sort(key=lambda d: _ip_sort(d.ip))
        return devices

    def count(self, status: str | None = "online") -> int:
        status = {"offline": "absent", "present": "online"}.get(status or "", status)
        if status:
            row = self.db.one("SELECT COUNT(*) FROM network_devices WHERE status=?", (status,))
        else:
            row = self.db.one("SELECT COUNT(*) FROM network_devices")
        return int(row[0]) if row else 0

    def counts(self) -> dict[str, int]:
        out = {"online": 0, "absent": 0, "unknown": 0, "total": 0, "trusted": 0, "untrusted_online": 0}
        for row in self.db.query("SELECT status, trusted, COUNT(*) AS n FROM network_devices GROUP BY status, trusted"):
            status = "absent" if row["status"] == "offline" else row["status"]
            out[status] = out.get(status, 0) + row["n"]
            out["total"] += row["n"]
            if row["trusted"]:
                out["trusted"] += row["n"]
            elif status == "online":
                out["untrusted_online"] += row["n"]
        return out

    def get(self, key: str) -> Device | None:
        row = self.db.one("SELECT * FROM network_devices WHERE key=?", (key,))
        return _row(row) if row else None

    def find(self, ref: str) -> Device:
        """Por chave, IP, MAC, apelido ou nome. Ambíguo → InventoryError com as opções."""
        ref = " ".join(str(ref or "").split())
        if not ref:
            raise InventoryError("diga qual dispositivo (IP, MAC, nome ou apelido)")
        exact = self.get(ref)
        if exact is not None:
            return exact
        needle = ref.casefold()
        devices = self.devices()
        for attr in ("ip", "mac", "alias", "hostname"):
            hits = [d for d in devices if str(getattr(d, attr) or "").casefold() == needle]
            if len(hits) == 1:
                return hits[0]
        hits = [d for d in devices if needle in f"{d.alias} {d.hostname} {d.extra.get('friendly_name', '')}".casefold()]
        if len(hits) == 1:
            return hits[0]
        if not hits:
            raise InventoryError(f"nenhum dispositivo do inventário corresponde a \"{ref}\"")
        raise InventoryError("mais de um dispositivo corresponde: " + "; ".join(d.label() for d in hits[:5]))

    # ------------------------------------------------------------ edição pelo usuário
    def update(self, key: str, *, alias: str | None = None, notes: str | None = None,
               trusted: bool | None = None) -> Device:
        device = self.get(key)
        if device is None:
            raise InventoryError("dispositivo não encontrado")
        if alias is not None:
            alias = " ".join(alias.split())[:60]
            if looks_secret(alias):
                raise InventoryError("o apelido parece conter dado sensível")
            device.alias = alias
        if notes is not None:
            notes = notes.strip()[:1000]
            if looks_secret(notes):
                raise InventoryError("as notas parecem conter senha, token ou dado sensível; não foram salvas")
            device.notes = notes
        if trusted is not None:
            device.trusted = bool(trusted)
        self.db.execute("UPDATE network_devices SET alias=?, notes=?, trusted=? WHERE key=?",
                        (device.alias, device.notes, int(device.trusted), key))
        return device

    def record_check(self, key: str, result: dict[str, Any]) -> None:
        self.db.execute("UPDATE network_devices SET last_check=? WHERE key=?",
                        (json.dumps(result, ensure_ascii=False, default=str), key))

    def forget(self, key: str) -> bool:
        return self.db.execute("DELETE FROM network_devices WHERE key=?", (key,)).rowcount > 0

    # ------------------------------------------------------------ relatório
    EXPORT_FIELDS = ("name", "alias", "ip", "ipv6", "mac", "vendor", "vendor_source", "hostname", "kind_label",
                     "state_label", "observation_label", "is_gateway", "confidence", "method_labels", "trusted",
                     "interface", "segment", "first_seen", "last_seen", "administration", "notes")

    def export(self, fmt: str = "md", *, meta: dict | None = None) -> str:
        devices = [d.to_dict() for d in self.devices()]
        meta = dict(meta or {})
        stamp = time.strftime("%Y-%m-%d %H:%M", time.localtime())

        def when(ts):
            return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else ""

        if fmt == "json":
            return json.dumps({"generated": stamp, **meta, "devices": devices}, ensure_ascii=False, indent=2,
                              default=str)
        rows = []
        for d in devices:
            rows.append({k: (", ".join(d[k]) if isinstance(d.get(k), list) else
                             when(d[k]) if k in ("first_seen", "last_seen") else
                             ("sim" if d[k] else "não") if k in ("trusted", "is_gateway") else d.get(k, ""))
                         for k in self.EXPORT_FIELDS})
        if fmt == "csv":
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=list(self.EXPORT_FIELDS))
            writer.writeheader()
            writer.writerows(rows)
            return buffer.getvalue()
        lines = [f"# Inventário da rede local — {stamp}", ""]
        for key, value in meta.items():
            lines.append(f"- **{key}**: {value}")
        lines += ["", "> Estados são observações: *presente* = visto na última varredura; *desconhecido* = não visto "
                      "uma vez ou visto em outra rede; *ausente* = não visto em varreduras seguidas. A presença de um "
                      "aparelho não identifica quem o usa. O inventário pode estar incompleto.", "",
                  "> **Descobrir não é administrar.** Estar nesta lista não dá ao JARVIS nem a ninguém permissão para "
                  "acessar ou controlar um aparelho; o JARVIS não acessa, não controla e não altera dispositivos de "
                  "terceiros.", "",
                  "| Nome | IP | MAC | Fabricante | Tipo | Observação | Gateway | Confiança | Origem | Primeira vez "
                  "| Última vez |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            cells = [r["name"], r["ip"] + (f" / {r['ipv6']}" if r["ipv6"] else ""), r["mac"] or "desconhecido",
                     r["vendor"] or "desconhecido", r["kind_label"], r["observation_label"], r["is_gateway"],
                     f"{float(r['confidence']):.0%}", r["method_labels"] or "desconhecida", r["first_seen"],
                     r["last_seen"]]
            lines.append("| " + " | ".join(str(c).replace("|", "/") for c in cells) + " |")
        return "\n".join(lines) + "\n"
