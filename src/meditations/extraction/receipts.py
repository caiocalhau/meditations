import hashlib
import json
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from meditations.config import load_workspace
from meditations.extraction.contracts import Contract, ExtractionReceipt
from meditations.files import atomic_write, workspace_directory
from meditations.records import EvidenceRecord, latest_records
from meditations.store import publish_records_locked


class PendingExtraction(Contract):
    receipt: ExtractionReceipt
    records: list[EvidenceRecord]


def receipt_key(session: str, unit: str, revision: int) -> str:
    return hashlib.sha256(json.dumps([session, unit, revision]).encode()).hexdigest()


def extraction_directory(workspace: Path) -> Path:
    directory = workspace_directory(workspace, "extractions")
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise ValueError("Invalid extraction receipt directory")
    return directory


def load_receipts(
    workspace: Path,
) -> tuple[list[ExtractionReceipt], list[PendingExtraction]]:
    config = load_workspace(workspace)
    receipts: list[ExtractionReceipt] = []
    pending: list[PendingExtraction] = []
    identities: set[tuple[str, str, int, bool]] = set()
    for path in sorted(extraction_directory(workspace).glob("*.json")):
        if path.is_symlink():
            raise ValueError("Symbolic-link extraction receipt")
        try:
            is_pending = path.name.endswith(".pending.json")
            if is_pending:
                manifest = PendingExtraction.model_validate_json(path.read_bytes())
                receipt = manifest.receipt
                if [
                    record.record_id for record in manifest.records
                ] != receipt.active_record_ids:
                    raise ValueError("Pending receipt record mismatch")
                pending.append(manifest)
            else:
                receipt = ExtractionReceipt.model_validate_json(path.read_bytes())
                receipts.append(receipt)
            key = (
                receipt.source_session_id,
                receipt.unit_id,
                receipt.source_revision,
                is_pending,
            )
            filename = receipt_key(*key[:3]) + (
                ".pending.json" if is_pending else ".json"
            )
            if (
                path.name != filename
                or key in identities
                or receipt.workspace_id != config.workspace_id
            ):
                raise ValueError("Conflicting extraction receipt identity")
            identities.add(key)
            record_ids = [str(record_id) for record_id in receipt.active_record_ids]
            if len(set(record_ids)) != len(record_ids) or set(record_ids) != set(
                receipt.source_references
            ):
                raise ValueError("Invalid extraction receipt references")
            if any(
                not refs or len(set(refs)) != len(refs)
                for refs in receipt.source_references.values()
            ):
                raise ValueError("Invalid extraction receipt source references")
            if len(receipt.usage) != receipt.attempts or (
                receipt.status == "completed-with-unresolved"
            ) != bool(receipt.unresolved_message_ids):
                raise ValueError("Invalid extraction receipt completion")
        except (ValidationError, ValueError) as error:
            raise ValueError("Invalid extraction receipt; files preserved") from error
    return receipts, pending


def select_active_records(
    workspace: Path, records: list[EvidenceRecord]
) -> list[EvidenceRecord]:
    receipts, pending = load_receipts(workspace)
    by_id = {record.record_id: record for record in records}
    managed: set[UUID] = set()
    latest: dict[tuple[str, str], ExtractionReceipt] = {}
    for receipt in receipts:
        for record_id in receipt.active_record_ids:
            record = by_id.get(record_id)
            if (
                record is None
                or record.source_session_id != receipt.source_session_id
                or record.source_revision != receipt.source_revision
                or not record.source_segment_id.startswith("extraction:")
            ):
                raise ValueError(
                    "Extraction receipt refers to missing or conflicting evidence"
                )
            managed.add(record_id)
        key = (receipt.source_session_id, receipt.unit_id)
        previous = latest.get(key)
        if previous is None or receipt.source_revision > previous.source_revision:
            latest[key] = receipt
    pending_ids = {
        record.record_id for manifest in pending for record in manifest.records
    }
    active = {
        record_id
        for receipt in latest.values()
        for record_id in receipt.active_record_ids
    }
    for record in records:
        if (
            record.source_segment_id.startswith("extraction:")
            and record.record_id not in managed | pending_ids
        ):
            raise ValueError("Extraction evidence is missing its receipt")
    return latest_records(
        [
            record
            for record in records
            if record.record_id in active
            or (record.record_id not in managed | pending_ids)
        ]
    )


def publish_extraction(workspace: Path, manifest: PendingExtraction) -> tuple[int, int]:
    """Publish or recover one validated transaction while holding workspace_lock."""
    receipt = manifest.receipt
    directory = extraction_directory(workspace)
    key = receipt_key(
        receipt.source_session_id, receipt.unit_id, receipt.source_revision
    )
    pending_path = directory / f"{key}.pending.json"
    final_path = directory / f"{key}.json"
    content = (manifest.model_dump_json(indent=2) + "\n").encode()
    if pending_path.exists():
        if pending_path.is_symlink() or pending_path.read_bytes() != content:
            raise ValueError("Conflicting pending extraction receipt")
    else:
        # Preflight all record identities before publishing the manifest.
        from meditations.store import validate_record_batch

        validate_record_batch(workspace, manifest.records)
        atomic_write(pending_path, content)
    created, unchanged = publish_records_locked(workspace, manifest.records)
    final_content = (receipt.model_dump_json(indent=2) + "\n").encode()
    if final_path.exists():
        if final_path.is_symlink() or final_path.read_bytes() != final_content:
            raise ValueError("Conflicting completed extraction receipt")
    else:
        atomic_write(final_path, final_content)
    pending_path.unlink()
    return created, unchanged
