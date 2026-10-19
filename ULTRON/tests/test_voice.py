import threading
import time
import unittest

import numpy as np

import helpers

from ultron.core.events import EventType
from ultron.personality.voice_profile import JARVIS
from ultron.voice import dsp
from ultron.voice.audio import AudioOutput, mix_block
from ultron.voice.processor import VoicePipeline, classify_short_command, echo_ratio, find_barge_in
from ultron.voice.wake_word import WakeWordDetector, learn_variants, learn_weak_variants


class FakeSTT:
    label = "fake"

    def __init__(self):
        self.script: list[tuple] = []
        self.last_confidence = 0.9

    def accept(self, chunk):
        return self.script.pop(0) if self.script else (None, None)

    def finish(self):
        return ""

    def reset(self):
        pass


class FakeSpeaker:
    def __init__(self):
        self.speaking = False
        self.current_text = ""
        self.last_spoken_at = 0.0
        self.available = True
        self.muted = False
        self._paused = False
        self.calls = []

    def recent_text(self, window=15.0):
        return self.current_text

    def interrupt(self):
        self.calls.append("interrupt")
        self.speaking, self.current_text = False, ""
        self.last_spoken_at = time.time()

    def pause(self):
        self.calls.append("pause")
        self._paused = True
        return True

    def resume(self):
        self.calls.append("resume")
        self._paused = False
        return True

    @property
    def paused(self):
        return self._paused


class WakeWordTest(unittest.TestCase):
    def test_strong_and_weak_forms(self):
        d = WakeWordDetector()                         # formas medidas do JARVIS
        self.assertEqual(d.detect("Jarvis, abra o chrome").command, "abra o chrome")
        self.assertEqual(d.detect("ok jarvis que horas são").strength, "strong")
        self.assertEqual(d.detect("já vis liste os dispositivos").strength, "strong")
        self.assertFalse(d.detect("eu falei com o jarvis ontem").detected, "só no início da frase")
        weak = d.detect("aviso abra o bloco de notas")
        self.assertEqual((weak.strength, weak.command), ("weak", "abra o bloco de notas"))
        self.assertFalse(d.detect("ultron abra o chrome").detected, "a identidade anterior não ativa mais")

    def test_names_are_strong_only_opening_the_sentence(self):
        d = WakeWordDetector()
        self.assertEqual(d.detect("Jarbas.").strength, "strong", "\"Jarvis\" ouvido como o nome Jarbas")
        self.assertEqual(d.detect("jarbas que horas são").strength, "strong")
        named = d.detect("o jarbas ligou ontem")
        self.assertEqual(named.strength, "weak", "depois de 'o' é o nome de alguém: exige comando")

    def test_calibration_never_learns_common_words(self):
        learned = learn_variants(["jarves", "aviso", "aves", "atenção", "jarbis"], ("jarvis",))
        self.assertIn("jarves", learned)
        self.assertIn("jarbis", learned)
        self.assertNotIn("aviso", learned)
        self.assertNotIn("atenção", learned)
        self.assertEqual(learn_weak_variants(["a vez", "a vez", "atenção"], ("jarvis",)), ("a vez",))

    def test_followup_window(self):
        d = WakeWordDetector(followup_seconds=0.2)
        d.open_followup()
        self.assertTrue(d.in_followup())
        time.sleep(0.25)
        self.assertFalse(d.in_followup())


class BargeInLogicTest(unittest.TestCase):
    def setUp(self):
        detector = WakeWordDetector(("jarvis",), ())
        self.wake = lambda t: (lambda r: r if r.detected and (r.strength == "strong" or r.command) else None)(
            detector.detect(t))
        self.spoken = "Entendido. Analisando o sistema. Eu sou o Jarvis."

    def test_echo_vs_user(self):
        self.assertGreaterEqual(echo_ratio("analisando o sistema", self.spoken), 0.5)
        self.assertIsNone(find_barge_in("analisando o sistema", self.spoken, self.wake))
        self.assertIsNone(find_barge_in("eu sou o jarvis", self.spoken, self.wake), "a própria voz não ativa")
        self.assertEqual(find_barge_in("entendido analisando pode parar", self.spoken, self.wake)[0], "cancel")
        self.assertEqual(find_barge_in("jarvis abra o chrome", self.spoken, self.wake), ("wake", "abra o chrome"))

    def test_short_commands(self):
        self.assertEqual(classify_short_command("pode parar"), "cancel")
        self.assertEqual(classify_short_command("espere um pouco"), "pause")
        self.assertEqual(classify_short_command("pode continuar"), "resume")
        self.assertIsNone(classify_short_command("para o carro agora já"), "frase longa não é controle")


class VoicePipelineTest(unittest.TestCase):
    def setUp(self):
        self.bus, self.state = helpers.make_bus_state()
        self.stt = FakeSTT()
        self.speaker = FakeSpeaker()
        self.commands = []
        from ultron.cognition.intent_engine import IntentEngine
        engine = IntentEngine()
        self.vp = VoicePipeline(bus=self.bus, state=self.state, speaker=self.speaker,
                                on_command=lambda text, meta: self.commands.append((text, meta)),
                                stt_factory=lambda: (self.stt, ""),
                                command_check=lambda t: engine.classify(t).kind not in ("unknown", "response"))
        self.vp.stt = self.stt
        self.vp._subs = [self.bus.subscribe(EventType.VOICE_FINISHED, self.vp._on_voice_finished)]

    def say(self, final, partials=()):
        for partial in partials:
            self.stt.script.append((None, partial))
            self.vp.process_chunk(b"\x00\x00" * 64)
        self.stt.script.append((final, None))
        self.vp.process_chunk(b"\x00\x00" * 64)

    def test_wake_word_command_and_privacy(self):
        self.say("abra o navegador")
        self.assertEqual(self.commands, [], "sem palavra de ativação: descartado")
        self.assertEqual(self.vp.ignored, 1)
        self.say("jarvis abra o navegador", partials=("jarvis", "jarvis abra"))
        self.assertEqual(self.commands[-1][0], "abra o navegador")
        self.assertTrue(self.commands[-1][1]["wake"])

    def test_weak_form_needs_a_real_command(self):
        self.say("aviso")
        self.say("aviso bom dia")
        self.say("o jarbas ligou ontem")
        self.assertEqual(self.commands, [], "formas fracas e nomes no meio da frase não ativam sozinhos")
        self.say("aviso abra o bloco de notas")
        self.assertEqual(self.commands[-1][0], "abra o bloco de notas")

    def test_followup_after_spoken_response(self):
        self.say("jarvis que horas são")
        self.bus.publish(EventType.VOICE_FINISHED, {"spoken": True, "interrupted": False})
        self.say("abra o navegador")
        self.assertEqual(self.commands[-1][0], "abra o navegador")
        self.assertTrue(self.commands[-1][1]["followup"])

    def test_wake_only_then_command(self):
        self.say("jarvis")
        self.assertTrue(self.vp.listening)
        self.say("abra o navegador")
        self.assertEqual(self.commands[-1][0], "abra o navegador")

    def test_echo_is_ignored_and_user_can_interrupt(self):
        self.speaker.speaking, self.speaker.current_text = True, "Entendido. Analisando o sistema."
        self.say("entendido analisando o sistema")
        self.assertEqual(self.commands, [])
        self.assertEqual(self.vp.echoes, 1)
        self.say("pode parar", partials=("pode parar",))
        self.assertIn("interrupt", self.speaker.calls)
        self.assertEqual(self.commands[-1][1]["control"], "cancel")

    def test_pause_and_resume_while_speaking(self):
        self.speaker.speaking, self.speaker.current_text = True, "Uma resposta longa sobre o sistema."
        self.say("espere um pouco")
        self.say("pode continuar")
        self.assertEqual(self.speaker.calls, ["pause", "resume"])
        self.assertEqual(self.commands, [])

    def test_mic_toggle_and_probe(self):
        self.assertFalse(self.vp.toggle_mic(False))
        self.assertEqual(self.vp.health()["status"], "WARN")
        probe = self.vp.mic_probe()
        self.assertFalse(probe["enabled"])
        self.assertIn("level", probe)

    def test_counters_and_absolute_silence_warning(self):
        from ultron.voice.processor import SILENT_CHUNKS_WARNING
        for _ in range(SILENT_CHUNKS_WARNING):
            self.vp.process_chunk(b"\x00\x00" * 64)
        self.assertIn("Privacidade", self.vp.silence_warning)
        self.vp.capturing, self.vp.device = True, "Mic"
        self.assertEqual(self.vp.health()["status"], "WARN", "silêncio absoluto é informado, não escondido")
        self.vp.process_chunk(b"\x10\x00" * 64)
        self.assertEqual(self.vp.silence_warning, "", "som de verdade limpa o aviso")
        counters = self.vp.counters()
        self.assertEqual(counters["chunks"], SILENT_CHUNKS_WARNING + 1)
        self.assertEqual(counters["zero_chunks"], SILENT_CHUNKS_WARNING)

    def test_injected_text_takes_the_voice_route(self):
        taps = []
        self.vp.diagnostic_tap = lambda kind, data: taps.append(kind)
        self.vp.inject_text("que horas são", diagnostic=True)
        self.assertEqual(self.commands[-1][0], "que horas são")
        self.assertTrue(self.commands[-1][1]["diagnostic"])
        self.assertEqual(self.vp.stats["delivered"], 1)
        self.assertIn("delivered", taps)


class SupervisorTest(unittest.TestCase):
    def test_microphone_failures_are_retried_and_reported(self):
        attempts = {"n": 0}

        class Stream:
            def __init__(self):
                self.chunks = [b"S" + b"\x00" * 7]

            def read(self, n, exception_on_overflow=False):
                time.sleep(0.01)
                if not self.chunks:
                    raise OSError("dispositivo removido")
                return self.chunks.pop(0)

        def opener():
            attempts["n"] += 1
            if attempts["n"] <= 2:
                raise RuntimeError("nenhum microfone disponível")
            return None, Stream(), "Microfone de teste"

        stt = FakeSTT()
        stt.script = [("jarvis que horas são", None)]
        got = []
        vp = VoicePipeline(on_command=lambda t, m: got.append(t), stt_factory=lambda: (stt, ""), mic_opener=opener)
        vp._sleep = lambda s: time.sleep(min(s, 0.02))
        vp.start()
        deadline = time.time() + 5
        while time.time() < deadline and not got:
            time.sleep(0.02)
        vp.stop()
        self.assertEqual(got, ["que horas são"])
        self.assertGreaterEqual(attempts["n"], 3)
        self.assertIn("removido", vp.reason)


class DspTest(unittest.TestCase):
    @staticmethod
    def voice_like(f0=140.0, rate=22050, seconds=1.0):
        """Espectro de voz: 40 harmônicos com inclinação de -6 dB/oitava e um pouco de sopro."""
        t = np.arange(int(rate * seconds)) / rate
        signal = sum((1.0 / k) * np.sin(2 * np.pi * f0 * k * t) for k in range(1, 41))
        signal += 0.02 * np.random.default_rng(1).standard_normal(len(t))
        return (signal / np.max(np.abs(signal)) * 0.8).astype(np.float32)

    def test_jarvis_profile_is_deeper_but_natural(self):
        from ultron.personality.voice_profile import ULTRON
        rate = 22050
        raw = self.voice_like(rate=rate)
        processed = dsp.process(raw, rate, JARVIS)
        before, after = dsp.estimate_pitch(raw, rate), dsp.estimate_pitch(processed, rate)
        self.assertLess(after, before * 0.98, "um pouco mais grave")
        self.assertGreater(after, before * 0.9, "sem rebaixar a ponto de perder naturalidade")
        self.assertLessEqual(float(np.max(np.abs(processed))), 0.93)

        def presence(x):
            """Energia na faixa de inteligibilidade (1–4 kHz) relativa à faixa da voz (100 Hz–4 kHz)."""
            power = np.abs(np.fft.rfft(x)) ** 2
            freqs = np.fft.rfftfreq(len(x), 1 / rate)
            return float(power[(freqs >= 1000) & (freqs < 4000)].sum() / power[(freqs >= 100) & (freqs < 4000)].sum())

        kept = presence(processed) / presence(raw)
        self.assertGreater(kept, 0.65, "a clareza da fala é preservada")
        self.assertLess(presence(dsp.process(raw, rate, ULTRON)) / presence(raw), kept,
                        "o perfil robótico anterior era menos inteligível")

    def test_speed_compensation_and_pcm_roundtrip(self):
        self.assertAlmostEqual(dsp.length_scale_for(JARVIS), JARVIS.pitch / JARVIS.speed, places=3)
        x = np.linspace(-0.5, 0.5, 100).astype(np.float32)
        self.assertTrue(np.allclose(dsp.from_int16(dsp.to_int16(x)), x, atol=1e-3))


class MicrophoneBackendTest(unittest.TestCase):
    def test_resampling_stream_turns_48k_into_16k(self):
        from ultron.voice.audio import _ResamplingStream

        class Source:
            def __init__(self):
                t = np.arange(48000 * 2) / 48000
                tone = 0.5 * np.sin(2 * np.pi * 440 * t) + 0.3 * np.sin(2 * np.pi * 15000 * t)   # 15 kHz: acima do Nyquist
                self.pcm = (tone * 32767).astype(np.int16).tobytes()
                self.pos = 0

            def read(self, frames, exception_on_overflow=False):
                chunk = self.pcm[self.pos:self.pos + frames * 2]
                self.pos += frames * 2
                return chunk

            def close(self):
                pass

        stream = _ResamplingStream(Source(), 48000, 16000)
        out = np.frombuffer(b"".join(stream.read(4000) for _ in range(6)), dtype=np.int16).astype(np.float32)
        self.assertEqual(len(out), 24000, "blocos de 250 ms a 16 kHz")
        spectrum = np.abs(np.fft.rfft(out[2000:]))
        freqs = np.fft.rfftfreq(len(out) - 2000, 1 / 16000)
        tone = spectrum[np.argmin(np.abs(freqs - 440))]
        alias = spectrum[np.argmin(np.abs(freqs - 1000))]          # 15 kHz dobraria para 1 kHz sem filtro
        self.assertGreater(tone, alias * 20, "o filtro impede o serrilhado")

    def test_device_order_never_tries_other_inputs_on_its_own(self):
        from ultron.voice.audio import _candidates
        devices = [{"index": 0, "name": "Mixagem estéreo (Realtek)"}, {"index": 1, "name": "Microfone (USB)"},
                   {"index": 2, "name": "Microfone (Realtek)"}]
        self.assertEqual([d["index"] for d in _candidates(devices, 2, "usb", -1)], [1, 2])
        self.assertEqual([d["index"] for d in _candidates(devices, None, "", 1)], [1])
        self.assertEqual(_candidates(devices, None, "", -1), [], "sem escolha nem padrão: pergunta ao usuário")

    def test_missing_audio_libraries_are_reported(self):
        from ultron.voice import audio
        listing = audio.list_input_devices("nao-existe")
        self.assertIsNone(listing["backend"])
        if not helpers.module_available("pyaudio") and not helpers.module_available("sounddevice"):
            with self.assertRaises(audio.AudioBackendMissing):
                audio.open_microphone()


class AudioOutputTest(unittest.TestCase):
    def test_no_device_is_reported_not_faked(self):
        out = AudioOutput()
        self.assertFalse(out.available)
        utterance = out.play_voice(np.zeros(100, dtype=np.float32))
        self.assertTrue(utterance.done.is_set())
        self.assertFalse(out.play_effect(np.zeros(10, dtype=np.float32)))

    def test_mixer_ducks_effects_and_fades_bed(self):
        voice = np.full(64, 0.5, dtype=np.float32)
        effect = np.full(64, 0.5, dtype=np.float32)
        alone = mix_block(None, [effect], voice_gain=1.0, sfx_gain=1.0)
        ducked = mix_block(voice, [effect], voice_gain=0.0, sfx_gain=1.0)
        self.assertLess(float(ducked[0]), float(alone[0]))
        out = AudioOutput()
        out.backend = "pyaudio"              # mixer sem dispositivo (verificação do roteamento)
        out.set_bed(np.sin(np.linspace(0, 200, 22050)).astype(np.float32))
        out.bed_target = 0.6
        levels = [float(np.abs(out._next_block(512)).max()) for _ in range(60)]
        self.assertLess(levels[0], levels[-1], "zumbido entra suavemente")

    def test_speaker_without_output_says_so(self):
        from ultron.voice.tts import Speaker
        bus, state = helpers.make_bus_state()
        finished = threading.Event()
        payloads = []
        bus.subscribe(EventType.VOICE_FINISHED, lambda e: (payloads.append(e.payload), finished.set()))
        speaker = Speaker(AudioOutput(), bus=bus, state=state, synth_loader=lambda: (None, "voz não instalada"))
        speaker.start()
        speaker.say("Teste de fala.")
        self.assertTrue(finished.wait(5))
        speaker.stop()
        self.assertFalse(payloads[0]["spoken"])
        self.assertIn("voz não instalada", payloads[0]["reason"])


class NeuralAudioTest(unittest.TestCase):
    def test_cues_follow_real_events_with_rate_limits(self):
        from ultron.audio import neural_audio as na
        bus, state = helpers.make_bus_state()
        out = AudioOutput()
        out.backend = "pyaudio"
        audio = na.NeuralAudio(out, bus=bus, state=state)
        audio.start()
        bus.publish(EventType.WAKE_WORD, {})
        bus.publish(EventType.WAKE_WORD, {})
        bus.publish(EventType.COGNITIVE_PHASE, {"phase": ""})
        self.assertEqual(audio.played, 1)
        state.set_runtime_state("EXECUTING")
        self.assertGreater(out.bed_target, 0)
        state.set_runtime_state("IDLE")
        self.assertEqual(out.bed_target, 0.0, "repouso é silencioso")
        audio.stop()
        silent = na.NeuralAudio(AudioOutput(), bus=bus)
        silent.start()
        self.assertEqual(silent.health()["status"], "UNAVAILABLE")


@unittest.skipIf(helpers.QUICK, "teste lento (--quick)")
@unittest.skipUnless(helpers.module_available("vosk") and helpers.module_available("piper"),
                     "Vosk e Piper necessários para a integração real de voz")
class RealSpeechIntegrationTest(unittest.TestCase):
    def test_piper_to_vosk_through_pipeline(self):
        from ultron.config import paths
        from ultron.voice.stt import SMALL, VoskSTT
        from ultron.voice.tts import PiperSynth
        voice = paths.voices_dir() / "pt_BR-faber-medium.onnx"
        model = paths.stt_models_dir() / SMALL
        if not voice.is_file() or not (model / "final.mdl").is_file():
            self.skipTest("voz ou modelo de fala ausente em assets/")
        samples, rate = PiperSynth(str(voice)).synthesize("Abra o navegador.")
        pcm = dsp.to_int16(np.concatenate([np.zeros(4000, np.float32), dsp.resample(samples, 16000 / rate),
                                           np.zeros(20000, np.float32)]), 0.8)
        commands = []
        vp = VoicePipeline(on_command=lambda t, m: commands.append(t), stt_factory=lambda: (None, ""))
        vp.stt = VoskSTT(model)
        vp.detector.open_followup(30)            # janela de continuação aberta: sem palavra de ativação
        for i in range(0, len(pcm), 8000):
            vp.process_chunk(pcm[i:i + 8000])
        vp.flush()
        self.assertTrue(commands and "navegador" in commands[0], commands)


if __name__ == "__main__":
    unittest.main()
