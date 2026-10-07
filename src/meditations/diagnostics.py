"""Private historical failure reports, readable without model calls."""

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime

from meditations.composition import (
    CompositionBudgetError,
    LearningResourceError,
    evidence_fingerprint,
)
from meditations.config import WorkspaceConfig
from meditations.extraction.contracts import Contract, Usage
from meditations.extraction.provider import ProviderError
from meditations.files import atomic_write, workspace_directory, workspace_lock
from meditations.records import EvidenceRecord


class CompositionFailureReport(Contract):
    schema_version: Literal[1]
    workspace_id: UUID
    day: date
    recorded_at: AwareDatetime
    evidence_fingerprint: str
    code: str
    details: dict[str, object]
    extraction_calls: int
    composition_calls: int
    usage: Usage | None


def _directory(workspace: Path) -> Path:
    directory = workspace_directory(workspace, "diagnostics/composition")
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError("Unsafe composition diagnostic directory")
    return directory


def save_composition_failure(
    workspace: Path,
    config: WorkspaceConfig,
    day: date,
    records: list[EvidenceRecord],
    error: ValueError | OSError | ProviderError,
    *,
    extraction_calls: int = 0,
    composition_calls: int = 0,
    usage: Usage | None = None,
) -> Path:
    details: dict[str, object]
    if isinstance(error, (LearningResourceError, CompositionBudgetError)):
        details = error.details
        code = str(details["code"])
    else:
        code = "composition_failed"
        details = {
            "reason": "Composition failed before resource diagnostics were available"
        }
    report = CompositionFailureReport(
        schema_version=1,
        workspace_id=config.workspace_id,
        day=day,
        recorded_at=datetime.now(timezone.utc),
        evidence_fingerprint=evidence_fingerprint(records, config, day),
        code=code,
        details=details,
        extraction_calls=extraction_calls,
        composition_calls=composition_calls,
        usage=usage,
    )
    with workspace_lock(workspace):
        path = _directory(workspace) / f"{day.isoformat()}.json"
        if path.is_symlink():
            raise ValueError("Unsafe composition failure report")
        original = path.read_bytes() if path.exists() else None
        content = report.model_dump_json().encode()
        if len(content) > 64 * 1024:
            raise ValueError("Composition failure report exceeds the size limit")
        atomic_write(path, content, expected=original)
    return path


def load_composition_failure(
    workspace: Path, config: WorkspaceConfig, day: date, records: list[EvidenceRecord]
) -> dict[str, object] | None:
    path = _directory(workspace) / f"{day.isoformat()}.json"
    if path.is_symlink():
        raise ValueError("Unsafe composition failure report")
    if not path.exists():
        return None
    if path.stat().st_size > 64 * 1024:
        raise ValueError("Composition failure report exceeds the size limit")
    try:
        report = CompositionFailureReport.model_validate_json(path.read_bytes())
        if report.workspace_id != config.workspace_id or report.day != day:
            raise ValueError("Report identity mismatch")
    except ValueError as error:
        raise ValueError("Invalid composition failure report") from error
    result: dict[str, object] = report.model_dump(mode="json")
    return result | {
        "historical": True,
        "evidence_matches": report.evidence_fingerprint
        == evidence_fingerprint(records, config, day),
    }


def saved_composition_failures(
    workspace: Path, config: WorkspaceConfig, records: list[EvidenceRecord]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for path in sorted(_directory(workspace).glob("*.json")):
        try:
            day = date.fromisoformat(path.stem)
        except ValueError as error:
            raise ValueError("Invalid composition report filename") from error
        report = load_composition_failure(workspace, config, day, records)
        if report is not None:
            result.append(report)
    return result
