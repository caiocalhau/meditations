from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "value",
    [
        '"synthetic-default" # comment',
        "'synthetic-default'",
        '"synthetic-\\u0064efault"',
    ],
)
def test_reads_global_model_using_toml_syntax(tmp_path, monkeypatch, value):
    from meditations.codex_config import resolve_model

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text(
        f'model = {value}\n[mcp_servers.unrelated]\ncommand = "do-not-execute"\n'
    )
    before = (tmp_path / "config.toml").read_bytes()
    assert resolve_model(None) == "synthetic-default"
    assert (tmp_path / "config.toml").read_bytes() == before


def test_explicit_model_overrides_invalid_global_configuration(tmp_path, monkeypatch):
    from meditations.codex_config import resolve_model

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    (tmp_path / "config.toml").write_text("invalid toml private-value")
    assert resolve_model("synthetic-override") == "synthetic-override"


@pytest.mark.parametrize(
    "content",
    [
        None,
        "model = ''",
        "model = 4",
        "[other]\nmodel = 'nested'",
        "private-value invalid toml",
    ],
)
def test_missing_or_invalid_model_has_actionable_error_without_config_dump(
    tmp_path, monkeypatch, content
):
    from meditations.codex_config import resolve_model

    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    if content is not None:
        (tmp_path / "config.toml").write_text(content)
    with pytest.raises(ValueError) as error:
        resolve_model(None)
    assert "--model" in str(error.value)
    assert "private-value" not in str(error.value)


def test_default_codex_home_is_respected(tmp_path, monkeypatch):
    from meditations.codex_config import resolve_model

    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    directory = tmp_path / ".codex"
    directory.mkdir()
    (directory / "config.toml").write_text('model = "synthetic-default"')
    assert resolve_model(None) == "synthetic-default"
