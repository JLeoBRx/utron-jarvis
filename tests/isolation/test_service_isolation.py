"""Os dois serviços são independentes (decisão AD-02). Critérios de aceitação 1 a 6 da Fase 2."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from safra_foundation import migrations
from safra_foundation.database import make_engine
from safra_foundation.errors import ConfigError, StorageError

REPO = Path(__file__).resolve().parents[2]
ASSISTANT_SRC = REPO / "backend" / "assistant" / "src" / "safra"
PORTAL_SRC = REPO / "backend" / "portal" / "src" / "safra_portal"


def _imports(root: Path) -> set[str]:
    found: set[str] = set()
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                found.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                found.add(node.module.split(".")[0])
    return found


def _source(root: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(root.rglob("*")) if p.suffix in {".py", ".html", ".css"})


def _assistant(tmp_path):
    from safra.api.app import create_app
    from safra.core.config import load_settings
    settings = load_settings(env={}, environment="test", data_dir=tmp_path / "assistant", log_to_file=False)
    return settings, create_app(settings)


def _portal(tmp_path):
    from safra_portal.api.app import create_app
    from safra_portal.config import load_settings
    settings = load_settings(env={}, environment="test", data_dir=tmp_path / "portal", log_to_file=False)
    return settings, create_app(settings)


# ------------------------------------------------------------------ código
def test_neither_service_imports_the_other():
    assert "safra_portal" not in _imports(ASSISTANT_SRC)
    assert "safra" not in _imports(PORTAL_SRC)
    assert len(_imports(ASSISTANT_SRC)) > 3 and len(_imports(PORTAL_SRC)) > 5        # a leitura não voltou vazia


def test_neither_service_mentions_the_other_ones_addresses_or_settings():
    assistant, portal = _source(ASSISTANT_SRC), _source(PORTAL_SRC)
    for needle in ("SAFRA_PORTAL_", "47900", "safra_portal_session", "/admin/api", "portal.sqlite3"):
        assert needle not in assistant, f"o Assistant menciona {needle}"
    for needle in ("47800", "/api/v1/", "safra.sqlite3", "safra-assistant", "SAFRA_API_", "SAFRA_DATA_DIR"):
        assert needle not in portal, f"o Portal menciona {needle}"


def test_the_portal_has_no_http_client_to_call_anything():
    """O Portal não faz chamadas de saída: não há como ele consultar o Assistant nem serviço algum."""
    clients = {"httpx", "requests", "urllib3", "aiohttp", "websockets", "socket", "http", "urllib"}
    used = _imports(PORTAL_SRC) & clients
    assert used <= {"urllib"}                                    # só urllib.parse, para ler o endereço público
    for path in PORTAL_SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "urlopen" not in text and "urllib.request" not in text, path.name


# ------------------------------------------------------------------ cada um sozinho
def _run_without(blocked: str, code: str, tmp_path: Path) -> dict:
    """Executa ``code`` num processo novo em que o pacote ``blocked`` NÃO pode ser importado."""
    script = textwrap.dedent(f"""
        import importlib.abc, json, sys
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name == {blocked!r} or name.startswith({blocked!r} + "."):
                    raise ImportError("pacote bloqueado no teste de isolamento: " + name)
        sys.meta_path.insert(0, Block())
        from fastapi.testclient import TestClient
        result = {{}}
    """) + textwrap.dedent(code) + "\nprint('RESULT=' + json.dumps(result))\n"
    done = subprocess.run([sys.executable, "-W", "ignore", "-c", script], capture_output=True, text=True, timeout=120,
                          env={"PATH": "/usr/bin:/bin", "TMP_DIR": str(tmp_path), "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")})
    assert done.returncode == 0, done.stderr[-2000:]
    line = next(l for l in done.stdout.splitlines() if l.startswith("RESULT="))
    return json.loads(line[len("RESULT="):])


def test_portal_starts_and_serves_without_the_assistant_installed(tmp_path):
    """Critérios 1 e 3."""
    result = _run_without("safra", """
        import os, pathlib
        from safra_portal.api.app import create_app
        from safra_portal.config import load_settings
        s = load_settings(env={}, environment="test", data_dir=pathlib.Path(os.environ["TMP_DIR"]) / "p", log_to_file=False)
        with TestClient(create_app(s), base_url=s.public_base_url) as c:
            result["health"] = c.get("/healthz").json()
            result["home"] = c.get("/").status_code
            result["page"] = c.get("/sobre").status_code
            result["admin"] = c.get("/admin/api/pages").status_code
        result["assistant_loaded"] = any(m == "safra" or m.startswith("safra.") for m in sys.modules)
    """, tmp_path)
    assert result["health"]["status"] == "ok" and result["health"]["service"] == "portal"
    assert (result["home"], result["page"], result["admin"]) == (200, 200, 401)
    assert result["assistant_loaded"] is False


def test_assistant_starts_and_serves_without_the_portal_installed(tmp_path):
    """Critérios 2 e 4."""
    result = _run_without("safra_portal", """
        import os, pathlib
        from safra.api.app import create_app
        from safra.core.config import load_settings
        s = load_settings(env={}, environment="test", data_dir=pathlib.Path(os.environ["TMP_DIR"]) / "a", log_to_file=False)
        with TestClient(create_app(s), base_url=f"http://127.0.0.1:{s.api_port}") as c:
            result["health"] = c.get("/api/v1/health").json()
        result["portal_loaded"] = any(m == "safra_portal" or m.startswith("safra_portal.") for m in sys.modules)
        result["jinja_loaded"] = "jinja2" in sys.modules
    """, tmp_path)
    assert result["health"]["status"] == "ok" and result["health"]["service"] == "assistant"
    assert result["portal_loaded"] is False and result["jinja_loaded"] is False


def test_each_service_keeps_working_while_the_other_is_down(tmp_path):
    _, assistant_app = _assistant(tmp_path)
    portal_settings, portal_app = _portal(tmp_path)
    with TestClient(portal_app, base_url=portal_settings.public_base_url) as portal:
        assert portal.get("/").status_code == 200                 # o Assistant nem foi iniciado
        with TestClient(assistant_app, base_url="http://127.0.0.1:47800") as assistant:
            assert assistant.get("/api/v1/health").json()["status"] == "ok"
        assert portal.get("/sobre").status_code == 200            # o Assistant já encerrou
    with TestClient(assistant_app, base_url="http://127.0.0.1:47800") as assistant:
        assert assistant.get("/api/v1/health").json()["status"] == "ok"   # o Portal já encerrou


# ------------------------------------------------------------------ rotas
def _paths(app, router=None) -> set[str]:
    found: set[str] = set()

    def walk(routes):
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(inner.routes)
            elif getattr(route, "path", None):
                found.add(route.path)

    walk(app.routes)
    return found


def test_no_route_is_shared_and_no_route_crosses_over(tmp_path):
    """Critério 5."""
    _, assistant_app = _assistant(tmp_path)
    _, portal_app = _portal(tmp_path)
    assistant, portal = _paths(assistant_app), _paths(portal_app)
    assert "/api/v1/health" in assistant and "/healthz" in portal and "/admin/api/pages" in portal
    # A raiz "/" é a porta de entrada de cada serviço, cada um no seu endereço (site público no Portal, interface
    # local no Assistant). É o único caminho que coincide; nenhum outro pode coincidir.
    assert assistant & portal <= {"/"}
    assert not any(p.startswith(("/admin", "/media", "/static", "/sitemap", "/robots")) for p in assistant)
    assert not any(p.startswith("/api/v1") for p in portal)
    private = ("conversation", "message", "memory", "memories", "tool", "voice", "project", "command", "assistant")
    assert not any(word in path.lower() for path in portal for word in private), "o Portal expõe algo do domínio do Assistant"


def test_each_service_answers_404_on_the_other_ones_routes(tmp_path):
    assistant_settings, assistant_app = _assistant(tmp_path)
    portal_settings, portal_app = _portal(tmp_path)
    with TestClient(assistant_app, base_url=f"http://127.0.0.1:{assistant_settings.api_port}") as assistant:
        for path in ("/admin/api/pages", "/admin/", "/sobre", "/healthz", "/sitemap.xml"):
            assert assistant.get(path).status_code == 404, path
    with TestClient(portal_app, base_url=portal_settings.public_base_url) as portal:
        assert portal.get("/api/v1/health").status_code == 404


# ------------------------------------------------------------------ bancos
def test_databases_are_separate_files_with_separate_owners(tmp_path):
    """Critério 6."""
    assistant_settings, assistant_app = _assistant(tmp_path)
    portal_settings, portal_app = _portal(tmp_path)
    assert assistant_settings.database_url != portal_settings.database_url
    assert assistant_settings.data_dir != portal_settings.data_dir
    with TestClient(assistant_app, base_url="http://127.0.0.1:47800"), \
            TestClient(portal_app, base_url=portal_settings.public_base_url):
        assert migrations.database_owner(assistant_app.state.engine) == "assistant"
        assert migrations.database_owner(portal_app.state.engine) == "portal"
        from sqlalchemy import inspect
        assistant_tables = set(inspect(assistant_app.state.engine).get_table_names())
        portal_tables = set(inspect(portal_app.state.engine).get_table_names())
    assert {"users", "sessions", "contents", "media"} <= portal_tables
    assert not {"users", "sessions", "contents", "media", "roles"} & assistant_tables
    assert not {"conversations", "messages", "memories"} & portal_tables
    assert assistant_tables & portal_tables == {"safra_service"}       # só a tabela que identifica o dono


def test_default_data_folders_are_different():
    from safra.core.config import load_settings as assistant_settings
    from safra_portal.config import load_settings as portal_settings
    env = {"LOCALAPPDATA": "/tmp/appdata", "XDG_DATA_HOME": "/tmp/xdg"}
    assert assistant_settings(env=env).data_dir != portal_settings(env=env).data_dir


def test_each_service_refuses_the_other_ones_database(tmp_path):
    from safra.api.app import create_app as create_assistant
    from safra.core.config import load_settings as assistant_settings
    from safra.storage import MIGRATIONS as ASSISTANT_MIGRATIONS
    from safra_portal.api.app import create_app as create_portal
    from safra_portal.config import load_settings as portal_settings
    from safra_portal.infrastructure import MIGRATIONS as PORTAL_MIGRATIONS

    portal_db = "sqlite:///" + (tmp_path / "do-portal.sqlite3").as_posix()
    engine = make_engine(portal_db)
    migrations.upgrade(engine, PORTAL_MIGRATIONS)
    engine.dispose()
    wrong = assistant_settings(env={}, environment="test", data_dir=tmp_path / "a", log_to_file=False, database_url=portal_db)
    with pytest.raises(StorageError) as info:
        with TestClient(create_assistant(wrong), base_url="http://127.0.0.1:47800"):
            pass
    assert "não compartilham banco" in info.value.message

    assistant_db = "sqlite:///" + (tmp_path / "do-assistant.sqlite3").as_posix()
    engine = make_engine(assistant_db)
    migrations.upgrade(engine, ASSISTANT_MIGRATIONS)
    engine.dispose()
    wrong = portal_settings(env={}, environment="test", data_dir=tmp_path / "p", log_to_file=False, database_url=assistant_db)
    with pytest.raises(StorageError):
        with TestClient(create_portal(wrong), base_url=wrong.public_base_url):
            pass


def test_the_assistant_never_accepts_a_database_server(tmp_path):
    from safra.core.config import load_settings
    with pytest.raises(ConfigError):
        load_settings(env={"SAFRA_DATABASE_URL": "postgresql://portal:x@servidor/portal"}, data_dir=tmp_path)


# ------------------------------------------------------------------ sessões, credenciais e configuração
def test_a_portal_session_means_nothing_to_the_assistant(tmp_path):
    from safra_portal.infrastructure.db import transaction
    portal_settings, portal_app = _portal(tmp_path)
    assistant_settings, assistant_app = _assistant(tmp_path)
    with TestClient(portal_app, base_url=portal_settings.public_base_url) as portal:
        with transaction(portal_app.state.session_factory) as db:
            portal_app.state.auth.create_user(db, email="a@exemplo.test", name="A", role="administrador",
                                              password="senha de teste bem comprida")
        login = portal.post("/admin/api/auth/login", json={"email": "a@exemplo.test", "password": "senha de teste bem comprida"},
                            headers={"Origin": portal_settings.public_base_url})
        assert login.status_code == 200
        cookie_header = login.headers["set-cookie"]
        token = portal.cookies.get("safra_portal_session")
    assert "Path=/admin" in cookie_header and "safra_portal_session" in cookie_header
    with TestClient(assistant_app, base_url=f"http://127.0.0.1:{assistant_settings.api_port}") as assistant:
        with_cookie = assistant.get("/api/v1/health", headers={"Cookie": f"safra_portal_session={token}"})
        without = assistant.get("/api/v1/health")
        assert with_cookie.json() == without.json()               # o cookie do Portal não muda nada
        assert "set-cookie" not in with_cookie.headers


def test_configuration_prefixes_do_not_leak_between_services(tmp_path):
    from safra.core.config import Settings as AssistantSettings, load_settings as assistant_settings
    from safra_portal.config import Settings as PortalSettings, load_settings as portal_settings
    assert not any(name.startswith("portal") for name in AssistantSettings.model_fields)
    assert not any(name.startswith(("api_", "assistant")) for name in PortalSettings.model_fields)
    env = {"SAFRA_API_PORT": "50111", "SAFRA_PORTAL_PORT": "50222", "SAFRA_LOG_LEVEL": "DEBUG", "SAFRA_PORTAL_LOG_LEVEL": "ERROR"}
    a = assistant_settings(env=env, data_dir=tmp_path / "a")
    p = portal_settings(env=env, data_dir=tmp_path / "p")
    assert (a.api_port, a.log_level) == (50111, "DEBUG") and (p.port, p.log_level) == (50222, "ERROR")


def test_neither_service_stores_or_reads_the_other_ones_credentials():
    assistant, portal = _source(ASSISTANT_SRC), _source(PORTAL_SRC)
    assert "password_hash" not in assistant and "recovery_token" not in assistant
    assert "keyring" not in portal and "api_key" not in portal.lower()
