"""Ponto de entrada do JARVIS.

    python main.py                 HUB principal (JARVIS CORE) com o TARDIS sob demanda
    python main.py --boot          início automático: começa recolhido no orbe
    python main.py --headless      console de texto, sem interface gráfica
    python main.py --diagnose      verifica saúde, modelos, voz (8 etapas), rede e plugins, e sai
    python main.py --voice-test    teste de voz interativo: diga "Jarvis, que horas são?"
    python main.py --list-mics     lista os microfones
    python main.py --mic 2         escolhe o microfone (número da lista ou parte do nome) e sai
    python main.py --say "texto"   executa um pedido sem interface e sai
    python main.py --backup        cria um backup do banco (memórias, lembretes, rede) e sai
    python main.py --list-backups  lista os backups
    python main.py --restore-backup ARQUIVO   restaura um backup (com o JARVIS FECHADO; guarda o atual)
    python main.py --export ARQUIVO.json|.csv exporta a memória pessoal para um arquivo novo
    python main.py --status        diz se o JARVIS está em execução (e o processo)
    python main.py --stop          pede à instância em execução que encerre normalmente

Registra em ``<dados>/logs/ultron.log`` (também quando iniciado por ``pythonw``, sem console).
O nome interno do pacote (``ultron``) e a pasta de dados foram mantidos para preservar os
dados e as configurações do usuário.
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import logging.handlers
import os
import sqlite3
import sys
import threading
import time

from . import __version__
from .config import paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="jarvis", description="JARVIS — inteligência local do computador")
    parser.add_argument("--headless", action="store_true", help="console de texto, sem interface gráfica")
    parser.add_argument("--boot", action="store_true", help="início automático com o Windows (orbe recolhido)")
    parser.add_argument("--diagnose", action="store_true", help="relatório de saúde e sai")
    parser.add_argument("--voice-test", action="store_true", help="teste de voz interativo (8 etapas)")
    parser.add_argument("--list-mics", action="store_true", help="lista os microfones e sai")
    parser.add_argument("--mic", metavar="DISPOSITIVO", help="escolhe o microfone (número ou parte do nome) e sai")
    parser.add_argument("--say", metavar="TEXTO", help="executa um pedido e sai")
    parser.add_argument("--backup", action="store_true", help="cria um backup do banco e sai")
    parser.add_argument("--list-backups", action="store_true", help="lista os backups e sai")
    parser.add_argument("--restore-backup", metavar="ARQUIVO", help="restaura um backup (JARVIS fechado) e sai")
    parser.add_argument("--export", metavar="ARQUIVO", help="exporta a memória pessoal (.json ou .csv) e sai")
    parser.add_argument("--import-models", metavar="PASTA",
                        help="copia modelos de fala/voz de uma instalação anterior (só o que falta) e sai")
    parser.add_argument("--set-openai-key", action="store_true",
                        help="guarda a chave da OpenAI no cofre do sistema (Gerenciador de Credenciais) e sai")
    parser.add_argument("--use-openai", action="store_true",
                        help="usa a OpenAI como cérebro (pede confirmação: os dados saem do computador) e sai")
    parser.add_argument("--use-ollama", action="store_true", help="volta ao cérebro local (Ollama) e sai")
    parser.add_argument("--test-openai", action="store_true", help="testa a conexão com a OpenAI e sai")
    parser.add_argument("--autostart-check", action="store_true",
                        help="confere a entrada de início automático com o Windows e sai")
    parser.add_argument("--status", action="store_true", help="diz se o JARVIS está em execução e sai")
    parser.add_argument("--stop", action="store_true", help="encerra a instância em execução (normalmente) e sai")
    parser.add_argument("--profile", help="perfil de configuração (default, performance, privacy, silent, developer)")
    parser.add_argument("--no-voice", action="store_true", help="sem microfone e sem fala")
    parser.add_argument("--no-perception", action="store_true", help="sem sensores de percepção")
    parser.add_argument("--no-plugins", action="store_true", help="não carrega plugins")
    parser.add_argument("--debug", action="store_true", help="registro detalhado")
    parser.add_argument("--version", action="version", version=f"JARVIS {__version__}")
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def install_exception_hooks() -> None:
    """Exceções não tratadas (inclusive em threads e em métodos do Qt como paintEvent) vão para o log:
    com pythonw não há console, e um traceback perdido esconde a causa de uma falha."""
    log = logging.getLogger("ultron")

    def main_hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("exceção não tratada", exc_info=(exc_type, exc, tb))

    def thread_hook(args) -> None:
        if args.exc_type is SystemExit:
            return
        name = args.thread.name if args.thread is not None else "?"
        log.critical("exceção não tratada na thread %s", name,
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = main_hook
    threading.excepthook = thread_hook


def setup_logging(debug: bool = False) -> None:
    root = logging.getLogger()
    if any(getattr(h, "_ultron", False) for h in root.handlers):
        return
    install_exception_hooks()
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


class StartupError(RuntimeError):
    """O JARVIS não pôde abrir algo essencial; a mensagem diz o que aconteceu e o que fazer."""


def _database_problem(exc: Exception) -> StartupError:
    return StartupError(
        f"O banco de memória do JARVIS não abriu ({exc}). O arquivo NÃO foi alterado: {paths.database_path()}\n"
        "Para recuperar, com o JARVIS fechado: START_JARVIS.bat --list-backups e depois "
        "START_JARVIS.bat --restore-backup ARQUIVO. Para começar com um banco novo, mova o arquivo para outra "
        "pasta antes de iniciar.")


def _show_startup_error(text: str) -> None:
    """Sem console (pythonw), a mensagem precisa aparecer numa janela; com console, o texto basta."""
    if sys.stderr is not None:
        return
    try:
        from PySide6 import QtWidgets
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        QtWidgets.QMessageBox.critical(None, "J.A.R.V.I.S. — não foi possível iniciar", text)
        del app
    except Exception:                                  # sem interface: fica o registro no log
        pass


def _make_core(args: argparse.Namespace, *, voice: bool | None = None, perception: bool | None = None):
    from .config import settings as settings_module
    from .core.neural_core import NeuralCore

    manager = settings_module.manager()
    if args.profile:
        manager.load(args.profile)
    try:
        return NeuralCore(manager, voice=not args.no_voice if voice is None else voice,
                          perception=not args.no_perception if perception is None else perception,
                          plugins=not args.no_plugins)
    except sqlite3.DatabaseError as exc:
        raise _database_problem(exc) from exc


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

    def shutdown_requested(_event) -> None:         # "encerre o JARVIS" (já confirmado pelo executor)
        def finish() -> None:
            time.sleep(1.0)                          # a resposta "Encerrando, senhor." chega antes
            core.shutdown()
            from .platform import control
            control.unregister()
            os._exit(0)

        threading.Thread(target=finish, name="ultron-console-exit", daemon=True).start()

    core.bus.subscribe(EventType.SHUTDOWN_REQUESTED, shutdown_requested, name="console.shutdown")
    core.boot()
    if not args.say:
        from .platform import control

        def watch_stop() -> None:                   # --stop: encerra normalmente, mesmo esperando entrada
            while core.booted:
                if control.stop_requested():
                    control.clear_stop_request()
                    print("\nEncerrando a pedido (--stop)…", flush=True)
                    core.shutdown()
                    control.unregister()
                    os._exit(0)
                time.sleep(1.5)

        threading.Thread(target=watch_stop, name="ultron-stop-watch", daemon=True).start()
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


def run_openai_command(args: argparse.Namespace, *, ask=input, secret_prompt=None) -> int:
    """Configuração da OpenAI pela linha de comando (o JARVIS original tinha configurar_openai.bat)."""
    from .config import settings as settings_module
    from .platform import credentials
    manager = settings_module.manager()
    manager.load()
    if args.set_openai_key:
        import getpass
        key = (secret_prompt or getpass.getpass)("Chave da OpenAI (não aparece na tela): ").strip()
        if not key:
            print("Nenhuma chave informada.")
            return 1
        try:
            where = credentials.set_secret("openai_api_key", key)
        except (RuntimeError, ValueError) as exc:
            print(f"Não foi possível guardar: {exc}")
            return 1
        print(f"Chave {credentials.mask(key)} guardada no {where}. Ela nunca é gravada no settings.json.")
    if args.use_openai:
        print("Usar a OpenAI significa que o conteúdo das conversas (e imagens da tela, quando o Observador ou\n"
              "uma análise visual for usada) sai deste computador para a API da OpenAI, com cobrança própria.\n"
              "As ferramentas continuam sendo executadas localmente. Para voltar: --use-ollama.")
        if ask("Digite SIM para confirmar: ").strip().upper() != "SIM":
            print("Nada foi alterado.")
            return 1
        manager.update(ai_provider="openai", privacy_mode="standard", allow_external_models=True)
        print(f"Provedor: OpenAI ({manager.settings.openai_model}). LOCAL MODE desligado.")
    if args.use_ollama:
        manager.update(ai_provider="ollama", privacy_mode="local", allow_external_models=False)
        print("Provedor: Ollama local. LOCAL MODE ligado: nenhuma chamada de IA sai do computador.")
    if args.test_openai:
        from .models.openai_provider import OpenAIProvider, ProviderError
        provider = OpenAIProvider(lambda: manager.settings)
        blocked = provider.blocked_reason()
        if blocked:
            print(f"OpenAI indisponível: {blocked}")
            return 1
        try:
            result = provider.chat([{"role": "user", "content": "Responda apenas: OK"}], timeout=30)
        except ProviderError as exc:
            print(f"Falha ({exc.kind}): {exc}")
            return 1
        print(f"OpenAI respondeu ({result.model}, {result.seconds:.1f} s): {result.content[:80]}")
    return 0


def run_data_command(args: argparse.Namespace) -> int:
    """Backup, restauração e exportação pela linha de comando — sem iniciar o núcleo."""
    from .memory import backup
    from .memory.store import Database

    if args.list_backups:
        items = backup.list_backups()
        if not items:
            print(f"Nenhum backup em {backup.backups_dir()}")
        for item in items:
            stamp = time.strftime("%d/%m/%Y %H:%M", time.localtime(item["created"]))
            print(f"{stamp}  {item['size'] / 2 ** 20:7.2f} MB  {item['path']}")
        return 0
    if args.restore_backup:
        try:
            result = backup.restore_backup(args.restore_backup)
        except (OSError, ValueError) as exc:
            print(f"Restauração recusada: {exc}")
            return 1
        print(f"Banco restaurado de {result['restored_from']} ({result['check']}).")
        if result["previous"]:
            print(f"O banco anterior foi guardado em {result['previous']}")
        return 0
    try:
        db = Database(paths.database_path())
    except sqlite3.DatabaseError as exc:
        raise _database_problem(exc) from exc
    try:
        if args.backup:
            path = backup.create_backup(db, reason="manual")
            print(f"Backup criado: {path}")
            return 0
        from .secondbrain.service import SecondBrainError, SecondBrainService
        target = args.export
        fmt = "csv" if str(target).lower().endswith(".csv") else "json"
        try:
            info = SecondBrainService(db).export(target, fmt=fmt)
        except SecondBrainError as exc:
            print(f"Exportação recusada: {exc}")
            return 1
        print(f"{info['count']} registro(s) exportado(s) em {info['format'].upper()}: {info['path']}")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.debug)
    log = logging.getLogger("ultron")
    log.info("JARVIS %s iniciando (%s)", __version__, " ".join(sys.argv[1:]) or "HUB")
    try:
        return _dispatch(args, log)
    except StartupError as exc:
        log.error("início interrompido: %s", exc)       # no console (stderr) e no log; sem console, numa janela
        _show_startup_error(str(exc))
        return 3


def _dispatch(args: argparse.Namespace, log: logging.Logger) -> int:
    if args.list_mics or args.mic:
        return run_microphones(args)
    from .platform import control, single_instance
    if args.import_models:
        from .platform.models_import import import_models
        report = import_models(args.import_models)
        print(report.summary())
        return 0 if not report.failed else 1
    if args.set_openai_key or args.use_openai or args.use_ollama or args.test_openai:
        return run_openai_command(args)
    if args.autostart_check:
        from .platform import autostart
        print(autostart.check()["text"])
        return 0
    if args.status:
        pid = control.running_pid()
        print(f"JARVIS em execução (processo {pid})." if pid else "O JARVIS não está em execução.")
        return 0
    if args.stop:
        ok, message = control.stop()
        print(message)
        return 0 if ok else 1
    if args.backup or args.list_backups or args.restore_backup or args.export:
        if args.restore_backup and not single_instance.acquire():
            print("Feche o JARVIS antes de restaurar um backup (bandeja > Sair).")
            return 2
        try:
            return run_data_command(args)
        finally:
            single_instance.release()
    if args.diagnose or args.voice_test:
        if not single_instance.acquire():
            print("O JARVIS já está em execução: feche-o (bandeja > Sair) para diagnosticar sem disputar o "
                  "microfone (START_JARVIS.bat --stop), ou use DIAGNÓSTICOS > VOZ > TESTAR na interface.")
            return 2
        try:
            return run_voice_test(args) if args.voice_test else run_diagnose(args)
        finally:
            single_instance.release()
    if not single_instance.acquire():
        if single_instance.blocked_by_legacy:
            print("O JARVIS original (versão anterior, jarvis_hud.py) está aberto. Feche-o antes: os dois "
                  "disputariam o microfone.")
            log.warning("JARVIS original em execução (mutex %s); esta instância não foi iniciada",
                        single_instance.LEGACY_NAME)
        else:
            print("O JARVIS já está em execução.")
        return 0
    control.register()
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
        control.unregister()
        single_instance.release()
