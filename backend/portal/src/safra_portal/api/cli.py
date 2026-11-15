"""Linha de comando do Portal.

    safra-portal                      inicia o servidor
    safra-portal check                valida a configuração, migra o banco (com backup) e informa a saúde
    safra-portal create-admin         cria o primeiro administrador (a senha é pedida no terminal)
    safra-portal recovery-token       gera um código de uso único para alguém redefinir a própria senha
    safra-portal seed                 cria o conteúdo inicial num banco vazio

Não existe conta padrão: sem `create-admin`, ninguém entra no painel.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import select

from safra_foundation import migrations
from safra_foundation.database import make_engine, ping
from safra_foundation.errors import SafraError

from .. import __version__
from ..auth.service import AuthService
from ..config import load_settings
from ..domain import permissions
from ..domain.models import User
from ..infrastructure import MIGRATIONS
from ..infrastructure.db import make_session_factory, transaction
from ..infrastructure.seed import seed_initial_content


def _open(settings):
    engine = make_engine(settings.database_url)
    migrations.upgrade(engine, MIGRATIONS, backups_dir=settings.backups_dir)
    return engine, make_session_factory(engine)


def _read_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass("Senha (mínimo de 12 caracteres): ")
    if first != getpass.getpass("Repita a senha: "):
        raise SafraError("As senhas não coincidem.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="safra-portal", description="SAFRA Portal — site público e painel administrativo.")
    parser.add_argument("--version", action="version", version=f"SAFRA Portal {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="inicia o servidor (padrão)")
    commands.add_parser("check", help="valida a configuração, migra o banco e informa a saúde")
    commands.add_parser("seed", help="cria o conteúdo inicial num banco vazio")
    create = commands.add_parser("create-admin", help="cria um administrador")
    create.add_argument("--email", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--password-stdin", action="store_true", help="lê a senha da entrada padrão (automação)")
    recovery = commands.add_parser("recovery-token", help="gera um código de recuperação de acesso")
    recovery.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        command = args.command or "serve"
        if command == "serve":
            import uvicorn

            from .app import create_app
            uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None,
                        access_log=False, proxy_headers=False)
            return 0
        engine, factory = _open(settings)
        try:
            if command == "check":
                ok = ping(engine) and migrations.current_revision(engine, MIGRATIONS) == migrations.head_revision(MIGRATIONS)
                print(f"SAFRA Portal {__version__} · banco na versão {migrations.current_revision(engine, MIGRATIONS)} · "
                      f"{'ok' if ok else 'FALHOU'}")
                return 0 if ok else 1
            if command == "seed":
                with transaction(factory) as db:
                    created = seed_initial_content(db)
                print("Conteúdo inicial criado." if created else "O banco já tem conteúdo; nada foi alterado.")
                return 0
            auth = AuthService(settings)
            if command == "create-admin":
                password = _read_password(args.password_stdin)
                with transaction(factory) as db:
                    user = auth.create_user(db, email=args.email, name=args.name, role=permissions.ADMINISTRADOR,
                                            password=password)
                print(f"Administrador criado: {user.email}")
                return 0
            if command == "recovery-token":
                with transaction(factory) as db:
                    user = db.scalar(select(User).where(User.email == auth.normalize_email(args.email),
                                                        User.deleted_at.is_(None)))
                    if user is None:
                        raise SafraError("Não existe conta com este e-mail.")
                    token = auth.create_recovery_token(db, user.id)
                print(f"Código de recuperação (uso único, vale {settings.recovery_token_minutes} minutos):\n{token}")
                return 0
        finally:
            engine.dispose()
    except SafraError as exc:
        print(f"SAFRA Portal: {exc.message}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
