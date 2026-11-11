"""``python -m jarvis_gateway``            — inicia o gateway (configuração pelo ambiente);
``python -m jarvis_gateway hash-secret``   — gera um segredo de inscrição forte e o hash scrypt dele.

O segredo (texto) vai para o SAFRA do seu computador uma única vez (CONFIGURAÇÕES > REDE REMOTA > CONECTAR);
no servidor fica SÓ o hash, em ``JARVIS_ENROLL_SECRET_HASH`` (gerenciador de segredos da hospedagem).
"""
from __future__ import annotations

import getpass
import secrets
import sys

from .security import hash_secret


def main(argv: list[str]) -> int:
    if argv[:1] == ["hash-secret"]:
        typed = getpass.getpass("Segredo de inscrição (Enter = gerar um aleatório): ") if sys.stdin.isatty() else ""
        secret = typed or secrets.token_urlsafe(24)
        if len(secret) < 16:
            print("O segredo precisa ter pelo menos 16 caracteres.", file=sys.stderr)
            return 2
        if not typed:
            print(f"Segredo gerado (guarde para o SAFRA do computador; não vai para o servidor):\n  {secret}\n")
        print("Coloque no servidor (gerenciador de segredos), não em arquivo versionado:")
        print(f"  JARVIS_ENROLL_SECRET_HASH={hash_secret(secret)}")
        return 0
    from .app import run
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
