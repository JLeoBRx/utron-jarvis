"""Skills de diagnóstico: relatório do sistema, saúde do ULTRON e processos."""
from __future__ import annotations

from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


class SystemReport(Skill):
    name = "diagnostics.system_report"
    description = "Relatório do computador: CPU, RAM, GPU, discos, bateria e processos mais pesados."
    category = "diagnostics"
    inputs = schema({})
    risk = Risk.NONE

    def available(self):
        return (True, "") if psutil is not None else (False, "psutil não instalado")

    def execute(self, ctx, **_) -> SkillResult:
        import platform

        from ...perception.system import cpu_name
        computer = ctx.world.get("computer") if ctx.world is not None else {}
        os_name = computer.get("os") or f"{platform.system()} {platform.release()}"
        cpu_label = computer.get("cpu_name") or cpu_name() or "CPU"
        cpu = psutil.cpu_percent(interval=0.4)
        vm = psutil.virtual_memory()
        parts = [f"{os_name} — {cpu_label}", f"CPU {cpu:.0f}%", f"RAM {vm.percent:.0f}% de {vm.total / 1024 ** 3:.1f} GB"]
        if computer.get("gpu_name"):
            parts.append(f"GPU {computer['gpu_name']}")
        for disk in (computer.get("disks") or [])[:4]:
            parts.append(f"disco {disk['mount']} {disk['used']:.0%} usado")
        battery = computer.get("battery")
        if battery:
            parts.append(f"bateria {battery['percent']}%{' carregando' if battery.get('plugged') else ''}")
        top = sorted(psutil.process_iter(["name", "memory_info"]),
                     key=lambda p: -(p.info["memory_info"].rss if p.info.get("memory_info") else 0))[:5]
        parts.append("maior uso de memória: " + ", ".join(p.info["name"] or "?" for p in top))
        return SkillResult(True, "; ".join(parts) + ".", ["psutil", "world model"],
                           {"cpu": cpu, "ram": vm.percent, "computer": computer})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.95, [check("measured", True, "medições diretas do sistema")])


class HealthReport(Skill):
    name = "diagnostics.health"
    description = "Saúde do ULTRON: CPU, RAM, GPU, disco, Ollama, voz, visão, rede, memória e HUD."
    category = "diagnostics"
    inputs = schema({})
    risk = Risk.NONE

    def execute(self, ctx, **_) -> SkillResult:
        monitor = ctx.extras.get("health")
        if monitor is None:
            return SkillResult(False, error="monitor de saúde indisponível", error_kind="UNSUPPORTED")
        report = monitor.check_all()
        lines = [f"{name}: {item['status']}{' — ' + item['detail'] if item.get('detail') else ''}"
                 for name, item in report["checks"].items()]
        return SkillResult(True, f"Saúde geral: {report['overall']}. " + " | ".join(lines), [], report)

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.95, [check("checked", True, "verificações executadas agora")])


class ProcessList(Skill):
    name = "diagnostics.processes"
    description = "Listar os processos que mais consomem CPU ou memória."
    category = "diagnostics"
    inputs = schema({"sort": string(6, enum=["cpu", "memory"])})
    risk = Risk.NONE

    def available(self):
        return (True, "") if psutil is not None else (False, "psutil não instalado")

    def execute(self, ctx, sort: str = "cpu") -> SkillResult:
        procs = list(psutil.process_iter(["pid", "name", "memory_info"]))
        for p in procs:
            try:
                p.cpu_percent(None)
            except psutil.Error:
                pass
        if ctx.wait(0.5):
            return SkillResult(False, error="cancelado", error_kind="CANCELLED")
        rows = []
        for p in procs:
            try:
                rows.append((p.info["name"] or "?", p.pid, p.cpu_percent(None),
                             (p.info["memory_info"].rss if p.info.get("memory_info") else 0) / 1048576))
            except psutil.Error:
                continue
        rows.sort(key=lambda r: -(r[2] if sort == "cpu" else r[3]))
        text = "; ".join(f"{n} (pid {pid}) CPU {c:.0f}% RAM {m:.0f} MB" for n, pid, c, m in rows[:8])
        return SkillResult(True, text + ".", [f"{len(rows)} processos"], {"top": rows[:15]})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.9, [check("measured", True, "amostragem de 0,5 s")])


SKILLS = (SystemReport, HealthReport, ProcessList)
