"""Linha de comando do SAFRA Core: ``safra-core`` inicia a API local; ``safra-core --check`` confere e sai."""
from __future__ import annotations

import argparse
import sys

from .. import __version__
from ..core.config import load_settings
from ..core.errors import SafraError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="safra-core", description="SAFRA Core — API local do assistente.")
    parser.add_argument("--version", action="version", version=f"SAFRA {__version__}")
    parser.add_argument("--port", type=int, help="porta da API local (padrão: 47800)")
    parser.add_argument("--check", action="store_true",
                        help="valida a configuração, aplica as migrações (com backup) e informa a saúde")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(**({"api_port": args.port} if args.port else {}))
    except SafraError as exc:
        print(f"SAFRA não iniciou: {exc.message}", file=sys.stderr)
        return 2
    if args.check:
        from ..storage import migrations
        from ..storage.database import make_engine, ping
        try:
            engine = make_engine(settings.database_url)
            result = migrations.upgrade(engine, backups_dir=settings.backups_dir)
            ok = ping(engine) and migrations.current_revision(engine) == migrations.head_revision()
            engine.dispose()
        except SafraError as exc:
            print(f"SAFRA não passou na verificação: {exc.message}", file=sys.stderr)
            return 1
        print(f"SAFRA {__version__} · dados em {settings.data_dir} · banco na versão {result.after} · "
              f"{'ok' if ok else 'FALHOU'}")
        return 0 if ok else 1
    import uvicorn

    from .app import create_core_app
    uvicorn.run(create_core_app(settings), host=settings.api_host, port=settings.api_port, log_config=None,
                access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
