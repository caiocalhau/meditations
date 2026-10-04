import pytest

from meditations import files
from meditations.render import update_daily_note


def test_reflection_survives_and_unchanged_render_does_not_write(tmp_path):
    path = tmp_path / "note.md"
    assert update_daily_note(path, "# Day\n") == "created"
    assert "Personal reflection: not provided." in path.read_text()
    with path.open("ab") as stream:
        stream.write(b"\r\nMy reflection stays exact.\r\n")
    assert update_daily_note(path, "# Changed day\n") == "updated"
    before = path.read_bytes()
    timestamp = path.stat().st_mtime_ns
    assert before.endswith(b"\r\nMy reflection stays exact.\r\n")
    assert update_daily_note(path, "# Changed day\n") == "unchanged"
    assert path.stat().st_mtime_ns == timestamp


@pytest.mark.parametrize(
    "text",
    [
        "Handwritten only.",
        "<!-- meditations:generated:end -->\n<!-- meditations:generated:start -->",
        "<!-- meditations:generated:start --> twice "
        "<!-- meditations:generated:start -->"
        "<!-- meditations:generated:end -->",
    ],
)
def test_invalid_generated_boundaries_preserve_file(tmp_path, text):
    path = tmp_path / "note.md"
    path.write_text(text)
    with pytest.raises(ValueError):
        update_daily_note(path, "replacement")
    assert path.read_text() == text


def test_failed_atomic_replace_preserves_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "note.md"
    update_daily_note(path, "old")
    before = path.read_bytes()

    def fail_replace(*args):
        raise OSError("synthetic disk failure")

    monkeypatch.setattr(files.os, "replace", fail_replace)
    with pytest.raises(OSError):
        update_daily_note(path, "new")
    assert path.read_bytes() == before
    assert list(tmp_path.glob(".meditations-*")) == []


def test_changed_input_is_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "note.md"
    update_daily_note(path, "old")
    real_fsync = files.os.fsync

    def edit_during_write(descriptor):
        path.write_text("Concurrent handwritten edit.")
        real_fsync(descriptor)

    monkeypatch.setattr(files.os, "fsync", edit_during_write)
    with pytest.raises(ValueError):
        update_daily_note(path, "new")
    assert path.read_text() == "Concurrent handwritten edit."


def test_symbolic_link_note_is_not_replaced(tmp_path):
    target = tmp_path / "user.md"
    target.write_text("User text.")
    link = tmp_path / "daily.md"
    link.symlink_to(target)
    with pytest.raises(ValueError):
        update_daily_note(link, "new")
    assert target.read_text() == "User text."
