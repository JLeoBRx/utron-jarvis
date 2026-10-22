"""SIMULADOR do Noctário — NÃO é o robô.

Um robô de mentira que fala NOCT/1 como o firmware de ``firmware/noctario/``: a mesma máquina de estados,
o mesmo PD, rampas, velocidade adaptativa, contagem de cruzamentos com filtro, perda de linha e
recuperação, cão de guarda do link (política "stop"/"continue") e parada de emergência pelo byte ``!``.
Por baixo, um modelo cinemático simples (tração diferencial) numa pista de TESTE inventada para o
simulador — não é a pista real, e seus tempos não dizem nada sobre o robô.

Serve para os testes automáticos e para treinar a interface sem o robô. Toda tela, registro e volta que
vem daqui é marcada "SIMULADOR".
"""
from __future__ import annotations

import math
import random
import threading
import time
import unicodedata
from collections import deque

from .protocol import DEFAULTS, MAX_LINE, PARAMS, ProtocolError, fmt, validate

FW = "simulador-1.0"
SENSORS = 8
CENTER = 3500
CAL_MIN_SPAN = 200                    # contraste mínimo (ADC bruto) para aceitar a calibração
STOPPED = ("IDLE", "READY", "STOP", "DONE")
RUNTIME_ONLY = ("loop", "flip", "white", "ldir", "rdir")    # só com o robô parado


class FirmwareModel:
    """A lógica do firmware sem hardware: entra byte, leitura dos sensores e tempo; sai PWM e linhas."""

    def __init__(self, *, fw: str = FW, calibrated: bool = False, link_scale: float = 1.0):
        self.fw = fw
        self.link_scale = link_scale          # só no simulador acelerado: o batimento do PC vem em tempo real
        self.params = dict(DEFAULTS)
        self.saved = dict(DEFAULTS)
        self.state = "IDLE"
        self.cal = False
        self.mins = [4095] * SENSORS
        self.maxs = [0] * SENSORS
        if calibrated:
            self.mins, self.maxs, self.cal, self.state = [400] * SENSORS, [3400] * SENSORS, True, "READY"
        self.out: deque[str] = deque()
        self._line = bytearray()
        self._overflow = False
        self.now = 0
        self.last_rx = 0
        self.crossings = 0
        self.last_cross = -10 ** 9
        self.cross_prev = False
        self.cross_raw = False                    # nível lido no pino de cruzamento (conferir o xact na bancada)
        self.lost_since: int | None = None
        self.last_err = 0
        self.ramp = 0.0
        self.lap_start = 0
        self.lap_ms = 0
        self.stop_reason = ""
        self.tel_last = -10 ** 9
        self.cal_until = 0
        self.cal_auto = False
        self.test = (0, 0, 0)
        self.values = [0] * SENSORS
        self.pos = CENTER
        self.err = 0
        self.corr = 0.0
        self.pwm = (0, 0)
        self.seen = False
        self.connected = False

    # ------------------------------------------------------------ saída
    def emit(self, line: str) -> None:
        self.out.append(line[:MAX_LINE])

    def sta(self) -> str:
        p = self.params
        return (f"STA st={self.state} cal={int(self.cal)} x={self.crossings} xt={p['cross']} lap={self.lap_ms} "
                f"why={self.stop_reason or '-'} fw={self.fw} tel={p['tel']} onlink={p['onlink']} hb={p['hb']}")

    def par(self) -> list[str]:
        """Parâmetros em linhas de até 12 campos (cada linha cabe em ``MAX_LINE``)."""
        items = [f"{k}={fmt(v)}" for k, v in self.params.items()]
        return ["PAR " + " ".join(items[i:i + 12]) for i in range(0, len(items), 12)]

    def emit_par(self) -> None:
        for line in self.par():
            self.emit(line)

    def set_state(self, state: str, reason: str = "") -> None:
        if state == self.state:
            return
        self.state = state
        if reason:
            self.stop_reason = reason
        self.emit(self.sta())

    # ------------------------------------------------------------ entrada
    def connect(self) -> None:
        self.connected = True
        self.last_rx = self.now
        self.emit(f"HELLO fw={self.fw} proto=1 st={self.state} cal={int(self.cal)} name=Noctario")
        self.emit(self.sta())
        self.emit_par()

    def disconnect(self) -> None:
        self.connected = False

    def feed(self, data: bytes) -> None:
        for byte in data:
            if byte == 0x21:                                 # "!" — parada de emergência, antes de tudo
                self._line.clear()
                self._overflow = False
                self.estop("bt")
                continue
            if byte in (0x0A, 0x0D):
                if self._overflow:                            # linha longa demais: descartada inteira
                    self._overflow = False
                    self._line.clear()
                    self.last_rx = self.now
                    self.emit("NAK 0 code=SYNTAX msg=linha_longa_demais")
                elif self._line:
                    line = self._line.decode("ascii", errors="replace")
                    self._line.clear()
                    self.last_rx = self.now
                    self.handle(line)
                continue
            if self._overflow:
                continue
            if len(self._line) < MAX_LINE:
                self._line.append(byte)
            else:
                self._overflow = True
                self._line.clear()

    def estop(self, source: str) -> None:
        self.pwm = (0, 0)
        self.ramp = 0.0
        if self.state in ("RUN", "LOST", "STOPPING"):
            self.lap_ms = self.now - self.lap_start
        self.stop_reason = "estop"
        if self.state != "ESTOP":
            self.state = "ESTOP"
            self.emit(f"EVT estop src={source}")
            self.emit(self.sta())

    def handle(self, line: str) -> None:
        tokens = line.split()
        if not tokens:
            return
        if tokens[0] == "HB":
            return
        if len(tokens) > 40:                                  # mais campos do que qualquer comando válido tem
            self.emit("NAK 0 code=SYNTAX msg=campos_demais")
            return
        if tokens[0] != "CMD" or len(tokens) < 3 or not (tokens[1].isascii() and tokens[1].isdigit()) \
                or len(tokens[1]) > 9:
            self.emit("NAK 0 code=SYNTAX msg=linha_malformada")
            return
        seq, verb = int(tokens[1]), tokens[2].upper()
        args = {}
        for token in tokens[3:]:
            key, sep, value = token.partition("=")
            if not sep or not key:
                self.emit(f"NAK {seq} code=SYNTAX msg=argumento_malformado")
                return
            args[key] = value
        handler = getattr(self, f"cmd_{verb.lower()}", None)
        if handler is None:
            self.emit(f"NAK {seq} code=UNKNOWN msg=verbo_desconhecido")
            return
        handler(seq, args)

    def nak(self, seq: int, code: str, msg: str) -> None:
        ascii_msg = unicodedata.normalize("NFKD", msg).encode("ascii", "ignore").decode("ascii")
        self.emit(f"NAK {seq} code={code} msg={'_'.join(ascii_msg.split())}")

    # ------------------------------------------------------------ comandos
    def cmd_ping(self, seq, args):
        self.emit(f"ACK {seq} pong=1 t={self.now}")

    def cmd_info(self, seq, args):
        self.emit(f"ACK {seq} fw={self.fw} proto=1 sensors={SENSORS} cal={int(self.cal)}")

    def cmd_status(self, seq, args):
        self.emit(f"ACK {seq} st={self.state}")
        self.emit(self.sta())

    def cmd_start(self, seq, args):
        if self.state == "ESTOP":
            return self.nak(seq, "ESTOP", "em parada de emergência: use CLEAR")
        if not self.cal:
            return self.nak(seq, "NOCAL", "sensores não calibrados: use CAL")
        if self.state not in ("READY", "STOP", "DONE"):
            return self.nak(seq, "STATE", f"não é possível partir em {self.state}")
        self.crossings, self.last_cross, self.lost_since = 0, -10 ** 9, None
        self.last_err, self.ramp, self.lap_start, self.lap_ms, self.stop_reason = 0, 0.0, self.now, 0, ""
        self.set_state("RUN")
        self.emit(f"ACK {seq} st=RUN")

    def cmd_stop(self, seq, args):
        if self.state in ("RUN", "LOST", "TEST") or (self.state == "CAL" and self.cal_auto):
            self.set_state("STOPPING", "cmd")
        self.emit(f"ACK {seq} st={self.state}")

    def cmd_clear(self, seq, args):
        if self.state == "ESTOP":
            self.set_state("READY" if self.cal else "IDLE")
        self.emit(f"ACK {seq} st={self.state}")

    def cmd_cal(self, seq, args):
        if self.state == "ESTOP":
            return self.nak(seq, "ESTOP", "em parada de emergência: use CLEAR")
        if self.state not in STOPPED:
            return self.nak(seq, "STATE", f"calibração só com o robô parado (agora {self.state})")
        try:
            duration = int(args.get("ms", 3000))
            auto = int(args.get("auto", 0))
        except ValueError:
            return self.nak(seq, "SYNTAX", "ms e auto devem ser inteiros")
        if not 500 <= duration <= 20000 or auto not in (0, 1):
            return self.nak(seq, "RANGE", "ms de 500 a 20000; auto 0 ou 1")
        self.mins, self.maxs = [4095] * SENSORS, [0] * SENSORS
        self.cal = False                      # a calibração anterior deixa de valer: interrompida, não há partida
        self.cal_until, self.cal_auto = self.now + duration, bool(auto)
        self.set_state("CAL")
        self.emit(f"ACK {seq} st=CAL ms={duration} auto={auto}")

    def cmd_set(self, seq, args):
        if not args:
            return self.nak(seq, "SYNTAX", "nada para ajustar")
        moving = self.state not in STOPPED and self.state != "ESTOP"
        locked = [k for k in args if k in RUNTIME_ONLY and moving]
        if locked:
            return self.nak(seq, "STATE", f"{','.join(locked)} só com o robô parado")
        try:
            clean = validate(args, self.params)
        except ProtocolError as exc:
            return self.nak(seq, "RANGE", str(exc))
        self.params.update(clean)
        self.emit(f"ACK {seq} " + " ".join(f"{k}={fmt(v)}" for k, v in clean.items()))
        self.emit_par()

    def cmd_params(self, seq, args):
        self.emit(f"ACK {seq}")
        self.emit_par()

    def cmd_save(self, seq, args):
        self.saved = dict(self.params)
        self.emit(f"ACK {seq} saved=1")

    def cmd_defaults(self, seq, args):
        if self.state not in STOPPED and self.state != "ESTOP":
            return self.nak(seq, "STATE", "padrões só com o robô parado")
        self.params = dict(DEFAULTS)
        self.emit(f"ACK {seq} defaults=1")
        self.emit_par()

    def cmd_resetx(self, seq, args):
        self.crossings = 0
        self.emit(f"ACK {seq} x=0")

    def cmd_tel(self, seq, args):
        if "hz" not in args:
            return self.nak(seq, "SYNTAX", "use TEL hz=0..50")
        try:
            clean = validate({"tel": args["hz"]}, self.params)
        except ProtocolError as exc:
            return self.nak(seq, "RANGE", str(exc))
        self.params.update(clean)
        self.emit(f"ACK {seq} tel={self.params['tel']}")

    def cmd_sens(self, seq, args):
        self.emit(f"ACK {seq}")
        self.emit(f"SEN cal={','.join(str(v) for v in self.values)} pos={self.pos} line={int(self.seen)} "
                  f"x={self.crossings} xin={int(self.cross_raw)}")

    def cmd_motor(self, seq, args):
        if self.state not in STOPPED:
            return self.nak(seq, "STATE", f"teste de motores só com o robô parado (agora {self.state})")
        try:
            left, right, duration = int(args.get("l", 0)), int(args.get("r", 0)), int(args.get("ms", 500))
        except ValueError:
            return self.nak(seq, "SYNTAX", "l, r e ms devem ser inteiros")
        if not (-255 <= left <= 255 and -255 <= right <= 255 and 100 <= duration <= 3000):
            return self.nak(seq, "RANGE", "l e r de -255 a 255; ms de 100 a 3000")
        self.test = (left, right, self.now + duration)
        self.set_state("TEST")
        self.emit(f"ACK {seq} st=TEST")

    # ------------------------------------------------------------ laço de controle
    def read_line(self, raw: list[int]) -> None:
        values = []
        for i in range(SENSORS):
            span = self.maxs[i] - self.mins[i]
            c = 0 if span <= 0 else max(0, min(1000, (raw[i] - self.mins[i]) * 1000 // span))
            values.append(1000 - c if self.params["white"] else c)
        if self.params["flip"]:
            values.reverse()
        self.values = values
        self.seen = max(values) >= self.params["thr"]
        if self.seen:
            weights = [(i * 1000, v) for i, v in enumerate(values) if v >= 50]
            total = sum(v for _, v in weights)
            self.pos = int(sum(p * v for p, v in weights) / total) if total else CENTER
        else:
            self.pos = 0 if self.last_err < 0 else 2 * CENTER
        self.err = self.pos - CENTER

    def tick(self, now: int, raw: list[int], cross_pin: bool) -> tuple[int, int]:
        """Um ciclo do laço de controle (``now`` em ms). Devolve o PWM (esquerdo, direito) já com o sentido."""
        dt = max(0, now - self.now) / 1000.0
        self.now = now
        p = self.params
        if self.state == "CAL":
            for i in range(SENSORS):
                self.mins[i], self.maxs[i] = min(self.mins[i], raw[i]), max(self.maxs[i], raw[i])
        self.read_line(raw)
        self.cross_raw = bool(cross_pin)
        active = bool(cross_pin) == bool(p["xact"])
        if active and not self.cross_prev and self.state in ("RUN", "LOST", "STOPPING") \
                and now - self.last_cross >= p["deb"]:
            self.crossings += 1
            self.last_cross = now
            self.emit(f"EVT cross n={self.crossings} t={now}")
        self.cross_prev = active
        left = right = 0
        state = self.state
        if state == "ESTOP":
            left = right = 0
        elif state == "CAL":
            if self.cal_auto:
                swing = 1 if (now // 600) % 2 == 0 else -1
                left, right = 80 * swing, -80 * swing
            if now >= self.cal_until:
                ok = all(self.maxs[i] - self.mins[i] >= CAL_MIN_SPAN for i in range(SENSORS))
                self.cal = ok
                self.emit("EVT cal ok=1" if ok else "EVT cal ok=0 msg=sensores_sem_contraste")
                self.set_state("READY" if ok else "IDLE")
                left = right = 0
        elif state == "TEST":
            left, right = self.test[0], self.test[1]
            if now >= self.test[2]:
                left = right = 0
                self.set_state("READY" if self.cal else "IDLE")
        elif state in ("RUN", "LOST", "STOPPING"):
            if p["hb"] and now - self.last_rx > p["hb"] * self.link_scale and p["onlink"] == "stop" \
                    and state != "STOPPING":
                self.set_state("STOPPING", "link")
                state = "STOPPING"
            if p["cross"] and self.crossings >= p["cross"] and state != "STOPPING":
                self.set_state("STOPPING", "done")
                state = "STOPPING"
            if state == "RUN":
                if not self.seen:
                    self.lost_since = now if self.lost_since is None else self.lost_since
                    if now - self.lost_since >= p["lostms"]:
                        self.emit("EVT lost")
                        self.set_state("LOST")
                        state = "LOST"
                else:
                    self.lost_since = None
            elif state == "LOST":
                if self.seen:
                    self.emit(f"EVT found ms={now - (self.lost_since if self.lost_since is not None else now)}")
                    self.lost_since = None
                    self.set_state("RUN")
                    state = "RUN"
                elif now - (self.lost_since if self.lost_since is not None else now) >= p["lostms"] + p["loststop"]:
                    self.set_state("STOPPING", "lost")
                    state = "STOPPING"
            target = 0.0 if state == "STOPPING" else p["base"] * (1.0 - p["adapt"] * min(1.0, abs(self.err) / CENTER))
            rate = p["accel"] if target > self.ramp else p["decel"]
            if rate <= 0:
                self.ramp = target
            else:
                step = rate * dt
                self.ramp = min(target, self.ramp + step) if target > self.ramp else max(target, self.ramp - step)
            self.corr = p["kp"] * self.err + p["kd"] * (self.err - self.last_err)
            self.last_err = self.err
            if state == "LOST":
                side = 1 if self.err > 0 else -1
                left, right = p["recov"] * side, -p["recov"] * side
            else:
                left = int(round(self.ramp + self.corr))
                right = int(round(self.ramp - self.corr))
            low, high = p["minpwm"], p["max"]
            left, right = max(low, min(high, left)), max(low, min(high, right))
            if state == "STOPPING" and self.ramp <= 0.5:
                left = right = 0
                self.lap_ms = now - self.lap_start
                reason = self.stop_reason or "cmd"
                if reason == "done":
                    self.emit(f"EVT done lap_ms={self.lap_ms} x={self.crossings}")
                    self.set_state("DONE")
                else:
                    self.emit(f"EVT stop reason={reason}")
                    self.set_state("STOP")
            else:
                self.lap_ms = now - self.lap_start
        self.pwm = (int(left * p["ldir"]), int(right * p["rdir"]))
        if p["tel"] and self.connected and now - self.tel_last >= 1000 // p["tel"]:
            self.tel_last = now
            self.emit(f"TEL t={now} st={self.state} pos={self.pos} err={self.err} corr={self.corr:.2f} "
                      f"l={self.pwm[0]} r={self.pwm[1]} x={self.crossings} lost={int(not self.seen)} "
                      f"b={int(self.ramp)} s={','.join(str(v) for v in self.values)}")
        return self.pwm


class TestTrack:
    """Pista de TESTE do simulador (inventada; não é a pista real): retas, curvas e 4 cruzamentos."""

    SEGMENTS = ((2.5, 0.0), (1.0, 1.6), (2.0, 0.0), (1.6, -2.0), (3.0, 0.0), (1.2, 1.3), (1.5, 0.0), (0.9, -2.2),
                (2.5, 0.0), (1.4, 1.8), (3.0, 0.0), (1.0, -1.5), (2.0, 0.0), (1.2, 2.0), (2.5, 0.0))
    CROSSINGS = (5.4, 11.3, 17.8, 26.0)

    def __init__(self):
        self.edges = []
        position = 0.0
        for length, curvature in self.SEGMENTS:
            self.edges.append((position, position + length, curvature))
            position += length
        self.length = position

    def curvature(self, s: float) -> float:
        for start, end, curvature in self.edges:
            if start <= s < end:
                return curvature
        return 0.0

    def crossing_at(self, s: float, half_width: float = 0.012) -> bool:
        return any(abs(s - c) <= half_width for c in self.CROSSINGS)


class Physics:
    """Tração diferencial com atraso de motor; sensores pela posição lateral da linha sob a barra."""

    WHEELBASE = 0.15                  # m
    SPEED_AT_255 = 1.25               # m/s
    MOTOR_TAU = 0.06                  # s
    BAR_AHEAD = 0.07                  # m
    PITCH = 0.0095                    # m entre sensores
    SIGMA = 0.0085                    # m (fita de ~19 mm)
    BLACK, WHITE = 3400, 450          # ADC de 12 bits (QTR-A: branco reflete → tensão baixa)

    def __init__(self, track: TestTrack, seed: int = 11):
        self.track = track
        self.s, self.y, self.psi = 0.0, 0.0, 0.0
        self.vl = self.vr = 0.0
        self.rng = random.Random(seed)
        self.yaw = 0.0                                      # giro no lugar (calibração automática)

    def step(self, dt: float, pwm: tuple[int, int]) -> None:
        k = self.SPEED_AT_255 / 255.0
        alpha = min(1.0, dt / self.MOTOR_TAU)
        self.vl += (pwm[0] * k - self.vl) * alpha
        self.vr += (pwm[1] * k - self.vr) * alpha
        v = (self.vl + self.vr) / 2.0
        omega = (self.vr - self.vl) / self.WHEELBASE
        kappa = self.track.curvature(self.s)
        self.psi += (omega - v * kappa) * dt
        self.psi = max(-1.2, min(1.2, self.psi))
        self.y += v * math.sin(self.psi) * dt
        self.s += max(0.0, v * math.cos(self.psi)) * dt

    def sensors(self) -> list[int]:
        offset = self.y + self.BAR_AHEAD * math.sin(self.psi)
        on_track = 0.0 <= self.s <= self.track.length
        on_cross = self.track.crossing_at(self.s + self.BAR_AHEAD)
        raw = []
        for i in range(SENSORS):
            x = (3.5 - i) * self.PITCH                        # sensor 0 à esquerda
            strength = 1.0 if on_cross else (math.exp(-((x + offset) ** 2) / (2 * self.SIGMA ** 2)) if on_track else 0.0)
            value = self.BLACK - (self.BLACK - self.WHITE) * strength + self.rng.gauss(0, 25)
            raw.append(int(max(0, min(4095, value))))
        return raw

    def cross_pin(self) -> bool:
        return self.track.crossing_at(self.s)


class NoctarioSimulator:
    """O robô simulado numa thread: lógica do firmware + física, em tempo simulado (``speed`` × real)."""

    def __init__(self, *, speed: float = 1.0, calibrated: bool = False, seed: int = 11):
        self.speed = max(0.1, float(speed))
        self.track = TestTrack()
        self.physics = Physics(self.track, seed)
        self.firmware = FirmwareModel(calibrated=calibrated, link_scale=max(1.0, self.speed))
        self._inbox: deque[bytes] = deque()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.sim_ms = 0
        self.attached = False
        self._acc = 0.0
        self._prev_state = self.firmware.state

    # ------------------------------------------------------------ ligação com o transporte
    def attach(self) -> None:
        with self._lock:
            self.attached = True
            self.firmware.connect()
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="noctario-simulador", daemon=True)
            self._thread.start()

    def detach(self) -> None:
        with self._lock:
            self.attached = False
            self.firmware.disconnect()

    def write(self, data: bytes) -> None:
        with self._lock:
            self._inbox.append(bytes(data))

    def take_output(self) -> list[str]:
        with self._lock:
            lines = list(self.firmware.out)
            self.firmware.out.clear()
        return lines

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------ relógio simulado
    def _run(self) -> None:
        batch_wall = 0.01
        last = time.monotonic()
        while not self._stop.is_set():
            now = time.monotonic()
            wall = now - last
            last = now
            with self._lock:
                while self._inbox:
                    self.firmware.feed(self._inbox.popleft())
                loop_hz = int(self.firmware.params["loop"])
                step_ms = max(1, 1000 // loop_hz)
                self._acc = min(self._acc + wall * 1000 * self.speed, 400.0 * step_ms)
                ticks = int(self._acc // step_ms)
                self._acc -= ticks * step_ms
                for _ in range(ticks):
                    self.sim_ms += step_ms
                    self._world(step_ms)
                    pwm = self.firmware.tick(self.sim_ms, self.physics.sensors(), self.physics.cross_pin())
                    self.physics.step(step_ms / 1000.0, pwm)
                idle = not self.attached and self.firmware.state not in ("RUN", "LOST", "STOPPING", "TEST", "CAL")
            if idle:
                break
            self._stop.wait(batch_wall)

    def _world(self, step_ms: int) -> None:
        """O que uma PESSOA faria na pista de teste: varrer a barra sobre a linha na calibração manual,
        recolocar o robô alinhado depois de calibrar e levá-lo ao início a cada partida."""
        firmware, physics = self.firmware, self.physics
        state = firmware.state
        if state == "CAL" and not firmware.cal_auto:
            physics.y = 0.05 * math.sin(math.tau * self.sim_ms / 1000.0)
        if state != self._prev_state:
            if self._prev_state == "CAL":
                physics.y, physics.psi, physics.vl, physics.vr = 0.0, 0.0, 0.0, 0.0
            if state == "RUN" and self._prev_state in ("READY", "STOP", "DONE"):
                self.physics = Physics(self.track, seed=self.sim_ms % 9973)
            self._prev_state = state

    def reset_position(self) -> None:
        with self._lock:
            self.physics = Physics(self.track)


__all__ = ["FirmwareModel", "NoctarioSimulator", "PARAMS", "Physics", "TestTrack"]
