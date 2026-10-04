from pathlib import Path

import pytest

from meditations.config import initialize_workspace, load_workspace


def test_initialization_preserves_files_and_identity(tmp_path):
    workspace = tmp_path / "notes"
    workspace.mkdir()
    handwritten = workspace / "personal.md"
    handwritten.write_text("Keep my reflection.\n")
    config = initialize_workspace(workspace, "America/Sao_Paulo")
    assert initialize_workspace(workspace, "America/Sao_Paulo") == config
    assert load_workspace(workspace) == config
    assert handwritten.read_text() == "Keep my reflection.\n"
    for relative in ("profile", "engineering/daily", "engineering/reviews", "records"):
        assert (workspace / relative).is_dir()


def test_conflicting_initialization_does_not_reset_config(tmp_path):
    initialize_workspace(tmp_path, "UTC")
    before = (tmp_path / "workspace.json").read_bytes()
    with pytest.raises(ValueError):
        initialize_workspace(tmp_path, "Europe/London")
    assert (tmp_path / "workspace.json").read_bytes() == before


def test_invalid_timezone_creates_no_workspace(tmp_path):
    workspace = tmp_path / "missing"
    with pytest.raises(ValueError):
        initialize_workspace(workspace, "not/a-timezone")
    assert not workspace.exists()


@pytest.mark.parametrize("symlink", [False, True])
def test_checkout_workspace_is_rejected(tmp_path, symlink):
    checkout = Path(__file__).resolve().parents[1]
    target = checkout / "should-not-exist"
    path = target
    if symlink:
        alias = tmp_path / "checkout"
        alias.symlink_to(checkout, target_is_directory=True)
        path = alias / "should-not-exist"
    with pytest.raises(ValueError):
        initialize_workspace(path, "UTC")
    assert not target.exists()


def test_malformed_existing_config_is_not_overwritten(tmp_path):
    (tmp_path / "workspace.json").write_text('{"schema_version": 99}')
    with pytest.raises(ValueError):
        initialize_workspace(tmp_path, "UTC")
    assert (tmp_path / "workspace.json").read_text() == '{"schema_version": 99}'


def test_layout_symlink_does_not_write_outside_workspace(tmp_path):
    workspace = tmp_path / "notes"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "engineering").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError):
        initialize_workspace(workspace, "UTC")
    assert list(outside.iterdir()) == []
    assert not (workspace / "workspace.json").exists()


def test_invalid_layout_fails_before_configuration_write(tmp_path):
    (tmp_path / "engineering").write_text("User file.")
    with pytest.raises(ValueError):
        initialize_workspace(tmp_path, "UTC")
    assert not (tmp_path / "workspace.json").exists()
    assert not (tmp_path / "profile").exists()


def test_interrupted_config_write_can_be_retried(tmp_path, monkeypatch):
    from meditations import files

    def interrupt(*args):
        raise OSError("synthetic interrupted configuration write")

    with monkeypatch.context() as context:
        context.setattr(files.os, "replace", interrupt)
        with pytest.raises(OSError):
            initialize_workspace(tmp_path, "UTC")
    assert not (tmp_path / "workspace.json").exists()
    config = initialize_workspace(tmp_path, "UTC")
    assert load_workspace(tmp_path).workspace_id == config.workspace_id


def test_missing_persisted_identity_is_rejected(tmp_path):
    (tmp_path / "workspace.json").write_text('{"timezone": "UTC"}')
    with pytest.raises(ValueError):
        load_workspace(tmp_path)


def test_config_symbolic_link_is_rejected(tmp_path):
    workspace = tmp_path / "notes"
    outside = tmp_path / "outside"
    initialize_workspace(outside, "UTC")
    workspace.mkdir()
    (workspace / "workspace.json").symlink_to(outside / "workspace.json")
    with pytest.raises(ValueError):
        initialize_workspace(workspace, "UTC")


def test_wheel_module_location_still_rejects_checkout(tmp_path, monkeypatch):
    from meditations import config

    monkeypatch.setattr(config, "__file__", str(tmp_path / "lib/meditations/config.py"))
    checkout = Path(__file__).resolve().parents[1]
    target = checkout / "should-not-exist"
    with pytest.raises(ValueError):
        initialize_workspace(target, "UTC")
    assert not target.exists()
