"""Diagnóstico pela linha de comando (``--diagnose``, ``DIAGNOSTICO_JARVIS.bat`` e o fim do ``INSTALL_JARVIS.bat``).

Cada etapa aparece assim que termina; as que podem demorar avisam antes de começar. Cada uma tem um prazo:
a que não responde é marcada ``[TEMPO]`` com o nome dela, e as etapas que não dependem dela continuam. Um
serviço opcional ausente (Ollama, voz, robô) é aviso, não impede o resto. Nada aqui altera dados: o banco só
é aberto e conferido, as configurações só são lidas, e a interface é montada sem ser mostrada.
"""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Any, Callable

log = logging.getLogger("ultron.diagnose")

MARK = {"OK": "[OK]   ", "AVISO": "[AVISO]", "FALHA": "[FALHA]", "TEMPO": "[TEMPO]", "—": "[ —  ] ", "...": "[....] "}
HEALTH = {"OK": "OK", "WARN": "AVISO", "DEGRADED": "AVISO", "UNAVAILABLE": "AVISO", "UNKNOWN": "AVISO",
          "FAIL": "FALHA", "DISABLED": "—", "SKIPPED": "—"}


class Timeout(Exception):
    pass


def within(seconds: float, fn: Callable[[], Any]) -> Any:
    """Roda ``fn`` com prazo. Estourou: ``Timeout`` (a thread fica para trás, sem segurar a saída)."""
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:                 # o erro volta para quem pediu
            box["error"] = exc

    thread = threading.Thread(target=run, name="ultron-diagnose-step", daemon=True)
    thread.start()
    thread.join(seconds)
    if thread.is_alive():
        raise Timeout(f"sem resposta em {seconds:.0f} s")
    if "error" in box:
        raise box["error"]
    return box.get("value")


class Report:
    def __init__(self, out: Callable[[str], None]):
        self.out = out
        self.results: list[tuple[str, str]] = []
        self.timed_out = False

    def waiting(self, name: str, text: str) -> None:
        self.out(f"{MARK['...']} {name}: {text}")

    def line(self, status: str, name: str, detail: str = "", extra: list[str] | None = None) -> str:
        self.results.append((name, status))
        self.out(f"{MARK.get(status, '[?]')} {name}" + (f": {detail}" if detail else ""))
        for row in extra or ():
            self.out(f"         {row}")
        if status in ("FALHA", "TEMPO"):
            log.info("diagnóstico: %s %s — %s", status, name, detail)
        return status

    def step(self, name: str, seconds: float, fn: Callable[[], tuple], *, wait_text: str = "") -> str:
        """``fn`` devolve (status, detalhe[, linhas extras]). Exceção vira FALHA; prazo estourado, TEMPO."""
        if wait_text:
            self.waiting(name, f"{wait_text} (até {seconds:.0f} s)…")
        try:
            result = within(seconds, fn)
        except Timeout as exc:
            self.timed_out = True
            return self.line("TEMPO", name, str(exc))
        except Exception as exc:
            log.exception("diagnóstico: etapa %s falhou", name)
            return self.line("FALHA", name, f"{type(exc).__name__}: {exc}")
        status, detail, *rest = result
        return self.line(status, name, detail, rest[0] if rest else None)

    def skipped(self, name: str, why: str) -> None:
        self.line("—", name, f"não verificado: {why}")

    def summary(self) -> int:
        count = {k: sum(1 for _n, s in self.results if s == k) for k in ("OK", "AVISO", "FALHA", "TEMPO")}
        self.out("")
        self.out(f"Resumo: {count['OK']} OK · {count['AVISO']} aviso(s) · {count['FALHA']} falha(s) · "
                 f"{count['TEMPO']} sem resposta")
        bad = [n for n, s in self.results if s in ("FALHA", "TEMPO")]
        if bad:
            self.out("Com problema: " + ", ".join(bad))
        return 1 if bad else 0


# ====================================================================== etapas
def check_settings(args: argparse.Namespace) -> tuple:
    from .config import settings as settings_module
    manager = settings_module.manager()
    manager.load(args.profile) if args.profile else manager.load()
    notes = list(getattr(manager, "migration_notes", []) or [])
    unreadable = [n for n in notes if "ilegível" in n]
    detail = f"{manager.path}" + (f" · perfil {args.profile}" if args.profile else "")
    return ("AVISO" if unreadable else "OK", detail, notes)


def check_database() -> tuple:
    import sqlite3

    from .config import paths
    from .memory.store import Database
    path = paths.database_path()
    existed = path.is_file()
    try:
        db = Database(path)
    except sqlite3.DatabaseError as exc:
        return ("FALHA", f"{path} não abriu ({exc}); o arquivo NÃO foi alterado",
                ["Com o SAFRA fechado: START_JARVIS.bat --list-backups e START_JARVIS.bat --restore-backup ARQUIVO"])
    try:
        verdict = str(db.one("PRAGMA quick_check")[0])
    finally:
        db.close()
    size = path.stat().st_size / 2 ** 20 if path.is_file() else 0.0
    if verdict.lower() != "ok":
        return ("FALHA", f"{path}: verificação de integridade: {verdict}",
                ["O arquivo não foi alterado. Restaure um backup: START_JARVIS.bat --list-backups"])
    return ("OK", f"{path} ({size:.1f} MB, íntegro)" + ("" if existed else " — criado agora (primeira execução)"))


def check_core(core, progress: dict) -> tuple:
    started = time.perf_counter()
    statuses = core.boot(on_progress=lambda name, status: progress.__setitem__(name, status))
    seconds = time.perf_counter() - started
    failed = [n for n, s in statuses.items() if s == "FAILED"]
    if failed:
        errors = [f"{n}: {core.lifecycle.health_of(n).detail}" for n in failed]
        return ("AVISO", f"{len(statuses) - len(failed)} de {len(statuses)} componentes iniciados em {seconds:.1f} s",
                errors)
    return ("OK", f"{len(statuses)} componentes iniciados em {seconds:.1f} s")


def health_line(health: dict, key: str, label: str = "") -> tuple:
    check = (health.get("checks") or {}).get(key)
    if check is None:
        return ("—", "sem verificação registrada")
    return (HEALTH.get(check["status"], "AVISO"), (label + check.get("detail", "")).strip())


def check_models(core) -> tuple:
    status = core.router.status().to_dict()
    if not status["ollama_alive"]:
        return ("AVISO", "não verificados: o Ollama não respondeu (comandos diretos, lembretes e memória "
                         "funcionam sem ele)")
    rows = []
    for task, sel in status["selections"].items():
        rows.append(f"{task}: {sel['model'] or '—'} ({sel['reason']})"
                    + (f" -> {sel['install_hint']}" if sel.get("install_hint") else ""))
    if status["missing"]:
        return ("AVISO", "instalados: " + (", ".join(status["installed"]) or "nenhum")
                + " · ausentes: " + ", ".join(status["missing"]), rows)
    return ("OK", "instalados: " + ", ".join(status["installed"]), rows)


def check_voice(core, wait_voice: Callable, voice_report: Callable) -> tuple:
    from .voice.diagnostics import VoiceDiagnostics
    wait_voice(core)
    report = VoiceDiagnostics(core).run(interactive=False, probe_response=True)
    status = {"OK": "OK", "WARN": "AVISO", "FAIL": "FALHA"}.get(report["overall"], "AVISO")
    failed = [s["title"] for s in report["steps"] if s["status"] == "FAIL"]
    warned = [s["title"] for s in report["steps"] if s["status"] == "WARN"]
    detail = ("falhou: " + ", ".join(failed) if failed else "atenção: " + ", ".join(warned) if warned
              else "as 8 etapas sem fala aprovadas (o teste com fala é START_JARVIS.bat --voice-test)")
    return (status, detail, voice_report(report).splitlines()[1:])


def check_gui(args: argparse.Namespace, seconds: float) -> tuple:
    """A interface montada de verdade, num processo separado (sem mostrar janela e sem iniciar serviços): pega
    erro de construção, de biblioteca do Qt e de plataforma gráfica — inclusive os que derrubam o processo."""
    import importlib.util
    if importlib.util.find_spec("PySide6") is None:
        return ("AVISO", "PySide6 não instalado: o SAFRA abre em modo console")
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    command = [sys.executable, main, "--gui-check"]
    for flag in ("no_voice", "no_perception", "no_plugins"):
        if getattr(args, flag, False):
            command.append("--" + flag.replace("_", "-"))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=seconds, env=env, stdin=subprocess.DEVNULL)
    lines = [ln for ln in (done.stdout + "\n" + done.stderr).splitlines() if ln.strip()]
    ok = next((ln for ln in lines if ln.startswith("INTERFACE OK:")), None)
    if done.returncode == 0 and ok:
        return ("OK", ok.split(":", 1)[1].strip())
    failed = next((ln for ln in lines if ln.startswith("INTERFACE FALHOU:")), None)
    reason = failed.split(":", 1)[1].strip() if failed else (lines[-1] if lines else f"código {done.returncode}")
    return ("FALHA", f"a janela não pôde ser montada: {reason}",
            lines[-12:] + ["Use o modo console enquanto isso: START_JARVIS.bat --console"])


# ====================================================================== sequência
def run(args: argparse.Namespace, *, make_core: Callable, wait_voice: Callable, version: str,
        out: Callable[[str], None] | None = None, gui_seconds: float = 120.0) -> int:
    out = out or (lambda text: print(text, flush=True))
    import platform

    from .config import paths
    from .voice.diagnostics import format_report as voice_report
    report = Report(out)
    out(f"SAFRA {version} — diagnóstico (Python {platform.python_version()}, {platform.system()} {platform.release()})")
    out(f"Dados: {paths.data_dir()} · registro: {paths.logs_dir() / 'ultron.log'}")
    out("")
    settings_ok = report.step("Configurações", 15, lambda: check_settings(args)) != "FALHA"
    database_ok = report.step("Banco de dados", 60, check_database) != "FALHA"

    core = None
    progress: dict[str, str] = {}
    if settings_ok and database_ok:
        core = make_core(args)
        status = report.step("Núcleo", 120, lambda: check_core(core, progress),
                             wait_text="iniciando os componentes")
        if status == "TEMPO":
            starting = [n for n, s in core.lifecycle.statuses().items() if s == "STARTING"]
            out(f"         o componente que não terminou de iniciar: {', '.join(starting) or 'desconhecido'}")
            core_ready = False
        else:
            core_ready = status != "FALHA"
    else:
        core_ready = False
        report.skipped("Núcleo", "configurações ou banco de dados com falha")

    dependents = ("Ollama", "Modelos de IA", "Memória", "TARDIS", "Comandos", "Voz", "Percepção", "Plugins",
                  "Sistema")
    if core_ready:
        health: dict = {}
        try:                                         # cada verificação de saúde já tem prazo próprio
            health = within(90, core.health.check_all)
        except Exception as exc:
            out(f"{MARK['AVISO']} Saúde: verificação geral não concluiu ({exc}); as etapas abaixo ficam sem ela")
        report.step("Ollama", 30, lambda: _ollama(health, core))
        report.step("Modelos de IA", 30, lambda: check_models(core))
        report.step("Memória", 15, lambda: _join(health, ("MEMORY", "SECOND_BRAIN")))
        report.step("TARDIS", 15, lambda: health_line(health, "TARDIS"))
        report.step("Comandos", 15, lambda: ("OK", f"Skills: {len(core.registry.available())}/{len(core.registry)} "
                                                  "disponíveis"))
        if core.enable_voice:
            report.step("Voz", 75, lambda: check_voice(core, wait_voice, voice_report),
                        wait_text="carregando o reconhecimento de fala e testando microfone e voz")
        else:
            report.line("—", "Voz", "desativada nesta execução (--no-voice).")
        if core.enable_perception:
            report.step("Percepção", 15, lambda: health_line(health, "VISION"))
        else:
            report.line("—", "Percepção", "desativada nesta execução (--no-perception).")
        report.step("Plugins", 15, lambda: _plugins(core))
        report.step("Sistema", 15, lambda: _system(health))
    else:
        for name in dependents:
            report.skipped(name, "o núcleo não iniciou")
    report.step("Interface gráfica", gui_seconds, lambda: check_gui(args, gui_seconds - 5),
                wait_text="montando a janela, as páginas e a bandeja sem mostrá-las")
    code = report.summary()
    out(f"Registro detalhado: {paths.logs_dir() / 'ultron.log'}")
    if core is not None and core.booted:
        try:
            within(30, core.shutdown)
        except Exception as exc:
            out(f"{MARK['AVISO']} Encerramento: {exc}; saindo assim mesmo")
            report.timed_out = True
    if report.timed_out:                             # uma etapa presa não pode segurar o processo
        logging.shutdown()
        sys.stdout.flush()
        os._exit(code)
    return code


def _join(health: dict, keys: tuple) -> tuple:
    parts = [health_line(health, k) for k in keys]
    worst = "FALHA" if any(p[0] == "FALHA" for p in parts) else "AVISO" if any(p[0] == "AVISO" for p in parts) else "OK"
    return (worst, " · ".join(p[1] for p in parts if p[1]))


def _plugins(core) -> tuple:
    plugins = core.plugins.list()
    if not plugins:
        return ("OK", "nenhum plugin instalado")
    bad = [p for p in plugins if p["status"] == "FAILED"]
    text = ", ".join(f"{p['name']} ({p['status']}{': ' + p['reason'] if p['reason'] else ''})" for p in plugins)
    return ("AVISO" if bad else "OK", text)


def _ollama(health: dict, core) -> tuple:
    """Ativo ou não é o que o servidor responde; modelos ausentes aparecem na etapa "Modelos de IA"."""
    status = core.router.status()
    _level, detail = health_line(health, "OLLAMA") if health else ("", "")
    for prefix in ("Ollama indisponível:", "Ollama ativo:"):
        if detail.startswith(prefix):
            detail = detail[len(prefix):].strip()
    if status.ollama_alive:
        version = f" {status.version}" if status.version else ""
        latency = f", respondeu em {status.latency_ms:.0f} ms" if status.latency_ms else ""
        return ("OK", f"ativo{version}{latency}")
    reason = status.error or detail or "não respondeu"
    return ("FALHA", f"indisponível — {reason}. Abra o Ollama (ollama.com); comandos diretos, lembretes e memória "
                     "continuam funcionando sem ele")


def _system(health: dict) -> tuple:
    parts = [health_line(health, k) for k in ("CPU", "RAM", "DISK", "GPU")]
    status = "FALHA" if any(p[0] == "FALHA" for p in parts[:3]) else "OK"
    return (status, " · ".join(p[1] for p in parts if p[1]))
