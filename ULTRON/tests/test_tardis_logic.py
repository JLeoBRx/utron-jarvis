"""TARDIS — a camada lógica: protocolo, cadeia de delegação, persistência, analisadores, motor e a cena da
sala de controle (sem Qt).

O modelo de linguagem é sempre um falso (``FakeRouter``); voltas do Noctário são dados de TESTE montados
aqui (senoides com frequência conhecida) — nenhum teste daqui é teste de robô, rede ou microfone reais.
"""
import math
import threading
import time
import unittest

import helpers

from ultron.tardis import protocol
from ultron.tardis.analyzers import Run, TardisContext
from ultron.tardis.analyzers import context as context_analyzer
from ultron.tardis.analyzers import diagnostics as diagnostics_analyzer
from ultron.tardis.analyzers import organization as organization_analyzer
from ultron.tardis.analyzers import planning as planning_analyzer
from ultron.tardis.analyzers import telemetry as telemetry_analyzer
from ultron.tardis.engine import FAULT_WINDOW, TardisEngine
from ultron.tardis.protocol import KINDS, ProposedAction, TaskEnvelope, TaskFailed, TaskResult, check_chain
from ultron.tardis.store import TardisStore


class FakeResult:
    def __init__(self, content, model="modelo-teste:1b"):
        self.content = content
        self.model = model


class FakeRouter:
    """Responde com um texto fixo (ou falha), registrando o que recebeu."""

    def __init__(self, reply="", *, error=None, model="modelo-teste:1b"):
        self.reply, self.error, self.model = reply, error, model
        self.calls = []

    def chat(self, task, messages, **kwargs):
        self.calls.append({"task": task, "messages": messages, **kwargs})
        if self.error is not None:
            raise self.error
        return FakeResult(self.reply, self.model)


class Registry:
    def __init__(self, *names):
        self.names = set(names)

    def __contains__(self, name):
        return name in self.names


class Recorder:
    def __init__(self):
        self.events = []
        self.lock = threading.Lock()

    def publish(self, kind, payload=None, source=""):
        with self.lock:
            self.events.append((getattr(kind, "value", kind), dict(payload or {})))

    def kinds(self):
        with self.lock:
            return [k for k, _ in self.events]

    def of(self, kind):
        with self.lock:
            return [p for k, p in self.events if k == kind]


def make_run(kind="consulta", ctx=None, *, input=None, deadline=30.0):
    envelope = TaskEnvelope(kind=kind, input=dict(input or {}), origin="usuario")
    return Run(envelope, ctx or TardisContext(), time.monotonic() + deadline)


def make_store():
    return TardisStore(helpers.make_memory().db)


def make_second_brain():
    from ultron.secondbrain import SecondBrainService
    memory = helpers.make_memory()
    settings = helpers.make_settings()
    service = SecondBrainService(memory.db, settings_getter=lambda: settings)
    service.start()
    return memory, service


def wait_until(condition, seconds=5.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.01)
    return False


# ====================================================================== protocolo
class ProtocolTest(unittest.TestCase):
    def test_chain_rules_prevent_cycles_and_long_delegation(self):
        self.assertEqual(check_chain("consulta", "jarvis", ["jarvis"]), "")
        self.assertEqual(check_chain("consulta", "usuario", []), "")
        self.assertEqual(check_chain("planejamento", "tardis", ["jarvis", "tardis:consulta"]), "",
                         "sub-análise pedida por outra análise da TARDIS: 2 saltos, sem repetição")
        self.assertIn("desconhecido", check_chain("hackear", "usuario", []))
        self.assertIn("origem desconhecida", check_chain("consulta", "internet", []))
        self.assertIn("longa demais", check_chain("rotinas", "tardis", ["jarvis", "tardis:consulta",
                                                                         "tardis:planejamento"]))
        self.assertIn("ciclo", check_chain("consulta", "tardis", ["jarvis", "tardis:consulta"]))
        self.assertIn("sem a análise", check_chain("consulta", "tardis", ["jarvis"]))
        self.assertIn("não devolve", check_chain("consulta", "jarvis", ["tardis:planejamento", "jarvis"]))

    def test_envelope_round_trip_keeps_every_protocol_field(self):
        envelope = TaskEnvelope(kind="planejamento", input={"goal": "montar a pista"}, origin="jarvis",
                                chain=["jarvis"])
        envelope.state = "DONE"
        envelope.started, envelope.finished, envelope.duration_ms = 10.0, 11.5, 1500
        envelope.model = "modelo-teste:1b (o mesmo do JARVIS)"
        envelope.note("iniciada")
        envelope.result = TaskResult("Plano com 2 etapas.", [{"title": "1. medir", "detail": "", "source": "x"}],
                                     ["plano"], [ProposedAction("guardar o plano", "secondbrain.capture",
                                                                {"text": "Plano"}, "fica no ARQUIVO")],
                                     {"steps": 2})
        data = envelope.to_dict()
        for key in ("id", "input", "state", "result", "error", "created", "started", "finished", "duration_ms",
                    "origin", "log", "model", "chain"):
            self.assertIn(key, data, "campo do protocolo")
        again = TaskEnvelope.from_dict(data)
        self.assertEqual(again.to_dict(), data)
        self.assertIsInstance(again.result.actions[0], ProposedAction)
        self.assertTrue(again.final)
        self.assertEqual(again.label, "planejamento")


# ====================================================================== persistência
class StoreTest(unittest.TestCase):
    def setUp(self):
        self.store = make_store()

    def test_tasks_persist_upsert_and_redact_secrets(self):
        envelope = TaskEnvelope(kind="consulta", input={"question": "qual é a senha do roteador?"}, origin="usuario")
        self.store.save(envelope)
        envelope.state = "FAILED"
        envelope.error = {"code": "NO_DATA", "message": "nada encontrado"}
        self.store.save(envelope)
        stored = self.store.get(envelope.id)
        self.assertEqual(stored.state, "FAILED")
        self.assertEqual(stored.error["code"], "NO_DATA")
        self.assertIn("redigido", stored.input["question"], "texto que parece segredo não é gravado")
        self.assertEqual([t.id for t in self.store.recent(5)], [envelope.id])

    def test_interrupted_tasks_become_cancelled_with_the_reason(self):
        running = TaskEnvelope(kind="rotinas", input={}, origin="usuario", state="RUNNING")
        done = TaskEnvelope(kind="rotinas", input={}, origin="usuario", state="DONE")
        self.store.save(running)
        self.store.save(done)
        self.assertEqual(self.store.interrupted(), 1)
        self.assertEqual(self.store.get(running.id).state, "CANCELLED")
        self.assertEqual(self.store.get(running.id).error["code"], "INTERRUPTED")
        self.assertEqual(self.store.get(done.id).state, "DONE")

    def test_project_memory_notes(self):
        first = self.store.add_note("Kd 0,1 oscilou menos na curva", project="Noctario", kind="parametro",
                                    data={"kd": 0.1})
        self.store.add_note("usar pista de 3 metros", project="Noctario", kind="decisao")
        self.store.add_note("comprar sensores extras", project="Atlas")
        with self.assertRaises(ValueError):
            self.store.add_note("a senha do wifi é 1234")
        with self.assertRaises(ValueError):
            self.store.add_note("texto", kind="segredo")
        noct = self.store.notes(project="Noctario")
        self.assertEqual(len(noct), 2)
        self.assertEqual(self.store.notes(kind="decisao")[0]["kind_label"], "decisão")
        self.assertEqual(self.store.notes(search="curva")[0]["id"], first)
        self.assertEqual(self.store.notes(search="curva")[0]["data"], {"kd": 0.1})
        self.assertEqual(self.store.projects(), ["Atlas", "Noctario"])


# ====================================================================== analisadores
class ContextAnalyzerTest(unittest.TestCase):
    def setUp(self):
        self.memory, self.sb = make_second_brain()
        self.store = make_store()
        self.sb.create("idea", "Painel solar portátil", project="Atlas")
        self.store.add_note("Atlas: decidir a bateria até sexta", project="Atlas", kind="decisao")

    def test_consult_cites_real_sources_and_names_the_same_model(self):
        router = FakeRouter("O projeto Atlas tem a ideia do painel solar portátil [1].")
        ctx = TardisContext(second_brain=self.sb, memory=self.memory, store=self.store, router=router)
        result = context_analyzer.consulta(make_run(ctx=ctx, input={"question": "projeto Atlas"}), {
            "question": "o que existe sobre o projeto Atlas?"})
        self.assertIn("painel solar", result.summary)
        titles = [i["title"] for i in result.items]
        self.assertIn("Painel solar portátil", titles)
        self.assertTrue(any("nota de projeto" in s for s in result.sources))
        prompt = router.calls[0]["messages"][1]["content"]
        self.assertIn("[1]", prompt, "as fontes vão numeradas para o modelo citar")
        self.assertIn("SOMENTE", router.calls[0]["messages"][0]["content"])

    def test_consult_model_label_and_fallback_without_model(self):
        run = make_run(ctx=TardisContext(second_brain=self.sb, router=FakeRouter("Resposta [1].")))
        context_analyzer.consulta(run, {"question": "painel solar"})
        self.assertEqual(run.envelope.model, "modelo-teste:1b (o mesmo do JARVIS)")
        offline = FakeRouter(error=RuntimeError("Ollama indisponível: sem resposta"))
        run = make_run(ctx=TardisContext(second_brain=self.sb, router=offline))
        result = context_analyzer.consulta(run, {"question": "painel solar"})
        self.assertIn("sem modelo", run.envelope.model)
        self.assertIn("Painel solar portátil", result.summary, "sem modelo: a lista do que foi encontrado")

    def test_consult_without_data_fails_instead_of_inventing(self):
        ctx = TardisContext(second_brain=self.sb, router=FakeRouter("inventado"))
        with self.assertRaises(TaskFailed) as raised:
            context_analyzer.consulta(make_run(ctx=ctx), {"question": "receita de bolo de cenoura"})
        self.assertEqual(raised.exception.code, "NO_DATA")
        with self.assertRaises(TaskFailed) as raised:
            context_analyzer.consulta(make_run(ctx=ctx), {"question": ""})
        self.assertEqual(raised.exception.code, "INVALID_INPUT")

    def test_consult_ignores_the_request_that_asked(self):
        from ultron.core.activity import ActivityLog
        activity = ActivityLog(self.memory.db)
        request = activity.begin("pedido", "consulte a TARDIS sobre o Zeppelin", origin="text",
                                 input="consulte a TARDIS sobre o Zeppelin")
        run = make_run(ctx=TardisContext(activity=activity, router=FakeRouter("x")))
        run.related_activity = {request}
        with self.assertRaises(TaskFailed, msg="o próprio pedido não é fonte da resposta"):
            context_analyzer.consulta(run, {"question": "Zeppelin"})
        activity.record("acao", "Pesquisa sobre o Zeppelin concluída", origin="user")
        result = context_analyzer.consulta(run, {"question": "Zeppelin"})
        self.assertEqual([i["title"] for i in result.items], ["Pesquisa sobre o Zeppelin concluída"])

    def test_project_memory_read(self):
        run = make_run("projeto", TardisContext(store=self.store))
        result = context_analyzer.projeto(run, {"project": "Atlas"})
        self.assertIn("1 decisão(s)", result.summary)
        self.assertEqual(run.envelope.model, "sem modelo: análise determinística")
        empty = context_analyzer.projeto(make_run("projeto", TardisContext(store=self.store)), {"project": "Zeta"})
        self.assertIn("Nenhuma nota", empty.summary)


class PlanningAnalyzerTest(unittest.TestCase):
    def test_plan_needs_the_model_and_only_proposes(self):
        ctx = TardisContext(router=FakeRouter(error=RuntimeError("sem modelo de texto")),
                            registry=Registry("secondbrain.capture"))
        with self.assertRaises(TaskFailed) as raised:
            planning_analyzer.planejamento(make_run("planejamento", ctx), {"goal": "montar a pista"})
        self.assertEqual(raised.exception.code, "NO_MODEL")
        reply = ('{"etapas": [{"titulo": "Medir a sala", "detalhe": "3 x 2 m"}, {"titulo": "Comprar fita branca"}],'
                 ' "riscos": ["piso refletivo"]}')
        ctx = TardisContext(router=FakeRouter(reply), registry=Registry("secondbrain.capture"))
        run = make_run("planejamento", ctx)
        result = planning_analyzer.planejamento(run, {"goal": "montar a pista"})
        self.assertEqual(result.data["steps"][0]["title"], "Medir a sala")
        self.assertEqual(result.data["risks"], ["piso refletivo"])
        self.assertEqual([a.skill for a in result.actions], ["secondbrain.capture"])
        self.assertIn("(o mesmo do JARVIS)", run.envelope.model)

    def test_bad_model_output_is_a_failure(self):
        for reply in ("não sei", '{"etapas": []}', "{quebrado"):
            ctx = TardisContext(router=FakeRouter(reply))
            with self.assertRaises(TaskFailed) as raised:
                planning_analyzer.planejamento(make_run("planejamento", ctx), {"goal": "x"})
            self.assertEqual(raised.exception.code, "BAD_MODEL_OUTPUT", reply)


class OrganizationAnalyzerTest(unittest.TestCase):
    def test_duplicates_are_reported_and_archiving_is_only_proposed(self):
        memory, sb = make_second_brain()
        first = sb.create("task", "Comprar cabos")
        second = sb.create("task", "comprar  cabos!")
        sb.create("task", "Revisar contrato")
        run = make_run("organizacao", TardisContext(second_brain=sb, registry=Registry("secondbrain.archive")))
        result = organization_analyzer.organizacao(run, {})
        self.assertEqual(result.data["duplicates"], 1)
        self.assertEqual(result.data["undated"], 3)
        self.assertEqual([a.args["ref"] for a in result.actions], [second.id], "arquiva a cópia mais nova")
        self.assertIn(first.id, result.items[0]["detail"])
        self.assertEqual(sb.get(second.id).status, "open", "nada foi arquivado: só proposto")
        self.assertTrue(result.summary.startswith("1 grupo de duplicados"))

    def test_routines_without_data(self):
        memory, sb = make_second_brain()
        result = organization_analyzer.rotinas(make_run("rotinas", TardisContext(second_brain=sb, memory=memory)), {})
        self.assertIn("Nenhum lembrete futuro", result.summary)


def lap(lap_id, *, duration=60.0, freq=0.0, amplitude=0.0, rate=50.0, params=None, losses=None, pwm=None,
        source="robo", result="concluida", crossings=(12.0, 28.0, 45.0, 58.0)):
    """Volta de TESTE: erro senoidal de frequência conhecida (não é telemetria de robô)."""
    params = {"kp": 0.0125, "kd": 0.1, "base_pwm": 220, "max_pwm": 220, "error_range": 3500, **(params or {})}
    n = int(duration * rate)
    samples = []
    for i in range(n):
        t = i / rate
        error = amplitude * math.sin(math.tau * freq * t) if freq else amplitude
        left, right = pwm(t) if pwm else (180.0, 180.0)
        samples.append({"t": t, "error": error, "pwm_l": left, "pwm_r": right})
    out = {"id": lap_id, "duration_s": duration, "params": params, "samples": samples, "source": source,
           "result": result, "crossings": list(crossings)}
    if losses is not None:
        out["losses"] = losses
    return out


class TelemetryAnalyzerTest(unittest.TestCase):
    def test_without_service_or_laps_there_is_nothing_to_analyze(self):
        with self.assertRaises(TaskFailed) as raised:
            telemetry_analyzer.telemetria(make_run("telemetria"), {})
        self.assertEqual(raised.exception.code, "NO_DATA")
        ctx = TardisContext(noctario_runs=lambda limit: [])
        with self.assertRaises(TaskFailed) as raised:
            telemetry_analyzer.telemetria(make_run("telemetria", ctx), {})
        self.assertIn("nenhuma volta", str(raised.exception))

    def test_metrics_are_measured_from_the_samples(self):
        metrics = telemetry_analyzer.lap_metrics(lap("v1", duration=20.0, freq=3.0, amplitude=1000.0))
        self.assertAlmostEqual(metrics["error_rms"], 1000.0 / math.sqrt(2), delta=5.0)
        self.assertAlmostEqual(metrics["error_rms_norm"], 0.202, delta=0.005)
        self.assertAlmostEqual(metrics["dominant_hz"], 3.0, delta=0.1)
        self.assertAlmostEqual(metrics["zero_cross_hz"], 6.0, delta=0.2, msg="dois cruzamentos por ciclo")
        self.assertEqual(metrics["saturation"], 0.0)
        self.assertEqual(metrics["crossings"], 4)
        self.assertEqual(metrics["crossing_intervals"], [12.0, 16.0, 17.0, 13.0])
        self.assertIsNone(metrics["losses"], "sem campo de perdas: não é estimado")

    def test_losses_and_saturation(self):
        samples_lap = lap("v2", duration=10.0, pwm=lambda t: (220.0, 120.0) if t < 4 else (150.0, 150.0))
        for i, sample in enumerate(samples_lap["samples"]):
            sample["lost"] = 100 <= i < 110 or 300 <= i < 305
        metrics = telemetry_analyzer.lap_metrics(samples_lap)
        self.assertAlmostEqual(metrics["saturation"], 0.4, delta=0.01)
        self.assertEqual(metrics["losses"], 2)

    def test_oscillation_hypothesis_is_explained_and_only_proposed(self):
        laps = [lap("v2", duration=62.0, freq=4.0, amplitude=1400.0)]
        ctx = TardisContext(noctario_runs=lambda limit: laps, registry=Registry("noctario.set_params"))
        result = telemetry_analyzer.telemetria(make_run("telemetria", ctx), {})
        self.assertTrue(any("Kd +15%" in s["title"] for s in result.data["suggestions"]))
        self.assertEqual(result.actions[0].skill, "noctario.set_params")
        self.assertEqual(result.actions[0].args, {"kd": 0.115})
        self.assertIn("hipótese", result.actions[0].reason)
        self.assertIn("Nenhuma sugestão garante", result.summary)
        no_skill = TardisContext(noctario_runs=lambda limit: laps)
        self.assertEqual(telemetry_analyzer.telemetria(make_run("telemetria", no_skill), {}).actions, [],
                         "sem a skill do robô, nada é proposto")

    def test_simulated_laps_are_labeled_and_never_become_robot_actions(self):
        laps = [lap("s1", freq=4.0, amplitude=1400.0, source="simulador")]
        ctx = TardisContext(noctario_runs=lambda limit: laps, registry=Registry("noctario.set_params"))
        result = telemetry_analyzer.telemetria(make_run("telemetria", ctx), {})
        self.assertIn("NÃO são dados do robô", result.summary)
        self.assertEqual(result.actions, [])
        self.assertTrue(result.data["simulated"])

    def test_slower_lap_points_back_to_the_best_measured_parameters(self):
        laps = [lap("v3", duration=70.0, params={"kp": 0.02}), lap("v2", duration=64.0)]
        ctx = TardisContext(noctario_runs=lambda limit: laps, registry=Registry("noctario.set_params"))
        result = telemetry_analyzer.telemetria(make_run("telemetria", ctx), {})
        self.assertEqual(result.data["best"], "v2")
        self.assertEqual(result.actions[0].args, {"kp": 0.0125})
        self.assertIn("melhor", result.data["suggestions"][0]["title"])


class FakeHealth:
    def __init__(self, checks):
        self.last = {"overall": "FAIL", "timestamp": time.time(), "checks": checks}


class FakeLifecycle:
    def statuses(self):
        return {"memory": "RUNNING", "network": "FAILED"}

    def health_of(self, name):
        class Status:
            detail = "porta ocupada"
        return Status()


class FakeRuntime:
    def status(self):
        return {"ai": {"alive": True, "pending": 0, "current": None},
                "voice": {"alive": False, "pending": 3, "current": None},
                "memory": {"alive": True, "pending": 25, "current": "consolidação"}}


class DiagnosticsAnalyzerTest(unittest.TestCase):
    def test_findings_have_source_and_severity(self):
        checks = {"CPU": {"status": "OK", "detail": "10%"},
                  "VOICE": {"status": "FAIL", "detail": "saída: sem dispositivo"},
                  "NETWORK": {"status": "WARN", "detail": "DNS lento"},
                  "GPU": {"status": "UNAVAILABLE", "detail": "nvidia-smi ausente"}}
        ctx = TardisContext(health=FakeHealth(checks), lifecycle=FakeLifecycle(), runtime=FakeRuntime(),
                            voice_probe=lambda: {"enabled": True, "capturing": False, "reason": "microfone mudo"},
                            registry=Registry("voice.diagnose", "network.diagnose"))
        result = diagnostics_analyzer.diagnostico(make_run("diagnostico", ctx), {})
        titles = {i["title"]: i["severity"] for i in result.items}
        self.assertEqual(titles["Voz: falha"], "alta")
        self.assertEqual(titles["Rede: atenção"], "média")
        self.assertEqual(titles["GPU: indisponível"], "baixa")
        self.assertEqual(titles["Componente network falhou"], "alta")
        self.assertEqual(titles["Worker voice parado"], "alta")
        self.assertEqual(titles["Worker memory com fila acumulada"], "média")
        self.assertEqual(titles["Microfone com aviso"], "média")
        self.assertNotIn("CPU: OK", titles)
        self.assertEqual(result.items[0]["severity"], "alta", "mais grave primeiro")
        self.assertEqual({a.skill for a in result.actions}, {"voice.diagnose", "network.diagnose"})
        self.assertTrue(result.summary.startswith("7 ponto(s) de atenção: 3 crítico(s), 3 aviso(s) e 1 "
                                                  "informativo(s)"), result.summary)

    def test_coordination_snapshot(self):
        bus, state = helpers.make_bus_state()
        ctx = TardisContext(state=state, runtime=FakeRuntime(),
                            voice_probe=lambda: {"enabled": True, "capturing": True, "listening": True})
        result = diagnostics_analyzer.coordenacao(make_run("coordenacao", ctx), {})
        self.assertIn("JARVIS em repouso", result.summary)
        self.assertIn("Workers: 2/3 ativos", result.summary)
        self.assertIn("microfone capturando, escutando", result.summary)
        with self.assertRaises(TaskFailed):
            diagnostics_analyzer.coordenacao(make_run("coordenacao"), {})


# ====================================================================== motor
class EngineTest(unittest.TestCase):
    def setUp(self):
        self.bus = Recorder()
        self.memory = helpers.make_memory()
        from ultron.core.activity import ActivityLog
        self.activity = ActivityLog(self.memory.db)
        self.store = TardisStore(self.memory.db)
        self.calls = []
        self.analyzers = {"consulta": self.ok, "organizacao": self.fails, "rotinas": self.loops,
                          "diagnostico": self.hangs, "coordenacao": self.ok}
        self.engine = TardisEngine(self.store, TardisContext(), bus=self.bus, activity=self.activity,
                                   analyzers=self.analyzers)
        self.saved_kinds = dict(KINDS)

    def tearDown(self):
        self.engine.stop()
        KINDS.clear()
        KINDS.update(self.saved_kinds)

    def ok(self, run, data):
        self.calls.append(run.envelope.kind)
        run.note("lido")
        return TaskResult(f"ok: {data.get('question', '')}", [{"title": "a", "detail": "", "source": "teste"}],
                          ["teste"])

    def fails(self, run, data):
        raise TaskFailed("NO_DATA", "nada para organizar")

    def loops(self, run, data):
        while True:
            run.check()
            time.sleep(0.01)

    def hangs(self, run, data):
        time.sleep(6)
        run.envelope.model = "escrito depois do abandono"
        return TaskResult("tarde demais")

    def short_deadline(self, kind, seconds):
        KINDS[kind] = protocol.KindSpec(kind, KINDS[kind].label, seconds, KINDS[kind].panel)

    def test_request_runs_saves_logs_and_emits_events_in_order(self):
        self.engine.start()
        request = self.activity.begin("pedido", "consulte a TARDIS", origin="text")
        with self.activity.scope(request):
            task = self.engine.request("consulta", {"question": "x"}, origin="jarvis", chain=["jarvis"])
        self.assertEqual(task.state, "DONE")
        self.assertEqual(task.result.summary, "ok: x")
        self.assertIsNotNone(task.duration_ms)
        self.assertTrue(any("lido" in line for line in task.log))
        self.assertEqual(self.store.get(task.id).state, "DONE", "gravada no banco do JARVIS")
        kinds = [k for k in self.bus.kinds() if k.startswith("TARDIS_TASK_")]
        self.assertEqual(kinds, ["TARDIS_TASK_QUEUED", "TARDIS_TASK_STARTED", "TARDIS_TASK_FINISHED"])
        started = self.bus.of("TARDIS_TASK_STARTED")[0]
        self.assertEqual((started["origin"], started["kind_label"]), ("jarvis", "consulta contextual"))
        record = [a for a in self.activity.recent(10) if a["kind"] == "tardis"][0]
        self.assertEqual((record["state"], record["parent"], record["ref"]), ("concluido", request, task.id))

    def test_rejected_cycle_and_engine_not_started(self):
        task = self.engine.submit("consulta", {"question": "x"})
        self.assertEqual(task.state, "REJECTED")
        self.assertIn("não está em funcionamento", task.error["message"])
        self.engine.start()
        cycle = self.engine.submit("consulta", {"question": "x"}, origin="tardis", chain=["jarvis", "tardis:consulta"])
        self.assertEqual(cycle.state, "REJECTED")
        self.assertIn("ciclo", cycle.error["message"])
        self.assertEqual(self.calls, [], "uma tarefa recusada nunca roda")
        self.assertEqual(len(self.bus.of("TARDIS_TASK_REJECTED")), 2)
        self.assertEqual(self.store.get(cycle.id).state, "REJECTED")

    def test_failure_lights_the_fault_mode_for_a_while(self):
        self.engine.start()
        task = self.engine.request("organizacao", {})
        self.assertEqual((task.state, task.error["code"]), ("FAILED", "NO_DATA"))
        state = self.engine.state()
        self.assertEqual(state["mode"], "falha")
        self.assertIn("nada para organizar", state["fault_text"])
        self.assertGreater(state["fault_until"], time.time() + FAULT_WINDOW - 1)

    def test_deadline_cancel_and_abandoned_analysis(self):
        self.engine.start()
        self.short_deadline("rotinas", 0.3)
        slow = self.engine.request("rotinas", {})
        self.assertEqual((slow.state, slow.error["code"]), ("FAILED", "TIMEOUT"))
        self.short_deadline("diagnostico", 0.2)
        hung = self.engine.submit("diagnostico", {})
        queued = self.engine.submit("consulta", {"question": "depois"})
        hung = self.engine.wait(hung.id, 5)
        self.assertEqual((hung.state, hung.error["code"]), ("FAILED", "TIMEOUT"))
        self.assertLess(hung.duration_ms, 4000, "abandonada no prazo + tolerância")
        self.assertEqual(self.engine.wait(queued.id, 5).state, "DONE", "a fila segue depois de uma análise travada")
        time.sleep(0.1)
        self.assertNotEqual(self.engine.get(hung.id).model, "escrito depois do abandono")
        self.short_deadline("rotinas", 30)
        running = self.engine.submit("rotinas", {})
        waiting = self.engine.submit("consulta", {"question": "na fila"})
        self.assertTrue(wait_until(lambda: self.engine.state()["running"] is not None))
        self.assertTrue(self.engine.cancel(waiting.id, "não precisa mais"))
        self.assertEqual(self.engine.get(waiting.id).state, "CANCELLED")
        self.assertTrue(self.engine.cancel(running.id))
        running = self.engine.wait(running.id, 3)
        self.assertEqual(running.state, "CANCELLED")
        self.assertNotIn("na fila", [c for c in self.calls], "cancelada na fila: nunca rodou")
        self.assertFalse(self.engine.cancel(running.id), "já terminou")

    def test_cancel_from_the_caller_and_cancel_all_by_origin(self):
        self.engine.start()
        token = threading.Event()

        class Token:
            @property
            def cancelled(self):
                return token.is_set()

        self.short_deadline("rotinas", 30)
        threading.Timer(0.3, token.set).start()
        task = self.engine.request("rotinas", {}, origin="jarvis", chain=["jarvis"], cancel=Token())
        self.assertEqual(task.state, "CANCELLED")
        mine = self.engine.submit("rotinas", {}, origin="usuario")
        theirs = self.engine.submit("consulta", {"question": "x"}, origin="jarvis", chain=["jarvis"])
        self.assertEqual(self.engine.cancel_all("cancelar", origin="jarvis"), 1)
        self.assertEqual(self.engine.get(theirs.id).state, "CANCELLED")
        self.assertFalse(self.engine.get(mine.id).final, "a análise pedida na sala continua")

    def test_modes_follow_real_work(self):
        self.engine.start()
        self.assertEqual(self.engine.state()["mode"], "repouso")
        self.short_deadline("rotinas", 30)
        task = self.engine.submit("rotinas", {}, origin="jarvis", chain=["jarvis"])
        self.assertTrue(wait_until(lambda: self.engine.state()["mode"] == "jarvis"))
        self.engine.cancel(task.id)
        self.engine.wait(task.id, 3)
        with self.engine.operation("backup do banco"):
            self.assertEqual(self.engine.state()["mode"], "operacao")
            self.assertEqual(self.engine.state()["operations"], ["backup do banco"])
        self.assertTrue(wait_until(lambda: self.engine.state()["mode"] == "repouso"))
        self.assertIn("TARDIS_STATE", self.bus.kinds())

    def test_restart_marks_interrupted_and_stop_cancels_the_queue(self):
        left = TaskEnvelope(kind="consulta", input={"question": "x"}, origin="usuario", state="RUNNING")
        self.store.save(left)
        self.engine.start()
        self.assertEqual(self.engine.interrupted_on_start, 1)
        self.assertEqual(self.store.get(left.id).error["code"], "INTERRUPTED")
        self.short_deadline("rotinas", 30)
        running = self.engine.submit("rotinas", {})
        queued = self.engine.submit("consulta", {"question": "y"})
        self.assertTrue(wait_until(lambda: self.engine.state()["running"] is not None))
        self.engine.stop()
        self.assertEqual(self.engine.get(queued.id).error["code"], "SHUTDOWN")
        self.assertEqual(self.engine.wait(running.id, 3).state, "CANCELLED")
        self.assertFalse(self.engine._thread.is_alive(), "a thread da TARDIS terminou")
        self.assertEqual(self.engine.health()["status"], "UNKNOWN")

    def test_health_and_project_notes(self):
        self.assertEqual(self.engine.health()["status"], "UNKNOWN")
        self.engine.start()
        self.assertEqual(self.engine.health()["status"], "OK")
        note = self.engine.add_note("Kd 0,12 na curva longa", project="Noctario", kind="parametro")
        self.assertEqual(self.store.notes(project="Noctario")[0]["id"], note)
        self.assertTrue(any(a["kind"] == "tardis" and "Memória de projeto" in a["title"]
                            for a in self.activity.recent(5)))


# ====================================================================== cena da sala (sem Qt)
class RoomSceneTest(unittest.TestCase):
    def setUp(self):
        from ultron.hud.tardis_room.scene import RoomScene
        self.scene = RoomScene()

    def settle(self, seconds=4.0):
        for _ in range(int(seconds * 30)):
            self.scene.step(1 / 30)

    def test_rotor_follows_the_engine_mode(self):
        from ultron.hud.tardis_room.scene import CYAN, MODES
        scene = self.scene
        self.settle()
        self.assertFalse(scene.in_motion(), "em repouso e sem painel, nada força quadros")
        scene.set_engine_state({"mode": "jarvis", "running": {"kind_label": "consulta"}})
        self.settle()
        self.assertAlmostEqual(scene.speed, MODES["jarvis"].speed, places=2)
        self.assertTrue(all(abs(a - b) < 2 for a, b in zip(scene.color, CYAN)))
        self.assertGreater(scene.beam, 0.95, "feixe JARVIS ⇄ TARDIS só na consulta do JARVIS")
        offsets = []
        for _ in range(200):
            scene.step(1 / 30)
            offsets.append(scene.rotor_offset())
        self.assertTrue(0.0 <= min(offsets) and max(offsets) <= 1.0)
        self.assertGreater(max(offsets) - min(offsets), 0.8, "o rotor sobe e desce de verdade")
        scene.set_engine_state({"mode": "falha", "fault": True, "fault_text": "x"})
        self.settle()
        self.assertLess(scene.beam, 0.05)
        self.assertGreater(scene.fault_glow, 0.95)
        self.assertTrue(scene.in_motion())
        scene.set_engine_state({"mode": "desconhecido"})
        self.assertEqual(scene.mode, "repouso")

    def test_panels_light_with_real_tasks(self):
        scene = self.scene
        scene.task_event("TARDIS_TASK_STARTED", {"kind": "planejamento"})
        self.settle(1.5)
        self.assertGreater(scene.panels["planejamento"].level, 0.9)
        self.assertEqual(scene.panels["analise"].level, 0.0)
        scene.task_event("TARDIS_TASK_FINISHED", {"kind": "planejamento", "summary": "Plano com 3 etapas",
                                                  "model": "qwen2.5:3b (o mesmo do JARVIS)"})
        self.assertEqual(scene.panels["planejamento"].flash, 1.0)
        self.assertEqual(scene.model_label, "qwen2.5:3b")
        scene.task_event("TARDIS_TASK_STARTED", {"kind": "organizacao"})
        scene.task_event("TARDIS_TASK_FAILED", {"kind": "organizacao", "error": {"message": "sem dados"},
                                                "model": "sem modelo: análise determinística"})
        self.assertEqual(scene.panels["arquivo"].fault, 1.0)
        self.assertEqual(scene.model_label, "qwen2.5:3b", "análise determinística não vira 'modelo'")
        self.settle(12)
        self.assertFalse(scene.in_motion(), "luzes apagam sozinhas")

    def test_selecting_a_panel_turns_the_camera_and_stops(self):
        from ultron.hud.tardis_room.scene import PANEL_ANGLES
        scene = self.scene
        scene.select("telemetria")
        self.assertTrue(scene.in_motion())
        self.settle(4)
        self.assertAlmostEqual(math.cos(scene.azimuth), math.cos(PANEL_ANGLES["telemetria"]), places=3)
        self.assertAlmostEqual(math.sin(scene.azimuth), math.sin(PANEL_ANGLES["telemetria"]), places=3)
        self.assertFalse(scene.in_motion(), "câmera parada no painel: sem quadros extras")
        scene.select("inexistente")
        self.assertEqual(scene.selected, "")


if __name__ == "__main__":
    unittest.main()
