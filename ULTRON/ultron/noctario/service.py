"""Serviço do Noctário no PC: conexão, comandos, estado SOLICITADO × CONFIRMADO, telemetria, voltas e PARADA.

* Uma thread (``noctario-link``) abre o transporte, lê e despacha as linhas, manda o batimento e, se o link
  cair sem pedido, tenta reconectar com espera crescente. Reconectar nunca dá partida no robô.
* Cada comando leva número de sequência e prazo; o resultado é ACK, NAK (com o código do firmware),
  TIMEOUT ou SEM LINK — e vai para ``noctario_ops`` no banco do JARVIS.
* SOLICITADO é o que o PC pediu; CONFIRMADO é o que o robô reportou (ACK, STA, TEL). A interface mostra os
  dois e "aguardando confirmação"/"sem confirmação do robô" — nunca supõe que o robô obedeceu.
* PARADA DE EMERGÊNCIA: o byte ``!`` vai direto para o transporte, sem fila, sem modelo de linguagem e
  sem esperar nada; é repetido até o robô confirmar ESTOP (ou 1,5 s). Sem link: diz que não há conexão e
  que o botão físico é a parada.
* A interface não roda o PD: o controle é do firmware; aqui só há leitura, pedidos e registro.
* Voltas: do RUN confirmado até DONE/STOP/ESTOP, com as amostras da telemetria; ficam no banco com a
  origem (robô ou SIMULADOR) e alimentam a análise de telemetria da TARDIS.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

from ..core.events import EventType
from . import protocol
from .protocol import DEFAULTS, ESTOP_BYTE, HEARTBEAT, MAX_LINE, STATES, ProtocolError, encode, parse, state_label
from .store import NoctarioStore
from .transport import SimulatorTransport, Transport, TransportError, from_settings

log = logging.getLogger("ultron.noctario")

CONFIRM_WINDOW = 3.0                 # s até "sem confirmação do robô"
ESTOP_REPEAT = 0.1                   # s entre repetições do "!"
ESTOP_WINDOW = 1.5                   # s repetindo até o robô confirmar
HELLO_TIMEOUT = 6.0
SERIES_SECONDS = 60
LINK_STATES = {"desconectado": "desconectado", "conectando": "conectando", "conectado": "conectado",
               "perdido": "link perdido"}
REQUEST_TARGETS = {"START": ("RUN", "em percurso", {"RUN", "LOST"}),
                   "STOP": ("STOP", "parado", {"STOPPING", "STOP", "DONE", "ESTOP"}),
                   "CAL": ("CAL", "calibrando", {"CAL", "READY", "IDLE"}),
                   "CLEAR": ("READY", "pronto", {"READY", "IDLE"}),
                   "MOTOR": ("TEST", "teste de bancada", {"TEST"}),
                   "ESTOP": ("ESTOP", "PARADA DE EMERGÊNCIA", {"ESTOP"})}
RUN_STATES = ("RUN", "LOST", "STOPPING")
RESULTS = {"DONE": "concluida", "ESTOP": "emergencia"}


@dataclass
class CommandResult:
    verb: str
    args: dict
    outcome: str                     # ACK | NAK | TIMEOUT | NO_LINK | INVALID
    seq: int | None = None
    fields: dict = field(default_factory=dict)
    code: str = ""
    message: str = ""
    latency_ms: float | None = None
    confirmed: str = ""

    @property
    def ok(self) -> bool:
        return self.outcome == "ACK"

    def describe(self) -> str:
        if self.outcome == "ACK":
            return f"{self.verb} confirmado pelo robô" + (f" ({state_label(self.confirmed)})" if self.confirmed else "")
        if self.outcome == "NAK":
            return f"o robô recusou {self.verb}: {self.message or protocol.NAK_CODES.get(self.code, self.code)}"
        if self.outcome == "TIMEOUT":
            return f"sem resposta do robô para {self.verb}: estado desconhecido"
        if self.outcome == "NO_LINK":
            return "sem conexão com o Noctário"
        return self.message or f"comando inválido: {self.verb}"


class _Pending:
    def __init__(self, seq: int):
        self.seq = seq
        self.event = threading.Event()
        self.message = None


class NoctarioService:
    name = "noctario"

    def __init__(self, settings_getter: Callable[[], Any], *, bus=None, activity=None, db=None,
                 transport_factory: Callable[[], Transport] | None = None, tardis=None):
        self._settings = settings_getter
        self._bus = bus
        self._activity = activity
        self.store = NoctarioStore(db) if db is not None else None
        self._factory = transport_factory
        self.tardis = tardis
        self._lock = threading.RLock()
        self._transport: Transport | None = None
        self._simulator = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._hello = threading.Event()
        self._pending: dict[int, _Pending] = {}
        self._seq = 0
        self.link = "desconectado"
        self.link_detail = ""
        self.simulated = False
        self.transport_label = ""
        self.fw = ""
        self.connected_at = 0.0
        self.confirmed: dict = {"state": "", "at": 0.0, "source": ""}
        self.requested: dict = {}
        self.sta: dict = {}
        self.params: dict = {}
        self.telemetry: dict = {}
        self.sensors: dict = {}
        self.series: deque = deque(maxlen=SERIES_SECONDS * 50)
        self.alerts: deque = deque(maxlen=50)
        self.last_failure = ""
        self._run: dict | None = None
        self.last_run: dict | None = None

    # ------------------------------------------------------------ ciclo de vida (LifecycleManager)
    def start(self) -> None:
        if getattr(self._settings(), "noctario_autoconnect", False):
            threading.Thread(target=self.connect, kwargs={"origin": "inicialização"}, name="noctario-autoconnect",
                             daemon=True).start()

    def stop(self) -> None:
        self.disconnect(origin="encerramento")

    def health(self) -> dict:
        tag = "SIMULADOR · " if self.simulated else ""
        if self.link == "conectado":
            state = self.confirmed.get("state") or "?"
            return {"status": "OK", "detail": f"{tag}{self.transport_label} · {state_label(state)}"}
        if self.link == "perdido":
            return {"status": "WARN", "detail": f"{tag}link perdido: {self.link_detail}"}
        if self.link == "conectando":
            return {"status": "OK", "detail": f"{tag}conectando a {self.transport_label}"}
        return {"status": "UNAVAILABLE", "detail": "desconectado" + (f" ({self.link_detail})" if self.link_detail else "")}

    # ------------------------------------------------------------ conexão
    @property
    def connected(self) -> bool:
        return self.link == "conectado" and self._transport is not None

    def _make_transport(self) -> Transport:
        if self._factory is not None:
            return self._factory()
        settings = self._settings()
        if getattr(settings, "noctario_transport", "") == "simulator":
            if self._simulator is None:
                self._simulator = SimulatorTransport().simulator
            return SimulatorTransport(self._simulator)
        return from_settings(settings)

    def connect(self, *, origin: str = "user", timeout: float = HELLO_TIMEOUT) -> dict:
        """Abre o link e espera o HELLO do robô. Nunca dá partida nem muda parâmetros de controle (só pede a
        taxa de telemetria das configurações)."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                if self.connected:
                    return {"ok": True, "detail": f"já conectado ({self.transport_label})"}
                return {"ok": False, "detail": "conexão em andamento"}
            transport = self._make_transport()
            self._stopping.clear()
            self._hello.clear()
            self.simulated = bool(transport.simulated)
            self.transport_label = transport.label
            self._set_link("conectando", requested=True)
            self._thread = threading.Thread(target=self._run_link, args=(transport, origin), name="noctario-link",
                                            daemon=True)
            self._thread.start()
        end = time.monotonic() + timeout
        thread = self._thread
        while not self._hello.wait(0.05):
            if time.monotonic() >= end or thread is None or not thread.is_alive():
                break
        if not self._hello.is_set():
            detail = self.link_detail or "o robô não respondeu (HELLO) no prazo"
            self.disconnect(origin=origin, quiet=True)
            self.link_detail = detail
            self._record("Conexão com o Noctário falhou", origin, state="falhou", error=detail)
            return {"ok": False, "detail": detail}
        self._record(f"Noctário conectado ({self.transport_label})", origin, result=f"firmware {self.fw}")
        return {"ok": True, "detail": f"conectado: {self.transport_label} · firmware {self.fw}"}

    def disconnect(self, *, origin: str = "user", quiet: bool = False) -> dict:
        """Fecha o link. O que o robô faz sem link é a política DO FIRMWARE (parâmetro ``onlink``)."""
        thread = self._thread
        self._stopping.set()
        transport = self._transport
        if transport is not None:
            try:
                transport.close()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        was = self.link
        with self._lock:
            self._thread = None
            self._transport = None
        self._fail_pending("NO_LINK")
        if was != "desconectado":
            self._set_link("desconectado", requested=True)
            if not quiet:
                policy = self.params.get("onlink", DEFAULTS["onlink"])
                self._record("Noctário desconectado", origin,
                             result="política do firmware sem link: " + ("parar" if policy == "stop" else "continuar"))
        return {"ok": True, "detail": "desconectado"}

    def _run_link(self, transport: Transport, origin: str) -> None:
        backoff = 1.0
        first = True
        while not self._stopping.is_set():
            try:
                transport.open(timeout=5.0)
            except Exception as exc:                          # o motivo vai para a interface, a thread segue
                self.link_detail = str(exc) if isinstance(exc, TransportError) else f"falha ao abrir o link: {exc}"
                log.info("Noctário: %s", self.link_detail)
                if first or not getattr(self._settings(), "noctario_reconnect", True):
                    self._set_link("desconectado", requested=False)
                    return
                if self._stopping.wait(backoff):
                    return
                backoff = min(30.0, backoff * 2)
                continue
            first = False
            backoff = 1.0
            with self._lock:
                self._transport = transport
            self.connected_at = time.time()
            self._read_loop(transport)
            with self._lock:
                self._transport = None
            try:
                transport.close()
            except Exception:
                pass
            if self._stopping.is_set():
                return
            moving = self.confirmed.get("state") in protocol.MOVING
            policy = self.params.get("onlink", DEFAULTS["onlink"])
            if self._run is not None:                       # amostras com lacuna: a volta fica marcada
                self._run["partial"] = True
            self._set_link("perdido", requested=False)
            self._fail_pending("NO_LINK")
            self._alert("link", "Link com o Noctário perdido" + (
                " durante o movimento — o firmware aplica a política: " + ("parar" if policy == "stop" else "continuar")
                if moving else ""), "alta" if moving else "média")
            if not getattr(self._settings(), "noctario_reconnect", True):
                return
            if self._stopping.wait(1.0):
                return

    def _read_loop(self, transport: Transport) -> None:
        buffer = bytearray()
        next_hb = time.monotonic()
        while not self._stopping.is_set():
            try:
                data = transport.read(0.1)
            except TransportError as exc:
                self.link_detail = str(exc)
                return
            if data:
                buffer.extend(data)
                while b"\n" in buffer:
                    line, _, rest = bytes(buffer).partition(b"\n")
                    buffer = bytearray(rest)
                    if line.strip():
                        try:
                            self._dispatch(parse(line))
                        except Exception:                     # uma linha estranha nunca derruba o link
                            log.exception("Noctário: linha não tratada: %r", line[:120])
                if len(buffer) > MAX_LINE * 2:
                    buffer.clear()
            interval = int(getattr(self._settings(), "noctario_heartbeat_ms", 500) or 0)
            if interval and self.link == "conectado" and time.monotonic() >= next_hb:
                next_hb = time.monotonic() + interval / 1000.0
                try:
                    transport.write(HEARTBEAT)
                except TransportError as exc:
                    self.link_detail = str(exc)
                    return

    # ------------------------------------------------------------ despacho das linhas do robô
    def _dispatch(self, msg) -> None:
        kind = msg.kind
        if kind == "HELLO":
            self.fw = msg.fields.get("fw", "")
            self.params = {}                                  # os do robô chegam no PAR logo a seguir
            self._confirm(msg.fields.get("st", ""), "HELLO")
            if self.link != "conectado":
                self._set_link("conectado", requested=True)
            self._hello.set()
            threading.Thread(target=self._sync_telemetry_rate, name="noctario-tel", daemon=True).start()
        elif kind in ("ACK", "NAK"):
            with self._lock:
                pending = self._pending.pop(msg.seq, None)
            if kind == "ACK":
                self._merge_params(msg.fields)                # o ACK de SET/TEL traz o valor aceito pelo robô
                if msg.fields.get("st"):
                    self._confirm(msg.fields["st"], "ACK")
            if pending is not None:
                pending.message = msg
                pending.event.set()
        elif kind == "STA":
            self.sta = dict(msg.fields)
            self._confirm(msg.fields.get("st", ""), "STA")
        elif kind == "TEL":
            self._telemetry(msg)
        elif kind == "PAR":                                   # pode vir em várias linhas: junta
            self._merge_params(msg.fields)
        elif kind == "SEN":
            self.sensors = {"cal": msg.ints("cal"), "pos": msg.int("pos"), "line": msg.int("line"),
                            "x": msg.int("x"), "xin": msg.int("xin"), "at": time.time()}
        elif kind == "EVT":
            self._event(msg)

    def _merge_params(self, fields: dict) -> None:
        known = {k: v for k, v in fields.items() if k in protocol.PARAMS}
        if not known:
            return
        params = dict(self.params)
        for key, value in known.items():
            try:
                params[key] = protocol.PARAMS[key].coerce(value)
            except ProtocolError:
                params[key] = value
        self.params = params

    def _sync_telemetry_rate(self) -> None:
        """A taxa de telemetria de CONFIGURAÇÕES > NOCTÁRIO vale a cada conexão (só a taxa: nada do controle
        muda, e nada é gravado no robô)."""
        wanted = int(getattr(self._settings(), "noctario_telemetry_hz", 0) or 0)
        end = time.monotonic() + 1.5
        while time.monotonic() < end and "tel" not in self.params and self.connected:
            time.sleep(0.02)
        if wanted and self.connected and "tel" in self.params and self.params["tel"] != wanted:
            self.command("TEL", {"hz": wanted}, origin="configuração")

    def _telemetry(self, msg) -> None:
        t = msg.int("t", 0)
        sample = {"t": t, "st": msg.fields.get("st", ""), "pos": msg.int("pos"), "err": msg.int("err"),
                  "corr": msg.num("corr"), "l": msg.int("l"), "r": msg.int("r"), "x": msg.int("x"),
                  "lost": msg.int("lost", 0), "b": msg.int("b"), "s": msg.ints("s"), "at": time.time()}
        self.telemetry = sample
        self.series.append(sample)
        if sample["st"]:
            self._confirm(sample["st"], "TEL")
        run = self._run
        if run is not None and run["state"] == "open":
            if run["t0"] is None:
                run["t0"] = t
            run["samples"].append({"t": round((t - run["t0"]) / 1000.0, 3), "error": sample["err"],
                                   "corr": sample["corr"], "pwm_l": sample["l"], "pwm_r": sample["r"],
                                   "lost": bool(sample["lost"]), "cross": sample["x"], "pos": sample["pos"]})

    def _event(self, msg) -> None:
        event = msg.event
        run = self._run
        if event == "cross":
            if run is not None and run["t0"] is not None and msg.int("t") is not None:
                run["crossings"].append(round((msg.int("t") - run["t0"]) / 1000.0, 3))
        elif event == "lost":
            if run is not None:
                run["losses"] += 1
            self._alert("lost", "Noctário perdeu a linha — recuperando", "média")
        elif event == "done":
            if run is not None:
                run["lap_ms"] = msg.int("lap_ms")
        elif event == "stop":
            reason = msg.fields.get("reason", "")
            if run is not None:
                run["reason"] = reason
            if reason in ("lost", "link", "fault"):
                self._alert("stop", f"Noctário parou: {protocol.STOP_REASONS.get(reason, reason)}", "alta")
        elif event == "estop":
            self._alert("estop", "PARADA DE EMERGÊNCIA confirmada pelo robô", "alta")
        elif event == "fault":
            self._alert("fault", f"Falha no Noctário: {msg.text('code') or msg.text('msg')}", "alta")
        elif event == "cal" and msg.fields.get("ok") == "0":
            self._alert("cal", f"Calibração falhou: {msg.text('msg') or 'sem contraste'}", "média")

    # ------------------------------------------------------------ estado confirmado e voltas
    def _confirm(self, state: str, source: str) -> None:
        state = str(state or "").upper()
        if state not in STATES:
            return
        with self._lock:
            previous = self.confirmed.get("state", "")
            self.confirmed = {"state": state, "at": time.time(), "source": source}
        if state == previous:
            return
        if state in RUN_STATES and previous not in RUN_STATES:
            self._begin_run(partial=previous == "")
        elif previous in RUN_STATES and state not in RUN_STATES:
            self._finish_run(state)
        self._publish_state()

    def _begin_run(self, *, partial: bool = False) -> None:
        """``partial``: o link abriu com o robô já em movimento — a volta começou antes da gravação."""
        self._run = {"id": "v" + uuid.uuid4().hex[:10], "started": time.time(), "t0": None, "samples": [],
                     "crossings": [], "losses": 0, "lap_ms": None, "reason": "", "state": "open", "partial": partial,
                     "params": dict(self.params), "source": "simulador" if self.simulated else "robo"}

    def _finish_run(self, state: str) -> None:
        run, self._run = self._run, None
        if run is None:
            return
        run["state"] = "closed"
        reason = run["reason"] or self.sta.get("why", "")
        result = RESULTS.get(state) or ("linha_perdida" if reason == "lost" else "interrompida")
        samples = run["samples"]
        duration = run["lap_ms"] / 1000.0 if run["lap_ms"] else (samples[-1]["t"] if samples else None)
        record = {"id": run["id"], "started": run["started"], "finished": time.time(), "duration_s": duration,
                  "result": result, "source": run["source"], "params": run["params"], "crossings": run["crossings"],
                  "losses": run["losses"], "samples": samples,
                  "summary": {"reason": reason, "samples": len(samples), "fw": self.fw, "partial": run["partial"]}}
        if self.store is not None:                            # gravada antes de anunciada
            try:
                self.store.save_run(record)
            except Exception as exc:
                log.warning("Noctário: volta não gravada: %s", exc)
        self.last_run = {k: v for k, v in record.items() if k != "samples"}
        label = {"concluida": "concluída", "linha_perdida": "linha perdida", "interrompida": "interrompida",
                 "emergencia": "parada de emergência"}[result]
        tag = "[SIMULADOR] " if self.simulated else ""
        self._record(f"{tag}Volta do Noctário: {label}" + (f" em {duration:.1f} s" if duration else ""), "noctario",
                     result=f"{len(run['crossings'])} cruzamento(s), {run['losses']} perda(s) de linha",
                     ref=f"volta:{run['id']}")
        self._publish(EventType.NOCTARIO_RUN, {"id": run["id"], "result": result, "duration_s": duration,
                                               "source": run["source"]})

    def runs(self, limit: int = 10) -> list[dict]:
        return self.store.runs(limit) if self.store is not None else []

    # ------------------------------------------------------------ comandos
    def _next_seq(self) -> int:
        with self._lock:
            self._seq = self._seq % protocol.SEQ_MAX + 1
            return self._seq

    def command(self, verb: str, args: dict | None = None, *, origin: str = "user",
                timeout: float = 2.0) -> CommandResult:
        verb = str(verb).upper()
        args = dict(args or {})
        target = REQUEST_TARGETS.get(verb)
        transport = self._transport
        if not self.connected or transport is None:
            result = CommandResult(verb, args, "NO_LINK")
            self._op(result, origin)
            return result
        seq = self._next_seq()
        try:
            data = encode(seq, verb, args)
        except ProtocolError as exc:
            result = CommandResult(verb, args, "INVALID", seq, message=str(exc))
            self._op(result, origin)
            return result
        pending = _Pending(seq)
        with self._lock:
            self._pending[seq] = pending
            if target is not None:
                self.requested = {"verb": verb, "state": target[0], "label": target[1], "accept": target[2],
                                  "at": time.time(), "seq": seq, "origin": origin}
        if target is not None:
            self._publish_state()
        started = time.monotonic()
        try:
            transport.write(data)
        except TransportError as exc:
            with self._lock:
                self._pending.pop(seq, None)
            result = CommandResult(verb, args, "NO_LINK", seq, message=str(exc))
            self._op(result, origin)
            return result
        answered = pending.event.wait(timeout)
        latency = round((time.monotonic() - started) * 1000, 1)
        message = pending.message
        if not answered or message is None:
            with self._lock:
                self._pending.pop(seq, None)
            result = CommandResult(verb, args, "TIMEOUT" if self.connected else "NO_LINK", seq, latency_ms=latency)
        elif message.kind == "ACK":
            result = CommandResult(verb, args, "ACK", seq, dict(message.fields), latency_ms=latency,
                                   confirmed=message.fields.get("st", ""))
        else:
            result = CommandResult(verb, args, "NAK", seq, dict(message.fields), message.fields.get("code", ""),
                                   message.text("msg"), latency)
        self._op(result, origin)
        return result

    def wait_confirmed(self, states, timeout: float = 2.0) -> bool:
        states = set(states)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.confirmed.get("state") in states:
                return True
            time.sleep(0.02)
        return self.confirmed.get("state") in states

    def estop(self, *, origin: str = "user") -> dict:
        """PARADA DE EMERGÊNCIA — direto no transporte, sem fila e sem esperar resposta."""
        transport = self._transport
        if transport is None or self.link != "conectado":
            self._alert("estop", "Parada de emergência pedida SEM CONEXÃO com o Noctário — use o botão físico",
                        "alta")
            self._record("Parada de emergência: sem conexão", origin, state="falhou",
                         error="sem link com o robô — use o botão físico")
            return {"sent": False, "confirmed": False, "detail": "SEM CONEXÃO — use o botão físico do Noctário"}
        try:
            transport.write(ESTOP_BYTE)
        except TransportError as exc:
            self._record("Parada de emergência: envio falhou", origin, state="falhou", error=str(exc))
            return {"sent": False, "confirmed": False, "detail": f"envio falhou ({exc}) — use o botão físico"}
        target = REQUEST_TARGETS["ESTOP"]
        with self._lock:
            self.requested = {"verb": "ESTOP", "state": target[0], "label": target[1], "accept": target[2],
                              "at": time.time(), "seq": None, "origin": origin}
        threading.Thread(target=self._repeat_estop, args=(transport, origin), name="noctario-estop",
                         daemon=True).start()
        self._publish_state()
        return {"sent": True, "confirmed": self.confirmed.get("state") == "ESTOP",
                "detail": "parada de emergência enviada"}

    def _repeat_estop(self, transport: Transport, origin: str) -> None:
        started = time.monotonic()
        while time.monotonic() - started < ESTOP_WINDOW:
            if self.confirmed.get("state") == "ESTOP":
                break
            time.sleep(ESTOP_REPEAT)
            if self.confirmed.get("state") == "ESTOP":
                break
            try:
                transport.write(ESTOP_BYTE)
            except TransportError:
                break
        confirmed = self.confirmed.get("state") == "ESTOP"
        latency = round((time.monotonic() - started) * 1000, 1)
        self._op(CommandResult("ESTOP", {}, "ACK" if confirmed else "TIMEOUT", latency_ms=latency,
                               confirmed="ESTOP" if confirmed else ""), origin)
        self._record("PARADA DE EMERGÊNCIA" + (" confirmada pelo robô" if confirmed else " sem confirmação do robô"),
                     origin, state="concluido" if confirmed else "falhou",
                     error="" if confirmed else "o robô não confirmou — use o botão físico")

    # atalhos usados pelas skills e pela página
    def start_run(self, *, origin: str = "user") -> CommandResult:
        return self.command("START", origin=origin)

    def stop_run(self, *, origin: str = "user") -> CommandResult:
        return self.command("STOP", origin=origin)

    def calibrate(self, *, auto: bool = False, ms: int = 3000, origin: str = "user") -> CommandResult:
        return self.command("CAL", {"ms": int(ms), "auto": int(bool(auto))}, origin=origin)

    def clear(self, *, origin: str = "user") -> CommandResult:
        return self.command("CLEAR", origin=origin)

    def read_params(self, *, origin: str = "user") -> CommandResult:
        return self.command("PARAMS", origin=origin)

    def read_sensors(self, *, origin: str = "user") -> CommandResult:
        return self.command("SENS", origin=origin)

    def set_params(self, values: dict, *, origin: str = "user") -> CommandResult:
        """Valida localmente (limites e regras) e envia; confirmado só quando o PAR do robô traz os valores."""
        try:
            clean = protocol.validate(values, self.params or DEFAULTS)
        except ProtocolError as exc:
            result = CommandResult("SET", dict(values), "INVALID", message=str(exc))
            self._op(result, origin)
            return result
        result = self.command("SET", clean, origin=origin)
        if result.ok:
            end = time.monotonic() + 1.5
            while time.monotonic() < end and any(self.params.get(k) != v for k, v in clean.items()):
                time.sleep(0.02)
            mismatched = {k: self.params.get(k) for k, v in clean.items() if self.params.get(k) != v}
            if mismatched:
                result.message = f"o robô aceitou, mas reporta outros valores: {mismatched}"
                result.outcome = "TIMEOUT"
            elif self.tardis is not None:
                try:
                    text = "Parâmetros confirmados pelo robô: " + ", ".join(f"{k}={protocol.fmt(v)}"
                                                                           for k, v in clean.items())
                    self.tardis.add_note(("[SIMULADOR] " if self.simulated else "") + text, project="Noctário",
                                         kind="parametro", data=dict(clean), source="noctario")
                except Exception as exc:
                    log.debug("memória de projeto: %s", exc)
        return result

    # ------------------------------------------------------------ leitura para interface e TARDIS
    def requested_status(self) -> dict:
        """Solicitado × confirmado: "confirmado", "aguardando confirmação" ou "sem confirmação do robô"."""
        with self._lock:
            requested = dict(self.requested)
            confirmed = dict(self.confirmed)
        if not requested:
            return {"label": "", "status": "", "age": 0.0}
        age = time.time() - requested["at"]
        if confirmed.get("state") in requested["accept"] and confirmed.get("at", 0) >= requested["at"] - 0.05:
            status = "confirmado"
        elif age < CONFIRM_WINDOW:
            status = "aguardando confirmação"
        else:
            status = "sem confirmação do robô — estado desconhecido"
        return {"label": requested["label"], "verb": requested["verb"], "status": status, "age": round(age, 1),
                "origin": requested.get("origin", "")}

    def status(self) -> dict:
        state = self.confirmed.get("state", "")
        sta = self.sta
        return {"link": self.link, "link_label": LINK_STATES.get(self.link, self.link), "detail": self.link_detail,
                "simulated": self.simulated, "transport": self.transport_label, "fw": self.fw,
                "state": state, "state_label": state_label(state) if state else "sem dado do robô",
                "requested": self.requested_status(), "cal": sta.get("cal") == "1",
                "crossings": int(sta.get("x", 0) or 0), "target": int(sta.get("xt", 0) or 0),
                "lap_ms": int(sta.get("lap", 0) or 0), "why": sta.get("why", "-"),
                "params": dict(self.params), "policy": self.params.get("onlink", ""),
                "last_failure": self.last_failure, "alerts": len(self.alerts), "connected_at": self.connected_at,
                "last_run": dict(self.last_run) if self.last_run else None}

    def snapshot(self) -> dict:
        return {**self.status(), "telemetry": dict(self.telemetry), "sensors": dict(self.sensors)}

    def recent_series(self, seconds: float = 20.0) -> list[dict]:
        cutoff = time.time() - seconds
        return [s for s in list(self.series) if s["at"] >= cutoff]

    def recent_alerts(self, limit: int = 20) -> list[dict]:
        return list(self.alerts)[-limit:][::-1]

    # ------------------------------------------------------------ registros e eventos
    def _set_link(self, link: str, *, requested: bool) -> None:
        if link == self.link:
            return
        self.link = link
        self._publish(EventType.NOCTARIO_LINK, {"link": link, "requested": requested, "simulated": self.simulated,
                                                "transport": self.transport_label, "detail": self.link_detail})

    def _publish_state(self) -> None:
        status = self.requested_status()
        self._publish(EventType.NOCTARIO_STATE, {"confirmed": self.confirmed.get("state", ""),
                                                 "label": state_label(self.confirmed.get("state", "")),
                                                 "requested": status.get("label", ""),
                                                 "pending": status.get("status", ""), "simulated": self.simulated})

    def _alert(self, kind: str, text: str, severity: str) -> None:
        text = ("[SIMULADOR] " if self.simulated else "") + text
        entry = {"at": time.time(), "kind": kind, "text": text, "severity": severity}
        self.alerts.append(entry)
        if severity == "alta":
            self.last_failure = text
        self._publish(EventType.NOCTARIO_ALERT, entry)
        if self._activity is not None:
            self._activity.record("noctario", text, origin="noctario", state="aviso")

    def _record(self, title: str, origin: str, *, state: str = "concluido", result: str = "", error: str = "",
                ref: str = "") -> None:
        if self._activity is not None:
            tag = "[SIMULADOR] " if self.simulated and not title.startswith("[SIMULADOR]") else ""
            self._activity.record("noctario", tag + title, origin=origin, state=state, result=result, error=error,
                                  ref=ref)

    def _op(self, result: CommandResult, origin: str) -> None:
        if self.store is None:
            return
        try:
            self.store.record_op(seq=result.seq, verb=result.verb, args=result.args, origin=origin,
                                 requested=REQUEST_TARGETS.get(result.verb, ("",))[0], outcome=result.outcome,
                                 detail=result.describe(), latency_ms=result.latency_ms,
                                 source="simulador" if self.simulated else "robo")
        except Exception as exc:
            log.debug("operação do Noctário não registrada: %s", exc)

    def _fail_pending(self, outcome: str) -> None:
        with self._lock:
            pending, self._pending = list(self._pending.values()), {}
        for item in pending:
            item.event.set()

    def _publish(self, kind: EventType, payload: dict) -> None:
        if self._bus is not None:
            self._bus.publish(kind, payload, source="noctario")
