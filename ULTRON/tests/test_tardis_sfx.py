"""Sons da TARDIS: efeitos ORIGINAIS sintetizados, substituíveis por arquivos autorizados do usuário, disparados
só por eventos reais (tarefas da TARDIS, modo do rotor, portas ao entrar/sair da sala), com volume próprio e
liga/desliga. Nenhum alto-falante real é usado (a saída de áudio é o mixer do JARVIS sem dispositivo)."""
import unittest
import wave
from pathlib import Path

import numpy as np

import helpers

from ultron.audio import tardis_sfx
from ultron.core.events import EventType
from ultron.voice.audio import AudioOutput


def _write_wav(path: Path, samples: np.ndarray, rate: int, channels: int = 1) -> None:
    data = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    if channels == 2:
        data = np.repeat(data, 2)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(data.tobytes())


class OriginalEffectsTest(unittest.TestCase):
    def test_every_effect_is_synthesized_clean_and_in_range(self):
        sounds, origin = tardis_sfx.load(None)
        self.assertEqual(set(sounds), set(tardis_sfx.FILES))
        self.assertTrue(all(v == "original" for v in origin.values()))
        durations = {k: len(v) / tardis_sfx.RATE for k, v in sounds.items()}
        self.assertGreater(durations["materializacao"], 4.0)
        self.assertLess(durations["porta_abrir"], 1.5)
        for name, x in sounds.items():
            self.assertTrue(np.isfinite(x).all(), name)
            self.assertLessEqual(float(np.max(np.abs(x))), 0.9, f"{name}: sem saturação")
            self.assertGreater(float(np.sqrt(np.mean(x ** 2))), 0.02, f"{name}: audível")
        loop = sounds["ambiente"]
        self.assertLess(abs(float(loop[0]) - float(loop[-1])), 0.2, "o laço do ambiente emenda sem estalo")

    def test_deterministic(self):
        a, _ = tardis_sfx.load(None)
        np.testing.assert_allclose(tardis_sfx.door_close(), tardis_sfx.door_close())
        self.assertEqual(len(a["rotor"]), len(tardis_sfx.rotor_start()))


class UserFilesTest(unittest.TestCase):
    def test_authorized_user_file_replaces_the_original_and_bad_files_fall_back(self):
        folder = helpers.temp_dir("sons-")
        t = np.arange(44100, dtype=np.float32) / 44100
        _write_wav(folder / "porta_abrir.wav", 0.5 * np.sin(2 * np.pi * 440 * t), 44100, channels=2)
        (folder / "alerta.wav").write_bytes(b"isto nao e um wav")
        sounds, origin = tardis_sfx.load(folder)
        self.assertEqual(origin["porta_abrir"], "porta_abrir.wav")
        self.assertAlmostEqual(len(sounds["porta_abrir"]) / tardis_sfx.RATE, 1.0, places=2, msg="reamostrado")
        self.assertEqual(origin["alerta"], "original", "arquivo ilegível: volta o efeito original")
        self.assertEqual(origin["materializacao"], "original")


class TardisCuesTest(unittest.TestCase):
    def setUp(self):
        from ultron.audio import neural_audio as na
        self.bus, self.state = helpers.make_bus_state()
        self.out = AudioOutput()
        self.out.backend = "pyaudio"
        self.settings = helpers.make_settings(sfx_volume=0.4, tardis_sfx_volume=0.8)
        self.audio = na.NeuralAudio(self.out, bus=self.bus, state=self.state, settings_getter=lambda: self.settings)
        self.played = []
        original = self.audio.play
        self.audio.play = lambda name, gain=1.0, **k: self.played.append((name, round(gain, 3))) or original(
            name, gain, **k)
        self.audio.start()

    def tearDown(self):
        self.audio.stop()

    def test_real_tardis_events_trigger_the_effects(self):
        self.bus.publish(EventType.TARDIS_TASK_STARTED, {"id": "t1"})
        self.bus.publish(EventType.TARDIS_STATE, {"mode": "repouso"})
        self.bus.publish(EventType.TARDIS_STATE, {"mode": "operacao"})
        self.bus.publish(EventType.TARDIS_STATE, {"mode": "processando"})      # já ativo: sem novo rotor
        self.bus.publish(EventType.TARDIS_TASK_FINISHED, {"id": "t1"})
        self.bus.publish(EventType.TARDIS_TASK_FAILED, {"id": "t2"})
        names = [n for n, _ in self.played]
        self.assertEqual(names, ["desmaterializacao_curta", "rotor", "materializacao", "alerta"])
        gain = dict(self.played)["alerta"]
        self.assertAlmostEqual(gain, round(0.7 * 0.8 / 0.4, 3), msg="volume próprio dos sons da TARDIS")

    def test_switches_and_doors_and_room(self):
        self.settings.tardis_sfx = False
        self.bus.publish(EventType.TARDIS_TASK_FAILED, {"id": "t"})
        self.assertFalse(self.audio.door(True))
        self.assertEqual(self.played, [], "desligado: nenhum som da TARDIS")
        self.settings.tardis_sfx = True
        self.settings.sound_effects = False
        self.assertFalse(self.audio.door(True), "o liga/desliga geral também vale")
        self.settings.sound_effects = True
        self.assertTrue(self.audio.door(True))
        beds = []
        self.out.set_bed = lambda samples: beds.append(samples)
        self.audio.set_room(True)
        self.assertIs(beds[-1], self.audio.sound("ambiente"), "ambiente da sala como leito")
        self.audio.set_room(False)
        self.assertIs(beds[-1], self.audio._hum, "fora da sala, volta o leito normal")


if __name__ == "__main__":
    unittest.main()
