"""Linha de comando: ``safra-assistant`` inicia a API local; ``safra-assistant --check`` confere e sai."""
from __future__ import annotations

import argparse
import sys

from safra_foundation.errors import SafraError

from .. import __version__
from ..core.config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="safra-assistant", description="SAFRA Assistant — API local do assistente.")
    parser.add_argument("--version", action="version", version=f"SAFRA Assistant {__version__}")
    parser.add_argument("--port", type=int, help="porta da API local (padrão: 47800)")
    parser.add_argument("--check", action="store_true",
                        help="valida a configuração, aplica as migrações (com backup) e informa a saúde")
    args = parser.parse_args(argv)
    try:
        settings = load_settings(**({"api_port": args.port} if args.port else {}))
    except SafraError as exc:
        print(f"SAFRA Assistant não iniciou: {exc.message}", file=sys.stderr)
        return 2
    if args.check:
        from safra_foundation import migrations
        from safra_foundation.database import make_engine, ping

        from ..storage import MIGRATIONS
        try:
            engine = make_engine(settings.database_url)
            result = migrations.upgrade(engine, MIGRATIONS, backups_dir=settings.backups_dir)
            ok = ping(engine) and migrations.current_revision(engine, MIGRATIONS) == migrations.head_revision(MIGRATIONS)
            engine.dispose()
        except SafraError as exc:
            print(f"SAFRA Assistant não passou na verificação: {exc.message}", file=sys.stderr)
            return 1
        print(f"SAFRA Assistant {__version__} · dados em {settings.data_dir} · banco na versão {result.after} · "
              f"{'ok' if ok else 'FALHOU'}")
        return 0 if ok else 1
    import uvicorn

    from .app import create_app
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port, log_config=None,
                access_log=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
