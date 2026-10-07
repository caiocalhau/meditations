from datetime import date, datetime, timezone
from pathlib import Path

from meditations.captures import prepare_day, save_capture
from meditations.contracts import (
    CaptureDraft,
    DailyDraft,
    JournalTopic,
    LearningItem,
)
from meditations.machine_config import configure
from meditations.render import write_daily


def setup_vault(tmp_path: Path):
    vault = tmp_path / "private"
    vault.mkdir()
    config = configure(
        vault,
        timezone="America/Sao_Paulo",
        language="en",
        path=tmp_path / "settings.json",
    )
    return config, vault


def add_capture(config, day, body, hour=13):
    return save_capture(
        config.workspace,
        day,
        CaptureDraft(body=body),
        captured_at=datetime(2026, 10, 7, hour, tzinfo=timezone.utc),
    )


def make_draft(prepared):
    return DailyDraft(
        source_snapshot=prepared.source_snapshot,
        expected_note_sha256=prepared.expected_note_sha256,
        overview=["The design changed and the test passed."],
        topics=[
            JournalTopic(
                title="Daily capture",
                paragraphs=[
                    "The earlier concern remains visible alongside the resolution."
                ],
            )
        ],
        open_items=[],
        learning=[],
        reflection_questions=["What evidence supports the result?"],
    )


def test_day_preparation_is_read_only_then_write_preserves_personal_reflection(
    tmp_path,
):
    config, vault = setup_vault(tmp_path)
    day = date(2026, 10, 7)
    add_capture(config, day, "The bug occurred.", hour=12)
    add_capture(config, day, "The regression test now passes.", hour=13)

    prepared = prepare_day(config, day)
    assert prepared.status == "ready"
    assert [item.body for item in prepared.captures] == [
        "The bug occurred.",
        "The regression test now passes.",
    ]
    assert not (vault / "engineering/daily/2026-10-07.md").exists()

    written = write_daily(config, day, make_draft(prepared))
    target = vault / "engineering/daily/2026-10-07.md"
    assert written.status == "created"
    content = target.read_text()
    assert "## The day at a glance" in content
    assert "## Work and outcomes" in content
    assert "### Daily capture\n\nThe earlier concern remains visible" in content
    assert "## Questions for my reflection" in content
    assert "## My reflection\n\nPersonal reflection: not provided." in content

    content = content.replace(
        "Personal reflection: not provided.", "My handwritten reflection."
    )
    target.write_text(content)
    add_capture(config, day, "A later checkpoint added another decision.")
    prepared = prepare_day(config, day)
    assert prepared.status == "ready"
    assert write_daily(config, day, make_draft(prepared)).status == "updated"
    assert target.read_text().endswith(
        "## My reflection\n\nMy handwritten reflection.\n"
    )


def test_unchanged_day_stops_before_composition_and_empty_day_does_not_write(tmp_path):
    config, vault = setup_vault(tmp_path)
    day = date(2026, 10, 7)
    assert prepare_day(config, day).status == "empty"
    add_capture(config, day, "A decision was made.")
    prepared = prepare_day(config, day)
    assert write_daily(config, day, make_draft(prepared)).status == "created"
    assert prepare_day(config, day).status == "unchanged"
    assert not (vault / "engineering/daily/2026-10-07.md").is_symlink()


def test_daily_write_refuses_stale_capture_snapshot_or_modified_note(tmp_path):
    config, vault = setup_vault(tmp_path)
    day = date(2026, 10, 7)
    add_capture(config, day, "Initial decision.")
    prepared = prepare_day(config, day)
    add_capture(config, day, "New result after preparation.")

    result = write_daily(config, day, make_draft(prepared))

    assert result.status == "conflict"
    assert not (vault / "engineering/daily/2026-10-07.md").exists()


def test_daily_prepare_reports_malformed_markers_before_composition(tmp_path):
    config, vault = setup_vault(tmp_path)
    day = date(2026, 10, 7)
    add_capture(config, day, "The work was reviewed.")
    target = vault / "engineering/daily/2026-10-07.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "<!-- meditations:generated:end -->\n<!-- meditations:generated:start -->\n"
    )

    prepared = prepare_day(config, day)

    assert prepared.status == "conflict"
    assert not prepared.captures


def test_previous_link_uses_latest_prior_iso_date(tmp_path):
    config, vault = setup_vault(tmp_path)
    daily = vault / "engineering/daily"
    daily.mkdir(parents=True)
    (daily / "2026-10-03.md").write_text("old")
    (daily / "2026-10-06.md").write_text("recent")
    (daily / "2026-10-08.md").write_text("future")
    day = date(2026, 10, 7)
    add_capture(config, day, "Work on today's task.")

    prepared = prepare_day(config, day)

    assert prepared.previous_note == "[[2026-10-06]]"


def test_learning_links_must_be_public_and_present_in_saved_capture(tmp_path):
    config, _ = setup_vault(tmp_path)
    day = date(2026, 10, 7)
    add_capture(config, day, "Reference: https://docs.python.org/3/library/")
    prepared = prepare_day(config, day)
    valid = make_draft(prepared).model_copy(
        update={
            "learning": [
                LearningItem(
                    concept="Python documentation",
                    explanation="The reference explains the standard library.",
                    suggested_practice="Read the module documentation.",
                    resource_urls=["https://docs.python.org/3/library/"],
                )
            ]
        }
    )
    assert write_daily(config, day, valid).status == "created"

    add_capture(config, day, "An unrelated resource was proposed.")
    refreshed = prepare_day(config, day)
    unsupported = make_draft(refreshed).model_copy(
        update={
            "learning": [
                LearningItem(
                    concept="Unverified source",
                    explanation="This source was not included in the capture.",
                    suggested_practice="Check the source manually.",
                    resource_urls=["https://example.org/unsupported"],
                )
            ]
        }
    )
    result = write_daily(config, day, unsupported)

    assert result.status == "conflict"
    assert "Learning resource is not a public URL found in a saved capture" in (
        result.message or ""
    )
