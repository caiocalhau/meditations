from datetime import date, datetime, timezone
from uuid import uuid4

from meditations.config import load_workspace
from meditations.records import EvidenceRecord
from meditations.render import render_daily, task_anchor


def test_multi_task_note_keeps_attribution_and_detail(workspace, record_data):
    first = EvidenceRecord.model_validate(record_data)
    second = EvidenceRecord.model_validate(
        record_data
        | {
            "record_id": uuid4(),
            "source_segment_id": "segment-2",
            "task_id": "tests",
            "task_label": "Test diagnosis",
            "attribution": "agent explanation",
            "summary": "Agent explained fixtures.",
        }
    )
    note = render_daily([second, first], load_workspace(workspace), date(2026, 10, 3))
    assert "Database migration" in note and "Test diagnosis" in note
    assert "user contribution" in note and "agent explanation" in note
    assert "Older clients need compatible writes." in note
    assert "Rollback was not demonstrated." in note
    assert "<details>" in note and str(first.record_id) in note
    assert note == render_daily(
        [first, second], load_workspace(workspace), date(2026, 10, 3)
    )


def test_timezone_midnight_and_cross_date_links(workspace, record_data):
    earlier = EvidenceRecord.model_validate(
        record_data
        | {
            "occurred_at": datetime(2026, 10, 4, 2, 59, tzinfo=timezone.utc),
            "summary": "Before local midnight.",
        }
    )
    later = EvidenceRecord.model_validate(
        record_data
        | {
            "record_id": uuid4(),
            "source_segment_id": "segment-2",
            "occurred_at": datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc),
            "summary": "After local midnight.",
        }
    )
    records = [earlier, later]
    note = render_daily(records, load_workspace(workspace), date(2026, 10, 3))
    assert "Before local midnight." in note
    assert "After local midnight." not in note
    assert f"2026-10-04.md#{task_anchor('migration')}" in note


def test_only_latest_source_revision_contributes(workspace, record_data):
    records = [
        EvidenceRecord.model_validate(record_data),
        EvidenceRecord.model_validate(
            record_data
            | {
                "record_id": uuid4(),
                "source_revision": 1,
                "summary": "Corrected summary.",
            }
        ),
    ]
    note = render_daily(records, load_workspace(workspace), date(2026, 10, 3))
    assert "Corrected summary." in note
    assert "Identified a compatibility concern." not in note


def test_content_cannot_inject_generated_markers_or_html(workspace, record_data):
    record = EvidenceRecord.model_validate(
        record_data
        | {"summary": "<!-- meditations:generated:end --> <script>bad()</script>"}
    )
    note = render_daily([record], load_workspace(workspace), date(2026, 10, 3))
    assert "<!-- meditations:generated:end -->" not in note
    assert "<script>" not in note
