"""Noctário no PC: protocolo NOCT/1, transportes, serviço (SOLICITADO × CONFIRMADO, voltas, PARADA), skills
pelo núcleo do JARVIS (autorização, emergência, permissões) e o painel NOCTÁRIO.

Tudo aqui roda contra o SIMULADOR (lógica do firmware + física de uma pista de teste inventada) ou contra
um "robô de teste" roteirizado linha a linha. NENHUM teste daqui é teste do robô real, de Bluetooth real
ou de motores: o firmware compilado é conferido em ``test_noctario_firmware.py``.
"""
import threading
import time
import unittest
from collections import deque
from unittest import mock

import helpers

from fake_ollama import FakeOllama
from ultron.noctario import protocol
from ultron.noctario import service as service_module
from ultron.noctario.protocol import DEFAULTS, ProtocolError, encode, parse, validate
from ultron.noctario.service import NoctarioService
from ultron.noctario.simulator import NoctarioSimulator
from ultron.noctario.store import NoctarioStore, pack, unpack
from ultron.noctario.transport import (RfcommTransport, SerialTransport, SimulatorTransport, Transport,
                                       TransportError, from_settings)

PAR = ["PAR " + " ".join(f"{k}={protocol.fmt(v)}" for k, v in list(DEFAULTS.items())[:12]),
       "PAR " + " ".join(f"{k}={protocol.fmt(v)}" for k, v in list(DEFAULTS.items())[12:])]


def wait_until(condition, seconds=5.0, step=0.01):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(step)
    return bool(condition())


class Recorder:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()

    def publish(self, kind, payload=None, source=""):
        with self.lock:
            self.events.append((getattr(kind, "value", kind), dict(payload or {})))

    def of(self, kind):
        with self.lock:
            return [p for k, p in self.events if k == kind]


class FakeActivity:
    def __init__(self):
        self.items = []

    def record(self, kind, title, **fields):
        self.items.append({"kind": kind, "title": title, **fields})
        return len(self.items)

    def titles(self):
        return [i["title"] for i in self.items]


class FakeTardis:
    def __init__(self):
        self.notes = []

    def add_note(self, text, **fields):
        self.notes.append({"text": text, **fields})


class ScriptedTransport(Transport):
    """"Robô" de teste: o teste decide o que ele diz; ``answer(linha)`` devolve as respostas (ou nada)."""

    kind = "teste"

    def __init__(self, *, hello=True, answer=None, fail_open=None):
        self.hello, self.answer, self.fail_open = hello, answer, fail_open
        self.written: list[bytes] = []
        self.incoming: deque[bytes] = deque()
        self.lock = threading.Lock()
        self.closed = True

    @property
    def label(self):
        return "robô de teste"

    def push(self, *chunks):
        with self.lock:
            self.incoming.extend(c if isinstance(c, bytes) else (c + "\n").encode("ascii") for c in chunks)

    def open(self, timeout=5.0):
        if self.fail_open:
            raise TransportError(self.fail_open)
        self.closed = False
        if self.hello:
            self.push("HELLO fw=teste-1 proto=1 st=READY cal=1 name=Noctario",
                      "STA st=READY cal=1 x=0 xt=4 lap=0 why=- fw=teste-1 tel=20 onlink=stop hb=1500", *PAR)

    def close(self):
        self.closed = True

    def write(self, data):
        if self.closed:
            raise TransportError("fechado")
        with self.lock:
            self.written.append(bytes(data))
        if self.answer is not None:
            for line in bytes(data).decode("ascii").splitlines():
                self.push(*(self.answer(line) or ()))

    def read(self, timeout):
        end = time.monotonic() + timeout
        while True:
            if self.closed:
                raise TransportError("fechado")
            with self.lock:
                if self.incoming:
                    return self.incoming.popleft()
            if time.monotonic() >= end:
                return b""
            time.sleep(0.005)

    def sent(self):
        with self.lock:
            return b"".join(self.written)


def make_service(factory, **settings):
    values = {"noctario_transport": "simulator", **settings}
    config = helpers.make_settings(**values)
    bus, activity, tardis = Recorder(), FakeActivity(), FakeTardis()
    service = NoctarioService(lambda: config, bus=bus, activity=activity, db=helpers.make_memory().db,
                              transport_factory=factory, tardis=tardis)
    return service, bus, activity, tardis


# ====================================================================== protocolo e transportes
class ProtocolTest(unittest.TestCase):
    def test_encode_builds_one_ascii_line_and_refuses_anything_odd(self):
        self.assertEqual(encode(5, "set", {"kp": 0.014, "onlink": "stop"}), b"CMD 5 SET kp=0.014 onlink=stop\n")
        self.assertEqual(encode(65535, "PING"), b"CMD 65535 PING\n")
        for seq, verb, args in ((0, "PING", {}), (65536, "PING", {}), (1, "VOAR", {}), (1, "SET", {"a b": 1}),
                                (1, "SET", {"kp": "1 2"}), (1, "SET", {"kp": "1!"}), (1, "SET", {"kp": "a=b"}),
                                (1, "SET", {f"k{i}": 123456 for i in range(30)})):
            with self.assertRaises(ProtocolError, msg=(seq, verb, args)):
                encode(seq, verb, args)

    def test_parse_reads_every_kind_and_never_raises(self):
        tel = parse(b"TEL t=1234 st=RUN pos=3600 err=100 corr=2.50 l=200 r=180 x=1 lost=0 b=210 "
                    b"s=0,10,900,1000,850,20,0,0\n")
        self.assertEqual((tel.kind, tel.int("t"), tel.num("corr"), tel.fields["st"]), ("TEL", 1234, 2.5, "RUN"))
        self.assertEqual(tel.ints("s"), [0, 10, 900, 1000, 850, 20, 0, 0])
        nak = parse(bytearray(b"NAK 7 code=RANGE msg=Kp:_0.5_fora_do_limite"))
        self.assertEqual((nak.kind, nak.seq, nak.fields["code"], nak.text("msg")),
                         ("NAK", 7, "RANGE", "Kp: 0.5 fora do limite"))
        evt = parse("EVT done lap_ms=26780 x=4")
        self.assertEqual((evt.kind, evt.event, evt.int("lap_ms")), ("EVT", "done", 26780))
        for junk in (b"", b"\xff\xfe\x00", "lixo total", "ACK", "ACK x", "ACK ² st=RUN", "EVT k=v",
                     "X" * 1000, "TEL t=abc"):
            message = parse(junk)
            self.assertIn(message.kind, ("UNKNOWN", "TEL"), junk)
        self.assertIsNone(parse("TEL t=abc").int("t"))
        self.assertEqual(parse("ACK ² st=RUN").kind, "UNKNOWN", "dígito que não é ASCII não é sequência")

    def test_validate_limits_and_rules_between_parameters(self):
        self.assertEqual(validate({"kd": "0,12", "base": "200", "onlink": "CONTINUE"}),
                         {"kd": 0.12, "base": 200, "onlink": "continue"})
        with self.assertRaises(ProtocolError) as raised:
            validate({"kp": 0.5, "base": 300, "voar": 1, "cross": 2.5})
        message = str(raised.exception)
        for part in ("Kp: 0.5 fora do limite (0 a 0.2)", "PWM base: 300 fora do limite", "parâmetro desconhecido: voar",
                     "use um número inteiro"):
            self.assertIn(part, message, "todos os problemas de uma vez")
        with self.assertRaises(ProtocolError):
            validate({"base": 240})                       # máximo padrão 220
        self.assertEqual(validate({"base": 240, "max": 250}), {"base": 240, "max": 250})
        with self.assertRaises(ProtocolError):
            validate({"minpwm": 100}, {"base": 90, "max": 220})
        for bad in ({"kp": "nan"}, {"kp": "inf"}, {"ldir": 0}, {"onlink": "talvez"}, {"loop": 50}):
            with self.assertRaises(ProtocolError, msg=bad):
                validate(bad)

    def test_initial_parameters_are_the_requested_ones(self):
        self.assertEqual({k: DEFAULTS[k] for k in ("kp", "kd", "base", "max", "cross", "xact", "loop")},
                         {"kp": 0.0125, "kd": 0.1, "base": 220, "max": 220, "cross": 4, "xact": 0, "loop": 100})
        self.assertEqual(DEFAULTS["white"], 1, "linha branca em pista preta")
        widest = {k: (1.23457e-05 if s.kind == "float" else -255 if s.low < 0 else int(s.high) if s.kind == "int"
                      else max(s.choices, key=len)) for k, s in protocol.PARAMS.items()}
        items = [f"{k}={protocol.fmt(v)}" for k, v in widest.items()]
        lines = ["PAR " + " ".join(items[i:i + 12]) for i in range(0, len(items), 12)]
        self.assertTrue(all(len(line) <= protocol.MAX_LINE for line in lines),
                        "cada linha PAR (12 campos) cabe no limite mesmo com os valores mais longos")


class IntentsTest(unittest.TestCase):
    def test_robot_phrases(self):
        from ultron.cognition.intent_engine import IntentEngine
        engine = IntentEngine()
        cases = {
            "pare o Noctário": ("noctario.emergency_stop", {}),
            "parada de emergência": ("noctario.emergency_stop", {}),
            "robô, pare!": ("noctario.emergency_stop", {}),
            "libere a emergência do Noctário": ("noctario.clear", {}),
            "pare o robô suavemente": ("noctario.stop", {}),
            "conecte o Noctário": ("noctario.connect", {}),
            "desconecte o robô": ("noctario.disconnect", {}),
            "calibre o Noctário": ("noctario.calibrate", {}),
            "calibre o robô girando": ("noctario.calibrate", {"auto": True}),
            "dê a partida no Noctário": ("noctario.start", {}),
            "teste o motor esquerdo do Noctário": ("noctario.motor_test", {"l": 120, "r": 0, "ms": 500}),
            "teste os motores do robô para trás": ("noctario.motor_test", {"l": -120, "r": -120, "ms": 500}),
            "ajuste o Kd do Noctário para 0,12": ("noctario.set_params", {"kd": 0.12}),
            "mude o PWM base do robô para 200": ("noctario.set_params", {"base": 200}),
            "telemetria do Noctário a 10 Hz": ("noctario.telemetry", {"hz": 10}),
            "desligue a telemetria do robô": ("noctario.telemetry", {"hz": 0}),
            "zere os cruzamentos do Noctário": ("noctario.reset_crossings", {}),
            "salve os parâmetros do Noctário": ("noctario.save_params", {}),
            "quantos cruzamentos o Noctário contou?": ("noctario.crossings", {}),
            "leia os sensores do robô": ("noctario.sensors", {}),
            "quais os parâmetros do Noctário?": ("noctario.params", {}),
            "alertas do Noctário": ("noctario.alerts", {}),
            "qual o estado do Noctário?": ("noctario.status", {}),
            "analise as voltas do Noctário": ("tardis.consult", {"kind": "telemetria"}),
        }
        for text, (skill, args) in cases.items():
            intent = engine.classify(text)
            self.assertEqual((intent.kind, intent.skill, intent.args), ("command", skill, args), text)
        self.assertEqual(engine.classify("pare").kind, "cancel", "'pare' sozinho continua cancelando")
        self.assertEqual(engine.classify("ajuste o robô").kind, "response", "sem valor: pergunta qual")

    def test_sentences_that_only_mention_the_robot_are_not_commands_to_it(self):
        """Um "sim" distraído para "calibrar o Noctário?" moveria o robô quando a pessoa queria um lembrete."""
        from ultron.cognition.intent_engine import IntentEngine
        engine = IntentEngine()
        cases = {"lembre-me de calibrar o robô amanhã às 9h": "secondbrain.capture",
                 "me lembre de dar a partida no Noctário às 15h": "secondbrain.capture",
                 "anote uma ideia: dar a partida no robô mais devagar": "secondbrain.capture",
                 "crie uma tarefa para testar os motores do Noctário": "secondbrain.capture",
                 "adicione uma tarefa: calibrar o Noctário": "secondbrain.capture",
                 "pesquise na internet como calibrar sensores QTR do robô": "web.search",
                 "anote que a parada de emergência do robô falhou": "memory.remember"}
        for text, skill in cases.items():
            self.assertEqual(engine.classify(text).skill, skill, text)
        self.assertIsNone(engine.classify("como calibrar o Noctário?").skill, "pergunta: conversa")
        for text in ("pare o Noctário", "robô, pare!", "emergência do robô", "parada de emergência"):
            self.assertEqual(engine.classify(text).skill, "noctario.emergency_stop", text)


class SkillValidationTest(unittest.TestCase):
    def test_arguments_are_checked_before_any_authorization(self):
        from ultron.skills.noctario import MotorTest, SetParams
        self.assertEqual(SetParams().validate({"kd": 0.12, "onlink": "continue", "ldir": -1}),
                         {"kd": 0.12, "onlink": "continue", "ldir": -1})
        for bad in ({"kd": float("nan")}, {"kp": float("inf")}, {"kp": 0.5}, {"ldir": 0}, {"voar": 1},
                    {"base": 300}, {"onlink": "talvez"}):
            with self.assertRaises(ValueError, msg=bad):
                SetParams().validate(bad)
        self.assertEqual(MotorTest().validate({"l": 120, "r": 0}), {"l": 120, "r": 0})
        for bad in ({"l": 300, "r": 0}, {"l": 100}, {"l": 100, "r": 100, "ms": 5000}):
            with self.assertRaises(ValueError, msg=bad):
                MotorTest().validate(bad)


class TransportTest(unittest.TestCase):
    def test_unconfigured_links_explain_what_is_missing(self):
        with self.assertRaises(TransportError) as raised:
            RfcommTransport("").open()
        self.assertIn("endereço Bluetooth do Noctário não configurado", str(raised.exception))
        with self.assertRaises(TransportError) as raised:
            SerialTransport("").open()
        self.assertIn("porta COM do Noctário não configurada", str(raised.exception))

    def test_bluetooth_failure_is_a_transport_error(self):
        """Sem Bluetooth no computador (ou sem o robô), o motivo chega à interface — a thread não morre."""
        try:
            RfcommTransport("00:11:22:33:44:55").open(timeout=0.5)
        except TransportError as exc:
            self.assertTrue(str(exc))
        else:                                              # só se houvesse um robô de verdade neste endereço
            self.fail("conectou a um endereço de teste")

    def test_settings_choose_the_transport(self):
        self.assertIsInstance(from_settings(helpers.make_settings(noctario_transport="serial", noctario_port="COM7")),
                              SerialTransport)
        rfcomm = from_settings(helpers.make_settings(noctario_transport="rfcomm",
                                                     noctario_address="AA:BB:CC:DD:EE:FF"))
        self.assertEqual(rfcomm.label, "Bluetooth AA:BB:CC:DD:EE:FF canal 1")
        sim = from_settings(helpers.make_settings(noctario_transport="simulator"))
        self.assertTrue(sim.simulated)
        self.assertEqual(sim.label, "SIMULADOR (não é o robô)")


class StoreTest(unittest.TestCase):
    def test_samples_round_trip_and_retention(self):
        samples = [{"t": i / 20, "error": i - 50, "corr": 0.5, "pwm_l": 200, "pwm_r": 190, "lost": False,
                    "cross": i // 30, "pos": 3500 + i} for i in range(100)]
        self.assertEqual(unpack(pack(samples)), samples)
        store = NoctarioStore(helpers.make_memory().db)
        with mock.patch("ultron.noctario.store.KEEP_RUNS", 3):
            for i in range(5):
                store.save_run({"id": f"v{i}", "started": 1000.0 + i, "finished": 1001.0 + i, "duration_s": 30.0,
                                "result": "concluida", "source": "simulador", "params": {"base": 220, "max": 220},
                                "crossings": [1.0], "losses": 0, "samples": samples, "summary": {}})
        runs = store.runs(10)
        self.assertEqual([r["id"] for r in runs], ["v4", "v3", "v2"])
        self.assertEqual((runs[0]["params"]["base_pwm"], runs[0]["params"]["error_range"]), (220, 3500))
        self.assertEqual(len(runs[0]["samples"]), 100)
        self.assertEqual(store.runs(1, samples=False)[0]["samples"], [])


# ====================================================================== serviço contra um robô roteirizado
class ScriptedServiceTest(unittest.TestCase):
    def tearDown(self):
        service = getattr(self, "service", None)
        if service is not None:
            service.disconnect(quiet=True)

    def test_connection_failure_is_reported_not_hidden(self):
        transport = ScriptedTransport(fail_open="o Noctário não respondeu (desligado)")
        self.service, bus, activity, _ = make_service(lambda: transport)
        outcome = self.service.connect(timeout=2.0)
        self.assertFalse(outcome["ok"])
        self.assertIn("desligado", outcome["detail"])
        self.assertEqual(self.service.link, "desconectado")
        self.assertEqual(self.service.health()["status"], "UNAVAILABLE")
        self.assertIn("Conexão com o Noctário falhou", activity.titles())
        status = self.service.status()
        self.assertEqual(status["state_label"], "sem dado do robô")
        self.assertEqual(self.service.command("START").outcome, "NO_LINK")

    def test_silent_robot_never_counts_as_connected(self):
        transport = ScriptedTransport(hello=False)
        self.service, *_ = make_service(lambda: transport)
        started = time.monotonic()
        outcome = self.service.connect(timeout=0.4)
        self.assertFalse(outcome["ok"])
        self.assertIn("não respondeu (HELLO)", outcome["detail"])
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertFalse(self.service.connected)

    def test_deaf_robot_means_unknown_state_and_repeated_stop(self):
        transport = ScriptedTransport()                    # diz HELLO e depois nunca responde
        self.service, bus, activity, _ = make_service(lambda: transport)
        self.assertTrue(self.service.connect(timeout=2.0)["ok"])
        self.assertEqual(self.service.confirmed["state"], "READY")
        with mock.patch.object(service_module, "CONFIRM_WINDOW", 0.3):
            result = self.service.command("START", timeout=0.3)
            self.assertEqual(result.outcome, "TIMEOUT")
            self.assertEqual(result.describe(), "sem resposta do robô para START: estado desconhecido")
            time.sleep(0.35)
            self.assertEqual(self.service.requested_status()["status"],
                             "sem confirmação do robô — estado desconhecido")
        self.assertEqual(self.service.status()["state"], "READY", "o confirmado continua o que o robô disse")
        ops = self.service.store.ops(5)
        self.assertEqual((ops[0]["verb"], ops[0]["outcome"]), ("START", "TIMEOUT"))
        with mock.patch.object(service_module, "ESTOP_WINDOW", 0.5), \
                mock.patch.object(service_module, "ESTOP_REPEAT", 0.05):
            outcome = self.service.estop(origin="teste")
            self.assertTrue(outcome["sent"])
            self.assertTrue(wait_until(lambda: any("sem confirmação do robô" in t for t in activity.titles()), 3))
        self.assertGreaterEqual(transport.sent().count(b"!"), 4, "o '!' é repetido até o robô confirmar")
        self.assertEqual(self.service.store.ops(1)[0]["outcome"], "TIMEOUT")

    def test_garbage_from_the_robot_does_not_break_the_link(self):
        transport = ScriptedTransport()
        self.service, *_ = make_service(lambda: transport)
        self.assertTrue(self.service.connect(timeout=2.0)["ok"])
        transport.push(b"\xff\xfe\x00 lixo\n", "ACK x", "EVT", "TEL t=abc st=VOAR", b"Z" * 1000,
                       "STA st=RUN cal=1 x=1 xt=4 lap=500 why=- fw=teste-1 tel=20 onlink=stop hb=1500")
        self.assertTrue(wait_until(lambda: self.service.confirmed["state"] == "RUN", 3))
        self.assertTrue(self.service.connected)
        self.assertEqual(self.service.status()["crossings"], 1)

    def test_answers_are_matched_by_sequence(self):
        def answer(line):
            parts = line.split()
            if parts[:1] == ["CMD"] and parts[2] == "PING":
                return [f"ACK {int(parts[1]) + 100} pong=1", f"ACK {parts[1]} pong=1 t=5"]
            return []
        transport = ScriptedTransport(answer=answer)
        self.service, *_ = make_service(lambda: transport)
        self.assertTrue(self.service.connect(timeout=2.0)["ok"])
        result = self.service.command("PING", timeout=1.0)
        self.assertEqual((result.outcome, result.fields.get("t")), ("ACK", "5"), "o ACK de outra sequência não vale")


# ====================================================================== serviço contra o SIMULADOR
class SimulatorServiceTest(unittest.TestCase):
    def setUp(self):
        self.sim = NoctarioSimulator(speed=25, seed=3)
        self.transports = []

        def factory():
            transport = SimulatorTransport(self.sim)
            self.transports.append(transport)
            return transport
        self.service, self.bus, self.activity, self.tardis = make_service(factory, noctario_telemetry_hz=25)
        outcome = self.service.connect(timeout=3.0)
        self.assertTrue(outcome["ok"], outcome)

    def tearDown(self):
        self.service.disconnect(quiet=True)
        self.sim.close()

    def calibrate(self):
        result = self.service.calibrate(ms=1000)
        self.assertEqual(result.outcome, "ACK", result.describe())
        self.assertTrue(self.service.wait_confirmed({"READY"}, 3.0))

    def test_1_simulator_is_labelled_and_telemetry_rate_follows_settings(self):
        self.assertTrue(self.service.simulated)
        self.assertEqual(self.service.fw, "simulador-1.0")
        self.assertIn("SIMULADOR", self.service.health()["detail"])
        self.assertTrue(wait_until(lambda: self.service.params.get("tel") == 25, 3), self.service.params)
        tel_ops = [op for op in self.service.store.ops(10) if op["verb"] == "TEL"]
        self.assertEqual((tel_ops[0]["origin"], tel_ops[0]["outcome"], tel_ops[0]["source"]),
                         ("configuração", "ACK", "simulador"))
        self.assertTrue(wait_until(lambda: len(self.service.recent_series(5)) > 5, 3), "telemetria chegando")
        self.assertEqual(self.bus.of("NOCTARIO_LINK")[-1]["link"], "conectado")

    def test_2_refusals_come_from_the_robot_or_from_local_limits(self):
        start = self.service.start_run()
        self.assertEqual((start.outcome, start.code), ("NAK", "NOCAL"))
        self.assertIn("o robô recusou START", start.describe())
        invalid = self.service.set_params({"kp": 0.5})
        self.assertEqual((invalid.outcome, invalid.seq), ("INVALID", None), "fora do limite: nem é enviado")
        self.assertIn("fora do limite", invalid.describe())
        self.assertEqual(self.service.set_params({"base": 240}).outcome, "INVALID")
        loop = self.service.command("SET", {"loop": 400})
        self.assertEqual(loop.outcome, "ACK", "parado, o ritmo do laço pode mudar")
        self.assertTrue(wait_until(lambda: self.service.params.get("loop") == 400, 2))

    def test_3_lap_is_recorded_with_confirmed_parameters(self):
        self.calibrate()
        tuned = self.service.set_params({"kd": "0,12"})
        self.assertTrue(tuned.ok, tuned.describe())
        self.assertEqual(self.service.params["kd"], 0.12)
        self.assertEqual(self.tardis.notes[-1]["text"], "[SIMULADOR] Parâmetros confirmados pelo robô: kd=0.12")
        self.assertEqual((self.tardis.notes[-1]["project"], self.tardis.notes[-1]["kind"]), ("Noctário", "parametro"))
        start = self.service.start_run()
        self.assertEqual((start.outcome, start.confirmed), ("ACK", "RUN"))
        self.assertEqual(self.service.requested_status()["status"], "confirmado")
        self.assertTrue(wait_until(lambda: self.service.confirmed["state"] == "DONE", 15), self.service.status())
        self.assertTrue(wait_until(lambda: self.service.last_run is not None, 2))
        last = self.service.last_run
        self.assertEqual((last["result"], last["source"], len(last["crossings"])), ("concluida", "simulador", 4))
        self.assertGreater(last["duration_s"], 10.0, "tempo de volta do SIMULADOR (em tempo simulado)")
        stored = self.service.store.runs(1)[0]
        self.assertEqual((stored["id"], stored["params"]["kd"], stored["params"]["base_pwm"]), (last["id"], 0.12, 220))
        self.assertGreater(len(stored["samples"]), 50)
        self.assertEqual(self.bus.of("NOCTARIO_RUN")[-1]["result"], "concluida")
        self.assertTrue(any(t.startswith("[SIMULADOR] Volta do Noctário: concluída") for t in self.activity.titles()))

    def test_4_emergency_stop_mid_run_is_confirmed_and_latched(self):
        self.calibrate()
        self.assertTrue(self.service.start_run().ok)
        time.sleep(0.2)
        outcome = self.service.estop(origin="teste")
        self.assertTrue(outcome["sent"])
        self.assertTrue(self.service.wait_confirmed({"ESTOP"}, 1.0), "o robô confirma a parada")
        self.assertTrue(wait_until(lambda: self.service.last_run is not None, 2))
        self.assertEqual(self.service.last_run["result"], "emergencia")
        self.assertIn("PARADA DE EMERGÊNCIA confirmada pelo robô", [a["text"].replace("[SIMULADOR] ", "")
                                                                    for a in self.service.recent_alerts()])
        again = self.service.start_run()
        self.assertEqual((again.outcome, again.code), ("NAK", "ESTOP"), "só sai da emergência com CLEAR")
        cleared = self.service.clear()
        self.assertEqual((cleared.outcome, cleared.confirmed), ("ACK", "READY"))

    def test_5_link_loss_alerts_reconnects_and_never_restarts(self):
        self.calibrate()
        self.assertTrue(self.service.start_run().ok)
        time.sleep(0.15)
        self.transports[-1].drop()
        self.assertTrue(wait_until(lambda: self.service.link == "perdido", 3))
        alert = self.service.recent_alerts(1)[0]
        self.assertIn("Link com o Noctário perdido durante o movimento — o firmware aplica a política: parar",
                      alert["text"])
        self.assertTrue(wait_until(lambda: self.service.link == "conectado", 5), "reconectou sozinho")
        self.assertTrue(wait_until(lambda: self.service.confirmed["state"] not in ("RUN", "LOST", "STOPPING"), 15))
        starts = [op for op in self.service.store.ops(50) if op["verb"] == "START"]
        self.assertEqual(len(starts), 1, "reconectar nunca dá partida")
        self.assertTrue(wait_until(lambda: self.service.last_run is not None, 2))
        self.assertTrue(self.service.last_run["summary"]["partial"], "a volta com lacuna fica marcada")

    def test_7_stopping_a_bench_test_is_confirmed_and_is_not_a_lap(self):
        self.calibrate()
        self.sim.speed = 1.0                               # tempo real: o teste de 3 s não acaba sozinho antes
        bench = self.service.command("MOTOR", {"l": 60, "r": 60, "ms": 3000})
        self.assertEqual((bench.outcome, bench.confirmed), ("ACK", "TEST"))
        stop = self.service.stop_run()
        self.assertEqual((stop.outcome, stop.confirmed), ("ACK", "READY"), "parou na hora, sem rampa")
        self.assertEqual(self.service.requested_status()["status"], "confirmado")
        time.sleep(0.3)
        self.assertIsNone(self.service.last_run, "teste de bancada não vira volta")
        self.assertEqual(self.service.store.runs(5), [])
        self.assertEqual(self.bus.of("NOCTARIO_RUN"), [])

    def test_6_disconnect_records_the_firmware_policy(self):
        self.service.disconnect()
        self.assertEqual(self.service.link, "desconectado")
        record = next(i for i in self.activity.items if i["title"].endswith("Noctário desconectado"))
        self.assertEqual(record["result"], "política do firmware sem link: parar")
        self.assertFalse(self.service.estop()["sent"])
        self.assertIn("use o botão físico", self.service.estop()["detail"])


# ====================================================================== pelo núcleo do JARVIS
STORY_DELAY = 3.0


def responder(payload):
    messages = payload.get("messages") or []
    last = str(messages[-1].get("content", "")) if messages else ""
    if "dragões" in last:
        time.sleep(STORY_DELAY)                            # o modelo "pensando" bastante
        return "Era uma vez um dragão."
    if payload.get("tools") and "bancada" in last:
        return {"content": "", "tool_calls": [{"function": {"name": "noctario.start", "arguments": {}}}]}
    return "Certo."


class CoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ultron.config.settings import SettingsManager
        from ultron.core.events import EventType
        from ultron.core.neural_core import NeuralCore
        cls.EventType = EventType
        cls.fake = FakeOllama(["qwen2.5:3b"], responder=responder)
        cls.fake.__enter__()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = cls.fake.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        manager.settings.noctario_transport = "simulator"
        cls.settings = manager.settings
        cls.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
        cls.sim = NoctarioSimulator(speed=10, seed=4)
        cls.core.noctario._simulator = cls.sim              # simulador acelerado (a volta inteira em ~3 s)
        cls.responses = []
        cls.auth = []
        cls.core.bus.subscribe(EventType.RESPONSE_READY, lambda e: cls.responses.append(e.payload), name="t")
        cls.core.bus.subscribe(EventType.AUTHORIZATION_REQUIRED, lambda e: cls.auth.append(e.payload), name="t.a")
        cls.core.boot()

    @classmethod
    def tearDownClass(cls):
        cls.core.shutdown()
        cls.sim.close()
        cls.fake.__exit__(None, None, None)

    @property
    def service(self):
        return self.core.noctario

    def final(self, seconds=20, after=0):
        end = time.time() + seconds
        while time.time() < end:
            final = [r for r in self.responses[after:] if not r.get("partial")]
            if final:
                return final[-1]
            time.sleep(0.02)
        self.fail("sem resposta final")

    def ask(self, text, seconds=20):
        mark = len(self.responses)
        self.assertTrue(self.core.submit(text, source="text"))
        return self.final(seconds, mark)

    def authorize(self, text, approve=True):
        mark = len(self.responses)
        self.assertTrue(self.core.submit(text, source="text"))
        self.assertTrue(wait_until(lambda: self.core.authorizations.pending() is not None, 10), text)
        request = self.core.authorizations.pending()
        self.core.authorizations.resolve(approve, by="teste")
        return request, self.final(20, mark)

    def ensure_ready(self):
        if not self.service.connected:
            self.assertTrue(self.service.connect()["ok"])
        state = self.service.confirmed.get("state")
        if state == "ESTOP":
            self.assertTrue(self.service.clear().ok)
        if not self.service.wait_confirmed({"READY", "STOP", "DONE"}, 0.1):
            self.assertTrue(self.service.calibrate(ms=1000).ok)
            self.assertTrue(self.service.wait_confirmed({"READY"}, 5))

    def starts(self):
        return [op for op in self.service.store.ops(100) if op["verb"] == "START"]

    def test_1_connect_and_status_by_text(self):
        response = self.ask("conecte o Noctário")
        self.assertIn("[SIMULADOR] Noctário conectado (SIMULADOR (não é o robô))", response["text"])
        status = self.ask("qual o estado do Noctário?")
        self.assertIn("estado informado pelo robô", status["text"])
        self.assertIn("sensores NÃO calibrados", status["text"])
        self.assertIn("sem link o firmware para", status["text"])
        self.assertEqual(self.core.health.check_all()["checks"]["NOCTARIO"]["status"], "OK")

    def test_2_motion_needs_specific_authorization_every_time(self):
        if not self.service.connected:
            self.assertTrue(self.service.connect()["ok"])
        request, response = self.authorize("calibre o Noctário")
        self.assertEqual((request.skill, request.permission, request.category),
                         ("noctario.calibrate", "robo", "robot_config"))
        self.assertIn("calibrar os sensores do Noctário por 3 s", request.description)
        self.assertFalse(request.standing_allowed(), "comando ao robô nunca vira 'sim, sempre'")
        self.assertIn("Sensores calibrados", response["text"])
        before = len(self.starts())
        request, response = self.authorize("dê a partida no Noctário", approve=False)
        self.assertEqual((request.skill, request.category), ("noctario.start", "robot_motion"))
        self.assertEqual(len(self.starts()), before, "negado: nada foi enviado ao robô")
        self.assertNotIn(self.service.confirmed["state"], ("RUN", "LOST"))
        request, response = self.authorize("dê a partida no Noctário", approve=True)
        self.assertIn("Noctário em movimento, confirmado pelo robô", response["text"])
        self.assertEqual(len(self.starts()), before + 1)
        self.assertTrue(wait_until(lambda: self.service.confirmed["state"] == "DONE", 20))

    def test_3_emergency_stop_does_not_wait_for_a_busy_model(self):
        self.ensure_ready()
        self.assertTrue(self.service.start_run(origin="teste").ok)
        mark = len(self.responses)
        self.assertTrue(self.core.submit("me conte uma história bem longa sobre dragões", source="text"))
        time.sleep(0.3)                                    # o pedido já está com o modelo
        started = time.monotonic()
        self.assertTrue(self.core.submit("pare o Noctário", source="voice"))
        sent_in = time.monotonic() - started
        self.assertTrue(self.service.wait_confirmed({"ESTOP"}, 1.5))
        confirmed_in = time.monotonic() - started
        story_done = any("dragão" in str(r.get("text", "")) for r in self.responses[mark:])
        self.assertFalse(story_done, "o modelo ainda estava ocupado quando o robô parou")
        self.assertLess(sent_in, 0.2, f"'!' enviado em {sent_in * 1000:.0f} ms")
        self.assertLess(confirmed_in, 1.0, f"ESTOP confirmado em {confirmed_in * 1000:.0f} ms")
        self.assertTrue(wait_until(lambda: any("confirmada pelo robô" in str(r.get("text", ""))
                                               for r in self.responses[mark:]), 3))
        self.assertTrue(wait_until(lambda: any("dragão" in str(r.get("text", "")) for r in self.responses[mark:]),
                                   STORY_DELAY + 10), "a conversa continua depois")

    def test_4_blocked_robot_category_refuses_motion_but_never_the_stop(self):
        self.ensure_ready()
        original = self.settings.permission_policy
        self.settings.permission_policy = ("robo=bloquear",)
        try:
            before = len(self.starts())
            response = self.ask("dê a partida no Noctário")
            self.assertIn("bloqueada", response["text"])
            self.assertEqual(len(self.starts()), before)
            self.assertIsNone(self.core.authorizations.pending())
            self.core.submit("parada de emergência", source="voice")
            self.assertTrue(self.service.wait_confirmed({"ESTOP"}, 1.5), "a parada nunca é bloqueada")
            stop = self.core.run_skill("noctario.stop")
            self.assertEqual(stop["status"], "executed", "a parada suave também é emergência")
        finally:
            self.settings.permission_policy = original
        self.assertTrue(self.service.clear(origin="teste").ok)

    def test_5_cancel_with_the_robot_moving_stops_the_robot(self):
        self.ensure_ready()
        self.assertTrue(self.service.start_run(origin="teste").ok)
        response = self.ask("cancelar")
        self.assertTrue(self.service.wait_confirmed({"ESTOP"}, 1.5))
        self.assertTrue(response["text"])
        self.assertTrue(self.service.clear(origin="teste").ok)

    def test_7_bench_motor_test_by_voice_needs_authorization(self):
        self.ensure_ready()
        request, response = self.authorize("teste o motor esquerdo do Noctário")
        self.assertEqual((request.skill, request.category), ("noctario.motor_test", "robot_motion"))
        self.assertIn("esquerdo 120, direito 0 por 500 ms (rodas fora do chão)", request.description)
        self.assertIn("Teste de motores em andamento, confirmado pelo robô", response["text"])
        self.assertTrue(wait_until(lambda: self.service.confirmed["state"] == "READY", 5), "volta a pronto sozinho")
        sensors = self.ask("leia os sensores do Noctário")
        self.assertIn("pino do cruzamento em nível", sensors["text"])

    def test_6_the_model_cannot_move_the_robot(self):
        self.ensure_ready()
        registry = self.core.registry
        hidden = {"noctario.start", "noctario.calibrate", "noctario.set_params", "noctario.motor_test",
                  "noctario.clear", "noctario.save_params", "noctario.defaults", "noctario.reset_crossings"}
        offered = {s["function"]["name"] for s in registry.schemas()}
        self.assertFalse(hidden & offered, "nunca oferecidas ao modelo")
        catalog = registry.catalog_text(200)
        self.assertFalse(any(name + "(" in catalog for name in hidden), "nem ao planejador")
        self.assertIn("noctario.status(", catalog)
        before, auth_before = len(self.starts()), len(self.auth)
        self.fake.requests.clear()
        intent = self.core.intents.classify("organize minha bancada de trabalho para amanhã")
        self.assertNotEqual(intent.kind, "command", intent)
        with self.assertLogs("ultron.reasoning", "WARNING") as logs:
            response = self.ask("organize minha bancada de trabalho para amanhã", seconds=30)
        self.assertIn("modelo pediu ferramenta não oferecida: noctario.start", "\n".join(logs.output))
        asked_tools = [p for p in self.fake.chat_requests() if p.get("tools")]
        self.assertTrue(asked_tools, "o pedido passou pelo modo com ferramentas")
        self.assertNotIn("noctario.start", {t["function"]["name"] for t in asked_tools[0]["tools"]})
        time.sleep(0.3)
        self.assertEqual(len(self.starts()), before, "a ferramenta inventada pelo modelo não rodou")
        self.assertEqual(len(self.auth), auth_before, "nem chegou a pedir autorização")
        self.assertIn("Nenhuma ação foi executada", response["text"])
        self.assertNotIn("verificad", response["text"], "nada executado não é 'feito e verificado'")
        self.assertFalse(response.get("verified"))


# ====================================================================== painel NOCTÁRIO
@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class PageUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets

        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        from ultron.hud.controller import HudController

        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.fake = FakeOllama(["qwen2.5:3b"])
        cls.fake.__enter__()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = cls.fake.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        manager.settings.noctario_transport = "simulator"
        cls.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
        cls.sim = NoctarioSimulator(speed=10, seed=6)
        cls.core.noctario._simulator = cls.sim
        cls.controller = HudController(cls.core)
        cls.controller.window.resize(1440, 900)
        cls.controller.show()
        threading.Thread(target=cls.core.boot, daemon=True).start()
        cls.pump_until(lambda: cls.core.booted, 30)
        cls.page = cls.controller.open_page("noctario")
        cls.pump(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.controller.quit()
        cls.core.shutdown()
        cls.sim.close()
        cls.pump(0.3)
        cls.fake.__exit__(None, None, None)

    @classmethod
    def pump(cls, seconds):
        from PySide6 import QtCore
        end = time.time() + seconds
        while time.time() < end:
            cls.app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            time.sleep(0.005)

    @classmethod
    def pump_until(cls, condition, seconds):
        from PySide6 import QtCore
        end = time.time() + seconds
        while time.time() < end:
            cls.app.processEvents(QtCore.QEventLoop.AllEvents, 20)
            if condition():
                return True
            time.sleep(0.005)
        return bool(condition())

    def chip(self):
        self.controller.window.refresh_chips()
        return next(c for c in self.controller.window.chips.chips if c.key == "noct")

    def test_1_without_connection_nothing_is_invented(self):
        page = self.page
        self.assertTrue(page.isVisible())
        self.assertTrue(page.banner.text().startswith("SEM CONEXÃO — nenhum dado do robô"), page.banner.text())
        self.assertEqual(page.state.text(), "—")
        self.assertEqual(page.graph.message, "SEM CONEXÃO — nenhum dado do robô")
        self.assertEqual(page.graph.samples, [])
        self.assertTrue(all(v.text() in ("—", "nenhuma") for v in page.values.values()),
                        {k: v.text() for k, v in page.values.items()})
        self.assertFalse(any(b.isEnabled() for b in page.motion_buttons), "sem link, nada de comandos")
        self.assertIn("MOTOR ESQUERDO", [b.text() for b in page.motion_buttons])
        ldir = page._fields["ldir"]
        self.assertEqual([ldir.itemText(i) for i in range(ldir.count())], ["invertido", "normal"])
        self.assertTrue(page.stop_button.isVisible() and page.stop_button.isEnabled(), "a PARADA sempre visível")
        self.assertIn("F12", page.stop_button.text())
        chip = self.chip()
        self.assertEqual((chip.value, chip.level), ("SEM CONEXÃO", "off"))
        page.stop_button.click()
        self.assertIn("PARADA NÃO enviada: SEM CONEXÃO — use o botão físico", page.feedback.text())
        self.pump(0.1)
        self.assertIn("SEM CONEXÃO", page.alerts.item(0).text())

    def test_2_simulator_data_is_labelled_and_drawn(self):
        page = self.page
        self.assertTrue(self.core.noctario.connect()["ok"])
        self.assertTrue(self.pump_until(lambda: page.banner.text().startswith("SIMULADOR — não é o robô"), 5))
        chip = self.chip()
        self.assertTrue(chip.value.startswith("SIM · "), chip.value)
        self.assertEqual(chip.level, "warn")
        self.assertTrue(self.pump_until(lambda: abs(page._fields["kp"].value() - 0.0125) < 1e-9, 3))
        self.assertTrue(self.core.noctario.calibrate(ms=1000).ok)
        self.assertTrue(self.core.noctario.wait_confirmed({"READY"}, 5))
        self.assertTrue(self.core.noctario.start_run(origin="teste").ok)
        self.assertTrue(self.pump_until(lambda: len(page.graph.samples) > 10, 5), "o gráfico recebe a telemetria")
        self.assertEqual(len(page.bars.values), 8)
        self.assertNotEqual(page.values["pwm"].text(), "—")
        self.assertEqual(page.state.text(), "EM PERCURSO")
        from PySide6 import QtCore, QtTest
        QtTest.QTest.keyClick(self.controller.window, QtCore.Qt.Key_F12)
        self.assertTrue(self.pump_until(lambda: self.core.noctario.confirmed.get("state") == "ESTOP", 2),
                        "F12 para o robô de qualquer página")
        self.assertTrue(self.pump_until(lambda: self.chip().level == "error", 2))
        self.assertTrue(self.core.noctario.clear(origin="teste").ok)

    def test_3_parameters_go_through_the_authorization(self):
        page = self.page
        if not self.core.noctario.connected:
            self.assertTrue(self.core.noctario.connect()["ok"])
        self.assertTrue(self.pump_until(lambda: "kd" in self.core.noctario.params and page.apply_button.isEnabled(), 5))
        page._fields["kd"].setValue(0.12)
        page.apply_params()
        self.assertTrue(self.pump_until(lambda: self.core.authorizations.pending() is not None, 5))
        request = self.core.authorizations.pending()
        self.assertEqual((request.skill, request.permission), ("noctario.set_params", "robo"))
        self.assertIn("Kd → 0.12", request.description)
        self.assertNotEqual(self.core.noctario.params.get("kd"), 0.12, "nada enviado antes do 'sim'")
        self.core.authorizations.resolve(True, by="teste")
        self.assertTrue(self.pump_until(lambda: self.core.noctario.params.get("kd") == 0.12, 5))
        self.assertTrue(self.pump_until(lambda: "Parâmetros confirmados pelo robô" in page.feedback.text(), 5),
                        page.feedback.text())


if __name__ == "__main__":
    unittest.main()
