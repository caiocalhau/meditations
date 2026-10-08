"""Validated data exchanged between Codex skills and the local helper."""

import json
import re
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Hash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Narrative = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1600)
]
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
RESERVED = re.compile(
    r"<!--\s*meditations:generated:(?:start|end)\s*-->", re.IGNORECASE
)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def reject_reserved_markers(self):
        if RESERVED.search(json.dumps(self.model_dump(mode="json"))):
            raise ValueError("Content contains a reserved Meditations marker")
        return self


class CaptureDraft(Contract):
    body: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=65536)
    ]


class JournalTable(Contract):
    headers: Annotated[list[Title], Field(min_length=2, max_length=5)]
    rows: Annotated[
        list[Annotated[list[Narrative], Field(min_length=2, max_length=5)]],
        Field(min_length=1, max_length=10),
    ]

    @model_validator(mode="after")
    def row_widths_match(self):
        if any(len(row) != len(self.headers) for row in self.rows):
            raise ValueError("Table rows must have the same number of cells as headers")
        return self


class JournalTopic(Contract):
    title: Title
    paragraphs: list[Narrative] = Field(default_factory=list, max_length=4)
    bullets: list[Narrative] = Field(default_factory=list, max_length=8)
    steps: list[Narrative] = Field(default_factory=list, max_length=8)
    table: JournalTable | None = None

    @model_validator(mode="after")
    def has_content(self):
        if not (self.paragraphs or self.bullets or self.steps or self.table):
            raise ValueError("Each topic must contain narrative content")
        return self


class LearningItem(Contract):
    concept: Title
    explanation: Narrative
    suggested_practice: Narrative
    resource_urls: list[str] = Field(default_factory=list, max_length=4)
    reading_question: Narrative | None = None


class DailyDraft(Contract):
    source_snapshot: Hash
    expected_note_sha256: Hash | None
    overview: Annotated[list[Narrative], Field(min_length=1, max_length=6)]
    topics: Annotated[list[JournalTopic], Field(min_length=1, max_length=5)]
    open_items: list[Narrative] = Field(default_factory=list, max_length=8)
    learning: list[LearningItem] = Field(
        default_factory=lambda: list[LearningItem](), max_length=3
    )
    reflection_questions: Annotated[list[Narrative], Field(min_length=1, max_length=4)]


class CaptureSource(Contract):
    capture_id: Hash
    body: str
    captured_at: datetime
    file_sha256: Hash


class CaptureResult(Contract):
    status: Literal["created", "unchanged"]
    path: str
    capture_id: Hash


class DayPreparation(Contract):
    status: Literal["ready", "unchanged", "empty", "conflict"]
    day: date
    language: Literal["en", "pt-BR"]
    source_snapshot: Hash
    expected_note_sha256: Hash | None
    captures: list[CaptureSource]
    previous_note: str | None
    message: str | None = None


class WriteResult(Contract):
    status: Literal["created", "updated", "unchanged", "conflict"]
    path: str
    message: str | None = None
