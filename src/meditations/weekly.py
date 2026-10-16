"""Select weekly evidence without writing or invoking a model."""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

from meditations.captures import END, START
from meditations.files import managed_directory
from meditations.machine_config import MachineConfig, resolve_work_date
from meditations.weekly_contracts import WeeklySource, WeekPreparation

MAX_SOURCE_BYTES = 256 * 1024
MAX_NOTE_BYTES = 2 * 1024 * 1024
TEMPLATE = b"<!-- meditations:template:weekly-review-v1 -->"
PRACTICE_START = b"<!-- meditations:weekly:practice:start -->"
PRACTICE_END = b"<!-- meditations:weekly:practice:end -->"
SOURCE_MARKER = re.compile(rb"<!-- meditations:sources:([0-9a-f]{64}) -->")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def split_weekly(content: bytes) -> tuple[bytes, bytes, bytes]:
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError("Weekly note has no single valid generated section")
    begin, end = content.index(START) + len(START), content.index(END)
    if begin > end or content[begin:end].count(TEMPLATE) != 1:
        raise ValueError("Weekly note has invalid boundaries or unsupported format")
    prefix, generated, suffix = content[:begin], content[begin:end], content[end:]
    practice_text(suffix)
    return prefix, generated, suffix


def practice_text(suffix: bytes) -> bytes:
    if suffix.count(PRACTICE_START) != 1 or suffix.count(PRACTICE_END) != 1:
        raise ValueError("Weekly note has no single valid practice section")
    begin = suffix.index(PRACTICE_START) + len(PRACTICE_START)
    end = suffix.index(PRACTICE_END)
    if begin > end:
        raise ValueError("Weekly practice boundaries are out of order")
    return suffix[begin:end]


def read_note(path: Path, *, limit: int = MAX_NOTE_BYTES) -> bytes:
    if path.is_symlink():
        raise ValueError(f"Symbolic-link source/target refused: {path.name}")
    try:
        size = path.stat().st_size
        if size > limit:
            raise ValueError(
                f"{path.name}: {size} bytes exceeds the {limit} byte limit"
            )
        with path.open("rb") as stream:
            content = stream.read(limit + 1)
        if len(content) > limit:
            raise ValueError(f"{path.name}: exceeds the {limit} byte limit")
        content.decode("utf-8")
        return content
    except (OSError, UnicodeDecodeError) as error:
        reason = error.strerror if isinstance(error, OSError) else "invalid UTF-8"
        raise ValueError(f"Cannot read {path.name}: {reason}") from error


def make_source(
    kind: Literal["daily", "current_personal", "previous_practice"],
    day: date,
    content: bytes,
) -> WeeklySource:
    names = {
        "daily": "daily",
        "current_personal": "weekly-current",
        "previous_practice": "weekly-prior",
    }
    folder = "daily" if kind == "daily" else "weekly"
    return WeeklySource(
        source_id=f"{names[kind]}:{day.isoformat()}",
        kind=kind,
        day=day,
        body=content.decode("utf-8"),
        sha256=digest(content),
        link=f"[[../{folder}/{day.isoformat()}]]",
    )


def review_snapshot(
    config: MachineConfig,
    start: date,
    through: date | None,
    sources: list[WeeklySource],
    personal: bytes,
    warnings: list[str],
) -> str:
    data = {
        "week": start.isoformat(),
        "through": through.isoformat() if through else None,
        "language": config.language,
        "timezone": config.timezone,
        "english_feedback": config.english_feedback,
        "template": TEMPLATE.decode(),
        "sources": [
            (source.source_id, source.sha256)
            for source in sources
            if source.kind != "current_personal"
        ],
        "personal": digest(personal),
        "warnings": warnings,
    }
    return digest(json.dumps(data, sort_keys=True, separators=(",", ":")).encode())


def previous_practice(
    directory: Path, start: date
) -> tuple[WeeklySource | None, list[str]]:
    candidates: list[tuple[date, Path]] = []
    warnings: list[str] = []
    for path in directory.glob("*.md"):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
            continue
        try:
            day = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if day < start and day.weekday() == 0:
            candidates.append((day, path))
    for day, path in sorted(candidates, reverse=True):
        content = read_note(path)
        if TEMPLATE not in content:
            if START in content or END in content or PRACTICE_START in content:
                raise ValueError(
                    f"Malformed or unsupported prior weekly note: {path.name}"
                )
            warnings.append(
                f"Prior weekly note {path.name} has no supported practice format; "
                "not reviewed."
            )
            continue
        _, _, suffix = split_weekly(content)
        return make_source("previous_practice", day, practice_text(suffix)), warnings
    return None, warnings


def prepare_week(
    config: MachineConfig, selected: date | None, *, now: datetime
) -> WeekPreparation:
    today = resolve_work_date(config, None, now=now)
    chosen = selected or today
    start = chosen - timedelta(days=chosen.weekday())
    end = start + timedelta(days=6)
    through = min(today, end) if today >= start else None
    dates = [start + timedelta(days=index) for index in range(7)]
    target = config.workspace / "engineering/weekly" / f"{start.isoformat()}.md"
    available: list[date] = []
    sources: list[WeeklySource] = []
    warnings: list[str] = []
    note_hash = None
    source_bytes = 0
    snapshot = "0" * 64
    status = "ready"
    message = None
    try:
        daily = managed_directory(config.workspace, "engineering/daily")
        weekly = managed_directory(config.workspace, "engineering/weekly")
        if (daily.exists() and not daily.is_dir()) or (
            weekly.exists() and not weekly.is_dir()
        ):
            raise ValueError("Managed daily/weekly path is not a directory")
        content = read_note(target) if target.exists() or target.is_symlink() else None
        personal = b""
        generated = b""
        if content is not None:
            note_hash = digest(content)
            prefix, generated, suffix = split_weekly(content)
            personal = prefix + suffix
        for day in dates:
            if through is None or day > through:
                continue
            path = daily / f"{day.isoformat()}.md"
            if path.exists() or path.is_symlink():
                body = read_note(path, limit=MAX_SOURCE_BYTES)
                source_bytes += len(body)
                sources.append(make_source("daily", day, body))
                available.append(day)
        if through is not None:
            prior, warnings = previous_practice(weekly, start)
            if prior is not None:
                sources.append(prior)
                source_bytes += len(prior.body.encode())
        if content is not None:
            sources.append(make_source("current_personal", start, personal))
            source_bytes += len(personal)
        if source_bytes > MAX_SOURCE_BYTES:
            raise ValueError(
                f"Weekly sources: {source_bytes} bytes exceeds "
                f"the {MAX_SOURCE_BYTES} byte limit"
            )
        snapshot = review_snapshot(config, start, through, sources, personal, warnings)
        if not available:
            status, message = (
                "empty",
                "No daily notes exist for the elapsed part of this week.",
            )
        else:
            markers = SOURCE_MARKER.findall(generated)
            if markers == [snapshot.encode()]:
                status, message = (
                    "unchanged",
                    "Sources, personal responses and settings are unchanged; "
                    "review skipped.",
                )
    except ValueError as error:
        status, message = "conflict", str(error)
    return WeekPreparation(
        status=status,
        week_start=start,
        week_end=end,
        review_through=through,
        provisional=today <= end,
        language=config.language,
        english_feedback=config.english_feedback,
        available_dates=available,
        missing_dates=[
            day
            for day in dates
            if through is not None and day <= through and day not in available
        ],
        pending_dates=[day for day in dates if through is None or day > through],
        source_snapshot=snapshot,
        expected_note_sha256=note_hash,
        sources=sources if status == "ready" else [],
        path=str(target),
        source_bytes=source_bytes,
        warnings=warnings,
        message=message,
    )
