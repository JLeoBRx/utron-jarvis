"""Voz do ULTRON: captura, reconhecimento, ativação, síntese e processamento de sinal."""
from .audio import AudioOutput, open_microphone
from .processor import VoicePipeline
from .profile import effective_profile
from .stt import VoskSTT, choose_model
from .tts import Speaker, load_synth
from .wake_word import WakeWordDetector

__all__ = ["AudioOutput", "open_microphone", "VoicePipeline", "effective_profile", "VoskSTT", "choose_model",
           "Speaker", "load_synth", "WakeWordDetector"]
