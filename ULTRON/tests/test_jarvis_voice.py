"""JARVIS: migração de identidade das configurações e diagnóstico de voz ponta a ponta.

Os testes de voz usam um núcleo REAL (Event Bus, intents, orquestrador, fala) com microfone,
reconhecedor e saída de áudio SIMULADOS — não substituem o teste com hardware real
(``python main.py --voice-test`` no Windows), que é descrito em VOICE_DIAGNOSTICS.md.
"""
import json
import threading
import time
import unittest

import numpy as np

import helpers

from ultron.config.settings import SettingsManager
from ultron.core.events import EventType


class SettingsMigrationTest(unittest.TestCase):
    def test_ultron_identity_fields_migrate_and_personal_ones_stay(self):
        folder = helpers.temp_dir()
        path = folder / "settings.json"
        legacy = {"wake_words": ["ultron"], "wake_variants": ["ultron", "ultrom", "ul tron", "outrom", "jarvas"],
                  "wake_weak_variants": ["o tom", "outro", "atencao"], "theme": "ultron-gold",
                  "performance_profile": "performance", "mic_name": "Microfone (USB)", "volume": 0.55,
                  "model": "qwen2.5:7b", "quiet_hours": "22:00-07:00"}
        path.write_text(json.dumps(legacy), encoding="utf-8")
        manager = SettingsManager(path)
        s = manager.load()
        self.assertEqual(s.wake_words, ("jarvis",))
        self.assertIn("jarvis", s.wake_variants)
        self.assertNotIn("ultrom", s.wake_variants)
        self.assertNotIn("outrom", s.wake_variants, "forma calibrada para 'ultron' não serve ao JARVIS")
        self.assertIn("jarvas", s.wake_variants, "forma calibrada que não é do ULTRON é mantida")
        self.assertNotIn("o tom", s.wake_weak_variants)
        self.assertIn("atencao", s.wake_weak_variants)
        self.assertEqual((s.theme, s.performance_profile), ("jarvis-blue", "economy"))
        self.assertEqual((s.mic_name, s.volume, s.model, s.quiet_hours),
                         ("Microfone (USB)", 0.55, "qwen2.5:7b", "22:00-07:00"), "preferências pessoais intactas")
        backup = folder / "settings.ultron-backup.json"
        self.assertTrue(backup.is_file(), "cópia do arquivo original guardada")
        self.assertEqual(json.loads(backup.read_text(encoding="utf-8"))["wake_words"], ["ultron"])
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["settings_version"], 2)
        again = SettingsManager(path)
        again.load()
        self.assertEqual(again.migration_notes, [], "migração roda uma única vez")


class FakeStream:
    def __init__(self):
        self.closed = False
        self.rng = np.random.default_rng(3)

    def read(self, frames, exception_on_overflow=False):
        time.sleep(0.01)
        return (self.rng.normal(0, 600, frames)).astype(np.int16).tobytes()   # ruído de sala: não é silêncio

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True


class ScriptedSTT:
    label = "stt-simulado"

    def __init__(self):
        self.script: list[tuple] = []
        self.lock = threading.Lock()
        self.last_confidence = 0.9

    def push(self, final):
        with self.lock:
            self.script.append((final, None))

    def accept(self, chunk):
        with self.lock:
            return self.script.pop(0) if self.script else (None, None)

    def finish(self):
        return ""

    def reset(self):
        pass


class FakeUtterance:
    def __init__(self):
        self.done = threading.Event()
        self.done.set()


class FakeOutput:
    """Saída de áudio simulada: 'toca' instantaneamente (não é um teste de alto-falante)."""
    rate = 22050
    backend = "simulada"
    reason = ""
    available = True
    mixes_effects = False
    paused = False
    voice_volume = 0.9
    sfx_volume = 0.3
    level = 0.0
    bed_target = 0.0
    played = 0

    def start(self):
        pass

    def stop(self):
        pass

    def play_voice(self, samples):
        FakeOutput.played += 1
        return FakeUtterance()

    def play_effect(self, samples, gain=1.0):
        return False

    def set_bed(self, samples):
        pass

    def stop_voice(self):
        pass

    def pause(self):
        pass

    def resume(self):
        pass

    @property
    def speaking(self):
        return False


class FakeSynth:
    name = "sintetizador-simulado"

    def synthesize(self, text, *, length_scale=1.0):
        return np.zeros(2205, dtype=np.float32), 22050


def make_voice_core(*, mic_ok=True):
    from ultron.core.neural_core import NeuralCore
    manager = SettingsManager(helpers.temp_dir() / "settings.json")
    manager.load()
    manager.settings.network_discovery = False
    manager.settings.ollama_url = "http://127.0.0.1:9"
    core = NeuralCore(manager, voice=True, perception=False, plugins=False, audio_output=FakeOutput(),
                      memory_db=helpers.make_memory().db)
    stt = ScriptedSTT()
    core.voice._stt_factory = lambda: (stt, "")

    def opener():
        if not mic_ok:
            raise RuntimeError("nenhum dispositivo de entrada de áudio encontrado")
        return None, FakeStream(), "Microfone simulado"

    core.voice._mic_opener = opener
    core.voice._sleep = lambda seconds: time.sleep(min(seconds, 0.05))
    core.speaker._loader = lambda: (FakeSynth(), "")
    return core, stt


class VoiceDiagnosticsTest(unittest.TestCase):
    def _devices(self, monkey_devices):
        from ultron.voice import audio
        original = audio.list_input_devices
        audio.list_input_devices = lambda backend="auto": monkey_devices
        self.addCleanup(lambda: setattr(audio, "list_input_devices", original))

    def test_full_round_trip_with_spoken_wake_word(self):
        from ultron.voice.diagnostics import VoiceDiagnostics
        self._devices({"backend": "simulado", "default": 0, "errors": [],
                       "devices": [{"index": 0, "name": "Microfone simulado", "host_api": "MME", "channels": 1,
                                    "rate": 16000, "default": True}]})
        core, stt = make_voice_core()
        core.boot()
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not core.voice.capturing:
                time.sleep(0.05)
            self.assertTrue(core.voice.capturing)
            prompts = []

            def prompt(text):
                prompts.append(text)
                threading.Timer(0.3, lambda: stt.push("jarvis que horas são")).start()

            report = VoiceDiagnostics(core).run(interactive=True, listen_seconds=8.0, prompt=prompt)
            steps = {s["key"]: s for s in report["steps"]}
            self.assertEqual(steps["mic_detected"]["status"], "OK")
            self.assertEqual(steps["device_selected"]["status"], "OK")
            self.assertEqual(steps["capture"]["status"], "OK", steps["capture"])
            self.assertEqual(steps["pt_model"]["status"], "OK")
            self.assertEqual(steps["wake"]["status"], "OK", steps["wake"])
            self.assertEqual(steps["delivery"]["status"], "OK", steps["delivery"])
            self.assertEqual(steps["response"]["status"], "OK", steps["response"])
            self.assertIn("que horas são", prompts[0])
            self.assertIn("jarvis que horas são", report["heard"])
            self.assertIsNone(core.voice.diagnostic_tap, "a escuta de diagnóstico é desligada ao final")
        finally:
            core.shutdown()

    def test_model_step_trusts_the_recognizer_in_use(self):
        """O reconhecedor já carregado pela captura é a evidência; o que está no disco agora não decide
        (pacote sem modelos, modelo trocado depois de carregado ou escolha automática por RAM)."""
        from ultron.voice import stt as stt_module
        from ultron.voice.diagnostics import VoiceDiagnostics
        self._devices({"backend": "simulado", "default": 0, "errors": [],
                       "devices": [{"index": 0, "name": "Microfone simulado", "host_api": "MME", "channels": 1,
                                    "rate": 16000, "default": True}]})
        original = stt_module.choose_model
        stt_module.choose_model = lambda engine="auto": (None, "nenhum modelo em assets/stt")
        self.addCleanup(lambda: setattr(stt_module, "choose_model", original))
        core, _stt = make_voice_core()
        core.boot()
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not core.voice.capturing:
                time.sleep(0.05)
            report = VoiceDiagnostics(core).run(interactive=False, probe_response=False)
            steps = {s["key"]: s for s in report["steps"]}
            self.assertEqual(steps["stt_engine"]["status"], "OK", steps["stt_engine"])
            self.assertEqual(steps["pt_model"]["status"], "OK", steps["pt_model"])
            self.assertIn("stt-simulado", steps["pt_model"]["detail"], "nomeia o reconhecedor realmente em uso")
        finally:
            core.shutdown()

    def test_missing_microphone_is_reported_with_cause(self):
        from ultron.voice.diagnostics import VoiceDiagnostics
        self._devices({"backend": None, "default": None, "devices": [],
                       "errors": ["pyaudio não instalado", "sounddevice: PortAudio library not found"]})
        core, _stt = make_voice_core(mic_ok=False)
        core.boot()
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not core.voice.reason:
                time.sleep(0.05)
            self.assertIn("nenhum dispositivo", core.voice.reason)
            report = VoiceDiagnostics(core).run(interactive=False, probe_response=False)
            steps = {s["key"]: s for s in report["steps"]}
            self.assertEqual(report["overall"], "FAIL")
            self.assertEqual(steps["mic_detected"]["status"], "FAIL")
            self.assertIn("pyaudio", steps["mic_detected"]["detail"])
            self.assertEqual(steps["capture"]["status"], "FAIL")
            self.assertNotEqual(core.health.check_all()["checks"]["VOICE"]["status"], "OK",
                                "a saúde não finge que a voz funciona")
        finally:
            core.shutdown()

    def test_voice_and_text_requests_run_together(self):
        core, stt = make_voice_core()
        responses = []
        lock = threading.Lock()

        def on_response(event):
            if not event.get("partial"):
                with lock:
                    responses.append((event.get("source"), event.get("text")))

        core.bus.subscribe(EventType.RESPONSE_READY, on_response)
        core.boot()
        try:
            deadline = time.time() + 10
            while time.time() < deadline and not core.voice.capturing:
                time.sleep(0.05)
            stt.push("jarvis que horas são")
            core.submit("que dia é hoje", source="text")
            deadline = time.time() + 15
            while time.time() < deadline:
                with lock:
                    sources = {source for source, _ in responses}
                if {"voice", "text"} <= sources:
                    break
                time.sleep(0.05)
            self.assertTrue({"voice", "text"} <= sources, responses)
            texts = " ".join(text for _, text in responses)
            self.assertIn("São ", texts)
            self.assertIn("Hoje é", texts)
        finally:
            core.shutdown()
        alive = [t.name for t in threading.enumerate() if t.name in ("ultron-microphone", "ultron-speaker")
                 and t.is_alive()]
        self.assertEqual(alive, [], "threads de áudio encerradas em ordem")


if __name__ == "__main__":
    unittest.main()
