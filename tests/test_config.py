"""Settings from the environment."""

from __future__ import annotations

from pathlib import Path

import pytest

from polish_archives_mcp import server
from polish_archives_mcp.config import ConfigError, load_config

from .conftest import call_tool

VARS = (
    "POLISH_ARCHIVES_CACHE_DIR",
    "POLISH_ARCHIVES_TIMEOUT",
    "POLISH_ARCHIVES_MIN_INTERVAL",
    "POLISH_ARCHIVES_CONTACT",
    "POLISH_ARCHIVES_DOWNLOAD_DIR",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # no stray .env


def test_the_defaults():
    cfg = load_config()
    assert cfg.cache_dir == Path.home() / ".cache" / "polish-archives-mcp"
    assert cfg.timeout == 60.0 and cfg.min_interval == 4.0
    assert cfg.contact == "" and cfg.download_dir is None


def test_every_setting_is_read(monkeypatch, tmp_path):
    monkeypatch.setenv("POLISH_ARCHIVES_CACHE_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("POLISH_ARCHIVES_TIMEOUT", "30")
    monkeypatch.setenv("POLISH_ARCHIVES_MIN_INTERVAL", "6")
    monkeypatch.setenv("POLISH_ARCHIVES_CONTACT", "me@example.org")
    monkeypatch.setenv("POLISH_ARCHIVES_DOWNLOAD_DIR", str(tmp_path))
    cfg = load_config()
    assert cfg.cache_dir == tmp_path / "c" and cfg.timeout == 30.0
    assert cfg.min_interval == 6.0 and cfg.contact == "me@example.org"
    assert cfg.download_dir == tmp_path


def test_a_dotenv_in_the_working_directory_is_read(tmp_path):
    (tmp_path / ".env").write_text("POLISH_ARCHIVES_TIMEOUT=45\n")
    assert load_config().timeout == 45.0


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("POLISH_ARCHIVES_TIMEOUT", "soon"),
        ("POLISH_ARCHIVES_TIMEOUT", "0"),
        ("POLISH_ARCHIVES_TIMEOUT", "nan"),
        ("POLISH_ARCHIVES_MIN_INTERVAL", "1"),  # below the floor of 4
        ("POLISH_ARCHIVES_CONTACT", "me@example.org\r\nX-Evil: 1"),
        ("POLISH_ARCHIVES_CONTACT", "me (at) example"),
        ("POLISH_ARCHIVES_DOWNLOAD_DIR", "relative/path"),
        ("POLISH_ARCHIVES_DOWNLOAD_DIR", "/no/such/folder/anywhere"),
    ],
)
def test_an_unusable_setting_names_its_variable(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError, match=name):
        load_config()


async def test_a_bad_setting_surfaces_as_not_configured(monkeypatch):
    monkeypatch.setenv("POLISH_ARCHIVES_MIN_INTERVAL", "0.5")
    monkeypatch.setattr(server.runtime, "http", None)
    monkeypatch.setattr(server.runtime, "config", None)
    out = await call_tool("cache_status")
    assert out["error"] == "not_configured"
    assert "POLISH_ARCHIVES_MIN_INTERVAL" in out["message"]
