from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    record_id: UUID
    workspace_id: UUID
    installation_id: UUID
    source_agent: Text
    source_session_id: Text
    source_segment_id: Text
    source_revision: Annotated[int, Field(strict=True, ge=0)]
    occurred_at: AwareDatetime
    captured_at: AwareDatetime
    processed_at: AwareDatetime
    task_id: Text
    task_label: Text
    tags: list[Text]
    concepts: list[Text]
    summary: Text
    reasoning: list[Text]
    alternatives: list[Text]
    decisions: list[Text]
    outcomes: list[Text]
    verification: list[Text]
    attribution: Literal[
        "user contribution",
        "agent explanation",
        "user self-report",
        "observed artifact",
    ]
    assistance: Literal[
        "independent", "guided", "agent-produced and reviewed", "unknown"
    ]
    uncertainties: list[Text]
    privacy_omissions: list[Text]

    @property
    def source_key(self) -> tuple[UUID, str, str, str]:
        return (
            self.workspace_id,
            self.source_agent,
            self.source_session_id,
            self.source_segment_id,
        )


def latest_records(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
    latest: dict[tuple[UUID, str, str, str], EvidenceRecord] = {}
    for record in records:
        previous = latest.get(record.source_key)
        if previous is None or record.source_revision > previous.source_revision:
            latest[record.source_key] = record
    return sorted(
        latest.values(), key=lambda item: (item.occurred_at, str(item.record_id))
    )
