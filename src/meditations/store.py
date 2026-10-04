from pathlib import Path
from typing import Literal

from meditations.config import load_workspace, validate_workspace_path
from meditations.files import atomic_write, workspace_directory, workspace_lock
from meditations.records import EvidenceRecord


def load_records(workspace: Path) -> list[EvidenceRecord]:
    workspace = validate_workspace_path(workspace)
    config = load_workspace(workspace)
    result: list[EvidenceRecord] = []
    identities: set[tuple[object, ...]] = set()
    ids: set[object] = set()
    for path in sorted(workspace_directory(workspace, "records").glob("*.json")):
        if path.is_symlink():
            raise ValueError("Refusing a symbolic-link evidence file")
        try:
            record = EvidenceRecord.model_validate_json(path.read_bytes())
        except ValueError as error:
            raise ValueError("Invalid persisted evidence; records preserved") from error
        key = (*record.source_key, record.source_revision)
        if record.workspace_id != config.workspace_id:
            raise ValueError("Evidence belongs to a different workspace")
        if key in identities or record.record_id in ids:
            raise ValueError("Conflicting persisted evidence identity")
        identities.add(key)
        ids.add(record.record_id)
        result.append(record)
    return result


def _record_result(
    existing_records: list[EvidenceRecord], record: EvidenceRecord
) -> Literal["created", "unchanged"]:
    for existing in existing_records:
        if (existing.source_key, existing.source_revision) == (
            record.source_key,
            record.source_revision,
        ) or existing.record_id == record.record_id:
            if existing == record:
                return "unchanged"
            raise ValueError(f"Evidence conflict for record {existing.record_id}")
    return "created"


def _write_record(workspace: Path, record: EvidenceRecord) -> None:
    directory = workspace_directory(workspace, "records")
    atomic_write(
        directory / f"{record.record_id}.json",
        (record.model_dump_json(indent=2) + "\n").encode(),
    )


def persist_record(
    workspace: Path, record: EvidenceRecord
) -> Literal["created", "unchanged"]:
    workspace = validate_workspace_path(workspace)
    with workspace_lock(workspace):
        if record.workspace_id != load_workspace(workspace).workspace_id:
            raise ValueError("Evidence belongs to a different workspace")
        result = _record_result(load_records(workspace), record)
        if result == "created":
            _write_record(workspace, record)
        return result


def import_records(workspace: Path, source: Path) -> tuple[int, int]:
    workspace = validate_workspace_path(workspace)
    try:
        records = [
            EvidenceRecord.model_validate_json(line)
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except ValueError as error:
        raise ValueError("Invalid evidence input; no records imported") from error
    unchanged = 0
    with workspace_lock(workspace):
        config = load_workspace(workspace)
        if any(record.workspace_id != config.workspace_id for record in records):
            raise ValueError("Evidence belongs to a different workspace")
        existing = load_records(workspace)
        pending: list[EvidenceRecord] = []
        for record in records:
            if _record_result(existing, record) == "created":
                pending.append(record)
                existing.append(record)
            else:
                unchanged += 1
        for record in pending:
            _write_record(workspace, record)
    return len(pending), unchanged


def validate_record_batch(
    workspace: Path, records: list[EvidenceRecord]
) -> tuple[list[EvidenceRecord], int]:
    """Preflight a batch; caller must hold the workspace lock through publication."""
    config = load_workspace(workspace)
    if any(record.workspace_id != config.workspace_id for record in records):
        raise ValueError("Evidence belongs to a different workspace")
    existing = load_records(workspace)
    pending: list[EvidenceRecord] = []
    unchanged = 0
    for record in records:
        if _record_result(existing, record) == "created":
            pending.append(record)
            existing.append(record)
        else:
            unchanged += 1
    return pending, unchanged


def publish_records_locked(
    workspace: Path, records: list[EvidenceRecord]
) -> tuple[int, int]:
    """Publish a preflighted batch under a lock already held by the caller."""
    pending, unchanged = validate_record_batch(workspace, records)
    for record in pending:
        _write_record(workspace, record)
    return len(pending), unchanged
