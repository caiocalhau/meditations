from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, TypeAdapter, ValidationError

from meditations.codex_config import resolve_model
from meditations.config import load_workspace
from meditations.extraction.codex_exec import (
    CodexExecProvider,
    runtime_policy_fingerprint,
)
from meditations.extraction.contracts import Contract
from meditations.extraction.privacy import (
    FilteringProvider,
    PrivacySettings,
    filter_input,
)
from meditations.extraction.prompt import request_payload
from meditations.extraction.provider import ExtractionProvider, ExtractionRequest
from meditations.extraction.service import ExtractionSettings, extract_unit
from meditations.extraction.validation import (
    MAX_INPUT_BYTES,
    validate_input,
    validate_unit_size,
)
from meditations.records import Text


class RuntimeApproval(Contract):
    schema_version: Literal[2]
    executable_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    runtime_policy_sha256: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    models: list[Text]
    isolation_reviewed: Annotated[bool, Field(strict=True)]


def add_extract_command(
    add_parser: Callable[..., argparse.ArgumentParser],
) -> None:
    child = add_parser(
        "extract", help="Preview or explicitly extract a normalized conversation"
    )
    child.add_argument("--workspace", type=Path)
    child.add_argument("--input", type=Path, required=True)
    mode = child.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        "--preview",
        dest="preview",
        action="store_true",
        help="Preview input without model calls or workspace writes",
    )
    mode.add_argument("--run-model", action="store_true", help=argparse.SUPPRESS)
    child.add_argument("--model", help="Override the model in global Codex config.toml")
    child.add_argument("--escalation-model")
    child.add_argument("--occurred-at")
    child.add_argument("--show-payload", action="store_true")
    child.add_argument(
        "--redact-file", type=Path, help="Private JSON list of known sensitive literals"
    )
    child.add_argument(
        "--runtime-approval",
        type=Path,
        help="Private operator-reviewed runtime capability record",
    )


def _read_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Input exceeds the file limit")
    return data


def privacy_settings(path: Path | None) -> PrivacySettings:
    if path is None:
        return PrivacySettings()
    try:
        values = TypeAdapter(list[Text]).validate_json(_read_bounded(path, 64 * 1024))
    except ValueError as error:
        raise ValueError("Invalid private literal filter file") from error
    return PrivacySettings(literals=tuple(values))


def reviewed_provider(path: Path | None, models: list[str]) -> CodexExecProvider:
    if path is None:
        raise ValueError("Live extraction requires a reviewed runtime approval file")
    try:
        approval = RuntimeApproval.model_validate_json(_read_bounded(path, 64 * 1024))
    except ValidationError as error:
        raise ValueError("Invalid runtime approval file") from error
    executable = shutil.which("codex")
    if executable is None:
        raise ValueError("Codex executable is unavailable")
    fingerprint = hashlib.sha256(Path(executable).resolve().read_bytes()).hexdigest()
    if (
        approval.schema_version != 2
        or not approval.isolation_reviewed
        or approval.executable_sha256 != fingerprint
        or approval.runtime_policy_sha256 != runtime_policy_fingerprint()
        or not set(models).issubset(approval.models)
    ):
        raise ValueError(
            "Runtime approval does not cover this executable, policy and models"
        )
    return CodexExecProvider(executable=executable, runtime_reviewed=True)


def extract_command(
    args: argparse.Namespace,
    provider: ExtractionProvider | None = None,
    state_directory: Path | None = None,
) -> int:
    config = load_workspace(args.workspace)
    if args.show_payload and not args.preview:
        raise ValueError("Showing source payload requires preview mode")
    override = None
    if args.occurred_at:
        try:
            override = datetime.fromisoformat(args.occurred_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Invalid occurrence override") from error
    privacy = privacy_settings(args.redact_file)
    source = filter_input(
        validate_input(_read_bounded(args.input, MAX_INPUT_BYTES), config, override),
        privacy,
    )
    for effective_unit in source.units:
        validate_unit_size(effective_unit)
    if args.preview:
        units: list[dict[str, object]] = []
        for unit in source.units:
            item: dict[str, object] = {
                "unit_id": unit.unit_id,
                "revision": unit.source_revision,
                "message_ids": [message.message_id for message in unit.messages],
                "input_bytes": len(unit.model_dump_json().encode()),
                "timestamp_basis": "user-supplied"
                if any(
                    message.timestamp_basis == "user-supplied"
                    for message in unit.messages
                )
                else "source",
            }
            if args.show_payload:
                item["payload"] = request_payload(
                    ExtractionRequest(
                        unit=unit,
                        model=args.model or "<select-model>",
                        language=config.language,
                    )
                )
            units.append(item)
        print(
            json.dumps(
                {
                    "mode": "preview",
                    "known_literal_filters": len(privacy.literals),
                    "credential_filter": True,
                    "units": units,
                }
            )
        )
        return 0
    args.model = resolve_model(args.model)
    models = [args.model] + ([args.escalation_model] if args.escalation_model else [])
    if provider is None:
        provider = reviewed_provider(args.runtime_approval, models)
    runtime_fingerprint = "test-provider"
    if isinstance(provider, CodexExecProvider):
        executable_fingerprint = hashlib.sha256(
            Path(provider.executable).resolve().read_bytes()
        ).hexdigest()
        runtime_fingerprint = hashlib.sha256(
            f"{executable_fingerprint}:{runtime_policy_fingerprint()}".encode()
        ).hexdigest()
    privacy_fingerprint = hashlib.sha256(
        json.dumps(privacy.literals).encode()
    ).hexdigest()
    provider = FilteringProvider(provider, privacy)
    outcomes: list[dict[str, object]] = []
    failed = False
    for unit in source.units:
        result = extract_unit(
            args.workspace,
            source.source_session_id,
            unit,
            provider,
            ExtractionSettings(
                model=args.model,
                language=config.language,
                escalation_model=args.escalation_model,
                state_directory=state_directory,
                privacy_fingerprint=privacy_fingerprint,
                runtime_fingerprint=runtime_fingerprint,
            ),
        )
        outcomes.append(
            {
                "unit_id": unit.unit_id,
                "created": result.created,
                "reused": result.reused,
                "attempts": result.attempts,
                "unresolved_message_ids": result.unresolved_message_ids,
                "failure_category": result.failure_category,
                "failure_detail": result.failure_detail,
                "usage": [usage.model_dump() for usage in result.usage],
            }
        )
        failed |= result.failure_category is not None
        if failed:
            break
    print(
        json.dumps(
            {
                "mode": "extraction",
                "units": outcomes,
                "render": "Run meditations render after reviewing extraction status.",
            }
        )
    )
    return 1 if failed else 0
