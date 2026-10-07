from typing import Annotated, Literal, cast
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from meditations.records import StudyResource, Text

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
    resources: list[StudyResource] = Field(
        default_factory=lambda: list[StudyResource]()
    )


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


def output_schema(contract: type[Contract]) -> dict[str, object]:
    """Require every wire field while allowing older persisted data to omit defaults."""

    def strict(value: object) -> object:
        if isinstance(value, list):
            return [strict(item) for item in cast(list[object], value)]
        if not isinstance(value, dict):
            return value
        result = {
            key: strict(item)
            for key, item in cast(dict[str, object], value).items()
            if key != "default"
        }
        if "properties" in result:
            result["required"] = list(cast(dict[str, object], result["properties"]))
        return result

    return cast(dict[str, object], strict(contract.model_json_schema()))
