"""Voz mais humana (prosódia) e as duas identidades vocais (JARVIS_VOICE_PROFILE / ULTRON_VOICE_PROFILE).

Partes puras (normalização e planejamento) e, quando a voz neural e o modelo de fala estão em assets/, a síntese
REAL pelo Piper — inclusive um teste de inteligibilidade: a fala processada do ULTRON precisa ser entendida pelo
reconhecedor Vosk. Nenhum alto-falante ou microfone real é usado aqui."""
import unittest

import numpy as np

import helpers  # noqa: F401  (ajusta o sys.path)

from ultron.voice import dsp, prosody


class NormalizationTest(unittest.TestCase):
    def test_written_forms_become_spoken_forms(self):
        cases = {
            "Sr. Leonardo": "senhor Leonardo",
            "às 15h30": "às 15 e 30",
            "às 9:00": "às 9 horas",
            "custa R$ 1.250,50": "custa 1250 reais e 50 centavos",
            "custa R$ 1": "custa 1 real",
            "CPU em 37%": "CPU em 37 por cento",
            "memória 2,5GB": "memória 2,5 gigabytes",
            "abra 3x": "abra 3 vezes",
            "veja https://www.exemplo.com.br/a?b=1.": "veja exemplo ponto com ponto br.",
            "a sala (andar 2) está livre": "a sala, andar 2, está livre",
            "ex.: abrir": "por exemplo, abrir",
        }
        for written, spoken in cases.items():
            self.assertEqual(prosody.normalize(written), spoken, written)

    def test_code_and_markup_are_not_read(self):
        self.assertEqual(prosody.normalize("**Pronto.** Rode `pip install x` depois."), "Pronto. Rode depois.")


class PlanningTest(unittest.TestCase):
    TEXT = ("Os sistemas estão operacionais, a memória foi verificada, os modelos locais responderam dentro do prazo "
            "e nenhuma falha foi registrada nas últimas horas. Deseja que eu continue?")

    def test_long_sentences_breathe_and_punctuation_sets_the_pauses(self):
        phrases = prosody.plan(self.TEXT)
        self.assertGreaterEqual(len(phrases), 3, "a frase longa é dividida nas vírgulas")
        self.assertTrue(phrases[0].text.endswith(","), "a vírgula fica no trecho (entonação de continuação)")
        self.assertAlmostEqual(phrases[0].pause_after, prosody.PAUSES[","])
        self.assertGreater(phrases[-2].pause_after, phrases[0].pause_after, "ponto pausa mais que vírgula")
        self.assertEqual(phrases[-1].pause_after, 0.0, "nada de silêncio no fim")
        self.assertTrue(phrases[-1].question)
        self.assertGreater(phrases[-1].length_mult, 1.0, "fim do enunciado e pergunta um pouco mais lentos")

    def test_rhythm_varies_but_deterministically(self):
        a, b = prosody.plan(self.TEXT), prosody.plan(self.TEXT)
        self.assertEqual([p.length_mult for p in a], [p.length_mult for p in b], "mesmo texto, mesmo ritmo")
        self.assertGreater(len({p.length_mult for p in a}), 1, "frases não saem todas na mesma velocidade")

    def test_ultron_style_is_flatter_slower_and_more_deliberate(self):
        j, u = prosody.plan(self.TEXT, prosody.JARVIS_STYLE), prosody.plan(self.TEXT, prosody.ULTRON_STYLE)
        self.assertLess(u[0].noise_scale, j[0].noise_scale)
        self.assertLess(u[0].noise_w_scale, j[0].noise_w_scale)
        self.assertGreater(u[0].pause_after, j[0].pause_after)


class ProfilesTest(unittest.TestCase):
    def test_two_independent_identities(self):
        from ultron.personality.voice_profile import JARVIS_VOICE_PROFILE, ULTRON_VOICE_PROFILE
        self.assertLess(ULTRON_VOICE_PROFILE.pitch, JARVIS_VOICE_PROFILE.pitch, "ULTRON mais grave")
        self.assertLess(ULTRON_VOICE_PROFILE.speed, JARVIS_VOICE_PROFILE.speed, "ritmo mais deliberado")
        self.assertGreater(ULTRON_VOICE_PROFILE.metal, 0.0)
        self.assertEqual(JARVIS_VOICE_PROFILE.metal, 0.0, "o JARVIS não tem textura metálica")

    def test_metallic_texture_keeps_length_and_level(self):
        rate = 22050
        t = np.arange(rate, dtype=np.float32) / rate
        voice = (0.4 * np.sin(2 * np.pi * 140 * t) * (1 + 0.5 * np.sin(2 * np.pi * 3 * t))).astype(np.float32)
        out = dsp.metallic(voice, 0.32, rate)
        self.assertEqual(len(out), len(voice))
        self.assertLess(float(np.max(np.abs(out))), 1.0)
        self.assertGreater(float(np.corrcoef(out, voice)[0, 1]), 0.6, "a voz original continua dominante")
        np.testing.assert_array_equal(dsp.metallic(voice, 0.0, rate), voice)


class SpeakerStyleTest(unittest.TestCase):
    def test_speaker_plans_with_the_persona_style(self):
        from ultron.personality import persona
        from ultron.voice.tts import Speaker

        class Synth:
            name = "falso"
            plans = []

            def synthesize_plan(self, phrases, *, length_scale=1.0):
                self.plans.append((phrases, length_scale))
                return np.zeros(4000, dtype=np.float32), 22050, []

        class Output:
            available, rate, paused, voice_volume = True, 22050, False, 1.0

            def play_voice(self, samples):
                import threading

                class Done:
                    done = threading.Event()
                Done.done.set()
                return Done

            def stop_voice(self):
                pass

        synth = Synth()
        speaker = Speaker(Output(), settings_getter=lambda: helpers.make_settings())
        speaker.synth = synth
        try:
            speaker._speak("Tudo pronto, senhor.")
            persona.set_persona("ultron", operator=False)
            speaker._speak("Operação concluída.")
        finally:
            persona.reset()
        (jarvis_plan, jarvis_scale), (ultron_plan, ultron_scale) = synth.plans
        self.assertEqual(jarvis_plan[0].noise_scale, prosody.JARVIS_STYLE.noise_scale)
        self.assertEqual(ultron_plan[0].noise_scale, prosody.ULTRON_STYLE.noise_scale)
        self.assertNotEqual(jarvis_scale, ultron_scale, "velocidade/altura do perfil de cada identidade")


class RealPiperProsodyTest(unittest.TestCase):
    def setUp(self):
        from ultron.config import paths
        self.voice = paths.voices_dir() / "pt_BR-faber-medium.onnx"
        if not self.voice.is_file():
            self.skipTest("voz neural ausente em assets/voices")
        try:
            from ultron.voice.tts import PiperSynth
            self.synth = PiperSynth(str(self.voice))
        except Exception as exc:                       # piper-tts não instalado
            self.skipTest(f"Piper indisponível: {exc}")

    def test_planned_pauses_are_real_and_the_mouth_alignment_is_kept(self):
        from ultron.voice.lipsync import LipSyncTrack
        text = "Bom dia. Os sistemas estão operacionais."
        flat, rate, _ = self.synth.synthesize_segments(text)
        planned, rate2, segments = self.synth.synthesize_plan(prosody.plan(text))
        self.assertEqual(rate, rate2)
        self.assertGreater(len(planned), len(flat), "a pausa do ponto ficou maior que a do modelo sozinho")
        starts = [s.start for s in segments]
        self.assertEqual(starts, sorted(starts))
        self.assertTrue(all(s.alignment or s.phonemes for s in segments))
        self.assertEqual(LipSyncTrack(planned, rate, segments).method, "phonemes", "a boca segue os fonemas")

    def test_ultron_voice_is_lower_and_still_intelligible(self):
        from ultron.config import paths
        from ultron.personality.voice_profile import JARVIS_VOICE_PROFILE as J, ULTRON_VOICE_PROFILE as U
        from ultron.voice.stt import SMALL, VoskSTT
        from ultron.voice.processor import VoicePipeline
        text = "Abra o navegador."
        voices = {}
        for name, profile, style in (("jarvis", J, prosody.JARVIS_STYLE), ("ultron", U, prosody.ULTRON_STYLE)):
            raw, rate, _ = self.synth.synthesize_plan(prosody.plan(text, style),
                                                      length_scale=dsp.length_scale_for(profile))
            voices[name] = (dsp.process(raw, rate, profile), rate)
        pitch = {k: dsp.estimate_pitch(v, r) for k, (v, r) in voices.items()}
        self.assertLess(pitch["ultron"], pitch["jarvis"], pitch)
        model = paths.stt_models_dir() / SMALL
        if not (model / "final.mdl").is_file():
            self.skipTest("modelo de fala ausente: inteligibilidade não verificada")
        samples, rate = voices["ultron"]
        pcm = dsp.to_int16(np.concatenate([np.zeros(4000, np.float32), dsp.resample(samples, 16000 / rate),
                                           np.zeros(20000, np.float32)]), 0.8)
        commands = []
        vp = VoicePipeline(on_command=lambda t, m: commands.append(t), stt_factory=lambda: (None, ""))
        vp.stt = VoskSTT(model)
        vp.detector.open_followup(30)
        for i in range(0, len(pcm), 8000):
            vp.process_chunk(pcm[i:i + 8000])
        vp.flush()
        self.assertTrue(commands and "navegador" in commands[0], f"o ULTRON não foi entendido: {commands}")


if __name__ == "__main__":
    unittest.main()
