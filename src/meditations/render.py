import hashlib
import html
import re
from datetime import date
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from meditations.config import WorkspaceConfig
from meditations.files import atomic_write, workspace_lock
from meditations.records import EvidenceRecord, latest_records

START = b"<!-- meditations:generated:start -->"
END = b"<!-- meditations:generated:end -->"


def task_anchor(task_id: str) -> str:
    return "task-" + hashlib.sha256(task_id.encode()).hexdigest()[:16]


def _text(value: str) -> str:
    escaped = html.escape(" ".join(value.split()), quote=False)
    return re.sub(r"([\\`*_\[\]])", r"\\\1", escaped)


def render_daily(
    records: list[EvidenceRecord], config: WorkspaceConfig, day: date
) -> str:
    zone = ZoneInfo(config.timezone)
    current = latest_records(records)
    selected = [
        item for item in current if item.occurred_at.astimezone(zone).date() == day
    ]
    lines = [f"# Engineering journal — {day.isoformat()}", "", "## Overview", ""]
    if not selected:
        lines.append("No relevant evidence available for this date.")
    for item in selected:
        lines.append(f"- {_text(item.summary)}")
    concepts = sorted({concept for item in selected for concept in item.concepts})
    questions = sorted(
        {question for item in selected for question in item.uncertainties}
    )
    lines += [
        "",
        "**Key learning material:** "
        + ("; ".join(_text(value) for value in concepts) or "Not recorded."),
        "",
        "**Open questions:** "
        + ("; ".join(_text(value) for value in questions) or "Not recorded."),
    ]
    tasks: dict[str, list[EvidenceRecord]] = {}
    for item in selected:
        tasks.setdefault(item.task_id, []).append(item)
    for task_id, items in tasks.items():
        lines += [
            "",
            f'<a id="{task_anchor(task_id)}"></a>',
            f"## {_text(items[-1].task_label)}",
            "",
        ]
        for item in items:
            lines += [
                f"- {_text(item.summary)}",
                "",
                "<details>",
                "<summary>Reasoning and evidence</summary>",
                "",
                f"**Evidence:** `{item.record_id}` (revision {item.source_revision})",
                f"**Attribution:** {_text(item.attribution)}",
                f"**Assistance:** {_text(item.assistance)}",
            ]
            for label, values in (
                ("Tags", item.tags),
                ("Concepts", item.concepts),
                ("Reasoning", item.reasoning),
                ("Alternatives", item.alternatives),
                ("Decisions", item.decisions),
                ("Outcomes", item.outcomes),
                ("Verification", item.verification),
                ("Uncertainty", item.uncertainties),
                ("Privacy omissions", item.privacy_omissions),
            ):
                if values:
                    lines += ["", f"**{label}:**"]
                    lines.extend(f"- {_text(value)}" for value in values)
            lines += ["", "</details>", ""]
        other_days = sorted(
            {
                item.occurred_at.astimezone(zone).date()
                for item in current
                if item.task_id == task_id
            }
            - {day}
        )
        if other_days:
            lines.append(
                "Related dates: "
                + ", ".join(
                    f"[{other.isoformat()}]({other.isoformat()}.md#{task_anchor(task_id)})"
                    for other in other_days
                )
            )
    return "\n".join(lines).rstrip() + "\n"


def generated_bounds(content: bytes) -> tuple[int, int]:
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError("Daily note needs exactly one generated block; file preserved")
    start, end = content.index(START) + len(START), content.index(END)
    if start > end:
        raise ValueError("Daily note markers are out of order; file preserved")
    return start, end


def update_daily_note(
    path: Path, generated: str
) -> Literal["created", "updated", "unchanged"]:
    payload = generated.encode("utf-8")
    if START in payload or END in payload:
        raise ValueError("Generated content contains reserved boundaries")
    with workspace_lock(path):
        if path.is_symlink():
            raise ValueError("Refusing a symbolic-link daily note")
        original = path.read_bytes() if path.exists() else None
        if original is None:
            content = (
                START
                + b"\n"
                + payload
                + END
                + (
                    b"\n\n## Personal reflection\n\n"
                    b"Personal reflection: not provided.\n"
                )
            )
        else:
            start, end = generated_bounds(original)
            content = original[:start] + b"\n" + payload + original[end:]
            if content == original:
                return "unchanged"
        atomic_write(path, content, expected=original)
        return "created" if original is None else "updated"
