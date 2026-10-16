"""Structured weekly review drafts and read-only source preparation."""

import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from meditations.contracts import Contract, Hash, Narrative, Title

PRACTICE_RESERVED = re.compile(
    r"<!--\s*meditations:weekly:practice:(?:start|end)\s*-->", re.I
)


class WeeklyContract(Contract):
    @model_validator(mode="after")
    def reject_practice_markers(self):
        if PRACTICE_RESERVED.search(self.model_dump_json()):
            raise ValueError("Content contains a reserved weekly practice marker")
        return self


class EvidenceReference(WeeklyContract):
    source_id: Title
    quote: Narrative


class WeeklyFinding(WeeklyContract):
    category: Literal[
        "sound_reasoning",
        "conceptual_error",
        "incomplete_reasoning",
        "unclear_expression",
        "contradiction",
        "unresolved",
        "practice_feedback",
    ]
    title: Title
    assessment: Narrative
    next_step: Narrative | None = None
    evidence: Annotated[list[EvidenceReference], Field(min_length=1)]


class EnglishFeedback(WeeklyContract):
    evidence: EvidenceReference
    suggestion: Narrative
    explanation: Narrative


class WeeklyPractice(WeeklyContract):
    questions: Annotated[list[Narrative], Field(min_length=1)]
    actions: Annotated[list[Narrative], Field(min_length=1, max_length=2)]
    resource_urls: list[str] = Field(default_factory=list, max_length=4)


class WeeklyDraft(WeeklyContract):
    source_snapshot: Hash
    expected_note_sha256: Hash | None
    overview: Annotated[list[Narrative], Field(min_length=1, max_length=6)]
    findings: list[WeeklyFinding] = Field(default_factory=lambda: list[WeeklyFinding]())
    limitations: list[Narrative] = Field(default_factory=list)
    english_feedback: list[EnglishFeedback] = Field(
        default_factory=lambda: list[EnglishFeedback]()
    )
    initial_practice: WeeklyPractice | None = None


class WeeklySource(BaseModel):
    # Stored source Markdown can contain markers; only model drafts reject them.
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: str
    kind: Literal["daily", "current_personal", "previous_practice"]
    day: date
    body: str
    sha256: Hash
    link: str


class WeekPreparation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["ready", "empty", "unchanged", "conflict"]
    week_start: date
    week_end: date
    review_through: date | None
    provisional: bool
    language: Literal["en", "pt-BR"]
    english_feedback: bool
    available_dates: list[date] = Field(default_factory=lambda: list[date]())
    missing_dates: list[date] = Field(default_factory=lambda: list[date]())
    pending_dates: list[date] = Field(default_factory=lambda: list[date]())
    source_snapshot: Hash
    expected_note_sha256: Hash | None
    sources: list[WeeklySource] = Field(default_factory=lambda: list[WeeklySource]())
    path: str
    source_bytes: int = 0
    max_source_bytes: int = 256 * 1024
    warnings: list[str] = Field(default_factory=list)
    message: str | None = None
