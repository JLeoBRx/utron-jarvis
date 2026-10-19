"""Ponto de entrada do JARVIS.

    python main.py                 HUB principal (JARVIS CORE) com o TARDIS sob demanda
    python main.py --boot          início automático: começa recolhido no orbe
    python main.py --headless      console de texto, sem interface gráfica
    python main.py --diagnose      verifica saúde, modelos, voz (8 etapas), rede e plugins, e sai
    python main.py --voice-test    teste de voz interativo: diga "Jarvis, que horas são?"
    python main.py --list-mics     lista os microfones
    python main.py --mic 2         escolhe o microfone (número da lista ou parte do nome) e sai
    python main.py --say "texto"   executa um pedido sem interface e sai

Registra em ``<dados>/logs/ultron.log`` (também quando iniciado por ``pythonw``, sem console).
O nome interno do pacote (``ultron``) e a pasta de dados foram mantidos para preservar os
dados e as configurações do usuário.
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import logging.handlers
import sys
import threading
import time

from . import __version__
from .config import paths


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jarvis", description="JARVIS — inteligência local do computador")
    parser.add_argument("--headless", action="store_true", help="console de texto, sem interface gráfica")
    parser.add_argument("--boot", action="store_true", help="início automático com o Windows (orbe recolhido)")
    parser.add_argument("--diagnose", action="store_true", help="relatório de saúde e sai")
    parser.add_argument("--voice-test", action="store_true", help="teste de voz interativo (8 etapas)")
    parser.add_argument("--list-mics", action="store_true", help="lista os microfones e sai")
    parser.add_argument("--mic", metavar="DISPOSITIVO", help="escolhe o microfone (número ou parte do nome) e sai")
    parser.add_argument("--say", metavar="TEXTO", help="executa um pedido e sai")
    parser.add_argument("--profile", help="perfil de configuração (default, performance, privacy, silent, developer)")
    parser.add_argument("--no-voice", action="store_true", help="sem microfone e sem fala")
    parser.add_argument("--no-perception", action="store_true", help="sem sensores de percepção")
    parser.add_argument("--no-plugins", action="store_true", help="não carrega plugins")
    parser.add_argument("--debug", action="store_true", help="registro detalhado")
    parser.add_argument("--version", action="version", version=f"JARVIS {__version__}")
    return parser.parse_args(argv)


def setup_logging(debug: bool = False) -> None:
    root = logging.getLogger()
    if any(getattr(h, "_ultron", False) for h in root.handlers):
        return
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    file_handler = logging.handlers.RotatingFileHandler(paths.logs_dir() / "ultron.log", maxBytes=5_000_000,
                                                        backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler._ultron = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    if sys.stderr is not None:                         # pythonw não tem console
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG if debug else logging.WARNING)
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        console._ultron = True  # type: ignore[attr-defined]
        root.addHandler(console)


def _make_core(args: argparse.Namespace, *, voice: bool | None = None, perception: bool | None = None):
    from .config import settings as settings_module
    from .core.neural_core import NeuralCore

    manager = settings_module.manager()
    if args.profile:
        manager.load(args.profile)
    return NeuralCore(manager, voice=not args.no_voice if voice is None else voice,
                      perception=not args.no_perception if perception is None else perception,
                      plugins=not args.no_plugins)


def _wait_voice_ready(core, timeout: float = 30.0) -> None:
    """Espera o modelo de fala carregar e a primeira tentativa de abrir o microfone (com prazo)."""
    if not core.enable_voice:
        return
    deadline = time.monotonic() + timeout
    voice = core.voice
    while time.monotonic() < deadline:
        stt_done = voice.stt is not None or bool(voice.stt_reason)
        mic_done = voice.capturing or bool(voice.reason) or not voice.mic_enabled
        if stt_done and mic_done:
            return
        time.sleep(0.2)


def run_diagnose(args: argparse.Namespace) -> int:
    from .health.monitor import format_report
    from .voice.diagnostics import VoiceDiagnostics
    from .voice.diagnostics import format_report as voice_report

    core = _make_core(args)
    statuses = core.boot()
    _wait_voice_ready(core)
    report = core.diagnose()
    print(f"JARVIS {__version__} — diagnóstico")
    print("Componentes: " + ", ".join(f"{k}={v}" for k, v in statuses.items()))
    print(format_report(report["health"]))
    models = report["models"]
    print(f"Ollama: {'ativo' if models['ollama_alive'] else 'indisponível'} {models.get('version', '')}"
          f" · instalados: {', '.join(models['installed']) or 'nenhum'}"
          + (f" · ausentes: {', '.join(models['missing'])}" if models["missing"] else ""))
    for task, sel in models["selections"].items():
        print(f"  {task}: {sel['model'] or '—'} ({sel['reason']})" + (f" → {sel['install_hint']}"
                                                                     if sel.get("install_hint") else ""))
    privacy = report["privacy"]
    print(f"Privacidade: {privacy.get('mode')} · Ollama local: {privacy.get('ollama_local')}")
    print("Plugins: " + (", ".join(f"{p['name']} ({p['status']}{': ' + p['reason'] if p['reason'] else ''})"
                                   for p in report["plugins"]) or "nenhum"))
    print(f"Skills: {report['skills']['available']}/{report['skills']['total']} disponíveis")
    if core.enable_voice:
        print(voice_report(VoiceDiagnostics(core).run(interactive=False, probe_response=True)))
    else:
        print("Voz: desativada nesta execução (--no-voice).")
    core.shutdown()
    return 1 if report["health"]["overall"] == "FAIL" else 0


def run_voice_test(args: argparse.Namespace) -> int:
    """Teste de voz completo pelo console: as 8 etapas com fala real do usuário."""
    from .voice.diagnostics import VoiceDiagnostics, format_report

    core = _make_core(args, voice=True, perception=False)
    print("Iniciando o JARVIS para o teste de voz…", flush=True)
    core.boot()
    _wait_voice_ready(core)
    diag = VoiceDiagnostics(core, on_step=lambda st: print(f"  · {st.title}: {st.status} — {st.detail}", flush=True))
    report = diag.run(interactive=True, listen_seconds=12.0, prompt=lambda text: print(f"\n>>> {text}\n", flush=True))
    print()
    print(format_report(report))
    core.shutdown()
    return 0 if report["overall"] != "FAIL" else 1


def run_microphones(args: argparse.Namespace) -> int:
    from .config import settings as settings_module
    from .voice.audio import list_input_devices

    listing = list_input_devices()
    devices = listing.get("devices", [])
    if not devices:
        print("Nenhum microfone disponível: " + ("; ".join(listing.get("errors", [])) or "nenhum dispositivo"))
        return 1
    manager = settings_module.manager()
    if args.mic:
        wanted = args.mic.strip()
        chosen = next((d for d in devices if wanted.isdigit() and d["index"] == int(wanted)), None)
        matches = [d for d in devices if wanted.casefold() in d["name"].casefold()]
        chosen = chosen or (matches[0] if len(matches) == 1 else None)
        if chosen is None:
            print(f"Microfone \"{wanted}\" não encontrado ou ambíguo.")
        else:
            manager.update(mic_name=chosen["name"], mic_index=int(chosen["index"]))
            print(f"Microfone escolhido: {chosen['index']}: {chosen['name']} (salvo nas configurações).")
            return 0
    current = manager.settings.mic_name or (manager.settings.mic_index if manager.settings.mic_index >= 0 else None)
    print(f"Microfones ({listing['backend']}); configurado: {current if current is not None else 'padrão do sistema'}")
    for d in devices:
        print(f"  {d['index']:>3}: {d['name']} [{d['host_api']}, {d['rate']} Hz]" + ("  ← padrão" if d["default"] else ""))
    print("Escolha com: python main.py --mic NÚMERO")
    return 0 if not args.mic else 1


def run_headless(args: argparse.Namespace) -> int:
    from .core.events import EventType

    core = _make_core(args)
    done = threading.Event()

    def show(event) -> None:
        payload = event.payload
        prefix = "…" if payload.get("partial") else "JARVIS:"
        print(f"{prefix} {payload.get('text', '')}", flush=True)
        if not payload.get("partial"):
            done.set()

    core.bus.subscribe(EventType.RESPONSE_READY, show, name="console")
    core.bus.subscribe(EventType.AUTHORIZATION_REQUIRED,
                       lambda e: print(f"[autorização] {e.payload.get('description')} — responda sim/não", flush=True),
                       name="console.auth")
    core.boot()
    if args.say:
        done.clear()
        core.submit(args.say, source="text")
        done.wait(float(getattr(core.settings(), "llm_timeout", 120.0)) + 30)
        time.sleep(0.3)
        core.shutdown()
        return 0
    print("JARVIS em modo console. Digite um comando (\"sair\" para encerrar; \"diagnóstico de voz\" testa a voz).",
          flush=True)
    try:
        while True:
            line = input("› ").strip()
            if line.lower() in ("sair", "exit", "quit"):
                break
            if line:
                core.submit(line, source="text")
    except (EOFError, KeyboardInterrupt):
        pass
    core.shutdown()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.debug)
    log = logging.getLogger("ultron")
    log.info("JARVIS %s iniciando (%s)", __version__, " ".join(sys.argv[1:]) or "HUB")
    if args.list_mics or args.mic:
        return run_microphones(args)
    from .platform import single_instance
    if args.diagnose or args.voice_test:
        if not single_instance.acquire():
            print("O JARVIS já está em execução: feche-o (bandeja > Sair) para diagnosticar sem disputar o "
                  "microfone, ou use HUB > Voz > Diagnóstico.")
            return 2
        try:
            return run_voice_test(args) if args.voice_test else run_diagnose(args)
        finally:
            single_instance.release()
    if not single_instance.acquire():
        print("O JARVIS já está em execução.")
        return 0
    try:
        if args.headless or args.say:
            return run_headless(args)
        try:
            if importlib.util.find_spec("PySide6") is None:
                raise ImportError("PySide6 não instalado")
            from .hud import run_hud
        except ImportError as exc:
            log.warning("interface indisponível (%s); modo console", exc)
            print(f"Interface gráfica indisponível ({exc}). Iniciando em modo console.")
            return run_headless(args)
        core = _make_core(args)
        minimized = args.boot or bool(getattr(core.settings(), "hud_start_minimized", False))
        return run_hud(core, minimized=minimized)
    finally:
        single_instance.release()
