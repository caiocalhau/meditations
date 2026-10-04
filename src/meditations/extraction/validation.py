import json
from datetime import datetime
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from meditations.config import WorkspaceConfig
from meditations.extraction.contracts import (
    ConversationInput,
    ConversationUnit,
    ExtractionResponse,
    SourceMessage,
)
from meditations.records import EvidenceRecord

MAX_UNIT_BYTES = 64 * 1024
MAX_INPUT_BYTES = 8 * 1024 * 1024
OVERRIDE_UNCERTAINTY = (
    "Occurrence time was supplied by the user; original source time is unavailable."
)


def validate_input(
    data: bytes,
    config: WorkspaceConfig,
    occurrence_override: datetime | None = None,
) -> ConversationInput:
    if len(data) > MAX_INPUT_BYTES:
        raise ValueError("Conversation input exceeds the file limit")
    if occurrence_override is not None and (
        occurrence_override.tzinfo is None or occurrence_override.utcoffset() is None
    ):
        raise ValueError("Occurrence override must include a timezone")
    try:
        source = ConversationInput.model_validate_json(data)
    except ValidationError as error:
        raise ValueError("Invalid conversation input") from error
    units: list[ConversationUnit] = []
    unit_ids: set[str] = set()
    message_ids: set[str] = set()
    for unit in source.units:
        if unit.unit_id in unit_ids:
            raise ValueError("Duplicate conversation unit identity")
        unit_ids.add(unit.unit_id)
        messages: list[SourceMessage] = []
        for message in unit.messages:
            if message.message_id in message_ids:
                raise ValueError("Duplicate source message identity")
            message_ids.add(message.message_id)
            if message.timestamp_basis != "source":
                raise ValueError("Timestamp provenance is application-owned")
            if not message.context_only and message.occurred_at is None:
                if occurrence_override is None:
                    raise ValueError(
                        "Missing source timestamp; supply an explicit override"
                    )
                message = message.model_copy(
                    update={
                        "occurred_at": occurrence_override,
                        "timestamp_basis": "user-supplied",
                    }
                )
            messages.append(message)
        effective = unit.model_copy(update={"messages": messages})
        days = {
            message.occurred_at.astimezone(ZoneInfo(config.timezone)).date()
            for message in messages
            if not message.context_only and message.occurred_at is not None
        }
        if len(days) != 1:
            raise ValueError("A unit must contain activity from one occurrence day")
        validate_unit_size(effective)
        units.append(effective)
    return source.model_copy(update={"units": units})


def validate_unit_size(unit: ConversationUnit) -> None:
    if len(unit.model_dump_json().encode()) > MAX_UNIT_BYTES:
        raise ValueError("Conversation unit exceeds the byte limit")


def validate_response(response: ExtractionResponse, unit: ConversationUnit) -> None:
    messages = {message.message_id: message for message in unit.messages}
    relevant = {key for key, message in messages.items() if not message.context_only}
    covered: set[str] = set()
    keys: set[tuple[str, str]] = set()
    roles = {
        "user contribution": "user",
        "user self-report": "user",
        "agent explanation": "assistant",
        "observed artifact": "tool",
    }
    for candidate in response.candidates:
        refs = set(candidate.source_message_ids)
        key = (candidate.primary_message_id, candidate.attribution)
        if (
            len(refs) != len(candidate.source_message_ids)
            or not refs.issubset(messages)
            or candidate.primary_message_id not in refs
            or candidate.primary_message_id not in relevant
            or key in keys
        ):
            raise ValueError("Invalid candidate source references")
        if messages[candidate.primary_message_id].role != roles[candidate.attribution]:
            raise ValueError("Candidate attribution does not match source role")
        if (
            candidate.attribution == "agent explanation"
            and candidate.assistance == "independent"
        ):
            raise ValueError("Agent explanation cannot establish independence")
        keys.add(key)
        covered.update(refs & relevant)
    excluded = set(response.excluded_message_ids)
    unresolved = set(response.unresolved_message_ids)
    if (
        len(excluded) != len(response.excluded_message_ids)
        or len(unresolved) != len(response.unresolved_message_ids)
        or not excluded.issubset(relevant)
        or not unresolved.issubset(relevant)
        or covered & excluded
        or covered & unresolved
        or excluded & unresolved
        or covered | excluded | unresolved != relevant
        or bool(unresolved) != bool(response.unresolved)
    ):
        raise ValueError("Invalid or incomplete source coverage")


def materialize_records(
    response: ExtractionResponse,
    unit: ConversationUnit,
    source_session_id: str,
    workspace_id: UUID,
    installation_id: UUID,
    captured_at: datetime,
    processed_at: datetime,
) -> list[EvidenceRecord]:
    validate_response(response, unit)
    messages = {message.message_id: message for message in unit.messages}
    records: list[EvidenceRecord] = []
    for candidate in response.candidates:
        origin = messages[candidate.primary_message_id]
        if origin.occurred_at is None:
            raise ValueError("Missing effective occurrence time")
        segment = "extraction:" + str(
            uuid5(
                workspace_id,
                json.dumps(
                    [
                        source_session_id,
                        unit.unit_id,
                        origin.message_id,
                        candidate.attribution,
                    ]
                ),
            )
        )
        conceptual = candidate.model_dump(
            exclude={"primary_message_id", "source_message_ids"}
        )
        if any(
            messages[ref].timestamp_basis == "user-supplied"
            for ref in candidate.source_message_ids
        ):
            conceptual["uncertainties"] = [
                *candidate.uncertainties,
                OVERRIDE_UNCERTAINTY,
            ]
        records.append(
            EvidenceRecord.model_validate(
                dict(
                    conceptual,
                    schema_version=1,
                    record_id=uuid5(workspace_id, f"{segment}:{unit.source_revision}"),
                    workspace_id=workspace_id,
                    installation_id=installation_id,
                    source_agent="codex",
                    source_session_id=source_session_id,
                    source_segment_id=segment,
                    source_revision=unit.source_revision,
                    occurred_at=origin.occurred_at,
                    captured_at=captured_at,
                    processed_at=processed_at,
                    task_id=unit.task_id,
                    task_label=unit.task_label,
                )
            )
        )
    return records
