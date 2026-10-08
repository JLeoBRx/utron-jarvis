"""Identificação de fabricante pelo prefixo MAC (OUI) — "vendor quando disponível".

Fontes, em ordem:

1. base IEEE completa em cache (``oui.csv`` na pasta de dados), obtida sob pedido explícito
   do usuário (``update_database``) e somente se a política de privacidade permitir;
2. arquivos de fabricantes já instalados por outras ferramentas (Wireshark ``manuf``,
   nmap ``nmap-mac-prefixes``);
3. uma tabela embutida pequena com prefixos de alta confiança.

Sem fonte, o fabricante fica vazio — nunca é adivinhado. MACs administrados localmente
(aleatórios, comuns em celulares) são identificados como tal.
"""
from __future__ import annotations

import csv
import io
import logging
import os
import threading
import urllib.request
from pathlib import Path

from ..config import paths

log = logging.getLogger("ultron.oui")

IEEE_URL = "https://standards-oui.ieee.org/oui/oui.csv"

BUILTIN = {
    "00:05:69": "VMware", "00:0C:29": "VMware", "00:1C:14": "VMware", "00:50:56": "VMware",
    "08:00:27": "Oracle VirtualBox", "00:15:5D": "Microsoft Hyper-V", "00:1C:42": "Parallels",
    "00:16:3E": "Xen", "52:54:00": "QEMU/KVM",
    "B8:27:EB": "Raspberry Pi", "DC:A6:32": "Raspberry Pi", "E4:5F:01": "Raspberry Pi",
    "D8:3A:DD": "Raspberry Pi",
}

_SYSTEM_FILES = (
    "/usr/share/wireshark/manuf", "/usr/share/wireshark/manuf.txt",
    "/usr/share/nmap/nmap-mac-prefixes", "/usr/local/share/nmap/nmap-mac-prefixes",
    r"C:\Program Files\Wireshark\manuf", r"C:\Program Files\Wireshark\manuf.txt",
    r"C:\Program Files (x86)\Nmap\nmap-mac-prefixes", r"C:\Program Files\Nmap\nmap-mac-prefixes",
)

_table: dict[str, str] | None = None
_source = "builtin"
_lock = threading.Lock()


def _cache_path() -> Path:
    return paths.data_file("oui.csv")


def _parse_ieee_csv(text: str) -> dict[str, str]:
    table = {}
    for row in csv.DictReader(io.StringIO(text)):
        assignment = (row.get("Assignment") or "").strip().upper()
        name = (row.get("Organization Name") or "").strip()
        if len(assignment) == 6 and name:
            table[":".join(assignment[i:i + 2] for i in (0, 2, 4))] = name
    return table


def _parse_system_file(text: str) -> dict[str, str]:
    table = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.replace("\t", " ").split(None, 1)
        if len(parts) != 2:
            continue
        prefix = parts[0].replace("-", ":").upper()
        digits = prefix.replace(":", "")
        if len(digits) == 6 and all(c in "0123456789ABCDEF" for c in digits):
            table[":".join(digits[i:i + 2] for i in (0, 2, 4))] = parts[1].strip().split("  ")[0]
    return table


def _load() -> dict[str, str]:
    global _table, _source
    with _lock:
        if _table is not None:
            return _table
        table = dict(BUILTIN)
        source = "builtin"
        for candidate in _SYSTEM_FILES:
            if os.path.isfile(candidate):
                try:
                    table.update(_parse_system_file(Path(candidate).read_text(encoding="utf-8", errors="replace")))
                    source = candidate
                    break
                except OSError:
                    continue
        cache = _cache_path()
        if cache.is_file():
            try:
                table.update(_parse_ieee_csv(cache.read_text(encoding="utf-8", errors="replace")))
                source = "ieee"
            except OSError:
                pass
        _table, _source = table, source
        return table


def is_locally_administered(mac: str) -> bool:
    try:
        return bool(int(mac.split(":")[0], 16) & 0x02)
    except (ValueError, IndexError):
        return False


def vendor(mac: str) -> str:
    mac = (mac or "").upper()
    if len(mac) < 8:
        return ""
    if is_locally_administered(mac) and mac[:8] not in BUILTIN:
        return "MAC aleatório (privacidade)"
    return _load().get(mac[:8], "")


def source() -> str:
    _load()
    return _source


def update_database(*, allowed: bool, timeout: float = 30.0) -> int:
    """Baixa a base oficial do IEEE (conexão externa — exige permissão explícita)."""
    global _table
    if not allowed:
        raise PermissionError("conexão externa bloqueada pela política de privacidade")
    with urllib.request.urlopen(IEEE_URL, timeout=timeout) as response:
        text = response.read().decode("utf-8", "replace")
    table = _parse_ieee_csv(text)
    if len(table) < 1000:
        raise ValueError("base do IEEE recebida está incompleta")
    tmp = _cache_path().with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, _cache_path())
    with _lock:
        _table = None
    return len(table)
