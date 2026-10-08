from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from meditations.captures import load_captures, save_capture
from meditations.contracts import CaptureDraft
from meditations.machine_config import configure


def configured(tmp_path: Path):
    vault = tmp_path / "private vault"
    vault.mkdir(parents=True)
    return configure(
        vault,
        timezone="America/Sao_Paulo",
        language="en",
        path=tmp_path / "settings.json",
    )


def test_capture_is_readable_and_exact_repeat_is_unchanged(tmp_path):
    config = configured(tmp_path)
    day = date(2026, 10, 7)
    body = "## Database migration\n\nThe rollback test remains open.\n"

    first = save_capture(
        config.workspace,
        day,
        CaptureDraft(body=body),
        captured_at=datetime(2026, 10, 7, 12, tzinfo=timezone.utc),
    )
    second = save_capture(
        config.workspace,
        day,
        CaptureDraft(body=body),
        captured_at=datetime(2026, 10, 7, 13, tzinfo=timezone.utc),
    )

    assert first.status == "created"
    assert second.status == "unchanged"
    assert Path(first.path).read_text().endswith(body)
    assert [source.body for source in load_captures(config.workspace, day)] == [
        body.strip()
    ]


def test_distinct_later_checkpoint_and_explicit_old_date_accumulate(tmp_path):
    config = configured(tmp_path)
    day = date(2026, 10, 6)
    captured_at = datetime(2026, 10, 7, 1, tzinfo=timezone.utc)

    save_capture(
        config.workspace,
        day,
        CaptureDraft(body="Problem found."),
        captured_at=captured_at,
    )
    save_capture(
        config.workspace,
        day,
        CaptureDraft(body="Rollback test passed."),
        captured_at=captured_at,
    )

    assert [item.body for item in load_captures(config.workspace, day)] == [
        "Problem found.",
        "Rollback test passed.",
    ]
    assert not list((config.workspace / "engineering/captures/2026-10-07").glob("*.md"))


def test_identical_capture_synced_from_another_machine_has_no_git_path_conflict(
    tmp_path,
):
    first = configured(tmp_path / "first")
    second = configured(tmp_path / "second")
    day = date(2026, 10, 7)
    body = "Same capture from a resumed session."
    first_result = save_capture(
        first.workspace,
        day,
        CaptureDraft(body=body),
        captured_at=datetime(2026, 10, 7, 12, tzinfo=timezone.utc),
    )
    second_result = save_capture(
        second.workspace,
        day,
        CaptureDraft(body=body),
        captured_at=datetime(2026, 10, 7, 15, tzinfo=timezone.utc),
    )

    destination = second.workspace / "engineering/captures/2026-10-07"
    copied = destination / Path(first_result.path).name
    copied.write_bytes(Path(first_result.path).read_bytes())

    assert copied != Path(second_result.path)
    assert len(load_captures(second.workspace, day)) == 1
    assert load_captures(second.workspace, day)[0].captured_at.hour == 12


def test_invalid_or_tampered_capture_is_rejected_without_partial_results(tmp_path):
    config = configured(tmp_path)
    day = date(2026, 10, 7)
    result = save_capture(
        config.workspace,
        day,
        CaptureDraft(body="Original."),
        captured_at=datetime.now(timezone.utc),
    )
    Path(result.path).write_text(
        Path(result.path).read_text().replace("Original.", "Changed.")
    )

    with pytest.raises(ValueError, match="[Cc]apture"):
        load_captures(config.workspace, day)


def test_capture_path_refuses_symlink_directory(tmp_path):
    config = configured(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    captures = config.workspace / "engineering/captures"
    captures.parent.mkdir(parents=True)
    captures.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="outside"):
        save_capture(
            config.workspace,
            date(2026, 10, 7),
            CaptureDraft(body="Text"),
            captured_at=datetime.now(timezone.utc),
        )
