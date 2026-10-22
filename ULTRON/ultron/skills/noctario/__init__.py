"""Skills do Noctário — o caminho de voz, texto e botões até o robô, pelo executor do JARVIS.

* PARADA (``noctario.emergency_stop`` e ``noctario.stop``) é emergência: nunca bloqueada nem condicionada a
  confirmação, com qualquer política de permissões;
* movimento (partida, calibração, teste de motores) e parâmetros são "comandos ao robô" (mínimo:
  confirmar) e categorias SENSÍVEIS (autorização específica a cada vez); o modelo de linguagem não os
  aciona por conta própria (``expose_to_llm = False``) — só pedidos diretos;
* leituras (estado, sensores, parâmetros, cruzamentos, alertas) não mudam nada no robô;
* cada resposta diz o que o ROBÔ confirmou. Sem confirmação: "estado desconhecido", nunca "feito".
"""
from __future__ import annotations

import time

from ...noctario import protocol
from ...noctario.protocol import PARAMS, fmt, state_label
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema

NOT_RUNNING = "o serviço do Noctário não está ativo nesta execução"


def _service(ctx):
    extras = ctx.extras or {}
    return extras.get("noctario") or getattr(extras.get("core"), "noctario", None)


def _tag(service) -> str:
    return "[SIMULADOR] " if service is not None and service.simulated else ""


def _no_link(service) -> SkillResult:
    detail = service.link_detail if service is not None and service.link_detail else ""
    return SkillResult(False, error="sem conexão com o Noctário" + (f" ({detail})" if detail else "") +
                       " — conecte em NOCTÁRIO ou diga 'conecte o Noctário'", error_kind="NETWORK_ERROR")


def _from_command(service, result, ok_text: str) -> SkillResult:
    data = {"outcome": result.outcome, "seq": result.seq, "fields": result.fields, "confirmed": result.confirmed,
            "latency_ms": result.latency_ms, "simulated": service.simulated}
    if result.ok:
        return SkillResult(True, _tag(service) + ok_text, [f"ACK {result.seq} em {result.latency_ms} ms"], data)
    kind = {"NAK": "REFUSED", "TIMEOUT": "TIMEOUT", "NO_LINK": "NETWORK_ERROR", "INVALID": "INVALID_ARGUMENT"}
    return SkillResult(False, error=_tag(service) + result.describe()[:1].upper() + result.describe()[1:],
                       error_kind=kind.get(result.outcome, "UNKNOWN_ERROR"), data=data)


class _NoctarioSkill(Skill):
    category = "devices"
    expose_to_llm = True

    def available(self):
        return True, ""

    def run(self, ctx, fn):
        service = _service(ctx)
        if service is None:
            return SkillResult(False, error=NOT_RUNNING, error_kind="UNSUPPORTED")
        return fn(service)

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.9, [check("robot_ack", True, "resposta do robô (ACK/estado)")])


# ------------------------------------------------------------------ conexão (não move nada)
class Connect(_NoctarioSkill):
    name = "noctario.connect"
    description = "Conectar ao Noctário (porta, endereço ou simulador configurados). Não dá partida."
    inputs = schema({})
    risk = Risk.LOW
    permission = "configurar"

    def execute(self, ctx, **_):
        def go(service):
            outcome = service.connect(origin="user")
            if not outcome["ok"]:
                return SkillResult(False, error=f"Noctário não conectado: {outcome['detail']}", error_kind="NETWORK_ERROR")
            status = service.status()
            return SkillResult(True, f"{_tag(service)}Noctário conectado ({status['transport']}). Estado informado "
                                     f"pelo robô: {status['state_label']}.", [outcome["detail"]], status)
        return self.run(ctx, go)

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        service = _service(ctx)
        ok = service is not None and service.connected
        return VerificationResult.from_checks([check("linked", ok, "HELLO recebido do robô" if ok else "sem link")])


class Disconnect(_NoctarioSkill):
    name = "noctario.disconnect"
    description = "Desconectar do Noctário. Sem link, vale a política do firmware (parar ou terminar o percurso)."
    inputs = schema({})
    risk = Risk.LOW
    permission = "configurar"

    def execute(self, ctx, **_):
        def go(service):
            policy = service.params.get("onlink", "")
            moving = service.confirmed.get("state") in protocol.MOVING
            service.disconnect(origin="user")
            note = ""
            if moving:
                note = " O robô estava em movimento: sem link, o firmware " + (
                    "para." if policy == "stop" else "termina o percurso." if policy == "continue" else
                    "aplica a política configurada nele.")
            return SkillResult(True, f"Noctário desconectado.{note}", [], {"policy": policy})
        return self.run(ctx, go)


# ------------------------------------------------------------------ paradas (emergência: nunca bloqueadas)
class EmergencyStop(_NoctarioSkill):
    name = "noctario.emergency_stop"
    description = "PARADA DE EMERGÊNCIA do Noctário: corta os motores imediatamente."
    inputs = schema({})
    risk = Risk.NONE
    emergency = True

    def execute(self, ctx, **_):
        def go(service):
            outcome = service.estop(origin="user")
            if not outcome["sent"]:
                return SkillResult(False, error=outcome["detail"], error_kind="NETWORK_ERROR", data=outcome)
            confirmed = service.wait_confirmed({"ESTOP"}, 1.6)
            if confirmed:
                return SkillResult(True, f"{_tag(service)}Parada de emergência confirmada pelo robô.",
                                   ["estado ESTOP reportado pelo robô"], {"confirmed": True})
            return SkillResult(False, error=f"{_tag(service)}Parada enviada, mas o robô NÃO confirmou — use o botão "
                                            "físico.", error_kind="TIMEOUT", data={"confirmed": False})
        return self.run(ctx, go)


class Stop(_NoctarioSkill):
    name = "noctario.stop"
    description = "Parar o Noctário com a rampa de frenagem (fim do percurso pedido)."
    inputs = schema({})
    risk = Risk.NONE
    emergency = True

    def execute(self, ctx, **_):
        def go(service):
            result = service.stop_run(origin="user")
            if result.ok:
                service.wait_confirmed({"STOP", "DONE", "ESTOP", "IDLE", "READY"}, 3.0)
            state = service.confirmed.get("state", "")
            return _from_command(service, result, f"Parada pedida; o robô informa: {state_label(state)}.")
        return self.run(ctx, go)


# ------------------------------------------------------------------ movimento e configuração (robô)
class Start(_NoctarioSkill):
    name = "noctario.start"
    description = "Dar a partida no percurso do Noctário (movimento físico)."
    inputs = schema({})
    risk = Risk.MEDIUM
    sensitive = "robot_motion"
    permission = "robo"
    expose_to_llm = False

    def describe_action(self, args):
        return "dar a partida no Noctário (o robô vai se mover)"

    def execute(self, ctx, **_):
        def go(service):
            if not service.connected:
                return _no_link(service)
            result = service.start_run(origin="user")
            if result.ok and service.confirmed.get("state") not in ("RUN", "LOST"):
                if not service.wait_confirmed({"RUN", "LOST"}, 2.0):
                    return SkillResult(False, error="Sem confirmação do robô; estado desconhecido.",
                                       error_kind="TIMEOUT")
            return _from_command(service, result, "Noctário em movimento, confirmado pelo robô.")
        return self.run(ctx, go)


class Clear(_NoctarioSkill):
    name = "noctario.clear"
    description = "Sair da parada de emergência (o robô fica pronto, parado)."
    inputs = schema({})
    risk = Risk.LOW
    sensitive = "robot_config"
    permission = "robo"
    expose_to_llm = False

    def describe_action(self, args):
        return "liberar o Noctário da parada de emergência (fica parado e pronto)"

    def execute(self, ctx, **_):
        def go(service):
            if not service.connected:
                return _no_link(service)
            result = service.clear(origin="user")
            return _from_command(service, result, f"Parada de emergência liberada; o robô informa: "
                                                  f"{state_label(service.confirmed.get('state'))}.")
        return self.run(ctx, go)


class Calibrate(_NoctarioSkill):
    name = "noctario.calibrate"
    description = ("Recalibrar os 8 sensores (manual: passe a barra sobre a linha durante o tempo; automático: o "
                   "robô gira no lugar).")
    inputs = schema({"auto": {"type": "boolean"}, "ms": {"type": "integer", "minimum": 500, "maximum": 20000}})
    risk = Risk.MEDIUM
    permission = "robo"
    expose_to_llm = False

    def sensitive_for(self, args):
        return "robot_motion" if args.get("auto") else "robot_config"

    def describe_action(self, args):
        seconds = int(args.get("ms", 3000)) / 1000
        if args.get("auto"):
            return f"calibrar o Noctário girando no lugar por {seconds:g} s (o robô vai se mover)"
        return f"calibrar os sensores do Noctário por {seconds:g} s (passe a barra sobre a linha)"

    def execute(self, ctx, auto: bool = False, ms: int = 3000):
        def go(service):
            if not service.connected:
                return _no_link(service)
            result = service.calibrate(auto=auto, ms=ms, origin="user")
            if not result.ok:
                return _from_command(service, result, "")
            finished = service.wait_confirmed({"READY", "IDLE"}, ms / 1000 + 3.0)
            state = service.confirmed.get("state")
            if not finished:
                return SkillResult(False, error="Calibração sem confirmação do robô; estado desconhecido.",
                                   error_kind="TIMEOUT")
            if state != "READY":
                return SkillResult(False, error="Calibração recusada pelo robô: sensores sem contraste suficiente "
                                                "(passe a barra sobre a linha e o fundo).", error_kind="REFUSED")
            return SkillResult(True, f"{_tag(service)}Sensores calibrados; robô pronto.", ["estado READY"],
                               {"state": state})
        return self.run(ctx, go)


_TUNABLE = {key: ({"type": "number", "minimum": spec.low, "maximum": spec.high} if spec.kind == "float" else
                  {"type": "integer", "minimum": int(spec.low), "maximum": int(spec.high)} if spec.kind == "int" else
                  {"type": "string", "enum": list(spec.choices)}) for key, spec in PARAMS.items()}


class SetParams(_NoctarioSkill):
    name = "noctario.set_params"
    description = "Ajustar parâmetros do Noctário (Kp, Kd, PWM base e máximo, rampas, cruzamentos...), com limites."
    inputs = schema(_TUNABLE)
    risk = Risk.MEDIUM
    sensitive = "robot_config"
    permission = "robo"
    expose_to_llm = False

    def validate(self, args: dict) -> dict:
        """Tipos e limites de cada campo ANTES de pedir autorização (as regras entre campos, como base ≤
        máximo, usam os valores do robô e ficam para o serviço — e o firmware confere de novo)."""
        clean = super().validate(args)
        return {key: PARAMS[key].coerce(value) for key, value in clean.items()}

    def describe_action(self, args):
        return "ajustar no Noctário: " + ", ".join(f"{PARAMS[k].label} → {fmt(v)}" for k, v in args.items())

    def describe_resource(self, ctx, args):
        service = _service(ctx)
        if service is None or not service.params:
            return ""
        return "atual: " + ", ".join(f"{PARAMS[k].label} {fmt(service.params.get(k))}" for k in args)

    def execute(self, ctx, **values):
        def go(service):
            if not values:
                return SkillResult(False, error="nenhum parâmetro informado", error_kind="INVALID_ARGUMENT")
            if not service.connected:
                return _no_link(service)
            result = service.set_params(values, origin="user")
            if result.ok:
                return SkillResult(True, f"{_tag(service)}Parâmetros confirmados pelo robô: " +
                                   ", ".join(f"{PARAMS[k].label} {fmt(service.params.get(k))}" for k in values) + ".",
                                   [f"PAR do robô: {k}={fmt(service.params.get(k))}" for k in values],
                                   {"params": {k: service.params.get(k) for k in values}})
            if result.outcome == "TIMEOUT" and result.message:
                return SkillResult(False, error=result.message, error_kind="TIMEOUT")
            return _from_command(service, result, "")
        return self.run(ctx, go)

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        service = _service(ctx)
        ok = service is not None and all(service.params.get(k) == v for k, v in result.data["params"].items())
        return VerificationResult.from_checks([check("robot_params", ok, "valores relidos do robô (PAR)" if ok else
                                                     "o robô reporta outros valores")])


class SaveParams(_NoctarioSkill):
    name = "noctario.save_params"
    description = "Gravar os parâmetros atuais na memória do Noctário (valem depois de religar)."
    inputs = schema({})
    risk = Risk.LOW
    sensitive = "robot_config"
    permission = "robo"
    expose_to_llm = False

    def execute(self, ctx, **_):
        def go(service):
            if not service.connected:
                return _no_link(service)
            return _from_command(service, service.command("SAVE", origin="user"), "Parâmetros gravados no robô.")
        return self.run(ctx, go)


class Defaults(_NoctarioSkill):
    name = "noctario.defaults"
    description = "Restaurar os parâmetros padrão do Noctário (só com o robô parado; não grava até SALVAR)."
    inputs = schema({})
    risk = Risk.MEDIUM
    sensitive = "robot_config"
    permission = "robo"
    expose_to_llm = False

    def execute(self, ctx, **_):
        def go(service):
            if not service.connected:
                return _no_link(service)
            return _from_command(service, service.command("DEFAULTS", origin="user"),
                                 "Parâmetros padrão restaurados no robô (ainda não gravados).")
        return self.run(ctx, go)


class ResetCrossings(_NoctarioSkill):
    name = "noctario.reset_crossings"
    description = "Zerar a contagem de cruzamentos do Noctário."
    inputs = schema({})
    risk = Risk.LOW
    sensitive = "robot_config"
    permission = "robo"
    expose_to_llm = False

    def execute(self, ctx, **_):
        def go(service):
            if not service.connected:
                return _no_link(service)
            return _from_command(service, service.command("RESETX", origin="user"), "Cruzamentos zerados no robô.")
        return self.run(ctx, go)


class MotorTest(_NoctarioSkill):
    name = "noctario.motor_test"
    description = "Teste de bancada dos motores (rodas fora do chão), por tempo limitado."
    inputs = schema({"l": {"type": "integer", "minimum": -255, "maximum": 255},
                     "r": {"type": "integer", "minimum": -255, "maximum": 255},
                     "ms": {"type": "integer", "minimum": 100, "maximum": 3000}}, ("l", "r"))
    risk = Risk.MEDIUM
    sensitive = "robot_motion"
    permission = "robo"
    expose_to_llm = False

    def describe_action(self, args):
        return (f"teste de motores do Noctário: esquerdo {args.get('l')}, direito {args.get('r')} por "
                f"{int(args.get('ms', 500))} ms (rodas fora do chão)")

    def execute(self, ctx, l: int, r: int, ms: int = 500):
        def go(service):
            if not service.connected:
                return _no_link(service)
            return _from_command(service, service.command("MOTOR", {"l": l, "r": r, "ms": ms}, origin="user"),
                                 "Teste de motores em andamento, confirmado pelo robô.")
        return self.run(ctx, go)


class Telemetry(_NoctarioSkill):
    name = "noctario.telemetry"
    description = "Ligar, desligar ou mudar a taxa da telemetria do Noctário (0 a 50 Hz)."
    inputs = schema({"hz": {"type": "integer", "minimum": 0, "maximum": 50}}, ("hz",))
    risk = Risk.LOW
    permission = "configurar"

    def execute(self, ctx, hz: int):
        def go(service):
            if not service.connected:
                return _no_link(service)
            text = "Telemetria desligada no robô." if hz == 0 else f"Telemetria a {hz} Hz, confirmada pelo robô."
            return _from_command(service, service.command("TEL", {"hz": hz}, origin="user"), text)
        return self.run(ctx, go)


# ------------------------------------------------------------------ leitura (não muda nada no robô)
class Status(_NoctarioSkill):
    name = "noctario.status"
    description = "Estado do Noctário: link, estado confirmado pelo robô, pedido em andamento, cruzamentos e falhas."
    inputs = schema({})
    risk = Risk.NONE
    permission = "consultar"

    def execute(self, ctx, **_):
        def go(service):
            s = service.status()
            if s["link"] != "conectado":
                return SkillResult(True, f"Noctário {s['link_label']}" + (f" ({s['detail']})" if s["detail"] else "")
                                   + ". Nenhum dado do robô sem conexão.", [], s)
            parts = [f"{_tag(service)}Noctário conectado ({s['transport']}), estado informado pelo robô: "
                     f"{s['state_label']}"]
            requested = s["requested"]
            if requested.get("label") and requested.get("status") != "confirmado":
                parts.append(f"pedido '{requested['label']}': {requested['status']}")
            parts.append(f"cruzamentos {s['crossings']} de {s['target']}")
            if not s["cal"]:
                parts.append("sensores NÃO calibrados")
            if s["policy"]:
                parts.append("sem link o firmware " + ("para" if s["policy"] == "stop" else "continua"))
            if s["last_failure"]:
                parts.append(f"última falha: {s['last_failure']}")
            return SkillResult(True, "; ".join(parts) + ".", [], s)
        return self.run(ctx, go)


class Sensors(_NoctarioSkill):
    name = "noctario.sensors"
    description = "Leitura avulsa dos 8 sensores calibrados, da posição da linha e do contador de cruzamentos."
    inputs = schema({})
    risk = Risk.NONE
    permission = "consultar"

    def execute(self, ctx, **_):
        def go(service):
            if not service.connected:
                return _no_link(service)
            before = service.sensors.get("at", 0)
            result = service.read_sensors(origin="user")
            if not result.ok:
                return _from_command(service, result, "")
            end = time.monotonic() + 1.0
            while service.sensors.get("at", 0) <= before and time.monotonic() < end:
                time.sleep(0.02)
            sensors = service.sensors
            if sensors.get("at", 0) <= before:
                return SkillResult(False, error="o robô confirmou, mas a leitura não chegou", error_kind="TIMEOUT")
            line = "linha vista" if sensors.get("line") else "linha NÃO vista"
            pin = ""
            if sensors.get("xin") is not None:
                active = sensors["xin"] == service.params.get("xact", protocol.DEFAULTS["xact"])
                pin = (f"; pino do cruzamento em nível {'alto' if sensors['xin'] else 'baixo'} "
                       f"({'cruzamento detectado' if active else 'sem cruzamento'} com o nível ativo configurado)")
            return SkillResult(True, f"{_tag(service)}Sensores (0–1000): {' '.join(str(v) for v in sensors['cal'])}; "
                                     f"posição {sensors.get('pos')} (centro 3500), {line}; cruzamentos "
                                     f"{sensors.get('x')}{pin}.", [], dict(sensors))
        return self.run(ctx, go)


class Params(_NoctarioSkill):
    name = "noctario.params"
    description = "Parâmetros atuais do Noctário, lidos do robô."
    inputs = schema({})
    risk = Risk.NONE
    permission = "consultar"

    def execute(self, ctx, **_):
        def go(service):
            if not service.connected:
                return _no_link(service)
            result = service.read_params(origin="user")
            if not result.ok:
                return _from_command(service, result, "")
            time.sleep(0.1)
            p = service.params
            keys = ("kp", "kd", "base", "max", "minpwm", "accel", "decel", "adapt", "cross", "onlink")
            return SkillResult(True, f"{_tag(service)}Parâmetros do robô: " +
                               ", ".join(f"{PARAMS[k].label} {fmt(p.get(k))}" for k in keys if k in p) + ".",
                               [], {"params": dict(p)})
        return self.run(ctx, go)


class Crossings(_NoctarioSkill):
    name = "noctario.crossings"
    description = "Quantos cruzamentos o Noctário contou e quantos faltam até o destino."
    inputs = schema({})
    risk = Risk.NONE
    permission = "consultar"

    def execute(self, ctx, **_):
        def go(service):
            if not service.connected:
                return _no_link(service)
            result = service.command("STATUS", origin="user")
            if not result.ok:
                return _from_command(service, result, "")
            time.sleep(0.05)
            s = service.status()
            left = max(0, s["target"] - s["crossings"]) if s["target"] else None
            text = f"{_tag(service)}{s['crossings']} cruzamento(s) contado(s)" + (
                f"; faltam {left} até o destino." if left is not None else "; sem destino configurado.")
            return SkillResult(True, text, [], {"crossings": s["crossings"], "target": s["target"]})
        return self.run(ctx, go)


class Alerts(_NoctarioSkill):
    name = "noctario.alerts"
    description = "Alertas recentes do Noctário (perda de linha, link, parada de emergência, falhas)."
    inputs = schema({})
    risk = Risk.NONE
    permission = "consultar"

    def execute(self, ctx, **_):
        def go(service):
            alerts = service.recent_alerts(5)
            if not alerts:
                return SkillResult(True, "Nenhum alerta do Noctário nesta sessão.", [], {"alerts": []})
            text = "; ".join(f"{time.strftime('%H:%M:%S', time.localtime(a['at']))} {a['text']}" for a in alerts)
            return SkillResult(True, f"Alertas do Noctário: {text}.", [], {"alerts": alerts})
        return self.run(ctx, go)


SKILLS = (Connect, Disconnect, EmergencyStop, Stop, Start, Clear, Calibrate, SetParams, SaveParams, Defaults,
          ResetCrossings, MotorTest, Telemetry, Status, Sensors, Params, Crossings, Alerts)
