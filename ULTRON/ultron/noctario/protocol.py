"""NOCT/1 — o protocolo de linha entre o JARVIS (PC) e o Noctário (ESP32), sobre Bluetooth SPP.

Linhas de texto ASCII terminadas em ``\\n`` (``\\r\\n`` aceito), até 240 bytes; campos ``chave=valor``
separados por espaço (valores sem espaço — o firmware troca espaço por ``_`` nas mensagens).

PC → robô:

* ``!`` — um byte, em QUALQUER ponto do fluxo: PARADA DE EMERGÊNCIA. O firmware corta os motores antes
  de analisar qualquer linha e descarta a linha parcial;
* ``HB`` — batimento (sem resposta): mantém satisfeito o cão de guarda do link no robô;
* ``CMD <seq> <VERBO> [chave=valor ...]`` — comando com número de sequência (1..65535).

Robô → PC: ``HELLO`` (ao conectar), ``ACK <seq> ...``, ``NAK <seq> code=... msg=...``, ``STA ...``
(estado completo), ``TEL ...`` (telemetria periódica), ``EVT <tipo> ...`` (eventos), ``PAR ...``
(parâmetros) e ``SEN ...`` (leitura avulsa dos sensores).

Os limites dos parâmetros são validados nos DOIS lados: aqui, antes de enviar, e no firmware, que
responde ``NAK code=RANGE`` se algo escapar. A especificação completa está em
``firmware/noctario/PROTOCOLO_NOCT1.md``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PROTO = 1
MAX_LINE = 240
ESTOP_BYTE = b"!"
HEARTBEAT = b"HB\n"
SEQ_MAX = 65535
VERBS = ("PING", "INFO", "STATUS", "START", "STOP", "CLEAR", "CAL", "SET", "PARAMS", "SAVE", "DEFAULTS", "RESETX",
         "TEL", "SENS", "MOTOR")
KINDS = ("HELLO", "ACK", "NAK", "STA", "TEL", "EVT", "PAR", "SEN")
STATES = {
    "BOOT": "iniciando", "IDLE": "parado — sem calibração", "CAL": "calibrando", "READY": "pronto",
    "RUN": "em percurso", "LOST": "linha perdida — recuperando", "STOPPING": "parando", "STOP": "parado",
    "DONE": "percurso concluído", "ESTOP": "PARADA DE EMERGÊNCIA", "FAULT": "falha", "TEST": "teste de bancada",
}
MOVING = frozenset({"RUN", "LOST", "STOPPING", "TEST", "CAL"})       # CAL só se move com auto=1 (no firmware)
EVENTS = {"cross": "cruzamento", "lost": "linha perdida", "found": "linha reencontrada", "done": "percurso concluído",
          "stop": "parada", "estop": "parada de emergência", "fault": "falha", "cal": "calibração",
          "link": "link"}
STOP_REASONS = {"cmd": "pedido de parada", "link": "link perdido (política do firmware)", "lost": "linha perdida",
                "done": "destino alcançado", "estop": "parada de emergência", "fault": "falha"}
NAK_CODES = {"RANGE": "valor fora do limite", "STATE": "não permitido neste estado", "SYNTAX": "comando malformado",
             "UNKNOWN": "verbo desconhecido", "NOCAL": "sensores não calibrados", "ESTOP": "em parada de emergência",
             "BUSY": "robô ocupado"}


class ProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    kind: str                 # "float" | "int" | "choice"
    default: Any
    low: float = 0.0
    high: float = 0.0
    unit: str = ""
    choices: tuple = ()
    help: str = ""

    def coerce(self, value: Any) -> Any:
        """Valor tipado e dentro do limite, ou ``ProtocolError`` com o motivo em português."""
        if self.kind == "choice":
            text = str(value).strip().lower()
            if text not in self.choices:
                raise ProtocolError(f"{self.label}: use {' ou '.join(self.choices)}")
            return text
        try:
            number = float(str(value).replace(",", "."))
        except ValueError as exc:
            raise ProtocolError(f"{self.label}: '{value}' não é um número") from exc
        if number != number or number in (float("inf"), float("-inf")):
            raise ProtocolError(f"{self.label}: valor inválido")
        if self.kind == "int":
            if number != int(number):
                raise ProtocolError(f"{self.label}: use um número inteiro")
            number = int(number)
        if not self.low <= number <= self.high:
            raise ProtocolError(f"{self.label}: {fmt(number)} fora do limite ({fmt(self.low)} a {fmt(self.high)}"
                                f"{' ' + self.unit if self.unit else ''})")
        if self.choices and number not in self.choices:
            raise ProtocolError(f"{self.label}: use {' ou '.join(fmt(c) for c in self.choices)}")
        return number


# Perfil inicial de 4 cruzamentos do JARVIS. O sketch original confirma o sensor em LOW e o laço a 100 Hz.
# A variante posterior Nefarious_6 usa seis cruzamentos e ganhos adaptativos diferentes.
PARAMS: dict[str, ParamSpec] = {p.key: p for p in (
    ParamSpec("kp", "Kp", "float", 0.0125, 0.0, 0.2, help="ganho proporcional do PD"),
    ParamSpec("kd", "Kd", "float", 0.1, 0.0, 2.0, help="ganho derivativo do PD (por ciclo do laço de controle)"),
    ParamSpec("base", "PWM base", "int", 220, 0, 255, help="velocidade nas retas"),
    ParamSpec("max", "PWM máximo", "int", 220, 0, 255, help="teto de cada motor"),
    ParamSpec("minpwm", "PWM mínimo", "int", 0, -255, 255, help="piso de cada motor (negativo permite ré nas curvas)"),
    ParamSpec("accel", "Rampa de aceleração", "int", 600, 0, 5000, "PWM/s", help="0 = sem rampa"),
    ParamSpec("decel", "Rampa de frenagem", "int", 900, 0, 5000, "PWM/s", help="0 = sem rampa"),
    ParamSpec("adapt", "Velocidade adaptativa", "float", 0.35, 0.0, 1.0,
              help="quanto a velocidade base cai com o erro (0 = desligada)"),
    ParamSpec("cross", "Cruzamentos até o destino", "int", 4, 0, 20, help="0 = sem destino (só para pelo comando)"),
    ParamSpec("deb", "Filtro do cruzamento", "int", 150, 20, 2000, "ms", help="intervalo mínimo entre contagens"),
    ParamSpec("xact", "Nível ativo do sensor de cruzamento", "int", 0, 0, 1, choices=(0, 1),
              help="0 = nível baixo; borda de descida no sketch original"),
    ParamSpec("thr", "Limiar de linha", "int", 200, 0, 1000, help="valor calibrado mínimo para considerar a linha vista"),
    ParamSpec("lostms", "Tempo até recuperar", "int", 300, 50, 3000, "ms", help="sem linha por este tempo → recuperação"),
    ParamSpec("loststop", "Tempo máximo de recuperação", "int", 1500, 100, 10000, "ms",
              help="recuperação sem sucesso → parada"),
    ParamSpec("recov", "PWM de recuperação", "int", 120, 0, 255, help="giro em direção ao último lado visto"),
    ParamSpec("hb", "Cão de guarda do link", "int", 1500, 0, 10000, "ms", help="0 = desligado"),
    ParamSpec("onlink", "Ao perder o link", "choice", "stop", choices=("stop", "continue"),
              help="política do firmware: parar (stop) ou terminar o percurso (continue)"),
    ParamSpec("tel", "Telemetria", "int", 20, 0, 50, "Hz", help="0 = desligada"),
    ParamSpec("loop", "Laço de controle", "int", 100, 100, 2000, "Hz", help="100 Hz = 10 ms, confirmado no sketch original"),
    ParamSpec("white", "Linha branca em pista preta", "int", 1, 0, 1, choices=(0, 1)),
    ParamSpec("flip", "Inverter a ordem dos sensores", "int", 0, 0, 1, choices=(0, 1),
              help="a confirmar no código original (esquerda → direita)"),
    ParamSpec("ldir", "Sentido do motor esquerdo", "int", 1, -1, 1, choices=(-1, 1), help="a confirmar na bancada"),
    ParamSpec("rdir", "Sentido do motor direito", "int", 1, -1, 1, choices=(-1, 1), help="a confirmar na bancada"),
)}
DEFAULTS = {k: p.default for k, p in PARAMS.items()}
TUNING = ("kp", "kd", "base", "max", "minpwm", "accel", "decel", "adapt")


def fmt(value: Any) -> str:
    if isinstance(value, float):
        return format(value, "g")
    return str(value)


def validate(values: dict, current: dict | None = None) -> dict:
    """Valores tipados e dentro dos limites, mais as regras entre parâmetros (base ≤ máximo, mínimo ≤ base).
    Levanta ``ProtocolError`` com TODOS os problemas encontrados."""
    clean: dict[str, Any] = {}
    errors: list[str] = []
    for key, value in values.items():
        spec = PARAMS.get(str(key))
        if spec is None:
            errors.append(f"parâmetro desconhecido: {key}")
            continue
        try:
            clean[spec.key] = spec.coerce(value)
        except ProtocolError as exc:
            errors.append(str(exc))
    merged = {**DEFAULTS, **(current or {}), **clean}
    if not errors:
        if merged["base"] > merged["max"]:
            errors.append(f"PWM base ({merged['base']}) maior que o PWM máximo ({merged['max']})")
        if merged["minpwm"] > merged["base"]:
            errors.append(f"PWM mínimo ({merged['minpwm']}) maior que o PWM base ({merged['base']})")
    if errors:
        raise ProtocolError("; ".join(errors))
    return clean


def _token(value: Any) -> str:
    text = fmt(value)
    if any(c.isspace() for c in text) or "=" in text or "!" in text or not text.isprintable():
        raise ProtocolError(f"valor com caractere proibido: {text!r}")
    return text


def encode(seq: int, verb: str, args: dict | None = None) -> bytes:
    if not 1 <= int(seq) <= SEQ_MAX:
        raise ProtocolError(f"sequência fora do intervalo: {seq}")
    verb = str(verb).upper()
    if verb not in VERBS:
        raise ProtocolError(f"verbo desconhecido: {verb}")
    parts = [f"CMD {int(seq)} {verb}"]
    for key, value in (args or {}).items():
        if not str(key).isidentifier():
            raise ProtocolError(f"chave inválida: {key!r}")
        parts.append(f"{key}={_token(value)}")
    line = " ".join(parts) + "\n"
    if len(line) > MAX_LINE:
        raise ProtocolError("comando longo demais")
    return line.encode("ascii")


@dataclass
class Message:
    kind: str
    seq: int | None = None
    event: str = ""
    fields: dict = field(default_factory=dict)
    raw: str = ""

    def text(self, key: str, default: str = "") -> str:
        value = self.fields.get(key)
        return value.replace("_", " ") if isinstance(value, str) else default

    def num(self, key: str, default: float | None = None) -> float | None:
        try:
            return float(self.fields[key])
        except (KeyError, ValueError):
            return default

    def int(self, key: str, default: int | None = None) -> int | None:
        value = self.num(key)
        return int(value) if value is not None else default

    def ints(self, key: str) -> list[int]:
        raw = self.fields.get(key, "")
        try:
            return [int(float(v)) for v in raw.split(",") if v != ""]
        except ValueError:
            return []


def parse(line: str | bytes | bytearray) -> Message:
    """Uma linha do robô → ``Message``. Lixo vira ``kind="UNKNOWN"`` (nunca exceção)."""
    if isinstance(line, (bytes, bytearray, memoryview)):
        line = bytes(line).decode("ascii", errors="replace")
    text = line.strip()[:MAX_LINE]
    tokens = text.split()
    if not tokens:
        return Message("UNKNOWN", raw=text)
    kind = tokens[0].upper()
    if kind not in KINDS:
        return Message("UNKNOWN", raw=text)
    rest = tokens[1:]
    message = Message(kind, raw=text)
    if kind in ("ACK", "NAK"):
        if not rest or not (rest[0].isascii() and rest[0].isdigit()):
            return Message("UNKNOWN", raw=text)
        message.seq = int(rest[0])
        rest = rest[1:]
    elif kind == "EVT":
        if not rest or "=" in rest[0]:
            return Message("UNKNOWN", raw=text)
        message.event = rest[0].lower()
        rest = rest[1:]
    for token in rest:
        key, sep, value = token.partition("=")
        if key:
            message.fields[key] = value if sep else "1"
    return message


def state_label(state: str | None) -> str:
    return STATES.get(str(state or "").upper(), "desconhecido" if not state else str(state))
