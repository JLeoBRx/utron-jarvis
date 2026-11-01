"""Transições — depois de QUALQUER desfecho o JARVIS volta ao repouso, e o rosto mostra o que acontece.

Para cada desfecho de um pedido — sucesso, falha da skill, autorização negada, autorização sem resposta,
pedido cancelado com o modelo ainda respondendo, modelo que quebra — a sequência REAL de estados do núcleo
é gravada (cada chamada a ``set_runtime_state``, na ordem) e os mesmos sinais alimentam a lógica do avatar
(``_AvatarCore``, a mesma do widget). Nenhum estado fica preso; o fim é sempre IDLE e "aguardando
interação"; enquanto o "sim" é esperado, o rosto mostra "aguardando confirmação".

O modelo é um servidor HTTP local de teste; não há microfone, alto-falante nem janela real aqui.
"""
import threading
import time
import unittest

import helpers

from fake_ollama import FakeOllama
from ultron.skills.base import Risk, Skill, SkillResult, VerificationResult, check, schema

SLOW = 4.0


class Ok(Skill):
    name = "teste.ok"
    description = "teste"
    inputs = schema({})
    risk = Risk.LOW

    def execute(self, ctx, **_):
        return SkillResult(True, "feito (teste)")

    def verify(self, ctx, args, result):
        return VerificationResult.from_checks([check("ok", True, "teste")])


class Broken(Ok):
    name = "teste.quebrada"

    def execute(self, ctx, **_):
        raise RuntimeError("falha provocada pelo teste")


class Critical(Ok):
    name = "teste.critica"
    risk = Risk.CRITICAL
    reversible = False


def responder(payload):
    last = str((payload.get("messages") or [{}])[-1].get("content", ""))
    if "demorada" in last:
        time.sleep(SLOW)
        return "Resposta que chegou tarde demais."
    if "quebra" in last:
        raise RuntimeError("o servidor do modelo quebrou")
    return "Certo."


@unittest.skipUnless(helpers.qt_available(), "PySide6 (com bibliotecas do sistema) necessário")
class TransitionsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6 import QtWidgets

        from ultron.config.settings import SettingsManager
        from ultron.core.events import EventType
        from ultron.core.neural_core import NeuralCore
        from ultron.hud.avatar.view import _AvatarCore

        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.fake = FakeOllama(["qwen2.5:3b"], responder=responder)
        cls.fake.__enter__()
        manager = SettingsManager(helpers.temp_dir() / "settings.json")
        manager.load()
        manager.settings.ollama_url = cls.fake.url
        manager.settings.network_discovery = False
        manager.settings.auto_backup = False
        manager.settings.authorization_timeout = 0.6            # "sem resposta = não", sem esperar 30 s
        cls.core = NeuralCore(manager, voice=False, perception=False, plugins=False,
                              memory_db=helpers.make_memory().db)
        for skill in (Ok(), Broken(), Critical()):
            cls.core.registry.register(skill)
        cls.sequence = []
        cls.lock = threading.Lock()
        original = cls.core.state.set_runtime_state

        def recording(state, reason="", *, source=""):
            changed = original(state, reason, source=source)
            if changed:
                with cls.lock:
                    cls.sequence.append(state)
                    cls.avatar.on_state(cls.core.state.as_dict())
                    cls.faces.append(cls.avatar.update_state().key)
            return changed

        cls.core.state.set_runtime_state = recording

        class Face(_AvatarCore):
            def __init__(self):
                self._init_avatar()

        cls.avatar = Face()
        cls.faces = []
        cls.core.bus.subscribe(None, lambda e: cls.avatar.on_event(getattr(e.type, "value", e.type), e.payload),
                               name="t.avatar")
        cls.responses = []
        cls.core.bus.subscribe(EventType.RESPONSE_READY, lambda e: cls.responses.append(e.payload), name="t")
        cls.core.boot()

    @classmethod
    def tearDownClass(cls):
        cls.core.shutdown()
        cls.fake.__exit__(None, None, None)

    def setUp(self):
        self.wait_idle()
        with self.lock:
            self.sequence.clear()
            self.faces.clear()
            self.avatar.signals.error_until = self.avatar.signals.alert_until = 0.0   # janelas do teste anterior

    def wait_idle(self, seconds=10.0):
        end = time.time() + seconds
        while time.time() < end and self.core.state.runtime_state != "IDLE":
            time.sleep(0.02)
        return self.core.state.runtime_state == "IDLE"

    def final_face(self, *, after: float = 0.0) -> str:
        self.avatar.on_state(self.core.state.as_dict())
        self.avatar.signals.now = time.time() + after
        from ultron.hud.avatar.states import resolve
        return resolve(self.avatar.signals).key

    def assert_back_at_rest(self, *, after: float = 0.0):
        self.assertTrue(self.wait_idle(), f"preso em {self.core.state.runtime_state}: {self.sequence}")
        self.assertEqual(self.sequence[-1] if self.sequence else "IDLE", "IDLE", self.sequence)
        self.assertEqual(self.final_face(after=after), "aguardando")

    def ask(self, text, seconds=30):
        mark = len(self.responses)
        self.assertTrue(self.core.submit(text, source="text"))
        end = time.time() + seconds
        while time.time() < end:
            final = [r for r in self.responses[mark:] if not r.get("partial")]
            if final:
                return final[-1]
            time.sleep(0.02)
        self.fail(f"sem resposta para: {text}")

    def test_success_executes_then_rests(self):
        outcome = self.core.run_skill("teste.ok")
        self.assertTrue(outcome["success"] and outcome["verified"], outcome)
        self.assert_back_at_rest()

    def test_a_crashing_skill_is_reported_and_rests(self):
        outcome = self.core.run_skill("teste.quebrada")
        self.assertFalse(outcome["success"])
        self.assertIn("falha provocada pelo teste", outcome["error"])
        self.assert_back_at_rest()

    def test_denied_authorization_shows_confirmation_then_rests(self):
        threading.Timer(0.3, lambda: self.core.authorizations.resolve(False, by="teste")).start()
        outcome = self.core.run_skill("teste.critica")
        self.assertEqual(outcome["status"], "denied")
        self.assertIn("AWAITING_AUTHORIZATION", self.sequence)
        self.assertIn("confirmacao", self.faces, "enquanto esperava o 'sim', o rosto pedia confirmação")
        self.assert_back_at_rest()

    def test_unanswered_authorization_means_no_and_rests(self):
        started = time.monotonic()
        outcome = self.core.run_skill("teste.critica")
        self.assertEqual((outcome["status"], outcome["authorization"]["status"]), ("denied", "expired"))
        self.assertLess(time.monotonic() - started, 5.0)
        self.assertIsNone(self.core.authorizations.pending())
        self.assert_back_at_rest()

    def test_cancel_while_the_model_answers_rests_without_waiting_for_it(self):
        mark = len(self.responses)
        self.assertTrue(self.core.submit("me conte uma história demorada", source="text"))
        end = time.time() + 5
        while time.time() < end and self.core.state.runtime_state == "IDLE":
            time.sleep(0.01)
        self.assertNotEqual(self.core.state.runtime_state, "IDLE", "o pedido começou")
        started = time.monotonic()
        self.core.submit("cancelar", source="text")
        self.assertTrue(self.wait_idle(SLOW - 1.0), "voltou ao repouso antes de o modelo terminar")
        self.assertLess(time.monotonic() - started, SLOW - 1.0)
        time.sleep(SLOW)                                      # o modelo termina depois: nada dele é mostrado
        texts = [r.get("text", "") for r in self.responses[mark:]]
        self.assertFalse(any("tarde demais" in t for t in texts), texts)
        self.assert_back_at_rest()

    def test_a_broken_model_lights_the_error_window_then_rests(self):
        answer = self.ask("isto quebra o modelo")
        self.assertEqual(answer.get("kind"), "error")
        self.assertTrue(self.wait_idle())
        self.assertEqual(self.sequence[-1], "IDLE", self.sequence)
        self.assertEqual(self.final_face(), "erro", "o rosto mostra a falha de integração na hora")
        self.assertEqual(self.final_face(after=9.0), "aguardando", "e volta a aguardar depois da janela de 8 s")


if __name__ == "__main__":
    unittest.main()
