"""Transportes do NOCT/1: porta COM (Bluetooth SPP pareado no Windows), RFCOMM direto e o SIMULADOR.

Só conecta ao dispositivo que o USUÁRIO configurou (porta ou endereço pareado). Não há busca de
dispositivos nem varredura: encontrar um robô por perto não é autorização para controlá-lo.

Cada transporte entrega bytes crus; o serviço monta as linhas. Falhas viram ``TransportError`` com o
motivo em português (porta ocupada, robô desligado, biblioteca ausente...).
"""
from __future__ import annotations

import re
import socket
import threading
import time

ADDRESS_RE = re.compile(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}")


class TransportError(OSError):
    pass


class Transport:
    kind = "base"
    simulated = False

    @property
    def label(self) -> str:
        return self.kind

    def open(self, timeout: float = 5.0) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def write(self, data: bytes) -> None:
        raise NotImplementedError

    def read(self, timeout: float) -> bytes:
        """Bytes disponíveis (``b""`` se nada chegou no prazo). Link caído → ``TransportError``."""
        raise NotImplementedError


class SerialTransport(Transport):
    """Porta COM criada pelo Windows para o Noctário pareado (Bluetooth SPP). Requer o pyserial."""

    kind = "serial"

    def __init__(self, port: str, baudrate: int = 115200):
        self.port = str(port or "").strip()
        self.baudrate = baudrate
        self._serial = None
        self._write_lock = threading.Lock()

    @property
    def label(self) -> str:
        return f"porta {self.port}"

    def open(self, timeout: float = 5.0) -> None:
        if not self.port:
            raise TransportError("porta COM do Noctário não configurada (CONFIGURAÇÕES > NOCTÁRIO)")
        try:
            import serial
        except ImportError as exc:
            raise TransportError("pyserial não instalado (python -m pip install pyserial)") from exc
        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=0.2, write_timeout=0.3)
        except (serial.SerialException, OSError, ValueError) as exc:
            raise TransportError(f"não foi possível abrir {self.port}: {exc}") from exc

    def close(self) -> None:
        port, self._serial = self._serial, None
        if port is not None:
            try:
                port.close()
            except Exception:
                pass

    def write(self, data: bytes) -> None:
        port = self._serial
        if port is None:
            raise TransportError("porta fechada")
        with self._write_lock:
            try:
                port.write(data)
                port.flush()
            except Exception as exc:
                raise TransportError(f"escrita na porta falhou: {exc}") from exc

    def read(self, timeout: float) -> bytes:
        port = self._serial
        if port is None:
            raise TransportError("porta fechada")
        try:
            port.timeout = timeout
            return port.read(max(1, port.in_waiting))
        except Exception as exc:
            raise TransportError(f"leitura da porta falhou: {exc}") from exc


class RfcommTransport(Transport):
    """Bluetooth Clássico RFCOMM direto ao endereço pareado (sem porta COM)."""

    kind = "rfcomm"

    def __init__(self, address: str, channel: int = 1):
        self.address = str(address or "").strip()
        self.channel = int(channel or 1)
        self._sock: socket.socket | None = None
        self._write_lock = threading.Lock()

    @property
    def label(self) -> str:
        return f"Bluetooth {self.address} canal {self.channel}"

    def open(self, timeout: float = 5.0) -> None:
        if not ADDRESS_RE.fullmatch(self.address):
            raise TransportError("endereço Bluetooth do Noctário não configurado (CONFIGURAÇÕES > NOCTÁRIO)")
        family = getattr(socket, "AF_BLUETOOTH", None)
        proto = getattr(socket, "BTPROTO_RFCOMM", None)
        if family is None or proto is None:
            raise TransportError("este Python não tem Bluetooth RFCOMM; use a porta COM do Bluetooth (serial)")
        try:
            sock = socket.socket(family, socket.SOCK_STREAM, proto)
        except OSError as exc:
            raise TransportError(f"Bluetooth indisponível neste computador ({exc}); use a porta COM do "
                                 f"Bluetooth (serial)") from exc
        sock.settimeout(timeout)
        try:
            sock.connect((self.address.replace("-", ":"), self.channel))
        except OSError as exc:
            sock.close()
            raise TransportError(f"o Noctário não respondeu em {self.address} (desligado, fora de alcance ou "
                                 f"não pareado): {exc}") from exc
        sock.settimeout(0.2)
        self._sock = sock

    def close(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    def write(self, data: bytes) -> None:
        sock = self._sock
        if sock is None:
            raise TransportError("link fechado")
        with self._write_lock:
            try:
                sock.sendall(data)
            except OSError as exc:
                raise TransportError(f"envio falhou: {exc}") from exc

    def read(self, timeout: float) -> bytes:
        sock = self._sock
        if sock is None:
            raise TransportError("link fechado")
        try:
            sock.settimeout(timeout)
            data = sock.recv(512)
        except socket.timeout:
            return b""
        except OSError as exc:
            raise TransportError(f"link perdido: {exc}") from exc
        if not data:
            raise TransportError("o Noctário fechou a conexão")
        return data


class SimulatorTransport(Transport):
    """O SIMULADOR (não é o robô). Sempre rotulado; as voltas gravadas daqui ficam marcadas."""

    kind = "simulator"
    simulated = True

    def __init__(self, simulator=None, *, speed: float = 1.0):
        if simulator is None:
            from .simulator import NoctarioSimulator
            simulator = NoctarioSimulator(speed=speed)
        self.simulator = simulator
        self._open = False
        self._dropped = False
        self._buffer = bytearray()

    @property
    def label(self) -> str:
        return "SIMULADOR (não é o robô)"

    def open(self, timeout: float = 5.0) -> None:
        self._dropped = False
        self._open = True
        self.simulator.attach()

    def close(self) -> None:
        if self._open:
            self._open = False
            self.simulator.detach()

    def drop(self) -> None:
        """Simula a queda do link Bluetooth (para testes): a próxima leitura falha."""
        self._dropped = True
        self.simulator.detach()

    def write(self, data: bytes) -> None:
        if not self._open or self._dropped:
            raise TransportError("link do simulador fechado")
        self.simulator.write(data)

    def read(self, timeout: float) -> bytes:
        end = time.monotonic() + timeout
        while True:
            if self._dropped:
                raise TransportError("link do simulador caiu")
            if not self._open:
                raise TransportError("link do simulador fechado")
            lines = self.simulator.take_output()
            if lines:
                return ("\n".join(lines) + "\n").encode("ascii", errors="replace")
            if time.monotonic() >= end:
                return b""
            time.sleep(0.005)


def from_settings(settings, *, simulator=None) -> Transport:
    kind = getattr(settings, "noctario_transport", "rfcomm")
    if kind == "simulator":
        return SimulatorTransport(simulator)
    if kind == "serial":
        return SerialTransport(getattr(settings, "noctario_port", ""))
    return RfcommTransport(getattr(settings, "noctario_address", ""), getattr(settings, "noctario_channel", 1))
