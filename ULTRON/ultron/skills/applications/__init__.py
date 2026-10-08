"""Skills de aplicações: abrir, fechar, verificar e encerrar (recuperação de travamento)."""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
import webbrowser

from ...platform import system, win32
from .._util import norm, processes_named, wait_until
from ..base import Risk, Skill, SkillContext, SkillResult, VerificationResult, check, schema, string
from . import app_index

IS_WINDOWS = sys.platform == "win32"

# Catálogo preservado do JARVIS (nome falado -> comando e processos esperados).
KNOWN_APPS: dict[str, dict] = {
    "calculadora": {"label": "Calculadora", "command": "calc", "process": ["CalculatorApp.exe", "calc.exe",
                                                                          "gnome-calculator", "kcalc"]},
    "bloco de notas": {"label": "Bloco de Notas", "command": "notepad", "process": ["notepad.exe", "Notepad.exe"]},
    "chrome": {"label": "Chrome", "browser": "chrome", "process": ["chrome.exe", "chrome", "google-chrome"]},
    "edge": {"label": "Edge", "browser": "edge", "process": ["msedge.exe"]},
    "firefox": {"label": "Firefox", "command": "firefox", "process": ["firefox.exe", "firefox"]},
    "explorador de arquivos": {"label": "Explorador de Arquivos", "command": "explorer", "process": ["explorer.exe"]},
    "paint": {"label": "Paint", "command": "mspaint", "process": ["mspaint.exe"]},
    "terminal": {"label": "Terminal", "command": "wt", "process": ["WindowsTerminal.exe", "gnome-terminal-server"]},
    "visual studio code": {"label": "VS Code", "command": "code", "process": ["Code.exe", "code"], "accepts_path": True},
    "gerenciador de tarefas": {"label": "Gerenciador de Tarefas", "command": "taskmgr", "process": ["Taskmgr.exe"]},
    "configuracoes": {"label": "Configurações", "uri": "ms-settings:", "process": ["SystemSettings.exe"]},
    "spotify": {"label": "Spotify", "command": "spotify", "process": ["Spotify.exe", "spotify"]},
    "word": {"label": "Word", "command": "winword", "process": ["WINWORD.EXE"]},
    "excel": {"label": "Excel", "command": "excel", "process": ["EXCEL.EXE"]},
    "discord": {"label": "Discord", "command": "discord", "process": ["Discord.exe", "discord"]},
    "obs studio": {"label": "OBS Studio", "command": "obs64", "process": ["obs64.exe", "obs"]},
}
ALIASES = {
    "google chrome": "chrome", "google": "chrome", "navegador": "chrome", "microsoft edge": "edge",
    "explorador": "explorador de arquivos", "explorer": "explorador de arquivos", "terminal do windows": "terminal",
    "windows terminal": "terminal", "vs code": "visual studio code", "vscode": "visual studio code",
    "code": "visual studio code", "configuracoes do windows": "configuracoes", "ajustes": "configuracoes",
    "notepad": "bloco de notas", "calc": "calculadora", "task manager": "gerenciador de tarefas", "obs": "obs studio",
}


def resolve_key(name: str) -> str:
    key = norm(name)
    key = re.sub(r"^(o|a|os|as|um|uma|aplicativo|app|programa)\s+", "", key)
    return ALIASES.get(key, key)


def _vscode_executable() -> str | None:
    """Prefere o Code.exe real (o ``code.cmd`` do PATH passa argumentos pelo cmd.exe)."""
    if IS_WINDOWS:
        candidates = (
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Microsoft VS Code", "Code.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Microsoft VS Code", "Code.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Microsoft VS Code", "Code.exe"),
        )
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
    return shutil.which("code")


def _browser_candidates(kind: str) -> list[str]:
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    pf86 = os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")
    paths = []
    if kind == "edge":
        paths += [os.path.join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
                  os.path.join(pf86, "Microsoft", "Edge", "Application", "msedge.exe")]
    if kind == "chrome":
        paths += [os.path.join(pf, "Google", "Chrome", "Application", "chrome.exe"),
                  os.path.join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
                  os.path.join(local, "Google", "Chrome", "Application", "chrome.exe")]
        for exe in ("google-chrome", "chromium", "chromium-browser"):
            found = shutil.which(exe)
            if found:
                paths.append(found)
    return [p for p in paths if p and os.path.isfile(p)]


def launch_known(key: str, path: str | None = None) -> dict:
    """Abre um app do catálogo. Devolve detalhes do lançamento (para a verificação)."""
    app = KNOWN_APPS[key]
    if app.get("uri"):
        system.open_with_default(app["uri"])
        return {"method": "uri"}
    if app.get("browser"):
        for candidate in _browser_candidates(app["browser"]):
            pid = system.spawn_detached([candidate])
            return {"method": "exe", "pid": pid, "exe": candidate}
        if app["browser"] == "edge" and IS_WINDOWS:
            os.startfile("microsoft-edge:https://www.bing.com")  # type: ignore[attr-defined]
            return {"method": "uri"}
        if webbrowser.open("about:blank", new=2):
            return {"method": "webbrowser"}
        raise FileNotFoundError(f"nenhuma instalação de {app['label']} encontrada")
    if key == "visual studio code":
        exe = _vscode_executable()
        if not exe:
            raise FileNotFoundError("VS Code não encontrado (instale ou adicione 'code' ao PATH)")
        args = [exe]
        if path:
            if exe.lower().endswith((".cmd", ".bat")):
                raise PermissionError("abrir pasta via script .cmd não é permitido; instale o VS Code no caminho padrão")
            args.append(path)
        return {"method": "exe", "pid": system.spawn_detached(args), "exe": exe}
    command = app["command"]
    exe = shutil.which(command)
    if not exe:
        raise FileNotFoundError(f"{app['label']} não encontrado neste computador")
    return {"method": "exe", "pid": system.spawn_detached([exe]), "exe": exe}


def _windows_of(processes: set[str]) -> list[dict]:
    wanted = {p.lower() for p in processes}
    return [w for w in win32.enumerate_windows() if (w.get("process") or "").lower() in wanted]


class OpenApplication(Skill):
    name = "app.open"
    description = "Abrir um aplicativo instalado pelo nome (opcionalmente com uma pasta, ex.: VS Code em um projeto)."
    category = "applications"
    inputs = schema({"name": string(80), "path": string(1000)}, ("name",))
    outputs = {"process": "processos esperados", "launch": "método de abertura"}
    risk = Risk.LOW
    timeout = 25.0

    def execute(self, ctx: SkillContext, name: str, path: str | None = None) -> SkillResult:
        key = resolve_key(name)
        started = time.time()
        before = {p["pid"] for p in processes_named(set(KNOWN_APPS.get(key, {}).get("process", [])))}
        before_windows = {w["hwnd"] for w in win32.enumerate_windows()} if win32.AVAILABLE else set()
        if path:
            from .._util import absolute_path
            path = absolute_path(path)
            if not os.path.exists(path):
                return SkillResult(False, error=f"caminho não encontrado: {path}", error_kind="FILE_NOT_FOUND")
            if not KNOWN_APPS.get(key, {}).get("accepts_path"):
                return SkillResult(False, error=f"{name} não aceita abrir caminhos", error_kind="INVALID_ARGUMENT")
        try:
            if key in KNOWN_APPS:
                launch = launch_known(key, path)
                label, expected = KNOWN_APPS[key]["label"], KNOWN_APPS[key].get("process", [])
            else:
                entry, score = app_index.find(name)
                if entry is not None and score >= app_index.CONFIDENT:
                    app_index.launch(entry)
                    launch, label, expected = {"method": entry["kind"]}, entry["name"], []
                elif entry is not None:
                    return SkillResult(False, error=f"não tenho certeza: você quis dizer {entry['name']}?",
                                       error_kind="AMBIGUOUS", data={"suggestion": entry["name"], "score": score})
                else:
                    exe = shutil.which(key.replace(" ", "")) or shutil.which(key)
                    if not exe:
                        return SkillResult(False, error=f"aplicativo {name} não encontrado", error_kind="NOT_FOUND")
                    launch = {"method": "exe", "pid": system.spawn_detached([exe]), "exe": exe}
                    label, expected = name, [os.path.basename(exe)]
        except PermissionError as exc:
            return SkillResult(False, error=str(exc), error_kind="PERMISSION_ERROR")
        except FileNotFoundError as exc:
            return SkillResult(False, error=str(exc), error_kind="NOT_FOUND")
        except OSError as exc:
            return SkillResult(False, error=f"falha ao iniciar {name}: {exc}", error_kind="APPLICATION_ERROR")
        return SkillResult(True, f"{label}: inicialização solicitada.", [f"lançamento via {launch['method']}"],
                           {"label": label, "expected_processes": expected, "launch": launch, "key": key,
                            "pre_pids": sorted(before), "pre_windows": sorted(before_windows), "started": started})

    def verify(self, ctx: SkillContext, args: dict, result: SkillResult) -> VerificationResult:
        if not result.success:
            return super().verify(ctx, args, result)
        expected = set(result.data.get("expected_processes") or [])
        label = result.data.get("label", args.get("name"))
        checks = []
        procs = []
        if expected:
            procs = wait_until(lambda: processes_named(expected), timeout=10.0, ctx=ctx) or []
            checks.append(check("process_started", bool(procs),
                                f"processo {procs[0]['name']} ativo (pid {procs[0]['pid']})" if procs
                                else f"nenhum processo {', '.join(sorted(expected))} encontrado"))
        if win32.AVAILABLE:
            pre = set(result.data.get("pre_windows") or [])

            def window_found():
                windows = _windows_of(expected) if expected else []
                if not expected:
                    fg = win32.foreground_window()
                    if norm(label) in norm(fg.get("title", "")) or norm(label) in norm(fg.get("process", "")):
                        return [fg]
                    return []
                new = [w for w in windows if w["hwnd"] not in pre]
                return new or windows

            windows = wait_until(window_found, timeout=10.0, ctx=ctx) or []
            checks.append(check("window_detected", bool(windows),
                                f"janela detectada: {windows[0]['title'][:80]}" if windows else "nenhuma janela detectada"))
            if windows:
                hung = win32.is_hung(windows[0]["hwnd"])
                checks.append(check("application_responsive", not hung,
                                    "aplicação respondendo" if not hung else "a janela não está respondendo"))
        else:
            checks.append(check("window_detected", None, "verificação de janela indisponível neste sistema"))
        return VerificationResult.from_checks(checks, unconfirmed_reason="processo confirmado; janela não verificável")


class CloseApplication(Skill):
    name = "app.close"
    description = "Fechar um aplicativo de forma graciosa (pode haver dados não salvos)."
    category = "applications"
    inputs = schema({"name": string(80)}, ("name",))
    risk = Risk.HIGH
    reversible = False

    def execute(self, ctx: SkillContext, name: str) -> SkillResult:
        key = resolve_key(name)
        procs = set(KNOWN_APPS.get(key, {}).get("process", []))
        if not procs:
            return SkillResult(False, error=f"não há processo conhecido para {name}", error_kind="NOT_FOUND")
        running = processes_named(procs)
        if not running:
            return SkillResult(False, error=f"{name} não está aberto", error_kind="NOT_RUNNING")
        if IS_WINDOWS:
            for proc in sorted({p["name"] for p in running}):
                system.run(["taskkill", "/IM", proc], timeout=10)
        else:
            import psutil
            for p in running:
                try:
                    psutil.Process(p["pid"]).terminate()
                except psutil.Error:
                    continue
        return SkillResult(True, f"Fechamento de {name} solicitado.", [f"{len(running)} processo(s) sinalizados"],
                           {"processes": sorted(procs)})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        procs = set(result.data["processes"])
        gone = wait_until(lambda: not processes_named(procs), timeout=8.0, ctx=ctx)
        return VerificationResult.from_checks([check("process_closed", bool(gone),
                                                     "processo encerrado" if gone else "o processo continua ativo "
                                                     "(talvez aguardando salvar)")])


class CheckApplication(Skill):
    name = "app.check"
    description = "Verificar se um aplicativo está em execução e respondendo."
    category = "applications"
    inputs = schema({"name": string(80)}, ("name",))
    risk = Risk.NONE

    def execute(self, ctx, name: str) -> SkillResult:
        key = resolve_key(name)
        procs = set(KNOWN_APPS.get(key, {}).get("process", [])) or {name}
        running = processes_named(procs)
        hung = []
        if win32.AVAILABLE and running:
            hung = [w for w in _windows_of(procs) if w.get("hung")]
        state = "travado" if hung else ("em execução" if running else "não está em execução")
        return SkillResult(True, f"{name}: {state}.", [f"{len(running)} processo(s)"],
                           {"running": bool(running), "hung": bool(hung), "pids": [p["pid"] for p in running],
                            "processes": sorted(procs)})

    def verify(self, ctx, args, result):
        return VerificationResult("VERIFIED", 0.95, [check("observed", True, result.result)], result.evidence,
                                  "leitura direta do sistema")


class TerminateApplication(Skill):
    name = "app.terminate"
    description = "Encerrar à força um aplicativo travado (recuperação). Dados não salvos são perdidos."
    category = "applications"
    inputs = schema({"name": string(80)}, ("name",))
    risk = Risk.CRITICAL
    reversible = False
    expose_to_llm = False

    def precheck(self, ctx, args):
        key = resolve_key(args.get("name", ""))
        procs = set(KNOWN_APPS.get(key, {}).get("process", [])) or {args.get("name", "")}
        if not processes_named(procs):
            return f"{args.get('name')} não está em execução; nada a encerrar"
        if win32.AVAILABLE and not any(w.get("hung") for w in _windows_of(procs)):
            return f"{args.get('name')} está respondendo; encerramento à força desnecessário"
        return None

    def execute(self, ctx, name: str) -> SkillResult:
        key = resolve_key(name)
        procs = set(KNOWN_APPS.get(key, {}).get("process", [])) or {name}
        running = processes_named(procs)
        if not running:
            return SkillResult(True, f"{name} já não está em execução.", ["nenhum processo encontrado"],
                               {"processes": sorted(procs)})
        if IS_WINDOWS:
            for proc in sorted({p["name"] for p in running}):
                system.run(["taskkill", "/F", "/IM", proc], timeout=10)
        else:
            import psutil
            for p in running:
                try:
                    psutil.Process(p["pid"]).kill()
                except psutil.Error:
                    continue
        return SkillResult(True, f"{name} encerrado à força.", [f"{len(running)} processo(s) encerrados"],
                           {"processes": sorted(procs)})

    def verify(self, ctx, args, result):
        procs = set(result.data.get("processes") or [])
        gone = wait_until(lambda: not processes_named(procs), timeout=6.0, ctx=ctx)
        return VerificationResult.from_checks([check("process_gone", bool(gone),
                                                     "nenhum processo restante" if gone else "processo ainda ativo")])


class ListApplications(Skill):
    name = "app.list"
    description = "Listar aplicativos com janelas abertas."
    category = "applications"
    inputs = schema({})
    risk = Risk.NONE

    def execute(self, ctx, **_):
        if not win32.AVAILABLE:
            return SkillResult(False, error="listagem de janelas disponível apenas no Windows", error_kind="UNSUPPORTED")
        windows = win32.enumerate_windows()
        apps = sorted({w.get("process", "") for w in windows if w.get("process")})
        return SkillResult(True, "Aplicativos abertos: " + ", ".join(apps[:30]) + ".", [f"{len(windows)} janelas"],
                           {"applications": apps})

    def verify(self, ctx, args, result):
        if not result.success:
            return super().verify(ctx, args, result)
        return VerificationResult("VERIFIED", 0.95, [check("observed", True, "leitura direta das janelas")])


SKILLS = (OpenApplication, CloseApplication, CheckApplication, TerminateApplication, ListApplications)
