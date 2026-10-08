import pytest

from meditations.files import atomic_write, workspace_directory, workspace_lock


def test_atomic_write_creates_and_compare_replaces_file(tmp_path):
    path = tmp_path / "vault/daily.md"
    atomic_write(path, b"first", expected=None)
    before = path.read_bytes()

    atomic_write(path, b"second", expected=before)

    assert path.read_bytes() == b"second"
    assert list(path.parent.glob(".meditations-*")) == []


def test_atomic_write_preserves_changed_content_and_cleans_temporary(tmp_path):
    path = tmp_path / "daily.md"
    path.write_bytes(b"newer user edit")

    with pytest.raises(ValueError, match="changed"):
        atomic_write(path, b"replace", expected=b"older")

    assert path.read_bytes() == b"newer user edit"
    assert list(tmp_path.glob(".meditations-*")) == []


def test_atomic_write_rejects_symlink_target(tmp_path):
    target = tmp_path / "user.md"
    target.write_text("keep")
    link = tmp_path / "daily.md"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="symbolic link"):
        atomic_write(link, b"replace", expected=b"keep")

    assert target.read_text() == "keep"


def test_workspace_directory_rejects_path_escape(tmp_path):
    workspace = tmp_path / "vault"
    workspace.mkdir()

    with pytest.raises(ValueError, match="outside"):
        workspace_directory(workspace, "../outside")


def test_workspace_lock_creates_machine_private_lock_directory(tmp_path):
    path = tmp_path / "vault"
    path.mkdir()
    with workspace_lock(path):
        assert path.is_dir()
    with workspace_lock(path):
        assert path.is_dir()
