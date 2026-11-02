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
    parser.add_argument("--gui-check", action="store_true",
                        help="monta a interface sem mostrá-la (sem iniciar serviços), diz se abriu e sai")
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
    """Diagnóstico por etapas, cada uma impressa ao terminar e com prazo próprio (``ultron/diagnose.py``)."""
    from . import diagnose
    return diagnose.run(args, make_core=_make_core, wait_voice=_wait_voice_ready, version=__version__)


def run_gui_check(args: argparse.Namespace) -> int:
    """Monta a interface completa SEM mostrá-la e sem iniciar o núcleo (nada de microfone, rede ou robô): prova
    que janela, páginas, avatar e o menu da bandeja sobem nesta máquina. Usado pelo diagnóstico, num processo
    separado, para que até uma falha que derrube o Qt seja informada."""
    import traceback
    started = time.perf_counter()
    try:
        from PySide6 import QtCore, QtWidgets

        from .hud.controller import HudController, log_qt_messages
        log_qt_messages()
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        tray = QtWidgets.QSystemTrayIcon.isSystemTrayAvailable()
        core = _make_core(args)
        controller = HudController(core)
        menu = controller._menu()                     # o menu da bandeja/orbe, como no Windows com bandeja
        menu.aboutToShow.emit()
        end = time.monotonic() + 0.5
        while time.monotonic() < end:
            app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        info = (f"Qt {QtCore.qVersion()}, plataforma {app.platformName()}, bandeja do sistema "
                f"{'disponível' if tray else 'indisponível'}, rosto {controller.avatar_reason}, "
                f"montada em {time.perf_counter() - started:.1f} s")
        controller.quit()
    except Exception as exc:
        logging.getLogger("ultron").exception("verificação da interface falhou")
        traceback.print_exc(file=sys.stdout)
        print(f"INTERFACE FALHOU: {type(exc).__name__}: {exc}", flush=True)
        return 1
    print(f"INTERFACE OK: {info}", flush=True)
    return 0


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


def run_headless(args: argparse.Namespace, core=None) -> int:
    """``--console``/``--headless``: a conversa pelo terminal (``ultron/console.py``); ``--say``: um pedido e sai.
    Os dois usam o MESMO núcleo da interface gráfica (``core`` já criado é reaproveitado, sem iniciar outro)."""
    from .core.events import EventType

    core = core or _make_core(args)
    if not args.say:
        from .console import Console
        return Console(core).run()
    done = threading.Event()

    def show(event) -> None:
        payload = event.payload
        prefix = "…" if payload.get("partial") else "JARVIS:"
        print(f"{prefix} {payload.get('text', '')}", flush=True)
        if not payload.get("partial"):
            done.set()

    core.bus.subscribe(EventType.RESPONSE_READY, show, name="console")
    core.bus.subscribe(EventType.AUTHORIZATION_REQUIRED,
                       lambda e: print(f"[autorização] {e.payload.get('description')} — com --say não há como "
                                       "responder; use START_JARVIS.bat --console", flush=True),
                       name="console.auth")
    core.boot()
    done.clear()
    core.submit(args.say, source="text")
    done.wait(float(getattr(core.settings(), "llm_timeout", 120.0)) + 30)
    time.sleep(0.3)
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


def _safe_output() -> None:
    """Nenhum caractere derruba a saída. Num console do Windows o Python já escreve Unicode; redirecionada (arquivo,
    pipe, o instalador) a página de código pode não ter "→" — vira "?" em vez de ``UnicodeEncodeError`` (o
    diagnóstico do instalador caía assim no Windows)."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _safe_output()
    code = 1
    try:
        code = _main(argv)
        return code
    except BaseException as exc:
        if os.environ.get("JARVIS_PAUSE_ON_ERROR") == "1" and not isinstance(exc, SystemExit):
            import traceback
            traceback.print_exc()
        raise
    finally:
        if code != 0 and os.environ.get("JARVIS_PAUSE_ON_ERROR") == "1":
            try:
                input("\nO JARVIS terminou com erro (detalhes acima e no registro). Pressione Enter para fechar.")
            except (EOFError, KeyboardInterrupt, RuntimeError, OSError):
                pass


def _main(argv: list[str] | None) -> int:
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
    if args.gui_check:                               # não inicia o núcleo: não disputa a instância
        return run_gui_check(args)
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
        return _already_running(args, log)
    control.register(mode="console" if (args.headless or args.say) else "janela")
    try:
        if args.headless or args.say:
            return run_headless(args)
        try:
            if importlib.util.find_spec("PySide6") is None:
                raise ImportError("PySide6 não instalado")
            from .hud import run_hud
        except ImportError as exc:
            return _interface_failed(args, None, exc, log)
        core = _make_core(args)
        minimized = args.boot or bool(getattr(core.settings(), "hud_start_minimized", False))
        try:
            return run_hud(core, minimized=minimized)
        except Exception as exc:                     # a janela não montou: registra, explica e oferece o console
            return _interface_failed(args, core, exc, log)
    finally:
        control.unregister()
        single_instance.release()


def _tell(title: str, text: str, *, kind: str = "error") -> None:
    """No console, imprime; sem console (pythonw), mostra numa caixa de mensagem do sistema."""
    from .platform import notice
    if sys.stdout is not None:                       # python.exe (terminal, arquivo ou pipe)
        print(text, flush=True)
    else:                                            # pythonw: ninguém leria o print
        notice.show(title, text, kind=kind)


def _already_running(args: argparse.Namespace, log: logging.Logger) -> int:
    """Outra instância segura a instância única. Abrir de novo traz a janela para a frente; se ela não responder
    (ou estiver em modo console), diz o que fazer — em vez de não acontecer nada."""
    from .platform import control, single_instance
    if single_instance.blocked_by_legacy:
        text = ("O JARVIS original (versão anterior, jarvis_hud.py) está aberto. Feche-o antes: os dois disputariam "
                "o microfone.")
        log.warning("JARVIS original em execução (mutex %s); esta instância não foi iniciada",
                    single_instance.LEGACY_NAME)
        _tell("J.A.R.V.I.S. — já em execução", text, kind="warning")
        return 0
    pid = control.running_pid()
    mode = control.running_mode()
    wants_window = not (args.headless or args.say)
    if wants_window and mode != "console" and control.bring_to_front():
        log.info("JARVIS já em execução (processo %s): janela trazida para a frente", pid)
        print("O JARVIS já estava aberto: a janela foi trazida para a frente.", flush=True)
        return 0
    which = f" (processo {pid})" if pid else ""
    if mode == "console":
        text = (f"O JARVIS já está aberto em modo console{which}. Use aquela janela de terminal ou encerre-o com "
                "\"sair\" (ou START_JARVIS.bat --stop) antes de abrir de novo.")
    else:
        text = (f"O JARVIS já está em execução{which}"
                + (", mas a janela dele não respondeu ao pedido para aparecer" if wants_window else "")
                + ".\nPara encerrá-lo: START_JARVIS.bat --stop (ou bandeja > Sair). Se ele não responder, finalize o "
                  "pythonw.exe do JARVIS pelo Gerenciador de Tarefas — os dados ficam íntegros.")
    log.warning("outra instância em execução%s (modo %s); esta não foi iniciada", which, mode or "desconhecido")
    _tell("J.A.R.V.I.S. — já em execução", text, kind="warning")
    return 0


def _interface_failed(args: argparse.Namespace, core, exc: BaseException, log: logging.Logger) -> int:
    """A interface gráfica não abriu: o erro completo vai para o registro, o motivo aparece para o usuário e o
    modo console é oferecido — com o MESMO núcleo (no terminal) ou numa janela de console nova (sem terminal,
    depois de liberar a instância: nunca duas ao mesmo tempo). Dados e sessão não são tocados."""
    from .platform import control, notice, single_instance
    log.error("a interface gráfica não abriu", exc_info=(type(exc), exc, exc.__traceback__))
    if core is not None:
        core.bus.unsubscribe_prefix("hud")           # nada da janela que não montou fica ligado ao núcleo
        core.hud_health = None
        core.hud_probe = lambda: False
    logfile = paths.logs_dir() / "ultron.log"
    text = (f"A interface gráfica do JARVIS não abriu.\n\nMotivo: {type(exc).__name__}: {exc}\n\n"
            f"O erro completo foi registrado em:\n{logfile}\n\n"
            "Seus dados (memória, lembretes e configurações) não foram alterados.")
    if notice.has_console():
        print(text, flush=True)
        try:
            answer = input("\nAbrir o JARVIS em modo console agora? [S/n] ").strip().casefold()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer in ("", "s", "sim", "y", "yes"):
            control.set_mode("console")
            return run_headless(args, core=core)
        print("Para usar pelo terminal: START_JARVIS.bat --console", flush=True)
        return 4
    if sys.stdout is not None:                       # saída redirecionada, sem ninguém para responder
        print(text + "\nPara usar pelo terminal: START_JARVIS.bat --console", flush=True)
        return 4
    if notice.show("J.A.R.V.I.S. — a interface não abriu",
                   text + "\n\nAbrir o JARVIS em modo console (pelo terminal) agora?", ask=True):
        if core is not None and core.booted:
            core.shutdown()
        control.unregister()
        single_instance.release()                    # a janela de console assume a instância única
        _open_console_window(args)
    return 4


def _open_console_window(args: argparse.Namespace) -> None:
    """Abre ``main.py --headless`` numa janela de console nova (lista de argumentos, nunca texto de comando);
    se o console sair com erro, a janela espera um Enter antes de fechar (``JARVIS_PAUSE_ON_ERROR``)."""
    import subprocess
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        exe = exe[: -len("pythonw.exe")] + "python.exe"
    command = [exe, str(paths.project_root() / "main.py"), "--headless"]
    for flag in ("no_voice", "no_perception", "no_plugins", "debug"):
        if getattr(args, flag, False):
            command.append("--" + flag.replace("_", "-"))
    if args.profile:
        command += ["--profile", args.profile]
    env = {**os.environ, "JARVIS_PAUSE_ON_ERROR": "1"}       # a janela nova não some se o console falhar
    if sys.platform == "win32":
        subprocess.Popen(command, cwd=str(paths.project_root()), env=env,
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        subprocess.Popen(command, cwd=str(paths.project_root()), env=env, start_new_session=True)
