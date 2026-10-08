"""Plugin de exemplo: tempo ligado do computador.

Mostra o contrato completo: metadados, requisitos, capacidade declarada, uma skill com
``execute`` e ``verify`` independentes, e limpeza automática no ``shutdown``.
"""
from __future__ import annotations

import time

from ultron.plugins import Plugin
from ultron.skills.base import Risk, Skill, SkillResult, VerificationResult, check


def _boot_time() -> float:
    import psutil
    return float(psutil.boot_time())


def _human(seconds: float) -> str:
    days, rest = divmod(int(seconds), 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    parts = ([f"{days} dia(s)"] if days else []) + ([f"{hours} h"] if hours else []) + [f"{minutes} min"]
    return " ".join(parts)


class UptimeSkill(Skill):
    name = "plugin.uptime"
    description = "Informar há quanto tempo o computador está ligado (tempo desde a inicialização)."
    category = "system"
    risk = Risk.NONE
    requirements = {"modules": ["psutil"]}

    def execute(self, ctx, **args):
        boot = _boot_time()
        seconds = time.time() - boot
        return SkillResult(True, f"Computador ligado há {_human(seconds)}.", [f"inicialização: {time.ctime(boot)}"],
                           {"boot_time": boot, "uptime_s": round(seconds)})

    def verify(self, ctx, args, result):
        if not result.success:
            return VerificationResult("FAILED", 0.9, [], [], result.error)
        again = _boot_time()                      # nova leitura independente
        same = abs(again - result.data.get("boot_time", 0)) < 2
        return VerificationResult.from_checks([check("boot_time", same, "instante de inicialização confirmado")])


class UptimePlugin(Plugin):
    name = "system_uptime"
    version = "1.0.0"
    description = "Skill de tempo ligado do sistema (exemplo de plugin)."
    capabilities = ("skills",)
    requirements = {"modules": ["psutil"], "ultron": "1.0"}

    def initialize(self, ctx):
        ctx.register_skill(UptimeSkill())


PLUGIN = UptimePlugin()
