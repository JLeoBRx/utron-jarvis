import pytest

from safra.core.config import DEFAULT_PORT, load_settings
from safra_foundation.errors import ConfigError


def test_defaults_are_local_and_safe(tmp_path):
    s = load_settings(env={}, data_dir=tmp_path)
    assert s.api_host == "127.0.0.1" and s.api_port == DEFAULT_PORT
    assert s.environment == "development"
    assert s.database_url == "sqlite:///" + (tmp_path / "safra.sqlite3").as_posix()
    assert s.logs_dir == tmp_path / "logs" and s.backups_dir == tmp_path / "backups"


def test_environment_variables_are_read_and_typed(tmp_path):
    s = load_settings(env={"SAFRA_DATA_DIR": str(tmp_path), "SAFRA_API_PORT": "50123", "SAFRA_LOG_LEVEL": "DEBUG",
                           "SAFRA_LOG_TO_FILE": "não", "SAFRA_ENVIRONMENT": "production"})
    assert (s.data_dir, s.api_port, s.log_level, s.log_to_file, s.environment) == (
        tmp_path, 50123, "DEBUG", False, "production")


def test_default_data_dir_is_the_new_folder_never_the_legacy_one():
    s = load_settings(env={"LOCALAPPDATA": "/tmp/appdata", "XDG_DATA_HOME": "/tmp/xdg"})
    assert s.data_dir.name.lower() == "safra"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.0.10", "example.com", "::"])
def test_assistant_refuses_to_listen_outside_this_computer(tmp_path, host):
    with pytest.raises(ConfigError) as info:
        load_settings(env={"SAFRA_API_HOST": host}, data_dir=tmp_path)
    assert "api_host" in info.value.details["fields"]


@pytest.mark.parametrize("url", ["postgresql://u:p@servidor/banco", "mysql://servidor/banco"])
def test_assistant_database_is_always_a_local_file(tmp_path, url):
    with pytest.raises(ConfigError) as info:
        load_settings(env={"SAFRA_DATABASE_URL": url}, data_dir=tmp_path)
    assert "database_url" in info.value.details["fields"]


@pytest.mark.parametrize("env", [{"SAFRA_API_PORT": "80"}, {"SAFRA_LOG_LEVEL": "TUDO"}, {"SAFRA_ENVIRONMENT": "qualquer"}])
def test_invalid_values_are_rejected(tmp_path, env):
    with pytest.raises(ConfigError):
        load_settings(env=env, data_dir=tmp_path)


def test_portal_variables_do_not_configure_the_assistant(tmp_path):
    s = load_settings(env={"SAFRA_PORTAL_DATABASE_URL": "postgresql://x/y", "SAFRA_PORTAL_SESSION_HOURS": "1"},
                      data_dir=tmp_path)
    assert s.database_url.startswith("sqlite:///")


def test_allowed_hosts_follow_the_port(tmp_path):
    s = load_settings(env={}, data_dir=tmp_path, api_port=50001)
    assert set(s.allowed_hosts) == {"127.0.0.1:50001", "localhost:50001", "[::1]:50001"}
