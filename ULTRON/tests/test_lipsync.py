"""Sincronização labial: visemas pelos fonemas, abertura pela energia REAL, boca fechada no silêncio,
legenda pelo progresso das palavras, e o Speaker lendo a posição real de reprodução.

A síntese com a voz Piper real só roda quando o modelo está instalado em assets/voices (o teste diz
quando foi pulado). A "reprodução" usa uma saída SIMULADA que avança a posição em tempo real — não é
teste de alto-falante.
"""
import threading
import time
import unittest

import numpy as np

import helpers

from ultron.voice.lipsync import REST, VISEMES, LipSyncTrack, Segment, tokens, viseme_of


def tone(seconds: float, rate: int = 22050, freq: float = 180.0, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(seconds * rate)) / rate
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class TrackTest(unittest.TestCase):
    def test_tokens_from_espeak_phonemes(self):
        toks = tokens(list("ˈpaɪ nˈɛʊ."))
        self.assertEqual([t.viseme for t in toks][:3], ["PBM", "AA", "II"])
        self.assertGreater(toks[1].weight, toks[0].weight, "vogal tônica pesa mais que consoante")
        self.assertEqual(viseme_of("m"), "PBM")
        self.assertIsNone(viseme_of("ˈ"))

    def test_silence_closes_and_energy_opens(self):
        rate = 22050
        audio = np.concatenate([np.zeros(int(0.3 * rate), np.float32), tone(0.5), np.zeros(int(0.3 * rate), np.float32)])
        track = LipSyncTrack(audio, rate, [Segment(0, len(audio), list("ˈaaaa"))])
        self.assertEqual(track.method, "phonemes")
        self.assertEqual(track.at(0.1)[0][0], 0.0, "silêncio antes da fala: boca fechada")
        self.assertGreater(track.at(0.55)[0][0], 0.5, "vogal aberta com energia: boca aberta")
        self.assertEqual(track.at(1.0)[0][0], 0.0, "silêncio depois da fala: fecha")
        self.assertEqual(track.at(5.0)[0][0], REST[0], "fora da fala: repouso")
        quiet = LipSyncTrack(audio * 0.3, rate, [Segment(0, len(audio), list("ˈaaaa"))])
        self.assertAlmostEqual(quiet.at(0.55)[0][0], track.at(0.55)[0][0], places=2,
                               msg="a abertura é relativa à energia da própria fala (normalizada)")

    def test_pauses_fall_on_real_silences_and_words_progress(self):
        rate = 22050
        gap = np.zeros(int(0.25 * rate), np.float32)
        audio = np.concatenate([tone(0.4), gap, tone(0.4)])
        track = LipSyncTrack(audio, rate, [Segment(0, len(audio), list("ˈpa, ˈma"))])
        self.assertEqual(track.at(0.52)[0][0], 0.0, "a vírgula cai no silêncio real")
        self.assertEqual(track.total_words, 2)
        progress = [track.word_progress(s) for s in np.arange(0.0, track.duration + 0.1, 0.05)]
        self.assertEqual(progress, sorted(progress), "a legenda nunca volta")
        self.assertEqual(progress[-1], 1.0)
        self.assertEqual(track.at(0.02)[0][3], VISEMES["PBM"][3], "p: lábios pressionados")

    def test_alignment_from_the_model_is_used_when_available(self):
        rate = 22050
        audio = tone(0.6)
        alignment = [("p", int(0.1 * rate)), ("a", int(0.3 * rate)), ("m", int(0.2 * rate))]
        track = LipSyncTrack(audio, rate, [Segment(0, len(audio), list("pam"), alignment)])
        self.assertEqual(track.method, "alignment")
        self.assertGreater(track.at(0.25)[0][0], 0.5, "trecho do 'a' (alinhamento real) aberto")
        self.assertEqual(track.at(0.5)[0][3], VISEMES["PBM"][3], "trecho do 'm' pressionado")

    def test_without_phonemes_the_spectrum_shapes_the_mouth(self):
        track = LipSyncTrack(tone(0.5), 22050, [Segment(0, 11025)])
        self.assertEqual(track.method, "spectral")
        self.assertGreater(track.at(0.25)[0][0], 0.0)
        self.assertGreaterEqual(track.total_words, 1)


@unittest.skipUnless((helpers.ROOT / "assets" / "voices" / "pt_BR-faber-medium.onnx").is_file()
                     and helpers.module_available("piper"), "voz Piper não instalada")
class PiperRealVoiceTest(unittest.TestCase):
    def test_real_synthesis_produces_phoneme_track(self):
        from ultron.personality.voice_profile import VoiceProfile
        from ultron.voice import dsp
        from ultron.voice.tts import PiperSynth
        synth = PiperSynth(str(helpers.ROOT / "assets" / "voices" / "pt_BR-faber-medium.onnx"))
        samples, rate, segments = synth.synthesize_segments("Entendido, senhor. Abrindo o painel.")
        self.assertEqual(len(segments), 2, "uma frase por trecho")
        self.assertTrue(all(s.phonemes for s in segments))
        profile = VoiceProfile()
        processed = dsp.process(samples, rate, profile)
        scale = dsp.time_scale(profile)
        for segment in segments:
            segment.start, segment.end, segment.scale = int(segment.start * scale), int(segment.end * scale), scale
        track = LipSyncTrack(processed, rate, segments)
        self.assertEqual(track.method, "phonemes")
        opening = np.array([track.at(s)[0][0] for s in np.arange(0, track.duration, 0.01)])
        energy = np.array([track.at(s)[1] for s in np.arange(0, track.duration, 0.01)])
        self.assertTrue((opening[energy < 0.05] == 0).all(), "sem energia real a boca nunca abre")
        self.assertGreater(opening.max(), 0.4)
        self.assertGreater(np.mean(np.abs(np.diff(opening)) > 0.02), 0.05, "a boca se move durante a fala")


class FakeTimedOutput:
    """Saída SIMULADA cujo 'dispositivo' consome amostras em tempo real (posição como a do mixer)."""
    rate = 22050
    backend = "sounddevice"
    reason = ""
    available = True
    paused = False
    voice_volume = 0.9

    def __init__(self):
        self.utterance = None

    def play_voice(self, samples):
        class Utterance:
            pos = 0
            done = threading.Event()

        utterance = Utterance()
        utterance.done = threading.Event()
        self.utterance = utterance
        total = len(samples)

        def run():
            started = time.monotonic()
            while not utterance.done.is_set():
                utterance.pos = int((time.monotonic() - started) * self.rate)
                if utterance.pos >= total:
                    utterance.done.set()
                time.sleep(0.005)

        threading.Thread(target=run, daemon=True).start()
        return utterance

    def stop_voice(self):
        if self.utterance is not None:
            self.utterance.done.set()


class SegmentSynth:
    name = "sintetizador-de-teste"

    def synthesize_segments(self, text, *, length_scale=1.0):
        rate = 22050
        audio = np.concatenate([tone(0.35, rate), np.zeros(int(0.2 * rate), np.float32), tone(0.35, rate)])
        return audio, rate, [Segment(0, len(audio), list("ˈpa, ˈma"))]


class SpeakerMouthTest(unittest.TestCase):
    def _speaker(self):
        from ultron.voice.tts import Speaker
        settings = helpers.make_settings()
        output = FakeTimedOutput()
        speaker = Speaker(output, settings_getter=lambda: settings, synth_loader=lambda: (SegmentSynth(), ""))
        speaker.start()
        self.addCleanup(speaker.stop)
        self.assertTrue(speaker.wait_ready(5))
        return speaker, output

    def test_mouth_follows_real_playback_position_and_closes_after(self):
        speaker, _output = self._speaker()
        self.assertEqual(speaker.mouth()["open"], 0.0, "sem fala: boca fechada")
        speaker.say("Pá, má.")
        openings, captions = [], []
        deadline = time.time() + 5
        while time.time() < deadline and (not speaker.speaking or not openings):
            time.sleep(0.01)
            if speaker.speaking:
                openings.append(speaker.mouth()["open"])
        while speaker.speaking and time.time() < deadline:
            openings.append(speaker.mouth()["open"])
            captions.append(speaker.caption()["progress"])
            time.sleep(0.01)
        self.assertGreater(max(openings), 0.3, "abriu nas vogais")
        self.assertIn(0.0, openings[5:], "fechou no silêncio entre as palavras")
        self.assertEqual(captions, sorted(captions), "legenda avança com o áudio")
        self.assertIn(speaker.lipsync_method, ("phonemes", "alignment"))
        self.assertEqual(speaker.mouth()["open"], 0.0, "fala terminada: boca em repouso")
        self.assertTrue(speaker.caption()["text"], "a legenda fica um instante depois da fala")

    def test_interrupt_closes_the_mouth_immediately(self):
        speaker, _output = self._speaker()
        speaker.say("Pá, má.")
        deadline = time.time() + 5
        while time.time() < deadline and not (speaker.speaking and speaker.mouth()["open"] > 0.2):
            time.sleep(0.005)
        self.assertGreater(speaker.mouth()["open"], 0.2)
        speaker.interrupt()
        self.assertEqual(speaker.mouth()["open"], 0.0, "interrompida: a boca fecha no mesmo quadro")
        self.assertFalse(speaker.audible())


if __name__ == "__main__":
    unittest.main()
