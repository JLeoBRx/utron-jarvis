"""Skills de dispositivos: periféricos conectados (câmera, microfone, áudio, USB, Bluetooth...)."""
from __future__ import annotations

from ...perception.devices import list_devices
from ...perception.base import SensorUnavailable
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string

LABELS = {"camera": "câmeras", "microphone": "microfones", "speakers": "saídas de áudio", "audio": "áudio",
          "keyboard": "teclados", "mouse": "mouses", "usb": "USB", "bluetooth": "Bluetooth", "printer": "impressoras",
          "monitor": "monitores", "storage": "armazenamento", "other": "outros"}


class ListDevices(Skill):
    name = "devices.list"
    description = "Listar periféricos conectados, opcionalmente por categoria."
    category = "devices"
    inputs = schema({"category": string(12, enum=sorted(LABELS))})
    risk = Risk.NONE
    timeout = 40.0

    def execute(self, ctx, category: str | None = None) -> SkillResult:
        try:
            devices = list_devices()
        except SensorUnavailable as exc:
            return SkillResult(False, error=str(exc), error_kind="UNSUPPORTED")
        if category:
            devices = [d for d in devices if d["category"] == category]
        if not devices:
            return SkillResult(True, "Nenhum dispositivo encontrado" + (f" na categoria {LABELS[category]}." if category
                                                                          else "."), [], {"devices": []})
        groups: dict[str, list[str]] = {}
        for d in devices:
            groups.setdefault(d["category"], []).append(d["name"])
        text = "; ".join(f"{LABELS.get(k, k)}: {', '.join(v[:5])}" for k, v in groups.items())
        return SkillResult(True, text + ".", [f"{len(devices)} dispositivo(s)"], {"devices": devices})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.9, [check("enumerated", True, "enumeração direta do sistema")])


SKILLS = (ListDevices,)
