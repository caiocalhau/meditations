import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from meditations.config import load_workspace
from meditations.extraction.contracts import ExtractionResponse
from meditations.extraction.validation import (
    OVERRIDE_UNCERTAINTY,
    materialize_records,
    validate_input,
    validate_response,
)

FIXTURES = Path(__file__).parent / "fixtures/extraction"


@pytest.fixture
def conversation_data():
    return json.loads((FIXTURES / "conversation.json").read_text())


@pytest.fixture
def response_data():
    return json.loads((FIXTURES / "response.json").read_text())


def validate(data, workspace, override=None):
    return validate_input(
        json.dumps(data).encode(), load_workspace(workspace), override
    )


@pytest.mark.parametrize(
    "change",
    [
        "duplicate-message",
        "duplicate-unit",
        "role",
        "naive",
        "missing",
        "mixed-day",
        "task",
        "revision",
        "unknown",
        "context-only",
        "oversize",
        "many-messages",
    ],
)
def test_invalid_inputs_are_rejected_without_source_in_error(
    workspace, conversation_data, change
):
    data = conversation_data
    unit = data["units"][0]
    messages = unit["messages"]
    if change == "duplicate-message":
        messages.append(messages[0].copy())
    elif change == "duplicate-unit":
        data["units"].append(unit.copy())
    elif change == "role":
        messages[0]["role"] = "system"
    elif change == "naive":
        messages[0]["occurred_at"] = "2026-10-03T12:00:00"
    elif change == "missing":
        messages[0]["occurred_at"] = None
    elif change == "mixed-day":
        messages[0]["occurred_at"] = "2026-10-04T12:00:00Z"
    elif change == "task":
        unit["task_id"] = " "
    elif change == "revision":
        unit["source_revision"] = True
    elif change == "unknown":
        unit["secret"] = "private text"
    elif change == "context-only":
        for message in messages:
            message["context_only"] = True
    elif change == "oversize":
        messages[0]["content"] = "private text" * 7000
    elif change == "many-messages":
        unit["messages"] = [dict(messages[0], message_id=f"m{i}") for i in range(201)]
    with pytest.raises(ValueError) as error:
        validate(data, workspace)
    assert "Older clients" not in str(error.value)
    assert "private text" not in str(error.value)


@pytest.mark.parametrize(
    "change",
    [
        "reference",
        "primary",
        "role",
        "coverage",
        "duplicate",
        "context-primary",
        "independence",
        "overlap",
        "unresolved",
    ],
)
def test_invalid_responses_are_rejected(
    workspace, conversation_data, response_data, change
):
    if change == "context-primary":
        conversation_data["units"][0]["messages"][0]["context_only"] = True
    unit = validate(conversation_data, workspace).units[0]
    candidate = response_data["candidates"][0]
    if change == "reference":
        candidate["source_message_ids"].append("missing")
    elif change == "primary":
        candidate["primary_message_id"] = "a1"
    elif change == "role":
        candidate["attribution"] = "agent explanation"
    elif change == "coverage":
        response_data["excluded_message_ids"] = []
    elif change == "duplicate":
        response_data["candidates"].append(candidate.copy())
    elif change == "independence":
        candidate.update(
            primary_message_id="a1",
            source_message_ids=["a1"],
            attribution="agent explanation",
            assistance="independent",
        )
        response_data["excluded_message_ids"] = ["u1"]
    elif change == "overlap":
        response_data["excluded_message_ids"].append("u1")
    elif change == "unresolved":
        response_data["unresolved_message_ids"] = ["absent"]
    with pytest.raises(ValueError):
        validate_response(ExtractionResponse.model_validate(response_data), unit)


def test_materialization_is_stable_and_preserves_v1(
    workspace, conversation_data, response_data
):
    config = load_workspace(workspace)
    source = validate(conversation_data, workspace)
    response = ExtractionResponse.model_validate(response_data)
    now = datetime.now(timezone.utc)
    installation = uuid4()
    args = (
        response,
        source.units[0],
        source.source_session_id,
        config.workspace_id,
        installation,
        now,
        now,
    )
    records = materialize_records(*args)
    assert records == materialize_records(*args)
    assert records[0].schema_version == 1
    assert records[0].attribution == "user contribution"
    assert records[0].task_id == "migration"
    assert records[0].occurred_at == source.units[0].messages[0].occurred_at
    changed = source.units[0].model_copy(update={"source_revision": 1})
    revised = materialize_records(
        response,
        changed,
        source.source_session_id,
        config.workspace_id,
        installation,
        now,
        now,
    )
    assert revised[0].record_id != records[0].record_id
    assert revised[0].source_segment_id == records[0].source_segment_id


def test_timestamp_override_is_disclosed(workspace, conversation_data, response_data):
    conversation_data["units"][0]["messages"][0]["occurred_at"] = None
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    source = validate(conversation_data, workspace, now)
    assert source.units[0].messages[0].timestamp_basis == "user-supplied"
    records = materialize_records(
        ExtractionResponse.model_validate(response_data),
        source.units[0],
        source.source_session_id,
        load_workspace(workspace).workspace_id,
        uuid4(),
        now,
        now,
    )
    assert OVERRIDE_UNCERTAINTY in records[0].uncertainties
    assert records[0].occurred_at == now


def test_zero_relevance_and_earlier_context_are_valid(workspace, conversation_data):
    conversation_data["units"][0]["messages"].append(
        dict(
            message_id="context",
            role="assistant",
            content="Earlier context.",
            occurred_at=None,
            context_only=True,
        )
    )
    source = validate(conversation_data, workspace)
    response = ExtractionResponse(
        candidates=[],
        excluded_message_ids=["u1", "a1"],
        unresolved_message_ids=[],
        unresolved=[],
    )
    now = datetime.now(timezone.utc)
    assert (
        materialize_records(
            response,
            source.units[0],
            source.source_session_id,
            load_workspace(workspace).workspace_id,
            uuid4(),
            now,
            now,
        )
        == []
    )


def test_study_resource_must_appear_in_cited_source(workspace):
    from pathlib import Path

    from meditations.config import load_workspace
    from meditations.extraction.contracts import ExtractionResponse
    from meditations.extraction.validation import validate_input, validate_response
    from meditations.records import StudyResource

    fixtures = Path(__file__).parent / "fixtures/extraction"
    source = validate_input(
        (fixtures / "conversation.json").read_bytes(), load_workspace(workspace)
    )
    response = ExtractionResponse.model_validate_json(
        (fixtures / "response.json").read_bytes()
    )
    resource = StudyResource(
        title="Migration guide", url="https://example.org/migrations"
    )
    candidate = response.candidates[0].model_copy(update={"resources": [resource]})
    result = response.model_copy(update={"candidates": [candidate]})
    with pytest.raises(ValueError, match="resource"):
        validate_response(result, source.units[0])
    unit = source.units[0]
    message = unit.messages[0].model_copy(
        update={
            "content": unit.messages[0].content
            + " [Read](https://example.org/migrations)."
        }
    )
    validate_response(
        result, unit.model_copy(update={"messages": [message, *unit.messages[1:]]})
    )


def test_wire_schema_requires_defaulted_fields_without_breaking_old_data():
    from meditations.composition import CompositionResponse
    from meditations.extraction.contracts import output_schema

    schema = output_schema(CompositionResponse)
    topic = schema["$defs"]["JournalTopic"]
    assert set(topic["required"]) == set(topic["properties"])
    assert "default" not in topic["properties"]["table"]


def test_study_urls_reject_credentials_and_local_addresses():
    from meditations.records import StudyResource

    for url in (
        "file:///tmp/notes",
        "https://user:secret@example.org",
        "http://127.0.0.1/docs",
        "https://wiki.internal/docs",
    ):
        with pytest.raises(ValueError):
            StudyResource(title="Guide", url=url)
