import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from meditations.machine_config import (
    configure,
    default_config_path,
    resolve_work_date,
    resolve_workspace,
)


def test_machine_config_paths_follow_linux_xdg_and_macos_conventions(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert default_config_path("linux") == tmp_path / "xdg/meditations/config.json"
    assert default_config_path("darwin") == (
        tmp_path / "home/Library/Application Support/meditations/config.json"
    )


def test_configure_and_resolve_workspace_with_timezone_and_language(tmp_path):
    vault = tmp_path / "private notes"
    vault.mkdir()
    settings = tmp_path / "settings" / "config.json"

    config = configure(
        vault, timezone="America/Sao_Paulo", language="en", path=settings
    )

    assert config.workspace == vault.resolve()
    assert json.loads(settings.read_text())["timezone"] == "America/Sao_Paulo"
    assert resolve_workspace(path=settings) == vault.resolve()


def test_unconfigured_workspace_fails_without_current_directory_fallback(tmp_path):
    with pytest.raises(ValueError, match="meditations configure"):
        resolve_workspace(path=tmp_path / "missing.json")


def test_configure_rejects_repo_and_invalid_timezone(tmp_path):
    with pytest.raises(ValueError, match="outside"):
        configure(
            Path(__file__).resolve().parents[1],
            timezone="UTC",
            language="en",
            path=tmp_path / "x.json",
        )
    vault = tmp_path / "vault"
    vault.mkdir()
    with pytest.raises(ValueError, match="timezone"):
        configure(
            vault, timezone="Mars/Olympus", language="en", path=tmp_path / "x.json"
        )


def test_work_date_uses_configured_zone_and_explicit_date_wins(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    config = configure(
        vault, timezone="America/Sao_Paulo", language="en", path=tmp_path / "x.json"
    )
    now = datetime(2026, 10, 8, 2, 0, tzinfo=timezone.utc)

    assert resolve_work_date(config, None, now=now) == date(2026, 10, 7)
    assert resolve_work_date(config, date(2026, 10, 6), now=now) == date(2026, 10, 6)
