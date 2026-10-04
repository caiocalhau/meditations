from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from meditations.records import Text

Revision = Annotated[int, Field(strict=True, ge=0)]
Attribution = Literal[
    "user contribution", "agent explanation", "user self-report", "observed artifact"
]
Assistance = Literal["independent", "guided", "agent-produced and reviewed", "unknown"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceMessage(Contract):
    message_id: Text
    role: Literal["user", "assistant", "tool"]
    content: Text
    occurred_at: AwareDatetime | None
    context_only: Annotated[bool, Field(strict=True)]
    timestamp_basis: Literal["source", "user-supplied"] = "source"


class ConversationUnit(Contract):
    unit_id: Text
    source_revision: Revision
    task_id: Text
    task_label: Text
    messages: Annotated[list[SourceMessage], Field(min_length=1, max_length=200)]


class ConversationInput(Contract):
    schema_version: Literal[1]
    source_agent: Literal["codex"]
    source_session_id: Text
    units: Annotated[list[ConversationUnit], Field(min_length=1)]


class EvidenceCandidate(Contract):
    primary_message_id: Text
    source_message_ids: Annotated[list[Text], Field(min_length=1)]
    summary: Text
    reasoning: list[Text]
    alternatives: list[Text]
    decisions: list[Text]
    outcomes: list[Text]
    verification: list[Text]
    tags: list[Text]
    concepts: list[Text]
    attribution: Attribution
    assistance: Assistance
    uncertainties: list[Text]
    privacy_omissions: list[Text]


class ExtractionResponse(Contract):
    candidates: list[EvidenceCandidate]
    excluded_message_ids: list[Text]
    unresolved_message_ids: list[Text]
    unresolved: list[Text]


class Usage(Contract):
    input_tokens: Revision | None = None
    output_tokens: Revision | None = None
    cached_input_tokens: Revision | None = None
    elapsed_seconds: Annotated[float, Field(ge=0)] | None = None


class ExtractionReceipt(Contract):
    schema_version: Literal[1]
    workspace_id: UUID
    source_session_id: Text
    unit_id: Text
    source_revision: Revision
    input_fingerprint: Text
    extractor_fingerprint: Text
    timestamp_basis: Literal["source", "user-supplied"]
    provider: Text
    requested_model: Text
    observed_model: Text | None
    active_record_ids: list[UUID]
    source_references: dict[str, list[Text]]
    excluded_message_ids: list[Text]
    unresolved_message_ids: list[Text]
    unresolved_reasons: list[Text]
    status: Literal["completed", "completed-with-unresolved"]
    attempts: Annotated[int, Field(strict=True, ge=1, le=2)]
    usage: list[Usage]
