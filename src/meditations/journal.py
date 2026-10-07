"""Build deterministic bounded conversation inputs from selected sessions."""

import argparse
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from datetime import date
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from meditations.codex_config import resolve_model
from meditations.composition import (
    MAX_COMPOSITION_BYTES,
    CompositionBudgetError,
    CompositionProvider,
    CompositionRequest,
    CompositionResult,
    LearningResourceError,
    cached_composition,
    compose_day,
    composition_payload,
    day_records,
    evidence_fingerprint,
    prepare_composition_request,
    validate_daily_completion,
)
from meditations.config import WorkspaceConfig, load_workspace, validate_workspace_path
from meditations.diagnostics import load_composition_failure, save_composition_failure
from meditations.extraction.cli import privacy_settings, reviewed_provider
from meditations.extraction.contracts import (
    ConversationInput,
    ConversationUnit,
    SourceMessage,
    Usage,
)
from meditations.extraction.privacy import (
    FilteringProvider,
    PrivacySettings,
    filter_input,
)
from meditations.extraction.prompt import request_payload
from meditations.extraction.provider import (
    ExtractionProvider,
    ExtractionRequest,
    ProviderError,
)
from meditations.extraction.receipts import select_active_records
from meditations.extraction.service import ExtractionSettings, extract_unit
from meditations.extraction.validation import (
    MAX_UNIT_BYTES,
    validate_unit_size,
)
from meditations.files import atomic_write, workspace_directory, workspace_lock
from meditations.records import EvidenceRecord
from meditations.render import (
    START,
    daily_frontmatter,
    generated_bounds,
    render_daily,
    update_daily_note,
)
from meditations.sessions import DaySelection, read_day
from meditations.store import load_records


def build_day_inputs(
    selection: DaySelection, day: date, revision: int
) -> list[ConversationInput]:
    """Build one extraction input per session, splitting at existing limits."""
    if revision < 0:
        raise ValueError("Source revision must be non-negative")
    results: list[ConversationInput] = []
    for session in sorted(selection.sessions, key=lambda item: item.session_id):
        if not session.messages:
            continue
        ordered = sorted(
            session.messages,
            key=lambda message: (message.occurred_at, message.message_id),
        )
        chunks: list[list[SourceMessage]] = []
        current: list[SourceMessage] = []
        for message in ordered:
            if message.context_only or message.occurred_at is None:
                raise ValueError("Journal messages require timestamped day evidence")
            candidate = [*current, message]
            if (
                len(candidate) > 200
                or _unit_size(session.session_id, day, revision, len(chunks), candidate)
                > MAX_UNIT_BYTES
            ):
                if not current:
                    raise ValueError(
                        "A single message exceeds the conversation unit limit"
                    )
                chunks.append(current)
                current = [message]
                if (
                    _unit_size(session.session_id, day, revision, len(chunks), current)
                    > MAX_UNIT_BYTES
                ):
                    raise ValueError(
                        "A single message exceeds the conversation unit limit"
                    )
            else:
                current = candidate
        if current:
            chunks.append(current)
        units = [
            ConversationUnit(
                unit_id=_unit_id(session.session_id, day, index),
                source_revision=revision,
                task_id=f"codex-session:{session.session_id}",
                task_label="Codex session",
                messages=chunk,
            )
            for index, chunk in enumerate(chunks)
        ]
        results.append(
            ConversationInput(
                schema_version=1,
                source_agent="codex",
                source_session_id=session.session_id,
                units=units,
            )
        )
    return results


def add_journal_command(
    add_parser: Callable[..., argparse.ArgumentParser],
) -> None:
    child = add_parser("journal", help="Preview or process a selected Codex day")
    child.add_argument("--workspace", type=Path)
    child.add_argument(
        "--date", required=True, help="Local occurrence date, YYYY-MM-DD"
    )
    child.add_argument(
        "--repo",
        type=Path,
        action="append",
        default=[],
        help="Optionally restrict selection to these repository roots",
    )
    child.add_argument(
        "--exclude-session",
        action="append",
        default=[],
        metavar="SESSION_ID",
        help="Exclude a session in addition to workspace exclusions (repeatable)",
    )
    child.add_argument("--sessions-dir", type=Path)
    mode = child.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        "--preview",
        dest="dry_run",
        action="store_true",
        help="Preview selection without model calls or workspace writes",
    )
    mode.add_argument("--run-model", action="store_true", help=argparse.SUPPRESS)
    child.add_argument("--model", help="Override the model in global Codex config.toml")
    child.add_argument("--runtime-approval", type=Path)
    child.add_argument("--redact-file", type=Path)
    child.add_argument("--revision", type=int, help=argparse.SUPPRESS)
    child.add_argument("--max-units", type=int, default=10)
    child.add_argument("--show-payload", action="store_true")
    child.add_argument("--json", action="store_true", dest="json_output")
    child.add_argument(
        "--from-records",
        action="store_true",
        help="Compose stored evidence without reading transcripts",
    )
    child.add_argument(
        "--output",
        type=Path,
        help="Write a separate Markdown candidate, preserving the daily baseline",
    )


def journal_command(
    args: argparse.Namespace,
    provider: ExtractionProvider | None = None,
    state_directory: Path | None = None,
    *,
    composer: CompositionProvider | None = None,
) -> int:
    workspace = validate_workspace_path(args.workspace)
    config = load_workspace(workspace)
    try:
        day = date.fromisoformat(args.date)
    except ValueError as error:
        raise ValueError("Invalid journal date; use YYYY-MM-DD") from error
    if args.revision is not None and args.revision < 0:
        raise ValueError("Revision must be non-negative")
    if args.max_units <= 0:
        raise ValueError("Maximum units must be positive")
    if args.show_payload and not args.dry_run:
        raise ValueError("Showing source payload requires --dry-run")
    sessions_dir = args.sessions_dir
    if sessions_dir is None:
        codex_home = os.environ.get("CODEX_HOME")
        sessions_dir = (
            Path(codex_home) / "sessions"
            if codex_home
            else Path.home() / ".codex/sessions"
        )
    excluded_session_ids = frozenset(
        [*config.excluded_session_ids, *args.exclude_session]
    )
    if args.from_records and (args.repo or args.sessions_dir or args.exclude_session):
        raise ValueError(
            "--from-records cannot be combined with transcript selection options"
        )
    if args.output is not None:
        candidate = args.output.expanduser().absolute()
        validate_workspace_path(candidate.parent)
        if candidate.suffix != ".md" or any(
            candidate.resolve().is_relative_to(
                workspace_directory(workspace, folder).resolve()
            )
            for folder in (
                "engineering/daily",
                "records",
                "extractions",
                "compositions",
            )
        ):
            raise ValueError("--output requires a separate private Markdown path")
        args.output = candidate
    selection = (
        DaySelection((), ())
        if args.from_records
        else read_day(
            sessions_dir,
            tuple(args.repo),
            day,
            config.timezone,
            excluded_session_ids=excluded_session_ids,
        )
    )
    privacy = privacy_settings(args.redact_file)
    inputs = [
        filter_input(source, privacy)
        for source in build_day_inputs(selection, day, args.revision or 0)
    ]
    units = [unit for source in inputs for unit in source.units]
    for unit in units:
        validate_unit_size(unit)
    if len(units) > args.max_units and not args.dry_run:
        raise ValueError(
            f"Selected day has {len(units)} units, above --max-units {args.max_units}"
        )
    active = select_active_records(workspace, load_records(workspace))
    stored = day_records(active, config, day)
    composition_bytes = (
        len(
            composition_payload(
                prepare_composition_request(
                    stored, config, day, args.model or "<select-model>", privacy
                )
            ).encode()
        )
        if stored
        else None
    )
    if args.dry_run:
        preview: dict[str, object] = {
            "mode": "preview",
            "date": day.isoformat(),
            "timezone": config.timezone,
            "selection_scope": (
                "selected-repositories" if args.repo else "all-local-repositories"
            ),
            "configured_exclusion_count": len(excluded_session_ids),
            "session_count": len(selection.sessions),
            "message_count": sum(len(item.messages) for item in selection.sessions),
            "unit_count": len(units),
            "unit_ids": [unit.unit_id for unit in units],
            "max_units": args.max_units,
            "attempts_note": (
                "Maximum attempts is an upper bound before receipt reuse. "
                "Payload bytes exclude runtime-added context and do not estimate "
                "subscription quota."
            ),
            "maximum_attempts": 2 * len(units) + (1 if units or stored else 0),
            "evidence_record_count": len(stored),
            "composition_input_bytes": composition_bytes,
            "max_composition_bytes": MAX_COMPOSITION_BYTES,
            "extraction_payload_bytes": [
                len(
                    request_payload(
                        ExtractionRequest(
                            unit=unit,
                            model=args.model or "<select-model>",
                            language=config.language,
                        )
                    ).encode()
                )
                for unit in units
            ],
            "last_composition_failure": load_composition_failure(
                workspace, config, day, active
            ),
            "run_allowed": len(units) <= args.max_units
            and (
                composition_bytes is None or composition_bytes <= MAX_COMPOSITION_BYTES
            ),
            "sessions": [
                {
                    "session_id": item.session_id,
                    "cli_version": item.cli_version,
                    "adapter_version": item.adapter_version,
                    "message_count": len(item.messages),
                    "omissions": item.omission_counts,
                }
                for item in selection.sessions
            ],
            "diagnostics": list(selection.diagnostics),
            "coverage_note": (
                "Selected Codex conversations do not necessarily describe all work "
                "performed that day."
            ),
            "context_note": (
                "Only messages occurring on this date are sent; earlier session "
                "context is omitted."
            ),
            "model_calls": 0,
            "workspace_writes": 0,
        }
        if args.show_payload:
            preview["payloads"] = [
                request_payload(
                    ExtractionRequest(
                        unit=unit,
                        model=args.model or "<select-model>",
                        language=config.language,
                    )
                )
                for unit in units
            ]
        _emit(preview, args.json_output)
        return 0
    if composition_bytes is not None and composition_bytes > MAX_COMPOSITION_BYTES:
        error = CompositionBudgetError(composition_bytes)
        report_error = _save_failure(workspace, config, day, active, error)
        _emit(
            {
                "mode": "run",
                "date": day.isoformat(),
                "units": [],
                "day_complete": False,
                "note_status": "not-rendered",
                "note_message": str(error),
                "composition_status": "failed",
                "composition_error": error.details,
                "model_calls": 0,
                "diagnostic_report_error": report_error,
            },
            args.json_output,
        )
        return 1
    if not units:
        return _render_selected_day(
            workspace,
            day,
            [],
            selection.diagnostics,
            args.json_output,
            composer=composer
            or (
                cast(CompositionProvider, provider)
                if hasattr(provider, "compose")
                else None
            ),
            model=args.model,
            runtime_approval=args.runtime_approval,
            privacy=privacy,
            output=args.output,
            compose_enabled=provider is None
            or composer is not None
            or hasattr(provider, "compose"),
        )
    args.model = resolve_model(args.model)
    if provider is None:
        provider = reviewed_provider(args.runtime_approval, [args.model])
    privacy_fingerprint = hashlib.sha256(
        json.dumps(privacy.literals, separators=(",", ":")).encode()
    ).hexdigest()
    runtime_fingerprint = "test-provider"
    if hasattr(provider, "executable"):
        executable = Path(getattr(provider, "executable")).resolve()
        executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
        from meditations.extraction.codex_exec import runtime_policy_fingerprint

        runtime_fingerprint = hashlib.sha256(
            f"{executable_hash}:{runtime_policy_fingerprint()}".encode()
        ).hexdigest()
    filtered_provider = FilteringProvider(provider, privacy)
    outcomes: list[dict[str, object]] = []
    failed = False
    for source in inputs:
        for unit in source.units:
            outcome = extract_unit(
                workspace,
                source.source_session_id,
                unit,
                filtered_provider,
                ExtractionSettings(
                    model=args.model,
                    language=config.language,
                    state_directory=state_directory,
                    privacy_fingerprint=privacy_fingerprint,
                    runtime_fingerprint=runtime_fingerprint,
                ),
                automatic_revision=args.revision is None,
            )
            outcomes.append(
                {
                    "unit_id": unit.unit_id,
                    "created": outcome.created,
                    "reused": outcome.reused,
                    "attempts": outcome.attempts,
                    "unresolved_message_ids": outcome.unresolved_message_ids,
                    "failure_category": outcome.failure_category,
                    "failure_detail": outcome.failure_detail,
                    "usage": [usage.model_dump() for usage in outcome.usage],
                }
            )
            if outcome.failure_category or outcome.unresolved_message_ids:
                failed = True
                break
        if failed:
            break
    if failed:
        _emit(
            {
                "mode": "run",
                "date": day.isoformat(),
                "units": outcomes,
                "day_complete": False,
                "note_status": "not-rendered",
                "diagnostics": list(selection.diagnostics),
            },
            args.json_output,
        )
        return 1
    return _render_selected_day(
        workspace,
        day,
        outcomes,
        selection.diagnostics,
        args.json_output,
        composer=composer
        or (
            cast(CompositionProvider, provider)
            if hasattr(provider, "compose")
            else None
        ),
        model=args.model,
        runtime_approval=args.runtime_approval,
        privacy=privacy,
        output=args.output,
        compose_enabled=composer is not None or hasattr(provider, "compose"),
    )


class _CountingComposer:
    def __init__(self, provider: CompositionProvider) -> None:
        self.provider = provider
        self.calls = 0
        self.usage: Usage | None = None

    def compose(self, request: CompositionRequest) -> CompositionResult:
        self.calls += 1
        try:
            result = self.provider.compose(request)
        except ProviderError as error:
            self.usage = error.usage
            raise
        self.usage = result.usage
        return result


def _render_selected_day(
    workspace: Path,
    day: date,
    outcomes: list[dict[str, object]],
    diagnostics: tuple[str, ...],
    json_output: bool,
    *,
    composer: CompositionProvider | None = None,
    model: str | None = None,
    runtime_approval: Path | None = None,
    privacy: PrivacySettings = PrivacySettings(),
    output: Path | None = None,
    compose_enabled: bool = True,
) -> int:
    config = load_workspace(workspace)
    active = select_active_records(workspace, load_records(workspace))
    zone = ZoneInfo(config.timezone)
    day_records = [
        record for record in active if record.occurred_at.astimezone(zone).date() == day
    ]
    note_status = "no-evidence"
    note_path: str | None = None
    note_message: str | None = None
    baseline = (
        workspace_directory(workspace, "engineering/daily") / f"{day.isoformat()}.md"
    )
    path = output or baseline
    composition_status = "no-evidence"
    composition_calls = 0
    composition_usage: dict[str, object] | None = None
    composition = None
    try:
        validate_daily_completion(workspace, active, config, day)
        for existing in {path, baseline}:
            if existing.is_symlink():
                raise ValueError("Refusing a symbolic-link note")
            if existing.exists():
                generated_bounds(existing.read_bytes())
    except (ValueError, OSError) as error:
        _emit(
            {
                "mode": "run",
                "date": day.isoformat(),
                "units": outcomes,
                "day_complete": False,
                "note_status": "conflict",
                "note_message": f"{error}; existing note preserved",
                "model_calls": sum(cast(int, item["attempts"]) for item in outcomes),
            },
            json_output,
        )
        return 1
    counter: _CountingComposer | None = None
    if day_records and compose_enabled:
        try:
            selected_model = resolve_model(model)
            if composer is None:
                composer = reviewed_provider(runtime_approval, [selected_model])
            counter = _CountingComposer(composer)
            outcome = compose_day(
                workspace, config, day, active, counter, selected_model, privacy
            )
            composition = outcome.response
            composition_status = "reused" if outcome.reused else "created"
            composition_calls = outcome.attempts
            composition_usage = outcome.usage.model_dump()
        except (ValueError, OSError, ProviderError) as error:
            report_error = _save_failure(
                workspace,
                config,
                day,
                active,
                error,
                extraction_calls=sum(cast(int, item["attempts"]) for item in outcomes),
                composition_calls=counter.calls if counter else 0,
                usage=counter.usage if counter else None,
            )
            _emit(
                {
                    "mode": "run",
                    "date": day.isoformat(),
                    "units": outcomes,
                    "day_complete": False,
                    "note_status": "not-rendered",
                    "composition_status": "failed",
                    "composition_error": error.details
                    if isinstance(
                        error, (LearningResourceError, CompositionBudgetError)
                    )
                    else None,
                    "note_message": str(error),
                    "diagnostic_report_error": report_error,
                    "composition_usage": counter.usage.model_dump()
                    if counter and counter.usage
                    else None,
                    "diagnostics": list(diagnostics),
                    "model_calls": sum(cast(int, item["attempts"]) for item in outcomes)
                    + (counter.calls if counter else 0),
                },
                json_output,
            )
            return 1
    elif day_records:
        composition = cached_composition(workspace, config, day, active)
        composition_status = "cached" if composition is not None else "evidence-only"
    if day_records or path.exists():
        note_path = str(path)
        try:
            with workspace_lock(workspace):
                current_config = load_workspace(workspace)
                current = select_active_records(workspace, load_records(workspace))
                validate_daily_completion(workspace, current, current_config, day)
                if current_config != config or evidence_fingerprint(
                    current, config, day
                ) != evidence_fingerprint(active, config, day):
                    raise ValueError("Daily evidence changed before rendering")
                generated = render_daily(active, config, day, composition=composition)
                if output is not None and not path.exists() and baseline.exists():
                    original = baseline.read_bytes()
                    start, end = generated_bounds(original)
                    content = (
                        original[:start] + b"\n" + generated.encode() + original[end:]
                    )
                    if content.startswith(START):
                        content = daily_frontmatter(day).encode() + content
                    atomic_write(path, content)
                    note_status = "created"
                else:
                    note_status = update_daily_note(
                        path, generated, metadata=daily_frontmatter(day)
                    )
        except ValueError as error:
            note_status = "conflict"
            note_message = f"{error}; existing note preserved."
        except OSError:
            note_status = "failed"
            note_message = "Writing the daily note failed after extraction completed."
    result = {
        "mode": "run",
        "date": day.isoformat(),
        "units": outcomes,
        "day_complete": True,
        "note_status": note_status,
        "note_path": note_path,
        "note_message": note_message,
        "diagnostics": list(diagnostics),
        "composition_status": composition_status,
        "composition_usage": composition_usage,
        "model_calls": sum(cast(int, item["attempts"]) for item in outcomes)
        + composition_calls,
        "coverage_note": (
            "Selected Codex conversations do not necessarily describe all work "
            "performed that day."
        ),
    }
    _emit(result, json_output)
    return 1 if note_status in {"conflict", "failed"} else 0


def _save_failure(
    workspace: Path,
    config: WorkspaceConfig,
    day: date,
    records: list[EvidenceRecord],
    error: ValueError | OSError | ProviderError,
    *,
    extraction_calls: int = 0,
    composition_calls: int = 0,
    usage: Usage | None = None,
) -> str | None:
    try:
        save_composition_failure(
            workspace,
            config,
            day,
            records,
            error,
            extraction_calls=extraction_calls,
            composition_calls=composition_calls,
            usage=usage,
        )
    except (ValueError, OSError):
        return "Could not save private failure report; primary failure preserved"
    return None


def _emit(result: Mapping[str, object], json_output: bool) -> None:
    if json_output:
        print(json.dumps(result))
        return
    mode = str(result.get("mode", "journal"))
    print(f"Journal {mode}: {result.get('date', 'unknown date')}")
    for key in (
        "session_count",
        "selection_scope",
        "configured_exclusion_count",
        "message_count",
        "unit_count",
        "max_units",
        "maximum_attempts",
        "extraction_payload_bytes",
        "composition_input_bytes",
        "max_composition_bytes",
        "run_allowed",
        "attempts_note",
        "model_calls",
        "workspace_writes",
        "day_complete",
        "note_status",
        "note_path",
        "note_message",
        "composition_status",
        "composition_usage",
    ):
        if key in result:
            print(f"{key.replace('_', ' ').capitalize()}: {result[key]}")
    historical = result.get("last_composition_failure")
    if historical is not None:
        print(f"Saved composition failure (historical): {json.dumps(historical)}")
    if result.get("diagnostic_report_error"):
        print(f"Diagnostic report: {result['diagnostic_report_error']}")
    units = result.get("units")
    if isinstance(units, list):
        for unit_value in cast(list[object], units):
            if isinstance(unit_value, dict):
                unit = cast(dict[str, object], unit_value)
                print(
                    f"Unit {unit.get('unit_id')}: created={unit.get('created', 0)}, "
                    f"reused={unit.get('reused', 0)}, "
                    f"attempts={unit.get('attempts', 0)}, "
                    f"failure={unit.get('failure_category')}"
                )
                if unit.get("failure_detail"):
                    print(f"  Validation: {unit['failure_detail']}")
    sessions = result.get("sessions")
    if isinstance(sessions, list):
        for session_value in cast(list[object], sessions):
            if isinstance(session_value, dict):
                session = cast(dict[str, object], session_value)
                print(
                    f"Session {session.get('session_id')}: "
                    f"{session.get('message_count', 0)} messages, "
                    f"Codex {session.get('cli_version') or 'version unknown'}, "
                    f"adapter {session.get('adapter_version', 'unknown')}"
                )
                omissions = session.get("omissions")
                if isinstance(omissions, dict) and omissions:
                    print(f"  Omitted items: {omissions}")
    diagnostics = result.get("diagnostics", [])
    diagnostic_values = (
        cast(list[object], diagnostics) if isinstance(diagnostics, list) else []
    )
    for diagnostic in diagnostic_values:
        print(f"Coverage: {diagnostic}")
    payloads = result.get("payloads")
    if isinstance(payloads, list):
        print("Filtered source payload (explicitly requested):")
        for payload in cast(list[object], payloads):
            print(str(payload))
    for key in ("coverage_note", "context_note"):
        if key in result:
            print(str(result[key]))


def _unit_id(session_id: str, day: date, chunk: int) -> str:
    return f"journal:{session_id}:{day.isoformat()}:{chunk}"


def _unit_size(
    session_id: str,
    day: date,
    revision: int,
    chunk: int,
    messages: list[SourceMessage],
) -> int:
    return len(
        ConversationUnit(
            unit_id=_unit_id(session_id, day, chunk),
            source_revision=revision,
            task_id=f"codex-session:{session_id}",
            task_label="Codex session",
            messages=messages,
        )
        .model_dump_json()
        .encode()
    )
