"""Skills de áudio: volume, controle de mídia e a própria voz do JARVIS (diagnóstico,
lista e escolha de microfone)."""
from __future__ import annotations

import time

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


def _core(ctx):
    core = (ctx.extras or {}).get("core")
    if core is None or not getattr(core, "enable_voice", False):
        raise RuntimeError("voz desativada nesta execução")
    return core


class VoiceDiagnose(Skill):
    name = "voice.diagnose"
    description = ("Diagnosticar a voz do JARVIS: microfone detectado e selecionado, captura, reconhecimento de fala, "
                   "modelo de português e saída de voz.")
    category = "audio"
    inputs = schema({})
    risk = Risk.NONE
    timeout = 25.0

    def execute(self, ctx, **_) -> SkillResult:
        from ...voice.diagnostics import VoiceDiagnostics, format_report
        try:
            core = _core(ctx)
        except RuntimeError as exc:
            return SkillResult(False, error=str(exc), error_kind="UNSUPPORTED")
        # Dentro de um pedido em andamento o teste de ida e volta (etapas 7 e 8) esperaria por este
        # mesmo pedido; ele roda completo pelo HUB (Voz > Diagnóstico) ou por --voice-test.
        report = VoiceDiagnostics(core, cancel=ctx.cancel).run(interactive=False, probe_response=False)
        problems = [s for s in report["steps"] if s["status"] in ("FAIL", "WARN")]
        if not problems:
            text = "Voz em ordem: microfone, captura, reconhecimento e modelo de português verificados."
        else:
            text = "Voz com problemas: " + "; ".join(f"{s['title']}: {s['detail']}" for s in problems[:3]) + "."
        return SkillResult(True, text, [format_report(report)], {"report": report})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.9, [check("diagnosed", True, "medições reais do dispositivo")])


class ListMicrophones(Skill):
    name = "voice.list_mics"
    description = "Listar os microfones disponíveis e qual o JARVIS está usando."
    category = "audio"
    inputs = schema({})
    risk = Risk.NONE

    def execute(self, ctx, **_) -> SkillResult:
        from ...voice.audio import list_input_devices
        listing = list_input_devices()
        devices = listing.get("devices", [])
        core = (ctx.extras or {}).get("core")
        current = getattr(getattr(core, "voice", None), "device", "") if core is not None else ""
        if not devices:
            reason = "; ".join(listing.get("errors", [])) or "nenhum dispositivo de entrada"
            return SkillResult(True, f"Nenhum microfone disponível ({reason}).", [], {"devices": []})
        lines = [f"{d['index']}: {d['name']}" + (" (padrão)" if d.get("default") else "") +
                 (" — em uso" if current and d["name"] == current else "") for d in devices]
        return SkillResult(True, f"{len(devices)} microfone(s): " + "; ".join(lines) + ".", [listing["backend"]],
                           {"devices": devices, "current": current})

    def verify(self, ctx, args, result):
        return VerificationResult("VERIFIED", 0.9, [check("listed", True, "dispositivos lidos do sistema")])


class SelectMicrophone(Skill):
    name = "voice.select_mic"
    description = "Escolher o microfone do JARVIS pelo número da lista ou por parte do nome."
    category = "audio"
    inputs = schema({"device": string(120)}, ("device",))
    risk = Risk.LOW
    timeout = 20.0

    def execute(self, ctx, device: str) -> SkillResult:
        from ...voice.audio import list_input_devices
        try:
            core = _core(ctx)
        except RuntimeError as exc:
            return SkillResult(False, error=str(exc), error_kind="UNSUPPORTED")
        devices = list_input_devices().get("devices", [])
        wanted = device.strip()
        chosen = None
        if wanted.isdigit():
            chosen = next((d for d in devices if d["index"] == int(wanted)), None)
        if chosen is None:
            matches = [d for d in devices if wanted.casefold() in d["name"].casefold()]
            chosen = matches[0] if len(matches) == 1 else None
            if len(matches) > 1:
                return SkillResult(False, error="mais de um microfone corresponde: " +
                                   "; ".join(f"{d['index']}: {d['name']}" for d in matches[:5]),
                                   error_kind="INVALID_ARGUMENT")
        if chosen is None:
            return SkillResult(False, error=f"microfone \"{wanted}\" não encontrado", error_kind="NOT_FOUND")
        core.settings_manager.update(mic_name=chosen["name"], mic_index=int(chosen["index"]))
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            if ctx.wait(0.3):
                break
            if core.voice.capturing and core.voice.device == chosen["name"]:
                break
        return SkillResult(True, f"Microfone selecionado: {chosen['name']}.", [chosen["name"]],
                           {"device": chosen["name"], "index": chosen["index"]})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        core = (ctx.extras or {}).get("core")
        voice = getattr(core, "voice", None)
        opened = voice is not None and voice.capturing and voice.device == result.data["device"]
        if opened:
            return VerificationResult.from_checks([check("capturing", True, f"capturando de {voice.device}")])
        reason = getattr(voice, "reason", "") if voice is not None else "voz indisponível"
        return VerificationResult.from_checks([check("capturing", False, f"o microfone não abriu: {reason}")])


SKILLS = (Volume, Media, VoiceDiagnose, ListMicrophones, SelectMicrophone)
