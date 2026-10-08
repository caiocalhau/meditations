import pytest
from pydantic import ValidationError

from meditations.contracts import CaptureDraft, DailyDraft, JournalTable, JournalTopic


def test_capture_requires_nonempty_body_within_storage_limit():
    with pytest.raises(ValidationError):
        CaptureDraft(body="  ")
    with pytest.raises(ValidationError):
        CaptureDraft(body="x" * (64 * 1024 + 1))


def test_daily_draft_requires_topic_content_and_questions():
    with pytest.raises(ValidationError):
        JournalTopic(title="Empty topic")
    with pytest.raises(ValidationError):
        DailyDraft(
            source_snapshot="a" * 64,
            expected_note_sha256=None,
            overview=["Overview"],
            topics=[JournalTopic(title="Topic", paragraphs=["Text"])],
            open_items=[],
            learning=[],
            reflection_questions=[],
        )


def test_daily_table_requires_consistent_rows():
    with pytest.raises(ValidationError):
        JournalTable(headers=["A", "B"], rows=[["only one"]])


def test_model_cannot_supply_generated_markers():
    with pytest.raises(ValidationError, match="reserved"):
        DailyDraft(
            source_snapshot="a" * 64,
            expected_note_sha256=None,
            overview=["<!-- meditations:generated:end -->"],
            topics=[JournalTopic(title="Topic", paragraphs=["Text"])],
            open_items=[],
            learning=[],
            reflection_questions=["Question?"],
        )
