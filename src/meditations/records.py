from ipaddress import ip_address
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class StudyResource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    title: Text
    url: Text

    @field_validator("url")
    @classmethod
    def public_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (
            parsed.scheme not in {"https", "http"}
            or not host
            or "." not in host
            or parsed.username
            or parsed.password
            or any(c.isspace() for c in value)
            or any(c in value for c in '<>"`\\')
            or host.endswith((".local", ".internal", ".localhost"))
        ):
            raise ValueError("Use a public HTTP(S) study URL without credentials")
        try:
            address = ip_address(host)
        except ValueError:
            pass
        else:
            if not address.is_global:
                raise ValueError("Private addresses are not study resources")
        return value


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
    resources: list[StudyResource] = Field(
        default_factory=lambda: list[StudyResource]()
    )

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
