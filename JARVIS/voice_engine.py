"""
J.A.R.V.I.S. // voz neural local (Piper)

Voz masculina natural em português do Brasil, 100% offline, com um leve acabamento
"assistente de IA" (eco curto + normalização). Se o Piper ou o arquivo da voz não
estiverem disponíveis, load() devolve None e o backend usa a voz do Windows (pyttsx3).

Instalação:
    pip install piper-tts numpy
    python baixar_voz.py            (baixa a voz para a pasta voices/)
"""
import io
import os
import wave

VOICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")
MODEL_FILE = "pt_BR-faber-medium.onnx"     # troque aqui para usar outra voz da pasta voices/
STYLE = "jarvis"                           # "jarvis" = leve eco; "clean" = voz pura
ECHOES = ((0.035, 0.16), (0.075, 0.09))    # (atraso em s, intensidade)


class NeuralVoice:
    def __init__(self, voice, log):
        self.voice = voice
        self.log = log
        self._failed = False

    def _synthesize(self, text):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            if hasattr(self.voice, "synthesize_wav"):      # piper-tts 1.3+
                self.voice.synthesize_wav(text, wav)
            else:                                          # piper-tts 1.2
                self.voice.synthesize(text, wav)
        return buffer.getvalue()

    @staticmethod
    def _style(wav_bytes):
        try:
            import numpy as np
        except ImportError:
            return wav_bytes
        with wave.open(io.BytesIO(wav_bytes), "rb") as src:
            rate, width, channels = src.getframerate(), src.getsampwidth(), src.getnchannels()
            raw = src.readframes(src.getnframes())
        if width != 2 or channels != 1:
            return wav_bytes
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        tail = int(rate * max(delay for delay, _ in ECHOES)) + 1
        out = np.zeros(len(samples) + tail, dtype=np.float32)
        out[:len(samples)] += samples
        for delay, gain in ECHOES:
            shift = int(rate * delay)
            out[shift:shift + len(samples)] += samples * gain
        peak = float(np.max(np.abs(out))) or 1.0
        out = out / peak * 0.92 * 32767
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as dst:
            dst.setnchannels(1)
            dst.setsampwidth(2)
            dst.setframerate(rate)
            dst.writeframes(out.astype(np.int16).tobytes())
        return buffer.getvalue()

    def speak(self, text):
        """Fala (bloqueante). Devolve False se falhar, para o backend usar a voz do Windows."""
        if self._failed:
            return False
        try:
            import winsound
            wav_bytes = self._synthesize(text)
            if STYLE == "jarvis":
                wav_bytes = self._style(wav_bytes)
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
            return True
        except Exception as exc:
            self._failed = True
            self.log(f"Voz neural falhou ({exc}); usando a voz do Windows.")
            return False


def load(log=print):
    path = os.path.join(VOICE_DIR, MODEL_FILE)
    if not os.path.isfile(path):
        log("Voz neural não instalada (rode baixar_voz.py); usando a voz do Windows.")
        return None
    try:
        from piper import PiperVoice
        voice = PiperVoice.load(path)
    except Exception as exc:
        log(f"Não consegui carregar o Piper ({exc}); usando a voz do Windows.")
        return None
    log("Voz neural carregada.")
    return NeuralVoice(voice, log)
