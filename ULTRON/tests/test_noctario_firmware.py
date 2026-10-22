"""Firmware do Noctário compilado no PC (g++): os testes do núcleo e a equivalência com o simulador.

O núcleo C++ (``firmware/noctario/src/noct_core.cpp``) e o modelo do simulador do JARVIS
(``ultron/noctario/simulator.py``, ``FirmwareModel``) precisam se comportar igual: o segundo é o que os
testes e a interface usam sem o robô. Aqui uma volta inteira roda no simulador (física + modelo, em malha
fechada) e cada leitura de sensor e cada comando ficam gravados; o mesmo roteiro é reproduzido no núcleo C++
e as saídas são comparadas LINHA A LINHA — mensagens, eventos, telemetria e o PWM de cada ciclo.

Não é teste do robô real: não há ESP32, motor, sensor nem Bluetooth aqui. Sem compilador C++, os testes são
pulados (e dizem por quê).
"""
import math
import shutil
import subprocess
import unittest

import helpers

from ultron.noctario import simulator

FIRMWARE = helpers.ROOT / "firmware" / "noctario"
CXX = shutil.which("g++") or shutil.which("clang++")
DESVIO = 0.15      # m: tira a linha de debaixo da barra; a busca do lado certo a reencontra
FLAGS = ["-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror", "-ffp-contract=off"]


def build(name: str):
    out = helpers.temp_dir("fw-") / name
    sources = [str(FIRMWARE / "test" / "host" / f"{name}.cpp"), str(FIRMWARE / "src" / "noct_core.cpp")]
    result = subprocess.run([CXX, *FLAGS, "-o", str(out), *sources, "-lm"], capture_output=True, text=True,
                            timeout=180)
    if result.returncode != 0:
        raise AssertionError(f"compilação falhou:\n{result.stderr[-3000:]}")
    return out


def normalize(line: str) -> str:
    """NAK: o código e a sequência importam; o texto explicativo é livre em cada lado."""
    if line.startswith("NAK "):
        return " ".join(part for part in line.split() if not part.startswith("msg="))
    return line


def scenario():
    """Uma sessão longa no SIMULADOR, em malha fechada, gravando o roteiro e a saída do modelo Python.

    Passa por: comandos válidos e inválidos, calibração, teste de motores, volta interrompida pela parada de
    emergência, volta completa até o destino, perda de linha (com reencontro e com parada), cão de guarda do
    link, desconexão e reconexão, linha longa demais, campos demais e padrões de fábrica.
    """
    model = simulator.FirmwareModel()
    physics = simulator.Physics(simulator.TestTrack(), seed=5)
    script: list[str] = []
    expected: list[str] = []
    agenda = {2: ["CMD 1 PING", "bom dia", "CMD 2 VOAR", "CMD 3 START", "CMD 4 SET kp=0.5", "CMD 5 SET base=240",
                  "CMD 6 TEL hz=10", "CMD 7 CAL ms=1500"],
              1600: ["CMD 8 SET kd=0,12 adapt=0.3", "CMD 9 PARAMS", "CMD 10 SENS", "CMD 11 MOTOR l=90 r=-90 ms=600"],
              1800: ["CMD 32 STOP"],                                 # STOP encerra o teste de bancada na hora
              2200: ["CMD 12 START"],
              9000: ["CMD 13 SET loop=400", "CMD 14 STATUS", "CMD 15 SET kp=0.014"],
              20000: ["CMD 16 S\\!"],                              # parada de emergência no meio de uma linha
              20500: ["CMD 17 CLEAR"],
              21000: ["CMD 18 RESETX", "CMD 19 START"]}
    marks: dict[str, int] = {}
    heartbeat = True

    def drain() -> list[str]:
        new = list(model.out)
        model.out.clear()
        expected.extend(new)
        return new

    def send(text: str):
        if text in ("C", "D"):
            script.append(text)
            model.connect() if text == "C" else model.disconnect()
        else:
            script.append("B " + text.replace("!", "\\!"))
            model.feed(text.encode("ascii") + b"\n")
        drain()

    def at(when: int, *lines: str):
        agenda.setdefault(when, []).extend(lines)

    send("C")
    now = 0
    state_before = model.state
    while now < 150000 and "fim" not in marks:
        now += 2
        for text in agenda.pop(now, []):
            send(text)
        if heartbeat and now % 200 == 0:
            send("HB")
        if model.state == "CAL":
            physics.y = 0.05 * math.sin(math.tau * now / 1000.0)
        if state_before == "CAL" and model.state != "CAL":
            physics.y, physics.psi = 0.0, 0.0
        if model.state == "RUN" and state_before in ("READY", "STOP", "DONE"):
            physics = simulator.Physics(simulator.TestTrack(), seed=7)
            marks["partida"] = now
        state_before = model.state
        raw, cross = physics.sensors(), physics.cross_pin()
        script.append(f"T {now} {' '.join(str(v) for v in raw)} {int(cross)}")
        left, right = model.tick(now, raw, cross)
        events = " | ".join(drain())
        expected.append(f"PWM {left} {right}")
        physics.step(0.002, (left, right))
        if "EVT done" in events and "destino" not in marks:          # 2ª volta completa: outra partida
            marks["destino"] = now
            at(now + 300, "CMD 20 INFO", "CMD 21 SAVE")
            at(now + 600, "CMD 22 START")
        elif "destino" in marks and "desvio" not in marks and model.state == "RUN" \
                and now - marks["partida"] >= 3000:                  # robô empurrado para fora da linha
            marks["desvio"] = now
            physics.y += DESVIO if model.last_err >= 0 else -DESVIO
        elif "EVT found" in events and "reencontro" not in marks:
            marks["reencontro"] = now
            at(now + 1000, "CMD 23 STOP")
        elif "EVT stop reason=cmd" in events and "parada" not in marks:
            marks["parada"] = now
            at(now + 300, "CMD 24 START")
        elif "parada" in marks and "sumiço" not in marks and model.state == "RUN" \
                and now - marks["partida"] >= 2000:                  # robô tirado da pista
            marks["sumiço"] = now
            physics.y += 0.3
        elif "EVT stop reason=lost" in events and "perdido" not in marks:
            marks["perdido"] = now
            at(now + 300, "CMD 25 START")
        elif "perdido" in marks and "mudo" not in marks and model.state == "RUN" \
                and now - marks["partida"] >= 1000:                  # o PC para de mandar o batimento
            marks["mudo"] = now
            heartbeat = False
        elif "EVT stop reason=link" in events and "link" not in marks:
            marks["link"] = now
            heartbeat = True
            at(now + 200, "D")
            at(now + 1000, "C", "CMD 26 STATUS", "X" * 300, " ".join(["CMD", "27", "SET"] + ["a=1"] * 40),
               "CMD 28 DEFAULTS", "CMD 29 TEL hz=0", "CMD 30 STOP")
            at(now + 1500, "CMD 31 PING", "CMD 33 CAL ms=2000 auto=1")
            at(now + 1800, "CMD 34 STOP", "CMD 35 START")            # calibração girando interrompida
        elif "link" in marks and now >= marks["link"] + 2500:
            marks["fim"] = now
    return script, expected, model, marks


@unittest.skipUnless(CXX, "compilador C++ (g++ ou clang++) não encontrado: firmware não testado")
class FirmwareHostTest(unittest.TestCase):
    def test_core_unit_tests(self):
        binary = build("test_core")
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("núcleo do firmware aprovado", result.stdout)

    def test_arduino_layer_type_checks_against_api_stubs(self):
        """``main.cpp`` contra cabeçalhos com as assinaturas do arduino-esp32 2.x e 3.x: pega erro de tipo e de
        sintaxe na camada da ESP32. NÃO é a compilação real para a ESP32 (essa é o primeiro ``pio run``)."""
        src, stubs = FIRMWARE / "src", FIRMWARE / "test" / "host" / "stubs"
        for major in (2, 3):
            result = subprocess.run([CXX, "-std=gnu++17", "-fsyntax-only", "-Wall", "-Wextra", "-Werror",
                                     f"-DESP_ARDUINO_VERSION_MAJOR={major}", "-I", str(stubs), "-I", str(src),
                                     str(src / "main.cpp")], capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, f"arduino-esp32 {major}.x: {result.stderr[-2000:]}")

    def test_firmware_matches_the_simulator_line_by_line(self):
        script, expected, model, marks = scenario()
        def seen(prefix: str) -> bool:
            return any(line.startswith(prefix) for line in expected)

        self.assertTrue(seen("EVT cal ok=1"), "a calibração da volta de teste aconteceu")
        self.assertTrue(seen("EVT estop src=bt"), "a parada de emergência foi exercitada")
        self.assertTrue(seen("NAK 3 code=NOCAL"), "START sem calibração foi recusado")
        self.assertTrue(seen("ACK 11 st=TEST"), "o teste de bancada dos motores foi exercitado")
        self.assertTrue(seen("EVT done lap_ms="), "uma volta chegou ao destino")
        self.assertTrue(seen("EVT lost") and seen("EVT found"), "a linha foi perdida e reencontrada")
        self.assertTrue(seen("EVT stop reason=lost"), "a linha foi perdida de vez e o robô parou")
        self.assertTrue(seen("EVT stop reason=link"), "o cão de guarda do link parou o robô")
        self.assertTrue(seen("NAK 0 code=SYNTAX msg=linha_longa_demais"))
        self.assertTrue(seen("NAK 0 code=SYNTAX msg=campos_demais"))
        self.assertTrue(seen("ACK 28 defaults=1"))
        self.assertTrue(seen("ACK 32 st=READY"), "STOP encerrou o teste de bancada")
        self.assertTrue(seen("ACK 34 st=IDLE") and seen("NAK 35 code=NOCAL"),
                        "calibração interrompida: sem calibração, sem partida")
        bench = expected[expected.index("ACK 11 st=TEST"):expected.index("ACK 32 st=READY")]
        self.assertFalse(any(line.startswith(("EVT stop", "STA st=STOPPING")) for line in bench),
                         "teste de bancada não é volta")
        self.assertIn("fim", marks, f"o roteiro chegou ao fim: {marks}")
        crossings = [line for line in expected if line.startswith("EVT cross")]
        self.assertGreaterEqual(len(crossings), 2, "a volta de teste passou por cruzamentos")
        binary = build("replay")
        result = subprocess.run([str(binary)], input="\n".join(script) + "\n", capture_output=True, text=True,
                                timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        produced = result.stdout.splitlines()
        self.assertEqual(len(produced), len(expected), "mesmo número de linhas")
        for index, (mine, theirs) in enumerate(zip(produced, expected)):
            if normalize(mine) != normalize(theirs):
                context = "\n".join(expected[max(0, index - 3):index])
                self.fail(f"linha {index} difere:\n  C++   : {mine}\n  Python: {theirs}\n  antes:\n{context}")
        tel = sum(1 for line in expected if line.startswith("TEL "))
        pwm = sum(1 for line in expected if line.startswith("PWM "))
        self.assertGreater(tel, 500)
        self.assertGreater(pwm, 25000, f"{pwm} ciclos do laço comparados")


if __name__ == "__main__":
    unittest.main()
