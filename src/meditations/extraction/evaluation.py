import json
from pathlib import Path
from typing import Literal

from meditations.config import WorkspaceConfig
from meditations.extraction.contracts import (
    Attribution,
    Contract,
    ConversationInput,
    ExtractionResponse,
    Usage,
)
from meditations.extraction.validation import validate_input, validate_response
from meditations.records import Text


class ExpectedFinding(Contract):
    primary_message_id: Text
    attribution: Attribution
    source_message_ids: list[Text]
    expected_fact: Text


class EvaluationCase(Contract):
    case_id: Text
    split: Literal["development", "held-out"]
    source: ConversationInput
    expected_findings: list[ExpectedFinding]
    prohibited_claims: list[Text]
    expected_input_error: bool
    expected_empty: bool
    human_review_notes: Text


class EvaluationReport(Contract):
    case_id: Text
    unit_id: Text
    source_validation_errors: int
    missing_expected_origins: int
    missing_expected_citations: int
    prohibited_literal_hits: int
    unexpected_candidates: int
    usage: Usage
    semantic_review: Literal["pending-human-review"] = "pending-human-review"


def load_cases(path: Path) -> list[EvaluationCase]:
    try:
        cases = [
            EvaluationCase.model_validate_json(line)
            for line in path.read_bytes().splitlines()
            if line.strip()
        ]
    except ValueError as error:
        raise ValueError("Invalid synthetic evaluation cases") from error
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Duplicate evaluation case identity")
    return cases


def evaluate_response(
    case: EvaluationCase,
    response: ExtractionResponse,
    config: WorkspaceConfig,
    usage: Usage,
    unit_index: int = 0,
) -> EvaluationReport:
    source_errors = 0
    unit = case.source.units[unit_index]
    try:
        source = validate_input(case.source.model_dump_json().encode(), config)
        unit = source.units[unit_index]
        validate_response(response, unit)
    except ValueError:
        source_errors = 1
    candidates = {
        (candidate.primary_message_id, candidate.attribution): candidate
        for candidate in response.candidates
    }
    message_ids = {message.message_id for message in unit.messages}
    expected = [
        finding
        for finding in case.expected_findings
        if finding.primary_message_id in message_ids
    ]
    missing_origins = sum(
        (finding.primary_message_id, finding.attribution) not in candidates
        for finding in expected
    )
    missing_citations = 0
    for finding in expected:
        candidate = candidates.get((finding.primary_message_id, finding.attribution))
        missing_citations += len(
            set(finding.source_message_ids)
            - set(candidate.source_message_ids if candidate else [])
        )
    text = json.dumps(
        [candidate.model_dump(mode="json") for candidate in response.candidates]
    ).casefold()
    return EvaluationReport(
        case_id=case.case_id,
        unit_id=unit.unit_id,
        source_validation_errors=source_errors,
        missing_expected_origins=missing_origins,
        missing_expected_citations=missing_citations,
        prohibited_literal_hits=sum(
            claim.casefold() in text for claim in case.prohibited_claims
        ),
        unexpected_candidates=len(response.candidates) if case.expected_empty else 0,
        usage=usage,
    )
