from pathlib import Path

import pytest

from safra.core.config import DEFAULT_PORT, default_data_dir, load_settings
from safra.core.errors import ConfigError


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


def test_data_dir_is_the_new_folder_never_the_legacy_one():
    windows = default_data_dir({"LOCALAPPDATA": r"C:\Users\x\AppData\Local"}, platform="win32")
    assert windows.name == "SAFRA"
    linux = default_data_dir({"XDG_DATA_HOME": "/home/x/.local/share"}, platform="linux")
    assert linux == Path("/home/x/.local/share/safra")


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.0.10", "example.com", "::"])
def test_api_refuses_to_listen_outside_this_computer(tmp_path, host):
    with pytest.raises(ConfigError) as info:
        load_settings(env={"SAFRA_API_HOST": host}, data_dir=tmp_path)
    assert "api_host" in info.value.details["fields"]


@pytest.mark.parametrize("env", [{"SAFRA_API_PORT": "80"}, {"SAFRA_API_PORT": "abc"}, {"SAFRA_LOG_LEVEL": "TUDO"},
                                 {"SAFRA_ENVIRONMENT": "qualquer"}, {"SAFRA_LOG_TO_FILE": "talvez"}])
def test_invalid_values_are_rejected_with_a_clear_error(tmp_path, env):
    with pytest.raises(ConfigError):
        load_settings(env=env, data_dir=tmp_path)


def test_error_names_the_field_but_never_echoes_the_value(tmp_path):
    with pytest.raises(ConfigError) as info:
        load_settings(env={"SAFRA_API_PORT": "senha-secreta-123"}, data_dir=tmp_path)
    assert "api_port" in info.value.message and "senha-secreta-123" not in info.value.message


def test_allowed_hosts_follow_the_port(tmp_path):
    s = load_settings(env={}, data_dir=tmp_path, api_port=50001)
    assert set(s.allowed_hosts) == {"127.0.0.1:50001", "localhost:50001", "[::1]:50001"}


def test_settings_are_immutable_and_reject_unknown_fields(tmp_path):
    s = load_settings(env={}, data_dir=tmp_path)
    with pytest.raises(Exception):
        s.api_port = 1
    with pytest.raises(ConfigError):
        load_settings(env={}, data_dir=tmp_path, campo_inexistente=1)
