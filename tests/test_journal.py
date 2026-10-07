from datetime import date, datetime, timedelta, timezone

import pytest

from meditations.extraction.contracts import SourceMessage
from meditations.journal import build_day_inputs
from meditations.sessions import DaySelection, SessionSelection


def source_message(identity: str, text: str, minute: int = 0) -> SourceMessage:
    return SourceMessage(
        message_id=identity,
        role="user",
        content=text,
        occurred_at=datetime(2026, 10, 6, 10, tzinfo=timezone.utc)
        + timedelta(minutes=minute),
        context_only=False,
        timestamp_basis="source",
    )


def test_chunks_chronologically_and_keeps_stable_ids_across_append_and_revision():
    first = SessionSelection(
        "session-a",
        "0.160.0",
        (source_message("m2", "second", 2), source_message("m1", "first", 1)),
        {},
    )
    selected = DaySelection((first,), ())

    original = build_day_inputs(selected, date(2026, 10, 6), 0)
    revised = build_day_inputs(
        DaySelection(
            (
                SessionSelection(
                    "session-a",
                    "0.160.0",
                    (*first.messages, source_message("m3", "third", 3)),
                    {},
                ),
            ),
            (),
        ),
        date(2026, 10, 6),
        1,
    )

    assert [message.message_id for message in original[0].units[0].messages] == [
        "m1",
        "m2",
    ]
    assert original[0].units[0].unit_id == revised[0].units[0].unit_id
    assert original[0].units[0].source_revision == 0
    assert revised[0].units[0].source_revision == 1
    assert revised[0].units[0].task_label == "Codex session"


def test_multiple_sessions_have_separate_inputs_and_empty_selection_stays_empty():
    one = SessionSelection("one", None, (source_message("a", "A"),), {})
    two = SessionSelection("two", None, (source_message("b", "B"),), {})

    result = build_day_inputs(DaySelection((two, one), ()), date(2026, 10, 6), 0)

    assert [item.source_session_id for item in result] == ["one", "two"]
    assert build_day_inputs(DaySelection((), ()), date(2026, 10, 6), 0) == []


def test_splits_at_existing_message_count_limit_without_loss():
    messages = tuple(source_message(f"m{i}", "x", i) for i in range(201))
    session = SessionSelection("many", None, messages, {})

    result = build_day_inputs(DaySelection((session,), ()), date(2026, 10, 6), 0)

    units = result[0].units
    assert [len(unit.messages) for unit in units] == [200, 1]
    assert [message.message_id for unit in units for message in unit.messages] == [
        f"m{i}" for i in range(201)
    ]


def test_rejects_message_larger_than_existing_unit_limit():
    session = SessionSelection("large", None, (source_message("m", "x" * 70_000),), {})

    with pytest.raises(ValueError, match="single message"):
        build_day_inputs(DaySelection((session,), ()), date(2026, 10, 6), 0)


def test_rejects_invalid_revision_and_empty_sessions_are_omitted():
    session = SessionSelection("empty", None, (), {})

    assert build_day_inputs(DaySelection((session,), ()), date(2026, 10, 6), 0) == []
    with pytest.raises(ValueError, match="revision"):
        build_day_inputs(DaySelection((), ()), date(2026, 10, 6), -1)
