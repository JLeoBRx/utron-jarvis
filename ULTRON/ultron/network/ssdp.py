"""SSDP/UPnP — aparelhos que SE ANUNCIAM na rede local (opcional; desligado por padrão).

Uso legítimo e limitado:

* uma única busca ``M-SEARCH`` multicast com TTL 1 (o pacote não sai do segmento local);
* só respostas vindas de endereços DENTRO da sub-rede privada autorizada são aceitas;
* a descrição do aparelho é lida apenas da URL que o próprio aparelho anunciou, se ela apontar
  para o mesmo IP privado; sem redirecionamentos, sem proxy, com limite de tamanho e de tempo;
* XML com ``DOCTYPE``/``ENTITY`` é recusado (sem expansão de entidades).

Nada é enviado além da busca padrão; nenhuma porta é varrida e nada é alterado nos aparelhos.
"""
from __future__ import annotations

import ipaddress
import socket
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

MULTICAST = ("239.255.255.250", 1900)
MAX_RESPONSES = 64
MAX_DESCRIPTIONS = 32
MAX_XML_BYTES = 64 * 1024
SEARCH = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 1\r\n"
          "ST: ssdp:all\r\nUSER-AGENT: JARVIS/1 UPnP/1.1\r\n\r\n").encode("ascii")
FIELDS = {"friendlyName": "friendly_name", "manufacturer": "manufacturer", "modelName": "model",
          "modelDescription": "model_description", "deviceType": "device_type"}


def parse_response(data: bytes) -> dict[str, str]:
    headers = {}
    for line in data.decode("utf-8", "replace").split("\r\n")[1:]:
        key, sep, value = line.partition(":")
        if sep:
            headers[key.strip().lower()] = value.strip()[:300]
    return headers


def safe_location(location: str, ip: str, network: ipaddress.IPv4Network) -> str | None:
    """A URL anunciada só é lida se for http no MESMO IP privado que respondeu."""
    try:
        url = urllib.parse.urlsplit(location)
        host = ipaddress.ip_address(url.hostname or "")
        port = url.port
    except ValueError:
        return None
    if url.scheme != "http" or str(host) != ip or host not in network or not host.is_private:
        return None
    if port is not None and not 1 <= port <= 65535:
        return None
    return urllib.parse.urlunsplit(("http", url.netloc, url.path or "/", url.query, ""))


def parse_description(data: bytes) -> dict[str, str]:
    if len(data) > MAX_XML_BYTES or b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        return {}
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return {}
    out: dict[str, str] = {}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in FIELDS and FIELDS[tag] not in out and (element.text or "").strip():
            out[FIELDS[tag]] = " ".join(element.text.split())[:120]
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):          # nunca seguir para outro lugar
        return None


_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)


def fetch_description(url: str, *, timeout: float = 1.5) -> dict[str, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "JARVIS/1"})
    with _OPENER.open(request, timeout=timeout) as response:
        data = response.read(MAX_XML_BYTES + 1)
    return parse_description(data)


def search(network: ipaddress.IPv4Network, *, timeout: float = 2.0, describe: bool = True) -> dict[str, dict]:
    """{ip: {"friendly_name", "manufacturer", "model", "server", ...}} dos aparelhos que responderam."""
    found: dict[str, dict] = {}
    locations: dict[str, str] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.settimeout(0.3)
        sock.sendto(SEARCH, MULTICAST)
        deadline = time.monotonic() + timeout
        responses = 0
        while time.monotonic() < deadline and responses < MAX_RESPONSES:
            try:
                data, (ip, _port) = sock.recvfrom(4096)
            except socket.timeout:
                continue
            responses += 1
            try:
                if ipaddress.ip_address(ip) not in network:
                    continue
            except ValueError:
                continue
            headers = parse_response(data)
            entry = found.setdefault(ip, {})
            if headers.get("server") and "server" not in entry:
                entry["server"] = headers["server"][:120]
            url = safe_location(headers.get("location", ""), ip, network)
            if url and ip not in locations:
                locations[ip] = url
    finally:
        sock.close()
    if describe and locations:
        with ThreadPoolExecutor(max_workers=8, thread_name_prefix="ultron-ssdp") as pool:
            futures = {pool.submit(fetch_description, url): ip for ip, url in list(locations.items())[:MAX_DESCRIPTIONS]}
            try:
                for future in as_completed(futures, timeout=6.0):
                    try:
                        found[futures[future]].update(future.result())
                    except Exception:
                        continue
            except TimeoutError:
                pass
            finally:
                for future in futures:
                    future.cancel()
    return found
