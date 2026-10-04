import hashlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from meditations.config import load_workspace, validate_workspace_path
from meditations.extraction.contracts import (
    ConversationUnit,
    ExtractionReceipt,
    Usage,
)
from meditations.extraction.prompt import INSTRUCTIONS, PROMPT_VERSION
from meditations.extraction.provider import (
    ExtractionProvider,
    ExtractionRequest,
    ProviderError,
    ProviderResult,
)
from meditations.extraction.receipts import (
    PendingExtraction,
    load_receipts,
    publish_extraction,
    select_active_records,
)
from meditations.extraction.validation import (
    materialize_records,
    validate_response,
    validate_unit_size,
)
from meditations.files import atomic_write, workspace_lock
from meditations.store import load_records


@dataclass(frozen=True)
class ExtractionSettings:
    model: str
    escalation_model: str | None = None
    timeout_seconds: float = 180
    output_limit_bytes: int = 2 * 1024 * 1024
    state_directory: Path | None = None
    privacy_fingerprint: str = "default"
    runtime_fingerprint: str = "unknown"


@dataclass(frozen=True)
class ExtractionOutcome:
    created: int = 0
    reused: int = 0
    unresolved_message_ids: list[str] = field(default_factory=lambda: list[str]())
    failure_category: str | None = None
    attempts: int = 0
    usage: list[Usage] = field(default_factory=lambda: list[Usage]())


def installation_id(directory: Path | None = None) -> UUID:
    if directory is None:
        root = (
            Path.home() / "Library/Application Support"
            if sys.platform == "darwin"
            else Path(
                os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))
            )
        )
        directory = root / "meditations"
    directory = directory.expanduser().absolute()
    with workspace_lock(directory):
        if directory.is_symlink():
            raise ValueError("Invalid machine-local state directory")
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / "installation.json"
        if path.is_symlink():
            raise ValueError("Invalid machine-local installation file")
        if path.exists():
            try:
                return UUID(json.loads(path.read_bytes())["installation_id"])
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(
                    "Invalid machine-local installation identity"
                ) from error
        identity = uuid4()
        atomic_write(path, json.dumps({"installation_id": str(identity)}).encode())
        return identity


def _hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _existing(
    workspace: Path,
    session: str,
    unit: ConversationUnit,
    input_hash: str,
    extractor_hash: str,
) -> ExtractionOutcome | None:
    records = load_records(workspace)
    select_active_records(workspace, records)
    receipts, pending = load_receipts(workspace)
    relevant = [
        receipt
        for receipt in receipts
        if receipt.source_session_id == session and receipt.unit_id == unit.unit_id
    ]
    manifests = [
        manifest
        for manifest in pending
        if manifest.receipt.source_session_id == session
        and manifest.receipt.unit_id == unit.unit_id
    ]
    all_receipts = relevant + [manifest.receipt for manifest in manifests]
    if any(receipt.source_revision > unit.source_revision for receipt in all_receipts):
        raise ValueError("Source revision is older than existing extraction")
    for receipt in all_receipts:
        if receipt.source_revision == unit.source_revision and (
            receipt.input_fingerprint != input_hash
            or receipt.extractor_fingerprint != extractor_hash
        ):
            raise ValueError("Input or settings changed; increase source revision")
    for manifest in manifests:
        if manifest.receipt.source_revision == unit.source_revision:
            created, unchanged = publish_extraction(workspace, manifest)
            return ExtractionOutcome(
                created=created,
                reused=unchanged,
                unresolved_message_ids=manifest.receipt.unresolved_message_ids,
            )
    for receipt in relevant:
        if receipt.source_revision == unit.source_revision:
            return ExtractionOutcome(
                reused=len(receipt.active_record_ids),
                unresolved_message_ids=receipt.unresolved_message_ids,
            )
    return None


def extract_unit(
    workspace: Path,
    source_session_id: str,
    unit: ConversationUnit,
    provider: ExtractionProvider,
    settings: ExtractionSettings,
) -> ExtractionOutcome:
    workspace = validate_workspace_path(workspace)
    config = load_workspace(workspace)
    validate_unit_size(unit)
    if (
        not settings.model.strip()
        or (
            settings.escalation_model is not None
            and not settings.escalation_model.strip()
        )
        or not 0 < settings.timeout_seconds <= 180
        or not 0 < settings.output_limit_bytes <= 2 * 1024 * 1024
    ):
        raise ValueError("Invalid extraction settings")
    input_hash = _hash(
        {"unit": unit.model_dump(mode="json"), "timezone": config.timezone}
    )
    from meditations.extraction.contracts import ExtractionResponse

    extractor_hash = _hash(
        {
            "prompt": PROMPT_VERSION,
            "instructions": INSTRUCTIONS,
            "privacy": settings.privacy_fingerprint,
            "runtime": settings.runtime_fingerprint,
            "schema": ExtractionResponse.model_json_schema(),
            "model": settings.model,
            "escalation_model": settings.escalation_model,
            "timeout": settings.timeout_seconds,
            "output_limit": settings.output_limit_bytes,
        }
    )
    with workspace_lock(workspace):
        cached = _existing(
            workspace, source_session_id, unit, input_hash, extractor_hash
        )
        if cached is not None:
            return cached
    captured_at = datetime.now(timezone.utc)
    usages: list[Usage] = []
    result: ProviderResult | None = None
    selected_model = settings.model
    for attempt in range(2):
        selected_model = (
            settings.escalation_model or settings.model if attempt else settings.model
        )
        try:
            result = provider.extract(
                ExtractionRequest(
                    unit=unit,
                    model=selected_model,
                    timeout_seconds=settings.timeout_seconds,
                    output_limit_bytes=settings.output_limit_bytes,
                    repair=bool(attempt),
                )
            )
        except ProviderError as error:
            usages.append(error.usage or Usage())
            if error.category == "validation" and attempt == 0:
                continue
            return ExtractionOutcome(
                failure_category=error.category, attempts=attempt + 1, usage=usages
            )
        usages.append(result.usage)
        try:
            validate_response(result.response, unit)
        except ValueError:
            if attempt == 0:
                continue
            return ExtractionOutcome(
                failure_category="validation", attempts=attempt + 1, usage=usages
            )
        break
    assert result is not None
    processed_at = datetime.now(timezone.utc)
    records = materialize_records(
        result.response,
        unit,
        source_session_id,
        config.workspace_id,
        installation_id(settings.state_directory),
        captured_at,
        processed_at,
    )
    response = result.response
    receipt = ExtractionReceipt(
        schema_version=1,
        workspace_id=config.workspace_id,
        source_session_id=source_session_id,
        unit_id=unit.unit_id,
        source_revision=unit.source_revision,
        input_fingerprint=input_hash,
        extractor_fingerprint=extractor_hash,
        timestamp_basis="user-supplied"
        if any(message.timestamp_basis == "user-supplied" for message in unit.messages)
        else "source",
        provider=result.provider,
        requested_model=selected_model,
        observed_model=result.observed_model,
        active_record_ids=[record.record_id for record in records],
        source_references={
            str(record.record_id): candidate.source_message_ids
            for record, candidate in zip(records, response.candidates, strict=True)
        },
        excluded_message_ids=response.excluded_message_ids,
        unresolved_message_ids=response.unresolved_message_ids,
        unresolved_reasons=["Source evidence remains unresolved."]
        if response.unresolved_message_ids
        else [],
        status="completed-with-unresolved"
        if response.unresolved_message_ids
        else "completed",
        attempts=len(usages),
        usage=usages,
    )
    with workspace_lock(workspace):
        if load_workspace(workspace) != config:
            raise ValueError("Workspace configuration changed during extraction")
        cached = _existing(
            workspace, source_session_id, unit, input_hash, extractor_hash
        )
        if cached is not None:
            return cached
        created, unchanged = publish_extraction(
            workspace, PendingExtraction(receipt=receipt, records=records)
        )
    return ExtractionOutcome(
        created=created,
        reused=unchanged,
        unresolved_message_ids=response.unresolved_message_ids,
        attempts=len(usages),
        usage=usages,
    )
