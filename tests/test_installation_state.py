from pathlib import Path

import pytest

from meditations.extraction.service import default_state_directory, installation_id


@pytest.mark.parametrize(
    "platform,configured,expected",
    [
        ("linux", False, ".local/state/meditations"),
        ("linux", True, "configured-state/meditations"),
        ("darwin", False, "Library/Application Support/meditations"),
        ("darwin", True, "Library/Application Support/meditations"),
    ],
)
def test_state_directory_respects_platform_and_xdg(
    tmp_path, monkeypatch, platform, configured, expected
):
    user_directory = tmp_path / "user"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_directory))
    if configured:
        monkeypatch.setenv("XDG_STATE_HOME", str(user_directory / "configured-state"))
    else:
        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert default_state_directory(platform) == user_directory / expected
    assert not user_directory.exists()


def test_default_installation_identity_is_reused(tmp_path, monkeypatch):
    from meditations.extraction import service

    directory = tmp_path / "machine-state"
    monkeypatch.setattr(service, "default_state_directory", lambda platform: directory)
    identity = installation_id()
    assert installation_id() == identity
    assert (directory / "installation.json").is_file()
