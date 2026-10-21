"""Permissões por categoria (consultar, configurar, executar programas, arquivos, apagar dados, robô)."""
import threading
import unittest

import helpers

from ultron.agent.autonomy import AuthorizationManager, AutonomyPolicy
from ultron.agent.execution import Action, ExecutionEngine
from ultron.agent.permissions import (DEFAULT_POLICY, SKILL_CATEGORIES, PermissionPolicy, category_for,
                                      parse_policy, policy_entries)
from ultron.config.settings import PERMISSION_CATEGORIES
from ultron.core.events import EventType
from ultron.skills.base import Risk, Skill, SkillContext, SkillResult, schema, string
from ultron.skills.registry import SkillRegistry, load_builtin


class _Probe(Skill):
    inputs = schema({"label": string(20)})
    risk = Risk.LOW

    def __init__(self):
        self.calls = 0

    def execute(self, ctx, label: str = ""):
        self.calls += 1
        return SkillResult(True, f"feito {label}")


class OpenProgram(_Probe):
    name = "test.open_program"
    permission = "executar_programas"


class WriteNote(_Probe):
    name = "test.write_note"
    permission = "arquivos"


class Trash(_Probe):
    name = "test.trash"
    permission = "apagar_dados"


class RobotStart(_Probe):
    name = "noctario.test_start"
    sensitive = "robot_motion"


class RobotConnect(_Probe):
    name = "noctario.test_connect"


class RobotStop(_Probe):
    name = "noctario.test_stop"
    risk = Risk.LOW
    emergency = True


class CategoryTest(unittest.TestCase):
    def test_every_builtin_skill_has_a_category(self):
        registry = load_builtin(SkillRegistry())
        for skill in registry.all():
            self.assertIn(category_for(skill, {}), PERMISSION_CATEGORIES, skill.name)
        self.assertEqual(set(SKILL_CATEGORIES) - set(registry.names()), set(), "tabela sem nomes inexistentes")
        deletions = {s.name for s in registry.all() if category_for(s, {}) == "apagar_dados"}
        self.assertEqual(deletions, {"fs.delete", "memory.forget", "automation.delete", "secondbrain.delete",
                                     "secondbrain.empty_trash"})
        reads = {s.name for s in registry.all() if s.risk is Risk.NONE}
        self.assertTrue(all(category_for(registry.get(n), {}) == "consultar" for n in reads),
                        "leitura pura é sempre 'consultar'")
        self.assertEqual(category_for(registry.get("app.open")), "executar_programas")
        self.assertEqual(category_for(registry.get("audio.volume")), "configurar")
        self.assertEqual(category_for(registry.get("fs.write_text")), "arquivos")
        self.assertEqual(category_for(registry.get("autonomy.revoke")), "consultar",
                         "revogar autorizações só reduz permissões")

    def test_robot_skills_and_emergency_stop(self):
        self.assertEqual(category_for(RobotStart()), "robo")
        self.assertEqual(category_for(RobotConnect()), "robo")
        self.assertEqual(category_for(RobotStop()), "", "a parada de emergência não pertence a categoria nenhuma")

    def test_policy_defaults_choices_and_floors(self):
        self.assertEqual(parse_policy(()), DEFAULT_POLICY)
        self.assertEqual(DEFAULT_POLICY["apagar_dados"], "confirmar")
        self.assertEqual(DEFAULT_POLICY["robo"], "confirmar")
        policy = parse_policy(("arquivos=confirmar", "executar_programas=bloquear", "consultar=xyz", "foo=permitir",
                               "apagar_dados=permitir", "robo=permitir"))
        self.assertEqual(policy["arquivos"], "confirmar")
        self.assertEqual(policy["executar_programas"], "bloquear")
        self.assertEqual(policy["consultar"], "permitir", "modo inválido é ignorado")
        self.assertEqual(policy["apagar_dados"], "confirmar", "apagar dados nunca fica abaixo de confirmar")
        self.assertEqual(policy["robo"], "confirmar", "comandos ao robô nunca ficam abaixo de confirmar")
        self.assertEqual(parse_policy(("robo=bloquear",))["robo"], "bloquear", "endurecer é sempre possível")
        self.assertEqual(policy_entries(policy), ("executar_programas=bloquear", "arquivos=confirmar"),
                         "só o que difere do padrão é gravado")

    def test_settings_validation_keeps_only_valid_entries(self):
        settings = helpers.make_settings(permission_policy=["arquivos=confirmar", "robo=talvez", "x=y",
                                                            "arquivos=confirmar"])
        self.assertEqual(settings.permission_policy, ("arquivos=confirmar",))
        described = {d["category"]: d for d in PermissionPolicy(lambda: settings).describe()}
        self.assertEqual(described["arquivos"]["mode"], "confirmar")
        self.assertEqual(described["robo"]["floor"], "confirmar")


class EnforcementTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.settings = helpers.make_settings(autonomy_level="balanced")
        self.registry = SkillRegistry()
        self.skills = {cls.name: cls() for cls in (OpenProgram, WriteNote, Trash, RobotStart, RobotConnect,
                                                   RobotStop)}
        for skill in self.skills.values():
            self.registry.register(skill)
        self.auth = AuthorizationManager(bus=self.bus, state=self.state, timeout_getter=lambda: 2.0)
        self.engine = ExecutionEngine(self.registry, autonomy=AutonomyPolicy(lambda: self.settings),
                                      authorizations=self.auth, context_factory=lambda c: SkillContext(cancel=c),
                                      bus=self.bus, state=self.state,
                                      permissions=PermissionPolicy(lambda: self.settings))
        self.requests = []
        self.bus.subscribe(EventType.AUTHORIZATION_REQUIRED, lambda e: self.requests.append(e.payload))

    def _policy(self, *entries):
        self.settings.apply({"permission_policy": list(entries)}, source="teste")

    def _reply_later(self, text: str, delay: float = 0.05):
        threading.Timer(delay, lambda: self.auth.handle_reply(text, by="teste")).start()

    def test_default_policy_keeps_common_actions_direct(self):
        record = self.engine.execute(Action("test.open_program", {"label": "a"}))
        self.assertEqual(record.status, "executed")
        self.assertIsNone(record.authorization)

    def test_blocked_category_is_refused_with_reason_and_nothing_runs(self):
        self._policy("executar_programas=bloquear")
        record = self.engine.execute(Action("test.open_program", {"label": "a"}))
        self.assertEqual(record.status, "refused")
        self.assertIn("executar programas", record.result.error)
        self.assertIn("CONFIGURAÇÕES > PERMISSÕES", record.result.error)
        self.assertEqual(self.skills["test.open_program"].calls, 0)
        self._policy()                                   # a mudança vale para o próximo pedido
        self.assertEqual(self.engine.execute(Action("test.open_program", {"label": "a"})).status, "executed")

    def test_confirm_category_asks_every_time_without_standing_grant(self):
        self._policy("arquivos=confirmar")
        self._reply_later("sim, sempre")
        first = self.engine.execute(Action("test.write_note", {"label": "n"}))
        self.assertEqual(first.status, "executed")
        self.assertEqual(first.authorization["permission"], "arquivos")
        self.assertFalse(first.authorization["standing_allowed"])
        self.assertEqual(self.auth.standing(), [], "'sim, sempre' não vira autorização permanente aqui")
        second = self.engine.execute(Action("test.write_note", {"label": "n"}))
        self.assertEqual(second.status, "denied", "sem resposta = não; perguntou de novo")
        self.assertEqual(self.skills["test.write_note"].calls, 1)

    def test_deletion_always_confirms_even_if_set_to_allow(self):
        self._policy("apagar_dados=permitir")
        self._reply_later("não")
        record = self.engine.execute(Action("test.trash", {"label": "x"}))
        self.assertEqual(record.status, "denied")
        self.assertEqual(self.skills["test.trash"].calls, 0)
        self.assertEqual(self.requests[-1]["permission"], "apagar_dados")

    def test_robot_motion_confirms_and_blocked_robot_still_stops(self):
        self._policy("robo=permitir")
        self._reply_later("sim, sempre")
        start = self.engine.execute(Action("noctario.test_start", {"label": "pista"}))
        self.assertEqual(start.status, "executed")
        self.assertEqual(start.authorization["category"], "robot_motion")
        self.assertFalse(start.authorization["standing_allowed"], "movimento nunca recebe 'sempre'")
        self._policy("robo=bloquear")
        self.settings.apply({"autonomy_level": "restricted"}, source="teste")
        connect = self.engine.execute(Action("noctario.test_connect", {"label": "a"}, origin="agent"))
        self.assertEqual(connect.status, "refused")
        stop = self.engine.execute(Action("noctario.test_stop", {"label": "a"}, origin="agent"))
        self.assertEqual(stop.status, "executed", "parada de emergência: nunca bloqueada nem perguntada")
        self.assertIsNone(stop.authorization)

    def test_permissions_never_relax_risk_based_authorization(self):
        class Critical(_Probe):
            name = "test.critical_read"
            risk = Risk.CRITICAL
            permission = "consultar"

        self.registry.register(Critical())
        record = self.engine.execute(Action("test.critical_read", {"label": "a"}))
        self.assertEqual(record.status, "denied", "'permitir' não dispensa a autorização exigida pelo risco")
        self.assertEqual(record.authorization["status"], "expired")


if __name__ == "__main__":
    unittest.main()
