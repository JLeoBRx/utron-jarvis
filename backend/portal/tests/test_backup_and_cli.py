import io

import pytest
from fastapi.testclient import TestClient

from safra_foundation import backup
from safra_foundation.database import sqlite_path
from safra_portal.api import cli
from safra_portal.api.app import create_app

from conftest import PASSWORD, Portal, page_data


def test_backup_can_be_restored(settings):
    """Critério 15: o conteúdo volta, e o banco substituído não se perde."""
    portal = Portal(settings)
    admin = portal.login("administrador")
    page = admin.post("/pages", json=page_data(title="Antes do desastre")).json()
    admin.post(f"/pages/{page['id']}/publish")
    database = sqlite_path(settings.database_url)
    saved = backup.backup_sqlite(database, settings.backups_dir, reason="teste", prefix="safra-portal")
    admin.delete(f"/pages/{page['id']}", json={"confirm_slug": "pagina-de-teste"})
    assert portal.public.get("/pagina-de-teste").status_code == 404
    portal.close()                                                    # restauração com o serviço parado

    safety = backup.restore_sqlite(saved.path, database, safety_dir=settings.backups_dir, prefix="safra-portal")
    assert safety is not None and backup.verify_sqlite(safety.path)
    restored = Portal(settings)
    try:
        response = restored.public.get("/pagina-de-teste")
        assert response.status_code == 200 and "Antes do desastre" in response.text
        assert restored.login("administrador", create=False).get("/pages").status_code == 200   # contas também voltam
    finally:
        restored.close()


def _env(monkeypatch, settings):
    monkeypatch.setenv("SAFRA_PORTAL_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("SAFRA_PORTAL_ENVIRONMENT", "test")
    monkeypatch.setenv("SAFRA_PORTAL_LOG_TO_FILE", "0")


def test_cli_creates_the_first_administrator_without_any_default(settings, monkeypatch, capsys):
    _env(monkeypatch, settings)
    assert cli.main(["check"]) == 0 and "ok" in capsys.readouterr().out
    monkeypatch.setattr("sys.stdin", io.StringIO("curta\n"))
    assert cli.main(["create-admin", "--email", "dono@exemplo.test", "--name", "Dono", "--password-stdin"]) == 2
    assert "pelo menos 12" in capsys.readouterr().err
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert cli.main(["create-admin", "--email", "dono@exemplo.test", "--name", "Dono", "--password-stdin"]) == 0
    out = capsys.readouterr().out
    assert "dono@exemplo.test" in out and PASSWORD not in out
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert cli.main(["create-admin", "--email", "dono@exemplo.test", "--name", "Dono", "--password-stdin"]) == 2   # já existe
    with TestClient(create_app(settings), base_url=settings.public_base_url) as client:
        response = client.post("/admin/api/auth/login", json={"email": "dono@exemplo.test", "password": PASSWORD},
                               headers={"Origin": settings.public_base_url})
        assert response.status_code == 200 and response.json()["user"]["role"] == "administrador"


def test_cli_recovery_token_and_seed(settings, monkeypatch, capsys):
    _env(monkeypatch, settings)
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    cli.main(["create-admin", "--email", "dono@exemplo.test", "--name", "Dono", "--password-stdin"])
    capsys.readouterr()
    assert cli.main(["recovery-token", "--email", "ninguem@exemplo.test"]) == 2
    capsys.readouterr()
    assert cli.main(["recovery-token", "--email", "dono@exemplo.test"]) == 0
    token = capsys.readouterr().out.strip().splitlines()[-1]
    assert cli.main(["seed"]) == 0 and "criado" in capsys.readouterr().out
    assert cli.main(["seed"]) == 0 and "nada foi alterado" in capsys.readouterr().out
    with TestClient(create_app(settings), base_url=settings.public_base_url) as client:
        headers = {"Origin": settings.public_base_url}
        assert client.post("/admin/api/auth/recover", json={"token": token, "new_password": "senha recuperada longa"},
                           headers=headers).status_code == 200
        assert client.post("/admin/api/auth/login", json={"email": "dono@exemplo.test", "password": "senha recuperada longa"},
                           headers=headers).status_code == 200


def test_cli_reports_configuration_errors_without_a_traceback(monkeypatch, capsys, settings):
    _env(monkeypatch, settings)
    monkeypatch.setenv("SAFRA_PORTAL_PORT", "abc")
    assert cli.main(["check"]) == 2
    assert "Configuração inválida" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["--version"])
