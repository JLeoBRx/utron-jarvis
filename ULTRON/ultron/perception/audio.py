"""Sensor de áudio do sistema: dispositivos de entrada/saída e o dispositivo padrão."""
from __future__ import annotations

from .base import Percept, Sensor, SensorUnavailable


def list_audio_devices() -> dict:
    try:
        import pyaudio
    except ImportError as exc:
        raise SensorUnavailable("PyAudio não instalado") from exc
    audio = pyaudio.PyAudio()
    try:
        inputs, outputs = [], []
        for index in range(audio.get_device_count()):
            info = audio.get_device_info_by_index(index)
            entry = {"index": index, "name": str(info.get("name", "")), "rate": int(info.get("defaultSampleRate", 0))}
            if int(info.get("maxInputChannels", 0)) > 0:
                inputs.append(entry)
            if int(info.get("maxOutputChannels", 0)) > 0:
                outputs.append(entry)
        default_in = default_out = None
        try:
            default_in = str(audio.get_default_input_device_info().get("name", ""))
        except (IOError, OSError):
            pass
        try:
            default_out = str(audio.get_default_output_device_info().get("name", ""))
        except (IOError, OSError):
            pass
        return {"inputs": inputs, "outputs": outputs, "default_input": default_in, "default_output": default_out}
    finally:
        audio.terminate()


class AudioSensor(Sensor):
    name = "audio"
    kind = "auditory"

    def __init__(self, interval: float = 30.0):
        super().__init__(interval)

    def available(self) -> tuple[bool, str]:
        import importlib.util
        if importlib.util.find_spec("pyaudio") is None:
            return False, "PyAudio não instalado"
        return True, ""

    def sense(self) -> Percept:
        return Percept("audio", "auditory", list_audio_devices(), 1.0)
