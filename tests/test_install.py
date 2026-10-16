import runpy
from pathlib import Path

import pytest


def installer():
    return runpy.run_path(str(Path(__file__).parents[1] / "scripts/install.py"))


def test_setup_refuses_conflicting_command_before_changing_environment(tmp_path):
    module = installer()
    home = tmp_path / "home"
    command = home / ".local/bin/meditations"
    command.parent.mkdir(parents=True)
    command.write_text("another application")

    with pytest.raises(ValueError, match="already exists"):
        module["install"](tmp_path / "repo", home, None, None, None)

    assert command.read_text() == "another application"
    assert not (home / ".local/share/meditations").exists()


def test_setup_links_are_repeatable_and_preserve_other_skills(tmp_path):
    module = installer()
    repo = tmp_path / "checkout with spaces"
    home = tmp_path / "home"
    for name in ("take-note", "update-journal", "weekly-review"):
        (repo / "skills" / name).mkdir(parents=True)
    other = home / ".agents/skills/other/SKILL.md"
    other.parent.mkdir(parents=True)
    other.write_text("existing skill")

    module["ensure_links"](repo, home)
    module["ensure_links"](repo, home)

    assert other.read_text() == "existing skill"
    for name in ("take-note", "update-journal", "weekly-review"):
        link = home / ".agents/skills" / f"meditations-{name}"
        assert link.is_symlink()
        assert link.resolve() == repo / "skills" / name


@pytest.mark.parametrize(
    ("platform", "config_root"),
    [("linux", ".config"), ("darwin", "Library/Application Support")],
)
def test_setup_reuses_local_settings_without_prompt_or_rewrite(
    tmp_path, monkeypatch, platform, config_root
):
    import json

    module = installer()
    home = tmp_path / "home"
    vault = tmp_path / "private vault"
    vault.mkdir()
    config = home / config_root / "meditations/config.json"
    config.parent.mkdir(parents=True)
    content = json.dumps(
        {
            "schema_version": 2,
            "workspace": str(vault),
            "timezone": "America/Sao_Paulo",
            "language": "pt-BR",
        }
    )
    config.write_text(content)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("sys.platform", platform)

    assert module["choose_settings"](home, None, None, None) is None
    assert config.read_text() == content


def test_setup_refuses_missing_vault_before_creating_environment(tmp_path):
    module = installer()
    home = tmp_path / "home"

    with pytest.raises(ValueError, match="must already exist"):
        module["install"](tmp_path / "repo", home, tmp_path / "missing", "UTC", "en")

    assert not (home / ".local/share/meditations").exists()


@pytest.mark.parametrize(
    ("timezone", "language"), [(None, None), ("UTC", None), (None, "en")]
)
def test_setup_requires_explicit_preferences_when_reconfiguring_vault(
    tmp_path, timezone, language
):
    module = installer()
    vault = tmp_path / "vault"
    vault.mkdir()

    with pytest.raises(ValueError, match="--timezone and --language"):
        module["choose_settings"](tmp_path / "home", vault, timezone, language)


@pytest.mark.parametrize("english", [True, False])
def test_setup_preserves_saved_english_preference(tmp_path, monkeypatch, english):
    import json

    module = installer()
    home = tmp_path / "home"
    vault = tmp_path / "vault"
    vault.mkdir()
    config = home / ".config/meditations/config.json"
    config.parent.mkdir(parents=True)
    content = json.dumps(
        {
            "schema_version": 2,
            "workspace": str(vault),
            "timezone": "UTC",
            "language": "en",
            "english_feedback": english,
        }
    )
    config.write_text(content)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr("sys.platform", "linux")
    assert module["choose_settings"](home, None, None, None) is None
    assert config.read_text() == content


def test_first_interactive_setup_offers_english_feedback(tmp_path, monkeypatch):
    module = installer()
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    answers = iter([str(vault), "UTC", "pt-BR", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert module["choose_settings"](tmp_path / "home", None, None, None) == (
        vault,
        "UTC",
        "pt-BR",
        True,
    )
