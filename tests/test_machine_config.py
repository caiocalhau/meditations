import json
from pathlib import Path

import pytest

from meditations.cli import main
from meditations.config import initialize_workspace


def preview_args(sessions: Path, *options: str) -> list[str]:
    return [
        "journal",
        "--date",
        "2026-10-06",
        "--dry-run",
        "--json",
        "--sessions-dir",
        str(sessions),
        *options,
    ]


def test_configure_once_then_use_default_from_another_directory(
    tmp_path, capsys, monkeypatch
):
    vault = tmp_path / "notes"
    initialize_workspace(vault, "UTC")
    config = tmp_path / "machine" / "config.json"
    before = {path: path.read_bytes() for path in vault.rglob("*") if path.is_file()}
    monkeypatch.chdir(tmp_path)
    assert main(["configure", "--workspace", "notes"], machine_config_path=config) == 0
    assert "default workspace" in capsys.readouterr().out.lower()
    another_directory = tmp_path / "another-project"
    another_directory.mkdir()
    monkeypatch.chdir(another_directory)
    assert main(preview_args(tmp_path / "sessions"), machine_config_path=config) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["timezone"] == "UTC"
    assert output["workspace_writes"] == 0
    assert before == {
        path: path.read_bytes() for path in vault.rglob("*") if path.is_file()
    }
    assert config.is_file()


def test_explicit_workspace_overrides_default_without_changing_it(tmp_path, capsys):
    default = tmp_path / "default"
    override = tmp_path / "override"
    initialize_workspace(default, "UTC")
    initialize_workspace(override, "America/Sao_Paulo")
    config = tmp_path / "machine" / "config.json"
    assert (
        main(["configure", "--workspace", str(default)], machine_config_path=config)
        == 0
    )
    capsys.readouterr()
    before = config.read_bytes()
    assert (
        main(
            preview_args(tmp_path / "sessions", "--workspace", str(override)),
            machine_config_path=config,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["timezone"] == "America/Sao_Paulo"
    assert main(preview_args(tmp_path / "sessions"), machine_config_path=config) == 0
    assert json.loads(capsys.readouterr().out)["timezone"] == "UTC"
    assert config.read_bytes() == before


def test_unconfigured_machine_has_actionable_error_without_writes(tmp_path, capsys):
    config = tmp_path / "machine" / "config.json"
    assert main(["status"], machine_config_path=config) == 1
    assert "configure --workspace" in capsys.readouterr().err
    assert not config.parent.exists()


def test_invalid_workspace_does_not_replace_default(tmp_path, capsys):
    vault = tmp_path / "notes"
    initialize_workspace(vault, "UTC")
    config = tmp_path / "machine" / "config.json"
    assert (
        main(["configure", "--workspace", str(vault)], machine_config_path=config) == 0
    )
    capsys.readouterr()
    before = config.read_bytes()
    missing = tmp_path / "missing"
    assert (
        main(["configure", "--workspace", str(missing)], machine_config_path=config)
        == 1
    )
    capsys.readouterr()
    assert config.read_bytes() == before
    assert not missing.exists()


def test_invalid_machine_config_is_preserved_and_override_still_works(tmp_path, capsys):
    vault = tmp_path / "notes"
    initialize_workspace(vault, "UTC")
    config = tmp_path / "config.json"
    config.write_text('{"schema_version":999,"workspace":"private-value"}')
    before = config.read_bytes()
    assert main(["status"], machine_config_path=config) == 1
    error = capsys.readouterr().err
    assert "configuration" in error
    assert "private-value" not in error
    assert main(["status", "--workspace", str(vault)], machine_config_path=config) == 0
    capsys.readouterr()
    assert config.read_bytes() == before


def test_configure_requires_at_least_one_setting(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        main(["configure"], machine_config_path=tmp_path / "config.json")
    assert error.value.code == 2
    assert "--workspace" in capsys.readouterr().err


@pytest.mark.parametrize(
    "platform,xdg,expected",
    [
        ("linux", False, ".config/meditations/config.json"),
        ("linux", True, "custom-config/meditations/config.json"),
        ("darwin", False, "Library/Application Support/meditations/config.json"),
        ("darwin", True, "Library/Application Support/meditations/config.json"),
    ],
)
def test_machine_config_location_is_platform_specific(
    tmp_path, monkeypatch, platform, xdg, expected
):
    from meditations.machine_config import default_config_path

    user_directory = tmp_path / "user"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_directory))
    if xdg:
        monkeypatch.setenv("XDG_CONFIG_HOME", str(user_directory / "custom-config"))
    else:
        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert default_config_path(platform) == user_directory / expected
    assert not user_directory.exists()


def test_reconfiguring_changes_default_without_changing_either_vault(tmp_path, capsys):
    config = tmp_path / "machine" / "config.json"
    first = tmp_path / "first"
    second = tmp_path / "second"
    initialize_workspace(first, "UTC")
    initialize_workspace(second, "America/Sao_Paulo")
    for vault in (first, second):
        before = (vault / "workspace.json").read_bytes()
        assert (
            main(["configure", "--workspace", str(vault)], machine_config_path=config)
            == 0
        )
        capsys.readouterr()
        assert (vault / "workspace.json").read_bytes() == before
    assert main(preview_args(tmp_path / "sessions"), machine_config_path=config) == 0
    assert json.loads(capsys.readouterr().out)["timezone"] == "America/Sao_Paulo"


def test_missing_configured_vault_fails_without_recreating_it(tmp_path, capsys):
    vault = tmp_path / "missing"
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"schema_version": 1, "workspace": str(vault)}))
    assert main(["status"], machine_config_path=config) == 1
    assert "Configured workspace" in capsys.readouterr().err
    assert not vault.exists()


def test_symbolic_link_machine_config_is_not_read_or_replaced(tmp_path, capsys):
    vault = tmp_path / "notes"
    initialize_workspace(vault, "UTC")
    target = tmp_path / "target.json"
    target.write_text(json.dumps({"schema_version": 1, "workspace": str(vault)}))
    before = target.read_bytes()
    config = tmp_path / "config.json"
    config.symlink_to(target)
    assert main(["status"], machine_config_path=config) == 1
    assert "symbolic-link" in capsys.readouterr().err
    assert (
        main(["configure", "--workspace", str(vault)], machine_config_path=config) == 1
    )
    assert "symbolic-link" in capsys.readouterr().err
    assert target.read_bytes() == before
    assert config.is_symlink()


def test_configure_approval_only_preserves_workspace_and_accepts_future_record(
    tmp_path, capsys
):
    vault = tmp_path / "notes"
    initialize_workspace(vault, "UTC")
    config = tmp_path / "machine" / "config.json"
    assert (
        main(["configure", "--workspace", str(vault)], machine_config_path=config) == 0
    )
    capsys.readouterr()
    approval = tmp_path / "runtime-approval.json"
    assert (
        main(
            ["configure", "--runtime-approval", str(approval)],
            machine_config_path=config,
        )
        == 0
    )
    capsys.readouterr()
    assert json.loads(config.read_text())["workspace"] == str(vault)
    assert json.loads(config.read_text())["runtime_approval"] == str(approval)
    assert not approval.exists()
    second = tmp_path / "other-notes"
    initialize_workspace(second, "UTC")
    assert (
        main(["configure", "--workspace", str(second)], machine_config_path=config) == 0
    )
    capsys.readouterr()
    assert json.loads(config.read_text())["runtime_approval"] == str(approval)


def test_approval_only_configuration_requires_existing_workspace(tmp_path, capsys):
    config = tmp_path / "machine" / "config.json"
    assert (
        main(
            ["configure", "--runtime-approval", str(tmp_path / "approval.json")],
            machine_config_path=config,
        )
        == 1
    )
    assert "--workspace" in capsys.readouterr().err
    assert not config.exists()


def test_saved_approval_is_checked_on_every_journal_run_and_override_wins(
    tmp_path, capsys
):
    vault = tmp_path / "notes"
    initialize_workspace(vault, "UTC")
    config = tmp_path / "machine" / "config.json"
    approval = tmp_path / "approval.json"
    approval.write_text("{}")
    assert (
        main(
            [
                "configure",
                "--workspace",
                str(vault),
                "--runtime-approval",
                str(approval),
            ],
            machine_config_path=config,
        )
        == 0
    )
    capsys.readouterr()
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    entries = [
        {"type": "session_meta", "payload": {"id": "test", "cwd": str(tmp_path)}},
        {
            "timestamp": "2026-10-06T12:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Test reasoning."}],
            },
        },
    ]
    (sessions / "rollout-test.jsonl").write_text(
        "\n".join(json.dumps(entry) for entry in entries) + "\n"
    )
    args = [
        "journal",
        "--date",
        "2026-10-06",
        "--sessions-dir",
        str(sessions),
        "--model",
        "test-model",
    ]
    assert main(args, machine_config_path=config) == 1
    assert "Invalid runtime approval file" in capsys.readouterr().err
    approval.unlink()
    assert main(args, machine_config_path=config) == 1
    assert "No such file" in capsys.readouterr().err
    override = tmp_path / "override.json"
    override.write_text("{}")
    before = config.read_bytes()
    assert (
        main([*args, "--runtime-approval", str(override)], machine_config_path=config)
        == 1
    )
    assert "Invalid runtime approval file" in capsys.readouterr().err
    assert config.read_bytes() == before
    assert not list(vault.rglob("*.md"))


def test_configure_workspace_repairs_invalid_settings(tmp_path, capsys):
    vault = tmp_path / "notes"
    initialize_workspace(vault, "UTC")
    config = tmp_path / "config.json"
    config.write_text("invalid json")
    assert (
        main(["configure", "--workspace", str(vault)], machine_config_path=config) == 0
    )
    capsys.readouterr()
    assert main(["status"], machine_config_path=config) == 0


def test_extract_uses_saved_approval_but_dry_run_does_not_validate_it(tmp_path, capsys):
    vault = tmp_path / "notes"
    initialize_workspace(vault, "UTC")
    config = tmp_path / "config.json"
    approval = tmp_path / "approval.json"
    approval.write_text("{}")
    assert (
        main(
            [
                "configure",
                "--workspace",
                str(vault),
                "--runtime-approval",
                str(approval),
            ],
            machine_config_path=config,
        )
        == 0
    )
    capsys.readouterr()
    source = Path(__file__).parent / "fixtures/extraction/conversation.json"
    args = ["extract", "--input", str(source), "--model", "test-model"]
    assert main(args, machine_config_path=config) == 1
    assert "Invalid runtime approval file" in capsys.readouterr().err
    assert main([*args, "--dry-run"], machine_config_path=config) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "preview"
    assert not list(vault.rglob("*.md"))
