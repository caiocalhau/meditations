"""Readable private checkpoints and deterministic daily-source preparation."""

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from meditations.contracts import (
    CaptureDraft,
    CaptureResult,
    CaptureSource,
    DayPreparation,
)
from meditations.files import atomic_write, workspace_directory, workspace_lock
from meditations.machine_config import MachineConfig

TEMPLATE_VERSION = "daily-report-v1"
DAILY_MARKER = re.compile(r"<!--\s*meditations:sources:([0-9a-f]{64})\s*-->")
START = b"<!-- meditations:generated:start -->"
END = b"<!-- meditations:generated:end -->"


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _managed_directory(workspace: Path, relative: str) -> Path:
    directory = workspace_directory(workspace, relative)
    for item in (directory, *directory.parents):
        if item == workspace.parent:
            break
        if item.is_symlink():
            raise ValueError("Managed vault path cannot contain a symbolic link")
    return directory


def _capture_directory(workspace: Path, day: date) -> Path:
    return _managed_directory(workspace, f"engineering/captures/{day.isoformat()}")


def _daily_directory(workspace: Path) -> Path:
    return _managed_directory(workspace, "engineering/daily")


def _normalize_body(body: str) -> str:
    return body.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


def _time_key(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def save_capture(
    workspace: Path,
    day: date,
    draft: CaptureDraft,
    *,
    captured_at: datetime,
) -> CaptureResult:
    body = _normalize_body(draft.body)
    body_bytes = body.encode("utf-8")
    if len(body_bytes) > 65536:
        raise ValueError("Capture exceeds the 64 KiB local storage limit")
    capture_id = _digest(day.isoformat().encode() + b"\0" + body_bytes)
    if captured_at.tzinfo is None:
        raise ValueError("Capture timestamp must include a timezone")
    captured_at = captured_at.astimezone(timezone.utc)
    timestamp = captured_at.isoformat()
    payload = (
        "---\n"
        "meditations_capture: 1\n"
        f"date: {day.isoformat()}\n"
        f"capture_id: {capture_id}\n"
        f"captured_at: {timestamp}\n"
        "---\n\n"
    ).encode() + body_bytes
    directory = _capture_directory(workspace, day)
    with workspace_lock(workspace):
        directory.mkdir(parents=True, exist_ok=True)
        existing = load_captures(workspace, day)
        if any(source.capture_id == capture_id for source in existing):
            path = next(
                item
                for item in sorted(directory.glob(f"{capture_id}-*.md"))
                if not item.is_symlink()
            )
            return CaptureResult(
                status="unchanged", path=str(path), capture_id=capture_id
            )
        path = directory / f"{capture_id}-{_time_key(captured_at)}.md"
        if path.is_symlink():
            raise ValueError("Refusing to replace a symbolic-link capture")
        original = path.read_bytes() if path.exists() else None
        if original is not None:
            _parse_capture(original, day, capture_id)
            return CaptureResult(
                status="unchanged", path=str(path), capture_id=capture_id
            )
        atomic_write(path, payload, expected=None)
    return CaptureResult(status="created", path=str(path), capture_id=capture_id)


def _parse_capture(content: bytes, day: date, expected_id: str) -> CaptureSource:
    try:
        header, body_bytes = content.split(b"\n---\n\n", maxsplit=1)
        lines = header.decode("utf-8").splitlines()
        metadata = dict(line.split(": ", maxsplit=1) for line in lines[1:])
        body = body_bytes.decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError("Invalid Markdown capture frontmatter or encoding") from error
    if (
        lines[:4]
        != [
            "---",
            "meditations_capture: 1",
            f"date: {day.isoformat()}",
            f"capture_id: {expected_id}",
        ]
        or len(lines) != 5
        or set(metadata) != {"meditations_capture", "date", "capture_id", "captured_at"}
        or metadata["meditations_capture"] != "1"
        or metadata["date"] != day.isoformat()
        or metadata["capture_id"] != expected_id
        or not metadata.get("captured_at")
    ):
        raise ValueError("Invalid Markdown capture metadata")
    try:
        captured_at = datetime.fromisoformat(metadata["captured_at"])
    except ValueError as error:
        raise ValueError("Invalid capture timestamp") from error
    if captured_at.tzinfo is None:
        raise ValueError("Capture timestamp must include a timezone")
    normalized = _normalize_body(body)
    calculated = _digest(day.isoformat().encode() + b"\0" + normalized.encode())
    if calculated != expected_id or normalized != body:
        raise ValueError("Capture content does not match its content identity")
    return CaptureSource(
        capture_id=expected_id,
        body=body.rstrip("\n"),
        captured_at=captured_at,
        file_sha256=_digest(content),
    )


def load_captures(workspace: Path, day: date) -> list[CaptureSource]:
    directory = _capture_directory(workspace, day)
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ValueError("Capture directory is not a directory")
    sources: list[CaptureSource] = []
    for path in sorted(directory.glob("*.md")):
        if path.is_symlink():
            raise ValueError("Invalid capture filename or symbolic link")
        match = re.fullmatch(r"([0-9a-f]{64})-([0-9]{8}T[0-9]{12}Z)", path.stem)
        if not match:
            raise ValueError("Invalid capture filename identity")
        source = _parse_capture(path.read_bytes(), day, match.group(1))
        if _time_key(source.captured_at) != match.group(2):
            raise ValueError("Capture timestamp does not match its filename")
        sources.append(source)
    unique: dict[str, CaptureSource] = {}
    for source in sources:
        previous = unique.get(source.capture_id)
        if previous is None or source.captured_at < previous.captured_at:
            unique[source.capture_id] = source
    return sorted(unique.values(), key=lambda item: (item.captured_at, item.capture_id))


def _previous_note(directory: Path, day: date) -> str | None:
    candidates: list[date] = []
    if not directory.exists():
        return None
    for path in directory.glob("*.md"):
        if path.is_symlink():
            raise ValueError("Daily-note directory contains a symbolic link")
        try:
            candidate = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if candidate < day:
            candidates.append(candidate)
    return f"[[{max(candidates).isoformat()}]]" if candidates else None


def _note_path(workspace: Path, day: date) -> Path:
    return _daily_directory(workspace) / f"{day.isoformat()}.md"


def prepare_day(config: MachineConfig, day: date) -> DayPreparation:
    directory = _daily_directory(config.workspace)
    note_path = directory / f"{day.isoformat()}.md"
    previous = _previous_note(directory, day)
    try:
        sources = load_captures(config.workspace, day)
        if note_path.is_symlink():
            raise ValueError("Refusing to read a symbolic-link daily note")
        note_bytes = note_path.read_bytes() if note_path.exists() else None
        note_hash = _digest(note_bytes) if note_bytes is not None else None
        snapshot_data = {
            "date": day.isoformat(),
            "language": config.language,
            "timezone": config.timezone,
            "template": TEMPLATE_VERSION,
            "previous_note": previous,
            "captures": [source.file_sha256 for source in sources],
        }
        snapshot = _digest(
            json.dumps(snapshot_data, sort_keys=True, separators=(",", ":")).encode()
        )
        if not sources:
            status = "empty"
            message = "No captures exist for this work date."
        elif note_bytes is not None and not _has_valid_note_boundaries(note_bytes):
            status = "conflict"
            message = "Existing note has no valid generated section; it was preserved."
        elif note_bytes is not None and _has_current_snapshot(note_bytes, snapshot):
            status = "unchanged"
            message = "Captures and note settings are unchanged; composition skipped."
        else:
            status = "ready"
            message = None
        return DayPreparation(
            status=status,
            day=day,
            language=config.language,
            source_snapshot=snapshot,
            expected_note_sha256=note_hash,
            captures=sources if status == "ready" else [],
            previous_note=previous,
            message=message,
        )
    except (ValueError, OSError) as error:
        return DayPreparation(
            status="conflict",
            day=day,
            language=config.language,
            source_snapshot="0" * 64,
            expected_note_sha256=None,
            captures=[],
            previous_note=previous,
            message=str(error),
        )


def source_snapshot(config: MachineConfig, day: date) -> str:
    return prepare_day(config, day).source_snapshot


def _has_current_snapshot(note_bytes: bytes, snapshot: str) -> bool:
    try:
        note = note_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return False
    match = DAILY_MARKER.search(note)
    return match is not None and match.group(1) == snapshot


def _has_valid_note_boundaries(note_bytes: bytes) -> bool:
    if note_bytes.count(START) != 1 or note_bytes.count(END) != 1:
        return False
    try:
        return note_bytes.index(START) + len(START) <= note_bytes.index(END)
    except ValueError:
        return False


def note_path(config: MachineConfig, day: date) -> Path:
    return _note_path(config.workspace, day)
