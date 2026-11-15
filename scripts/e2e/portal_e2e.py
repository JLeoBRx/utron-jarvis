"""Sobe um SAFRA Portal descartável e roda o teste de ponta a ponta do navegador contra ele.

Uso:  python scripts/e2e/portal_e2e.py [--shots PASTA] [--node-path CAMINHO]

* banco, mídia e logs em pasta temporária; nada fica no computador depois;
* o administrador é criado pelo comando oficial (`safra-portal create-admin`), com senha gerada na hora;
* exige o painel compilado em apps/admin/dist e o pacote `playwright` do Node com o Chromium.
"""
from __future__ import annotations

import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "apps" / "admin" / "e2e" / "portal.e2e.mjs"


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shots", default="", help="pasta para as capturas de tela")
    parser.add_argument("--node-path", default=os.environ.get("NODE_PATH", ""), help="onde está o pacote playwright")
    args = parser.parse_args()
    if not (REPO / "apps" / "admin" / "dist" / "index.html").is_file():
        print("Compile o painel antes: cd apps/admin && npm ci && npm run build", file=sys.stderr)
        return 2
    folder = Path(tempfile.mkdtemp(prefix="safra-portal-e2e-"))
    port = free_port()
    env = {**os.environ, "SAFRA_PORTAL_DATA_DIR": str(folder), "SAFRA_PORTAL_ENVIRONMENT": "test",
           "SAFRA_PORTAL_PORT": str(port), "SAFRA_PORTAL_LOG_TO_FILE": "0",
           "SAFRA_PORTAL_ADMIN_DIST": str(REPO / "apps" / "admin" / "dist")}
    email = "e2e@exemplo.test"
    password = "e2e-" + secrets.token_urlsafe(18)          # gerada na hora; nunca gravada
    cli = [sys.executable, "-m", "safra_portal.api.cli"]
    created = subprocess.run(cli + ["create-admin", "--email", email, "--name", "Administrador E2E", "--password-stdin"],
                             input=password + "\n", text=True, capture_output=True, env=env, timeout=120)
    if created.returncode != 0:
        print(created.stderr, file=sys.stderr)
        return 1
    server = subprocess.Popen(cli + ["serve"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(url + "/healthz", timeout=1) as response:   # noqa: S310 - endereço local
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.2)
        else:
            print("o Portal não respondeu", file=sys.stderr)
            return 1
        node_env = {**os.environ, "PORTAL_URL": url, "ADMIN_EMAIL": email, "ADMIN_PASSWORD": password,
                    "SHOTS_DIR": args.shots}
        if args.node_path:
            node_env["NODE_PATH"] = args.node_path
        return subprocess.run(["node", str(SCRIPT)], env=node_env, cwd=REPO / "apps" / "admin", timeout=600).returncode
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    sys.exit(main())
