"""Read a bounded, text-only view of authorized Codex session transcripts."""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from meditations.extraction.contracts import SourceMessage

MAX_TRANSCRIPT_BYTES = 64 * 1024 * 1024
MAX_LINE_BYTES = 2 * 1024 * 1024
ADAPTER_VERSION = "codex-jsonl-v1"
_TEXT_BLOCKS = {"input_text", "output_text"}
_OUTPUT_TYPES = {"function_call_output", "custom_tool_call_output"}
_INTERNAL_ORIGINATORS = {
    "codex_exec",
    "subagent",
    "reviewer",
    "extractor",
    "meditations-journal-extraction",
}


@dataclass(frozen=True)
class SessionSelection:
    session_id: str
    cli_version: str | None
    messages: tuple[SourceMessage, ...]
    omission_counts: dict[str, int]
    adapter_version: str = ADAPTER_VERSION


@dataclass(frozen=True)
class DaySelection:
    sessions: tuple[SessionSelection, ...]
    diagnostics: tuple[str, ...]


def read_day(
    sessions_dir: Path,
    repositories: tuple[Path, ...],
    day: date,
    timezone: str,
    *,
    excluded_session_ids: frozenset[str] = frozenset(),
) -> DaySelection:
    """Select day text from all repositories, or explicitly narrowed roots."""
    if any(
        not re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", value)
        for value in excluded_session_ids
    ):
        raise ValueError("Use valid opaque session IDs for exclusions")
    try:
        zone = ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("Invalid workspace timezone") from error
    if sessions_dir.is_symlink():
        raise ValueError("Sessions source must be a real directory")
    if not sessions_dir.exists():
        return DaySelection(
            (), ("Sessions directory does not exist; no sessions scanned",)
        )
    source_root = sessions_dir.resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError("Sessions source must be a real directory")
    authorized = {path.resolve(strict=True) for path in repositories}
    if any(not path.is_dir() for path in authorized):
        raise ValueError("Repository filters must be existing directories")

    diagnostics: list[str] = []
    selected: list[SessionSelection] = []
    seen_ids: set[str] = set()
    for path in sorted(source_root.rglob("*.jsonl")):
        if path.is_symlink():
            raise ValueError("Symlink transcript is not allowed")
        try:
            metadata, snapshot, stat_before = _read_authorized_snapshot(
                path, authorized, excluded_session_ids
            )
        except _NotAuthorized:
            continue
        except _MissingMetadata as error:
            diagnostics.append(str(error))
            continue
        session_id = _metadata_text(metadata, "id") or _metadata_text(
            metadata, "session_id"
        )
        if not session_id:
            diagnostics.append("Session metadata is missing a session ID")
            continue
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", session_id):
            diagnostics.append("Session metadata contains an unsupported session ID")
            continue
        if session_id in seen_ids:
            raise ValueError("Duplicate session ID in selected source")
        seen_ids.add(session_id)
        if metadata.get("parent_thread_id"):
            diagnostics.append("Subagent session omitted")
            continue
        originator = _metadata_text(metadata, "originator")
        thread_source = _metadata_text(metadata, "thread_source")
        if (
            originator and originator.casefold() in _INTERNAL_ORIGINATORS
        ) or thread_source == "meditations-journal-extraction":
            diagnostics.append("Internal Codex session omitted")
            continue
        events, partial = _parse_snapshot(snapshot)
        if _snapshot_changed(path, stat_before):
            raise ValueError("Transcript changed while being read; retry selection")
        messages: list[SourceMessage] = []
        omissions: dict[str, int] = {}
        if partial:
            diagnostics.append(f"Session {session_id}: incomplete final line omitted")
            omissions["incomplete_line"] = 1
        for line_number, event in events[1:]:
            if event is None:
                _count(omissions, "oversized_line")
                diagnostics.append(
                    f"Session {session_id}: line {line_number} exceeds 2 MiB and was "
                    "omitted; its date, type and content are unknown"
                )
                continue
            timestamp = _parse_timestamp(event.get("timestamp"))
            kind = event.get("type")
            if kind != "response_item":
                continue
            payload_value = event.get("payload")
            if not isinstance(payload_value, dict):
                _count(omissions, "unsupported_shape")
                continue
            payload = cast(dict[str, Any], payload_value)
            if timestamp is None:
                if _could_be_conversational(payload):
                    _count(omissions, "missing_timestamp")
                continue
            if timestamp.astimezone(zone).date() != day:
                continue
            normalized = _normalize_payload(payload, omissions)
            if normalized is None:
                continue
            role, content = normalized
            try:
                messages.append(
                    SourceMessage(
                        message_id=f"codex:{session_id}:{line_number}",
                        role=cast(Literal["user", "assistant", "tool"], role),
                        content=content,
                        occurred_at=timestamp,
                        context_only=False,
                        timestamp_basis="source",
                    )
                )
            except Exception as error:
                raise ValueError("Selected transcript contains invalid text") from error
        if messages or omissions:
            selected.append(
                SessionSelection(
                    session_id=session_id,
                    cli_version=_metadata_text(metadata, "cli_version"),
                    messages=tuple(messages),
                    omission_counts=omissions,
                )
            )
    return DaySelection(tuple(selected), tuple(diagnostics))


class _NotAuthorized(Exception):
    pass


class _MissingMetadata(Exception):
    pass


def _read_authorized_snapshot(
    path: Path, authorized: set[Path], excluded_session_ids: frozenset[str]
) -> tuple[dict[str, Any], bytes, os.stat_result]:
    file_descriptor: int | None = None
    try:
        flags = (
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        file_descriptor = os.open(path, flags)
        before = os.fstat(file_descriptor)
        if not stat.S_ISREG(before.st_mode):
            return {}, b"", before
        with os.fdopen(file_descriptor, "rb") as source:
            file_descriptor = None
            first = source.readline(min(MAX_LINE_BYTES + 1, before.st_size))
            if len(first) > MAX_LINE_BYTES:
                raise _MissingMetadata("Session metadata line exceeds the limit")
            if not first.endswith(b"\n"):
                raise _MissingMetadata("Session metadata is incomplete")
            try:
                envelope: Any = json.loads(first)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise _MissingMetadata("Session metadata is malformed") from error
            envelope_dict = (
                cast(dict[str, Any], envelope) if isinstance(envelope, dict) else {}
            )
            metadata_value: Any = envelope_dict.get("payload")
            metadata = (
                cast(dict[str, Any], metadata_value)
                if isinstance(metadata_value, dict)
                else None
            )
            if (
                not isinstance(metadata, dict)
                or envelope_dict.get("type") != "session_meta"
            ):
                raise _MissingMetadata("Session metadata is missing or unsupported")
            session_id = _metadata_text(metadata, "id") or _metadata_text(
                metadata, "session_id"
            )
            if session_id in excluded_session_ids:
                raise _NotAuthorized
            if authorized:
                cwd = _metadata_text(metadata, "cwd")
                if cwd is None:
                    raise _MissingMetadata("Session repository metadata is missing")
                if Path(cwd).resolve(strict=False) not in authorized:
                    raise _NotAuthorized
            chunks = [first]
            size = len(first)
            if before.st_size > MAX_TRANSCRIPT_BYTES:
                raise ValueError("Selected transcript exceeds the 64 MiB limit")
            while size < before.st_size:
                chunk = source.read(min(1024 * 1024, before.st_size - size))
                if not chunk:
                    raise ValueError("Transcript was truncated while being read; retry")
                chunks.append(chunk)
                size += len(chunk)
            after = os.fstat(source.fileno())
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ) and after.st_size <= before.st_size:
                raise ValueError("Transcript changed while being read; retry selection")
        return metadata, b"".join(chunks), before
    except OSError as error:
        raise ValueError("Unable to read session transcript") from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


def _parse_snapshot(
    snapshot: bytes,
) -> tuple[list[tuple[int, dict[str, Any] | None]], bool]:
    complete = snapshot.endswith(b"\n")
    lines = snapshot.splitlines(keepends=True)
    partial = not complete
    if partial and lines:
        lines = lines[:-1]
    events: list[tuple[int, dict[str, Any] | None]] = []
    for line_number, line in enumerate(lines, start=1):
        if len(line) > MAX_LINE_BYTES:
            events.append((line_number, None))
            continue
        try:
            value: Any = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(
                "Selected transcript contains a malformed complete line"
            ) from error
        if not isinstance(value, dict):
            raise ValueError(
                "Selected transcript contains an unsupported complete line"
            )
        events.append((line_number, cast(dict[str, Any], value)))
    metadata = events[0][1] if events else None
    if metadata is None or metadata.get("type") != "session_meta":
        raise ValueError("Selected transcript metadata changed; retry selection")
    return events, partial


def _snapshot_changed(path: Path, before: os.stat_result) -> bool:
    try:
        after = path.stat(follow_symlinks=False)
    except OSError:
        return True
    return (
        after.st_ino != before.st_ino
        or after.st_size < before.st_size
        or (after.st_size == before.st_size and after.st_mtime_ns != before.st_mtime_ns)
    )


def _normalize_payload(
    payload: dict[str, Any], omissions: dict[str, int]
) -> tuple[str, str] | None:
    item_type = payload.get("type")
    if item_type == "message":
        role = payload.get("role")
        if role not in {"user", "assistant"}:
            if role in {"developer", "system"}:
                _count(omissions, "instruction_message")
            return None
        content_value = payload.get("content")
        if not isinstance(content_value, list):
            _count(omissions, "unsupported_shape")
            return None
        content = cast(list[Any], content_value)
        pieces: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                _count(omissions, "unsupported_block")
                continue
            block_dict = cast(dict[str, Any], block)
            if block_dict.get("type") in _TEXT_BLOCKS and isinstance(
                block_dict.get("text"), str
            ):
                pieces.append(cast(str, block_dict["text"]))
            elif block_dict.get("type") == "reasoning":
                _count(omissions, "reasoning_block")
            elif block_dict.get("type") not in {"refusal", "summary_text"}:
                _count(omissions, "nontext_block")
        joined = "\n".join(part for part in pieces if part.strip()).strip()
        if joined:
            return role, joined
        if not pieces:
            _count(omissions, "empty_or_nontext_message")
        return None
    if item_type in _OUTPUT_TYPES:
        output = payload.get("output")
        if isinstance(output, str) and output.strip():
            return "tool", output.strip()
        _count(omissions, "nontext_tool_output")
        return None
    if item_type in {"custom_tool_call", "function_call", "mcp_tool_call"}:
        _count(omissions, "action_invocation")
        return None
    if item_type == "reasoning":
        _count(omissions, "reasoning_item")
        return None
    if item_type in {"compaction", "ghost_snapshot"}:
        return None
    if item_type:
        _count(omissions, "unsupported_conversational_shape")
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (
        parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    )


def _metadata_text(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _could_be_conversational(payload: dict[str, Any]) -> bool:
    return payload.get("type") == "message" or payload.get("type") in _OUTPUT_TYPES


def _count(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1
