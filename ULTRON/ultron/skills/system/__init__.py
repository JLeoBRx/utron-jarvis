"""Skills de sistema: energia, bloqueio, espera, rádios (Wi-Fi/Bluetooth/avião), brilho e estado.

Os scripts PowerShell abaixo são FIXOS (herdados do JARVIS). Somente valores de listas
fechadas entram neles, por variável de ambiente.
"""
from __future__ import annotations

import sys

from ...platform import system, win32
from .._util import wait_until
from ..base import Risk, Skill, SkillResult, VerificationResult, check, schema, string

IS_WINDOWS = sys.platform == "win32"

_PS_WINRT = r'''
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) {
    $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}
[Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
'''
_PS_RADIO_GET = _PS_WINRT + r'''
foreach ($r in $radios) { Write-Output ('{0}={1}' -f $r.Kind, $r.State) }
'''
_PS_RADIO_SET = _PS_WINRT + r'''
$kind = $env:ULTRON_RADIO
$state = $env:ULTRON_STATE
$targets = @($radios | Where-Object { $_.Kind.ToString() -eq $kind })
if ($targets.Count -eq 0) { Write-Output 'NONE'; exit 3 }
foreach ($r in $targets) {
    Await ($r.SetStateAsync($state)) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
}
Write-Output 'OK'
'''
_PS_BRIGHT_GET = r'''
$ErrorActionPreference = 'Stop'
$b = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness | Select-Object -First 1
if ($null -eq $b) { Write-Output 'NONE'; exit 3 }
Write-Output $b.CurrentBrightness
'''
_PS_BRIGHT_SET = r'''
$ErrorActionPreference = 'Stop'
$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods | Select-Object -First 1
if ($null -eq $m) { Write-Output 'NONE'; exit 3 }
Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{ Timeout = [uint32]1; Brightness = [byte][int]$env:ULTRON_LEVEL } | Out-Null
Write-Output 'OK'
'''

RADIO_KINDS = {"wifi": ("WiFi",), "bluetooth": ("Bluetooth",), "airplane": ("WiFi", "Bluetooth", "MobileBroadband")}
RADIO_LABELS = {"wifi": "Wi-Fi", "bluetooth": "Bluetooth", "airplane": "Modo avião"}


def radio_states() -> dict[str, list[str]]:
    result = system.powershell(_PS_RADIO_GET)
    if not result.ok:
        raise RuntimeError((result.stdout or result.stderr).strip()[:200] or "falha ao ler rádios")
    states: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            kind, value = line.strip().split("=", 1)
            states.setdefault(kind, []).append(value)
    return states


def get_brightness() -> int:
    result = system.powershell(_PS_BRIGHT_GET)
    try:
        return int(float(result.stdout.strip().splitlines()[-1]))
    except (ValueError, IndexError):
        raise RuntimeError("este monitor não permite controlar o brilho por software (comum em monitores externos)")


class _WindowsOnly(Skill):
    category = "system"
    requirements = {"platform": "win32"}


class Power(_WindowsOnly):
    name = "system.power"
    description = "Desligar, reiniciar, suspender, encerrar sessão ou cancelar desligamento agendado."
    inputs = schema({"action": string(20, enum=["shutdown", "restart", "sleep", "logoff", "cancel"])}, ("action",))
    risk = Risk.CRITICAL
    reversible = False
    expose_to_llm = True       # JARVIS original: power_control era ferramenta do agente; risco crítico = sempre pede

    def risk_for(self, args):
        return Risk.LOW if args.get("action") == "cancel" else Risk.CRITICAL

    def execute(self, ctx, action: str) -> SkillResult:
        commands = {"shutdown": ["shutdown", "/s", "/t", "15"], "restart": ["shutdown", "/r", "/t", "15"],
                    "logoff": ["shutdown", "/l"], "cancel": ["shutdown", "/a"],
                    "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]}
        result = system.run(commands[action], timeout=10)
        if action == "cancel":
            return SkillResult(True, "Desligamento cancelado." if result.ok else "Não havia desligamento agendado.", [])
        if not result.ok and action != "sleep":
            return SkillResult(False, error=result.stderr.strip()[:200] or "o comando falhou",
                               error_kind="PERMISSION_ERROR")
        message = "Agendado para daqui a 15 segundos. Diga 'cancelar desligamento' para abortar." \
            if action in ("shutdown", "restart") else "Executando."
        return SkillResult(True, message, [f"shutdown {action}"])


class Lock(_WindowsOnly):
    name = "system.lock"
    description = "Bloquear o computador."
    inputs = schema({})
    risk = Risk.MEDIUM

    def execute(self, ctx, **_) -> SkillResult:
        if not win32.lock_workstation():
            return SkillResult(False, error="o Windows recusou o bloqueio", error_kind="PERMISSION_ERROR")
        return SkillResult(True, "Computador bloqueado.", ["LockWorkStation"])


class Wait(Skill):
    name = "system.wait"
    description = "Aguardar alguns segundos (ex.: depois de abrir um aplicativo)."
    category = "system"
    inputs = schema({"seconds": {"type": "integer", "minimum": 1, "maximum": 15}}, ("seconds",))
    risk = Risk.NONE

    def execute(self, ctx, seconds: int) -> SkillResult:
        if ctx.wait(seconds):
            return SkillResult(False, error="espera cancelada", error_kind="CANCELLED")
        return SkillResult(True, f"Aguardei {seconds} s.", [])

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.99, [check("elapsed", True, result.result)])


class Radio(_WindowsOnly):
    name = "system.radio"
    description = "Ligar ou desligar Wi-Fi, Bluetooth ou modo avião."
    inputs = schema({"radio": string(12, enum=["wifi", "bluetooth", "airplane"]),
                     "state": string(3, enum=["on", "off"])}, ("radio", "state"))
    risk = Risk.LOW

    def risk_for(self, args):
        disables = (args.get("state") == "off") != (args.get("radio") == "airplane")
        return Risk.HIGH if disables else Risk.LOW          # desligar rádios pode derrubar a conexão

    def execute(self, ctx, radio: str, state: str) -> SkillResult:
        target = "On" if (state == "on") != (radio == "airplane") else "Off"
        done = []
        for kind in RADIO_KINDS[radio]:
            result = system.powershell(_PS_RADIO_SET, ULTRON_RADIO=kind, ULTRON_STATE=target)
            if result.ok:
                done.append(kind)
            elif "NONE" in result.stdout and radio == "airplane":
                continue
            elif "NONE" in result.stdout:
                return SkillResult(False, error=f"rádio {RADIO_LABELS[radio]} não encontrado", error_kind="NOT_FOUND")
            else:
                return SkillResult(False, error=(result.stderr or result.stdout).strip()[:200],
                                   error_kind="PERMISSION_ERROR")
        if not done:
            return SkillResult(False, error="nenhum rádio controlável encontrado", error_kind="NOT_FOUND")
        return SkillResult(True, f"{RADIO_LABELS[radio]}: {'ligado' if state == 'on' else 'desligado'}.", done,
                           {"want": target, "kinds": done})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        want, kinds = result.data["want"], result.data["kinds"]

        def ok():
            states = radio_states()
            return all(v == want for k in kinds for v in states.get(k, [])) and any(k in states for k in kinds)

        confirmed = wait_until(ok, timeout=5.0, interval=1.0, ctx=ctx)
        return VerificationResult.from_checks([check("radio_state", bool(confirmed), f"estado {want} confirmado"
                                                     if confirmed else f"estado {want} não confirmado")])


class Brightness(_WindowsOnly):
    name = "system.brightness"
    description = "Ajustar o brilho do monitor interno (up/down mudam 15 pontos; set define 5-100)."
    inputs = schema({"action": string(4, enum=["up", "down", "set"]),
                     "level": {"type": "integer", "minimum": 5, "maximum": 100}}, ("action",))
    risk = Risk.LOW

    def execute(self, ctx, action: str, level: int | None = None) -> SkillResult:
        try:
            current = get_brightness()
        except RuntimeError as exc:
            return SkillResult(False, error=str(exc), error_kind="UNSUPPORTED")
        if action == "set" and level is None:
            return SkillResult(False, error="informe o nível de brilho", error_kind="INVALID_ARGUMENT")
        target = {"up": current + 15, "down": current - 15, "set": level}[action]
        target = max(5, min(100, int(target)))
        result = system.powershell(_PS_BRIGHT_SET, ULTRON_LEVEL=str(target))
        if not result.ok:
            return SkillResult(False, error="falha ao ajustar o brilho", error_kind="APPLICATION_ERROR")
        return SkillResult(True, f"Brilho ajustado para {target}%.", [f"antes {current}%"], {"target": target})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        target = result.data["target"]
        ok = wait_until(lambda: abs(get_brightness() - target) <= 3, timeout=3.0, interval=0.6, ctx=ctx)
        return VerificationResult.from_checks([check("brightness", bool(ok), f"brilho em {target}%" if ok
                                                     else "brilho não confirmado")])


class SystemStatus(Skill):
    name = "system.status"
    description = "Consultar bateria, Wi-Fi, Bluetooth e brilho (somente leitura)."
    category = "system"
    inputs = schema({})
    risk = Risk.NONE

    def execute(self, ctx, **_) -> SkillResult:
        parts, data = [], {}
        power = win32.power_status()
        if power is None:
            try:
                import psutil
                batt = psutil.sensors_battery()
                power = {"has_battery": batt is not None, "percent": batt.percent if batt else None,
                         "plugged": bool(batt.power_plugged) if batt else None}
            except Exception:
                power = None
        if power:
            data["power"] = power
            parts.append("sem bateria (desktop)" if not power["has_battery"] else
                         f"bateria em {power['percent']}%" + (", carregando" if power.get("plugged") else ""))
        if IS_WINDOWS:
            try:
                states = radio_states()
                data["radios"] = states
                for kind, label in (("WiFi", "Wi-Fi"), ("Bluetooth", "Bluetooth")):
                    if kind in states:
                        parts.append(f"{label} {'ligado' if 'On' in states[kind] else 'desligado'}")
            except RuntimeError:
                pass
            try:
                data["brightness"] = get_brightness()
                parts.append(f"brilho em {data['brightness']}%")
            except RuntimeError:
                pass
        if not parts:
            return SkillResult(False, error="não consegui ler o estado do sistema", error_kind="UNSUPPORTED")
        return SkillResult(True, "Estado do sistema: " + "; ".join(parts) + ".", [], data)

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.95, [check("read", True, "leitura direta do sistema")])


SKILLS = (Power, Lock, Wait, Radio, Brightness, SystemStatus)
