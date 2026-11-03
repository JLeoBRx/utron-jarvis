"""Inteligência (Fase D da Operação Phoenix): perfis, roteamento por tarefa, consumo e limite, autorização
no primeiro uso pago, privacidade do contexto enviado à nuvem, procedência das respostas e recuperação da
memória (perguntas gerais, decisões, relações entre projetos).

Os modelos são SEMPRE falsos aqui (servidor que imita o Ollama; provedor de nuvem falso): nenhum teste chama
um serviço pago real nem afirma que a OpenAI real funciona."""
import time
import unittest

import helpers

from ultron.models import profiles
from ultron.models.profiles import (CLOUD_FAST, CLOUD_ROBUST, LOCAL_FAST, LOCAL_ROBUST, NONE, Availability,
                                    assess, decide, effective_profile)


def _avail(**values):
    base = dict(local_fast=True, local_robust=True, cloud_ready=True, cloud_blocked="", within_budget=True)
    base.update(values)
    return Availability(**base)


class AssessmentTest(unittest.TestCase):
    def test_complexity_and_sensitivity(self):
        self.assertEqual(assess("oi").level, "baixa")
        self.assertEqual(assess("que horas são?").level, "baixa")
        heavy = assess("explique a diferença entre TCP e UDP e compare as vantagens de cada um para jogos online")
        self.assertEqual(heavy.level, "alta")
        self.assertIn("raciocínio", heavy.signals)
        self.assertEqual(assess("monte um plano", purpose="planejamento").level, "alta")
        self.assertTrue(assess("minha senha do banco é 1234").sensitive)
        self.assertTrue(assess("qual o saldo da minha conta bancária?").sensitive)
        self.assertFalse(assess("qual a capital da França?").sensitive)


class RoutingTest(unittest.TestCase):
    heavy = assess("explique e compare a arquitetura de microsserviços com a de monólitos, passo a passo")
    light = assess("qual a capital da França?")
    trivial = assess("obrigado")

    def test_local_and_privacy_profiles_never_use_the_cloud(self):
        for profile in ("local", "privacidade"):
            for task in (self.heavy, self.light, self.trivial):
                route = decide(task, profile, _avail())
                self.assertTrue(route.local, (profile, route.reason))
                self.assertFalse(route.paid)
        self.assertEqual(decide(self.heavy, "local", _avail()).target, LOCAL_ROBUST, "pesado → local robusto")
        self.assertEqual(decide(self.light, "local", _avail()).target, LOCAL_FAST)

    def test_hybrid_sends_only_heavy_work_to_the_cloud(self):
        self.assertEqual(decide(self.heavy, "hibrido", _avail()).target, CLOUD_ROBUST)
        self.assertEqual(decide(self.light, "hibrido", _avail()).target, LOCAL_FAST)
        self.assertEqual(decide(self.trivial, "hibrido", _avail()).target, LOCAL_FAST)

    def test_advanced_and_economic(self):
        self.assertEqual(decide(self.heavy, "avancado", _avail()).target, CLOUD_ROBUST)
        self.assertEqual(decide(self.light, "avancado", _avail()).target, CLOUD_FAST)
        self.assertEqual(decide(self.trivial, "avancado", _avail()).target, LOCAL_FAST, "trivial fica local")
        self.assertTrue(decide(self.heavy, "economico", _avail()).local, "econômico: local primeiro")
        offline = _avail(local_fast=False, local_robust=False)
        self.assertEqual(decide(self.heavy, "economico", offline).target, CLOUD_FAST, "reserva: modelo rápido")

    def test_sensitive_content_and_images_stay_local_in_every_profile(self):
        secret = assess("guarde minha senha do email: abc123 e explique como trocar ela com segurança passo a passo")
        image = assess("o que há nesta tela?", purpose="visao", images=True)
        for profile in profiles.PROFILE_KEYS:
            self.assertTrue(decide(secret, profile, _avail()).local, profile)
            self.assertTrue(decide(image, profile, _avail()).local, profile)
        self.assertEqual(decide(image, "avancado", _avail(cloud_images=True)).target, CLOUD_FAST,
                         "só com o envio de imagens ligado explicitamente")

    def test_cloud_not_ready_or_over_budget_falls_back_to_local_with_the_reason(self):
        blocked = decide(self.heavy, "avancado", _avail(cloud_ready=False, cloud_blocked="chave ausente"))
        self.assertTrue(blocked.local)
        self.assertIn("chave ausente", blocked.reason)
        over = decide(self.heavy, "hibrido", _avail(within_budget=False, budget_reason="limite mensal atingido"))
        self.assertTrue(over.local)
        self.assertIn("limite mensal", over.reason)

    def test_nothing_available_is_none_not_an_invented_answer(self):
        route = decide(self.light, "local", _avail(local_fast=False, local_robust=False))
        self.assertEqual(route.target, NONE)
        self.assertIn("nenhum modelo local", route.reason)

    def test_effective_profile_keeps_the_previous_behavior(self):
        self.assertEqual(effective_profile(helpers.make_settings()), "local")
        self.assertEqual(effective_profile(helpers.make_settings(ai_provider="openai")), "avancado")
        self.assertEqual(effective_profile(helpers.make_settings(ai_provider="openai",
                                                                  intelligence_profile="hibrido")), "hibrido")


class UsageLedgerTest(unittest.TestCase):
    def setUp(self):
        from ultron.models.usage import UsageLedger
        self.memory = helpers.make_memory()
        self.settings = helpers.make_settings(cloud_monthly_limit_usd=1.0, cloud_monthly_token_limit=10_000,
                                              cloud_price_robust_in=2.0, cloud_price_robust_out=8.0)
        self.now = time.time()
        self.ledger = UsageLedger(self.memory.db, settings_getter=lambda: self.settings, clock=lambda: self.now)

    def tearDown(self):
        self.memory.db.close()

    def test_costs_tokens_and_limits(self):
        self.ledger.record(provider="ollama", model="qwen2.5:3b", target=LOCAL_FAST, input_tokens=500,
                           output_tokens=100)
        row = self.ledger.record(provider="openai", model="m", target=CLOUD_ROBUST, input_tokens=1000,
                                 output_tokens=500)
        self.assertAlmostEqual(row["cost_usd"], (1000 * 2.0 + 500 * 8.0) / 1e6)
        unpriced = self.ledger.record(provider="openai", model="m2", target=CLOUD_FAST, input_tokens=10,
                                      output_tokens=10)
        self.assertIsNone(unpriced["cost_usd"], "sem preço configurado: custo desconhecido, não inventado")
        month = self.ledger.month()
        self.assertEqual((month["local_calls"], month["cloud_calls"], month["unpriced_calls"]), (1, 2, 1))
        self.assertEqual(month["cloud_tokens"], 1520)
        ok, reason, _ = self.ledger.budget()
        self.assertTrue(ok, reason)
        self.ledger.record(provider="openai", model="m", target=CLOUD_ROBUST, input_tokens=9000, output_tokens=0)
        ok, reason, _ = self.ledger.budget()
        self.assertFalse(ok)
        self.assertIn("tokens", reason)

    def test_zero_limit_blocks_paid_use(self):
        self.settings.cloud_monthly_limit_usd = 0.0
        ok, reason, _ = self.ledger.budget()
        self.assertFalse(ok)
        self.assertIn("zero", reason)


if __name__ == "__main__":
    unittest.main()


class RouterIntegrationTest(unittest.TestCase):
    """Roteador real contra servidores falsos locais (Ollama e Responses API)."""

    KEY = "sk-teste-roteamento-000"

    def _router(self, openai_url, ollama_url, *, consent=None, ledger=True, **values):
        from ultron.config.settings import SettingsManager
        from ultron.models.ollama_client import OllamaClient
        from ultron.models.openai_provider import OpenAIProvider
        from ultron.models.router import ModelRouter
        from ultron.models.usage import UsageLedger
        from ultron.privacy.privacy_mode import PrivacyPolicy
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        base = {"intelligence_profile": "hibrido", "openai_model": "robusto-teste", "openai_model_fast": "rapido-teste",
                "openai_base_url": openai_url, "privacy_mode": "standard", "allow_external_models": True,
                "ollama_url": ollama_url}
        base.update(values)
        manager.settings.apply(base)
        self.asked = []

        def ask(description):
            self.asked.append(description)
            approved = consent(description) if consent else False
            if approved:
                manager.update(cloud_consent_at=time.time())
            return approved

        privacy = PrivacyPolicy(lambda: manager.settings)
        memory = helpers.make_memory()
        self.addCleanup(memory.db.close)
        usage = UsageLedger(memory.db, settings_getter=lambda: manager.settings) if ledger else None
        router = ModelRouter(OllamaClient(ollama_url), settings_getter=lambda: manager.settings, privacy=privacy,
                             usage=usage, consent=ask)
        router.register_provider("openai", OpenAIProvider(lambda: manager.settings, privacy=privacy,
                                                          key_getter=lambda: self.KEY))
        return router, manager, usage

    HEAVY = "explique e compare a arquitetura de microsserviços com a de monólitos, passo a passo"

    def test_first_paid_use_asks_once_and_records_consumption(self):
        from fake_ollama import FakeOllama
        from fake_openai import FakeOpenAI
        with FakeOpenAI(lambda p: {"text": "Resposta da nuvem.", "web": True}, key=self.KEY) as api, \
                FakeOllama(["qwen2.5:3b"], responder=lambda p: "Resposta local.") as ollama:
            router, manager, usage = self._router(api.url, ollama.url, consent=lambda d: True)
            light = router.chat("text", [{"role": "user", "content": "que horas são em Tóquio?"}])
            self.assertEqual(light.content, "Resposta local.", "HÍBRIDO: pergunta simples fica local")
            self.assertEqual(api.requests, [])
            heavy = router.chat("text", [{"role": "user", "content": self.HEAVY}])
            self.assertEqual(heavy.content, "Resposta da nuvem.")
            self.assertEqual(len(self.asked), 1, "autorização pedida antes do primeiro uso pago")
            self.assertIn("PAGO", self.asked[0])
            self.assertEqual(api.requests[0]["payload"]["model"], "robusto-teste", "tarefa pesada → modelo robusto")
            router.chat("text", [{"role": "user", "content": self.HEAVY}])
            self.assertEqual(len(self.asked), 1, "a autorização não é pedida de novo")
            self.assertTrue(heavy.route["web"], "a resposta diz que veio da internet")
            self.assertEqual(router.last_route()["provider"], "openai")
            month = usage.month()
            self.assertEqual((month["local_calls"], month["cloud_calls"]), (1, 2))
            self.assertEqual(month["cloud_tokens"], 2 * (40 + 7))

    def test_denied_consent_means_no_request_and_an_honest_local_answer(self):
        from fake_ollama import FakeOllama
        from fake_openai import FakeOpenAI
        with FakeOpenAI(key=self.KEY) as api, FakeOllama(["qwen2.5:3b"], responder=lambda p: "Local.") as ollama:
            router, manager, _usage = self._router(api.url, ollama.url, consent=lambda d: False)
            result = router.chat("text", [{"role": "user", "content": self.HEAVY}])
            self.assertEqual(result.content, "Local.")
            self.assertEqual(api.requests, [], "nenhuma chamada paga sem autorização")
            self.assertEqual(result.route["provider"], "ollama")
            self.assertIn("não autorizado", " ".join(result.route["notes"]))
            self.assertEqual(manager.settings.cloud_consent_at, 0.0)

    def test_budget_and_privacy_of_what_is_sent(self):
        from fake_ollama import FakeOllama
        from fake_openai import FakeOpenAI
        with FakeOpenAI(key=self.KEY) as api, FakeOllama(["qwen2.5:3b"], responder=lambda p: "Local.") as ollama:
            router, manager, usage = self._router(api.url, ollama.url, consent=lambda d: True)
            messages = [{"role": "system", "content": "Identidade. MEMÓRIA PESSOAL: o cofre fica na garagem.",
                         "cloud_content": "Identidade."},
                        {"role": "user", "content": "conversa anterior com dado pessoal", "history": True},
                        {"role": "user", "content": self.HEAVY}]
            router.chat("text", messages)
            sent = api.requests[0]["payload"]
            self.assertEqual(sent["instructions"], "Identidade.", "memória pessoal não vai para a nuvem")
            self.assertNotIn("conversa anterior", str(sent["input"]), "nem o histórico da conversa")
            local_payload = None

            def capture(payload):
                nonlocal local_payload
                local_payload = payload
                return "Local."
            ollama.responder = capture
            manager.update(intelligence_profile="local")
            router.chat("text", messages)
            self.assertIn("garagem", local_payload["messages"][0]["content"], "o modelo local recebe o contexto todo")
            self.assertNotIn("cloud_content", local_payload["messages"][0], "marcas internas nunca saem")
            manager.update(intelligence_profile="avancado", cloud_monthly_token_limit=10)
            before = len(api.requests)
            result = router.chat("text", [{"role": "user", "content": self.HEAVY}])
            self.assertEqual(len(api.requests), before, "limite mensal atingido: nenhuma chamada paga")
            self.assertIn("limite", result.route["reason"])

    def test_tools_and_tardis_stay_local_without_explicit_sharing(self):
        from fake_ollama import FakeOllama
        from fake_openai import FakeOpenAI
        with FakeOpenAI(key=self.KEY) as api, FakeOllama(["qwen2.5:3b"], responder=lambda p: "Local.") as ollama:
            router, _manager, _usage = self._router(api.url, ollama.url, consent=lambda d: True,
                                                    intelligence_profile="avancado")
            tools = [{"type": "function", "function": {"name": "fs.search", "parameters": {}}}]
            router.chat("text", [{"role": "user", "content": self.HEAVY}], tools=tools, purpose="agente")
            router.chat("text", [{"role": "user", "content": self.HEAVY}], purpose="tardis")
            self.assertEqual(api.requests, [], "resultados de ferramentas e memória da TARDIS não saem")

    def test_robust_local_model_for_heavy_work(self):
        from fake_ollama import FakeOllama
        with FakeOllama(["qwen2.5:3b", "qwen2.5:7b"], responder=lambda p: "ok") as ollama:
            router, _manager, _usage = self._router("http://127.0.0.1:9/v1", ollama.url, intelligence_profile="local")
            router.chat("text", [{"role": "user", "content": "oi"}])
            router.chat("text", [{"role": "user", "content": self.HEAVY}])
            models = [p["model"] for p in ollama.chat_requests()]
            self.assertEqual(models, ["qwen2.5:3b", "qwen2.5:7b"], "rápido no simples, robusto no pesado")
            self.assertEqual(router.last_route()["target"], LOCAL_ROBUST)

    def test_ollama_offline_and_no_cloud_is_unavailable_not_invented(self):
        from ultron.models.router import ModelUnavailable
        router, _manager, _usage = self._router("http://127.0.0.1:9/v1", "http://127.0.0.1:9",
                                                intelligence_profile="local")
        with self.assertRaises(ModelUnavailable):
            router.chat("text", [{"role": "user", "content": "oi"}])


class MemoryRetrievalTest(unittest.TestCase):
    """Perguntas gerais à memória, decisões (Second Brain + memória de projeto da TARDIS) e relações entre
    projetos — respondidas SÓ com o que está salvo; sem registro, a resposta diz que não encontrou."""

    def setUp(self):
        from ultron.secondbrain.service import SecondBrainService
        self.memory = helpers.make_memory()
        self.settings = helpers.make_settings()
        self.service = SecondBrainService(self.memory.db, settings_getter=lambda: self.settings)
        self.service.start()

    def tearDown(self):
        self.service.stop()
        self.memory.db.close()

    def ask(self, text):
        from ultron.secondbrain.queries import answer
        return answer(self.service, text)

    def test_general_questions_list_what_was_saved(self):
        self.assertEqual(self.ask("quais ideias salvei?").kind, "empty")
        self.assertIn("Não há ideias registradas", self.ask("quais ideias salvei?").text)
        phoenix = self.service.create("project", "Phoenix")
        self.service.create("idea", "ORBE no celular", project=phoenix.id)
        self.service.create("idea", "voz mais grave para o ULTRON")
        self.service.create("note", "trocar a pasta térmica do notebook")
        found = self.ask("quais ideias salvei?")
        self.assertEqual(found.kind, "list")
        self.assertIn("ORBE no celular", found.text)
        self.assertIn("voz mais grave", found.text)
        self.assertIn("pasta térmica", self.ask("liste minhas notas").text)

    def test_decisions_include_the_tardis_project_memory(self):
        from ultron.tardis.store import TardisStore
        self.assertIn("Não há decisões", self.ask("quais decisões tomei?").text)
        self.service.create("note", "Decisão: usar SQLite local", tags=["decisão"])
        TardisStore(self.memory.db).add_note("publicar só com HTTPS", project="Phoenix", kind="decisao")
        everything = self.ask("quais decisões tomei?")
        self.assertIn("usar SQLite local", everything.text)
        self.assertIn("publicar só com HTTPS", everything.text)
        self.assertIn("memória de projeto da TARDIS", everything.text)
        about = self.ask("o que decidi sobre o Phoenix?")
        self.assertIn("HTTPS", about.text)

    def test_relations_between_projects(self):
        phoenix = self.service.create("project", "Phoenix", tags=["jarvis", "web"])
        atlas = self.service.create("project", "Atlas", tags=["web"])
        orion = self.service.create("project", "Orion")
        self.service.create("task", "integrar com o Orion", project=phoenix.id)
        self.service.relate(phoenix.id, atlas.id, "related")
        related = self.ask("que projetos estão relacionados ao Phoenix?")
        self.assertIn("Atlas", related.text)
        self.assertIn("etiquetas em comum", related.text)
        self.assertIn("Orion", related.text, "citado nos registros do projeto")
        between = self.ask("qual a relação entre o projeto Phoenix e o Atlas?")
        self.assertIn("ligação registrada", between.text)
        self.assertIn("web", between.text)
        nothing = self.ask("qual a relação entre o projeto Atlas e o Orion?")
        self.assertEqual(nothing.kind, "empty")
        self.assertIn("Não encontrei relação", nothing.text)
        self.assertTrue(orion.id)


class ProvenanceTest(unittest.TestCase):
    def test_labels(self):
        from ultron.cognition.provenance import describe, line
        memory = describe(response_kind="answer", text="Ideias: x", success=True, verified=True,
                          skills=["secondbrain.query"], route={})
        self.assertEqual(memory["kinds"], ["memoria"])
        cloud = describe(response_kind="answer", text="Provavelmente sim.", success=None, verified=None, skills=[],
                         route={"provider": "openai", "model": "openai:m", "web": True, "notes": []})
        self.assertEqual(cloud["kinds"], ["internet", "inferencia", "hipotese"])
        local = describe(response_kind="answer", text="Paris.", success=None, verified=None, skills=[],
                         route={"provider": "ollama", "model": "qwen2.5:3b", "notes": ["uso pago não autorizado"]})
        self.assertIn("modelo local qwen2.5:3b", line(local))
        self.assertIn("uso pago não autorizado", line(local))
        down = describe(response_kind="error", text="Núcleo indisponível", success=False, verified=None, skills=[],
                        route={})
        self.assertEqual(down["kinds"], ["indisponivel"])
        action = describe(response_kind="result", text="Aberto.", success=True, verified=True, skills=["app.open"],
                          route={})
        self.assertIn("ação verificada", action["label"])


class IntelligenceIntentsTest(unittest.TestCase):
    def test_usage_and_profile_phrases(self):
        from ultron.cognition.intent_engine import IntentEngine
        engine = IntentEngine()
        self.assertEqual(engine.classify("quanto gastei com a OpenAI este mês?").args, {"ai_usage": True})
        self.assertEqual(engine.classify("use o perfil local").args, {"intelligence_profile": "local"})
        self.assertEqual(engine.classify("ative o modo privacidade").args, {"privacy_shield": True},
                         "o modo privacidade (microfone) continua igual")
        for phrase in ("quais ideias salvei?", "quais decisões tomei?", "que projetos estão relacionados ao Phoenix?"):
            self.assertEqual(engine.classify(phrase).skill, "secondbrain.query", phrase)


class CoreIntelligenceTest(unittest.TestCase):
    def test_usage_answer_and_voice_cannot_turn_on_the_cloud(self):
        from fake_ollama import FakeOllama
        from ultron.config.settings import SettingsManager
        from ultron.core.neural_core import NeuralCore
        with FakeOllama(["qwen2.5:3b"]) as ollama:
            manager = SettingsManager(helpers.temp_dir() / "settings.json")
            manager.load()
            manager.settings.apply({"ollama_url": ollama.url, "network_discovery": False, "auto_backup": False})
            core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
            try:
                from ultron.cognition.intent_engine import IntentEngine
                engine = IntentEngine()
                usage = core._control(engine.classify("qual o consumo da IA?"))
                self.assertIn("Perfil de inteligência: LOCAL", usage.text)
                self.assertIn("0 na nuvem", usage.text)
                refused = core._control(engine.classify("ative o perfil avançado"))
                self.assertIn("CONFIGURAÇÕES > INTELIGÊNCIA", refused.text)
                self.assertEqual(manager.settings.intelligence_profile, "", "por voz, a nuvem não é ligada")
                core._control(engine.classify("use o perfil privacidade"))
                self.assertEqual(manager.settings.intelligence_profile, "privacidade")
                self.assertIsNotNone(core.router.usage, "o roteador registra consumo no mesmo banco")
            finally:
                core.memory.db.close()
