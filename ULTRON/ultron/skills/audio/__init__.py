"""Skills de áudio: volume e controle de mídia (teclas de mídia do sistema)."""
from __future__ import annotations

from .._util import pyautogui
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string


def _master_volume():
    """Volume mestre via pycaw (opcional, Windows). Devolve o controlador ou None."""
    try:
        from ctypes import POINTER, cast

        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(interface, POINTER(IAudioEndpointVolume))
    except Exception:
        return None


class Volume(Skill):
    name = "audio.volume"
    description = "Aumentar, diminuir ou silenciar o volume do sistema."
    category = "audio"
    inputs = schema({"direction": string(5, enum=["up", "down", "mute"])}, ("direction",))
    requirements = {"modules": ["pyautogui"]}
    risk = Risk.LOW

    def execute(self, ctx, direction: str) -> SkillResult:
        control = _master_volume()
        before = None
        if control is not None:
            try:
                before = {"level": float(control.GetMasterVolumeLevelScalar()), "muted": bool(control.GetMute())}
            except Exception:
                before = None
        key, count = {"up": ("volumeup", 5), "down": ("volumedown", 5), "mute": ("volumemute", 1)}[direction]
        for _ in range(count):
            pyautogui().press(key)
        labels = {"up": "Volume aumentado.", "down": "Volume diminuído.", "mute": "Som alternado (mudo)."}
        return SkillResult(True, labels[direction], [f"tecla {key} x{count}"], {"before": before})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        before = result.data.get("before")
        control = _master_volume()
        if before is None or control is None:
            return VerificationResult("UNCONFIRMED", 0.6, [check("volume", None, "pycaw indisponível")],
                                      reason="nível de volume não legível sem pycaw")
        level, muted = float(control.GetMasterVolumeLevelScalar()), bool(control.GetMute())
        direction = args["direction"]
        ok = (level > before["level"] or level >= 0.99) if direction == "up" else \
             (level < before["level"] or level <= 0.01) if direction == "down" else muted != before["muted"]
        return VerificationResult.from_checks([check("volume", ok, f"volume {level:.0%}{' (mudo)' if muted else ''}")])


class Media(Skill):
    name = "audio.media"
    description = "Controlar reprodução de mídia: tocar/pausar, próxima, anterior."
    category = "audio"
    inputs = schema({"action": string(12, enum=["play_pause", "next", "previous"])}, ("action",))
    requirements = {"modules": ["pyautogui"]}
    risk = Risk.LOW

    def execute(self, ctx, action: str) -> SkillResult:
        key = {"play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack"}[action]
        pyautogui().press(key)
        return SkillResult(True, {"play_pause": "Reprodução alternada.", "next": "Próxima faixa.",
                                  "previous": "Faixa anterior."}[action], [f"tecla {key}"])


SKILLS = (Volume, Media)
