from faster_whisper import WhisperModel
import sounddevice as sd
import numpy as np
import wave
import tempfile
import os

print("Carregando Whisper...")

model = WhisperModel(
    "small",
    device="cpu",
    compute_type="int8"
)

print("Whisper carregado!")
print("Fale uma frase.")

sample_rate = 16000
duration = 6

audio = sd.rec(
    int(duration * sample_rate),
    samplerate=sample_rate,
    channels=1,
    dtype="float32"
)

sd.wait()

audio = np.squeeze(audio)

arquivo = tempfile.NamedTemporaryFile(
    suffix=".wav",
    delete=False
).name

with wave.open(arquivo, "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(sample_rate)

    audio_int16 = (audio * 32767).astype(np.int16)
    wav.writeframes(audio_int16.tobytes())

segments, info = model.transcribe(
    arquivo,
    language="pt",
    vad_filter=True
)

texto = " ".join(segment.text for segment in segments)

print()
print("Você disse:")
print(texto)

os.remove(arquivo)