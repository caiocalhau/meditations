"""Render one structured daily report and preserve text owned by the user."""

import ipaddress
import re
from datetime import date
from urllib.parse import quote, urlsplit

from meditations.captures import END, START, note_path, prepare_day
from meditations.contracts import DailyDraft, JournalTable, JournalTopic, WriteResult
from meditations.files import atomic_write, workspace_lock
from meditations.machine_config import MachineConfig

LABELS = {
    "en": {
        "title": "Daily report",
        "previous": "Previous note",
        "overview": "The day at a glance",
        "work": "Work and outcomes",
        "resume": "Where to resume",
        "study": "Study connected to the work",
        "questions": "Questions for my reflection",
        "reflection": "My reflection",
        "practice": "Suggested practice",
        "read": "Reading question",
        "no_reflection": "Personal reflection: not provided.",
        "intro": (
            "Organized from the day's recorded work for reading and reflection. "
            "Agent explanations and reported results do not establish "
            "independent mastery."
        ),
    },
    "pt-BR": {
        "title": "Relatório diário",
        "previous": "Nota anterior",
        "overview": "O dia em resumo",
        "work": "Trabalho e resultados",
        "resume": "Por onde retomar",
        "study": "Estudo ligado ao trabalho",
        "questions": "Perguntas para minha reflexão",
        "reflection": "Minha reflexão",
        "practice": "Prática sugerida",
        "read": "Pergunta de leitura",
        "no_reflection": "Reflexão pessoal: não fornecida.",
        "intro": (
            "Organizada a partir do trabalho registrado no dia para leitura e "
            "reflexão. Explicações do agente e resultados relatados não "
            "demonstram domínio independente."
        ),
    },
}


def _text(value: str) -> str:
    return " ".join(value.split()).replace("<", "&lt;").replace(">", "&gt;")


def _cell(value: str) -> str:
    return _text(value).replace("|", "\\|")


def _link_url(url: str) -> str:
    return quote(url, safe=":/?#[]@!$&'()*+,;=%")


def _valid_resource(url: str, captures: list[str]) -> bool:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return False
        port = parsed.port
        if (port is not None and port == 0) or any(
            character.isspace() for character in url
        ):
            return False
        host = parsed.hostname.lower().rstrip(".")
        if (
            "." not in host
            or host in {"localhost", "localhost.localdomain"}
            or host.endswith((".local", ".test", ".example", ".invalid"))
        ):
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        return any(
            candidate.rstrip(".,;:") == url
            for capture in captures
            for candidate in re.findall(r"https?://[^\s<>\])]+", capture)
        )
    except ValueError:
        return False


def _topic(topic: JournalTopic) -> list[str]:
    lines = [f"### {_text(topic.title)}\n\n"]
    lines.extend(f"{_text(item)}\n\n" for item in topic.paragraphs)
    if topic.bullets:
        lines.extend(f"- {_text(item)}\n" for item in topic.bullets)
        lines.append("\n")
    if topic.steps:
        lines.extend(
            f"{index}. {_text(item)}\n" for index, item in enumerate(topic.steps, 1)
        )
        lines.append("\n")
    if topic.table is not None:
        lines.extend(_table(topic.table))
    if not lines[-1].endswith("\n\n"):
        lines.append("\n")
    return lines


def _table(table: JournalTable) -> list[str]:
    lines = ["| " + " | ".join(_cell(item) for item in table.headers) + " |\n"]
    lines.append("| " + " | ".join("---" for _ in table.headers) + " |\n")
    lines.extend(
        "| " + " | ".join(_cell(item) for item in row) + " |\n" for row in table.rows
    )
    lines.append("\n")
    return lines


def render_daily(
    day: date,
    config: MachineConfig,
    draft: DailyDraft,
    *,
    previous_note: str | None,
) -> bytes:
    labels = LABELS[config.language]
    captures = [item.body for item in prepare_day(config, day).captures]
    for item in draft.learning:
        if any(not _valid_resource(url, captures) for url in item.resource_urls):
            raise ValueError(
                "Learning resource is not a public URL found in a saved capture"
            )

    lines = [
        f"<!-- meditations:sources:{draft.source_snapshot} -->\n",
        "<!-- meditations:template:daily-report-v1 -->\n",
        f"# {labels['title']} — {day.isoformat()}\n\n",
        f"> {labels['intro']}\n\n",
    ]
    if previous_note:
        lines.append(f"{labels['previous']}: {previous_note}.\n\n")
    lines.extend([f"## {labels['overview']}\n\n"])
    lines.extend(f"- {_text(item)}\n" for item in draft.overview)
    lines.extend([f"\n## {labels['work']}\n\n"])
    for topic in draft.topics:
        lines.extend(_topic(topic))
    if draft.open_items:
        lines.extend([f"## {labels['resume']}\n\n"])
        lines.extend(f"- {_text(item)}\n" for item in draft.open_items)
        lines.append("\n")
    if draft.learning:
        lines.extend([f"## {labels['study']}\n\n"])
        for item in draft.learning:
            lines.extend(
                [f"### {_text(item.concept)}\n\n", f"{_text(item.explanation)}\n\n"]
            )
            if item.resource_urls:
                links = ", ".join(
                    f"[{_text(urlsplit(url).hostname or 'source')}]({_link_url(url)})"
                    for url in item.resource_urls
                )
                lines.extend([f"**Reading:** {links}\n\n"])
            if item.reading_question:
                lines.extend(
                    [f"**{labels['read']}:** {_text(item.reading_question)}\n\n"]
                )
            lines.extend(
                [f"**{labels['practice']}:** {_text(item.suggested_practice)}\n\n"]
            )
    lines.extend([f"## {labels['questions']}\n\n"])
    lines.extend(f"- {_text(item)}\n" for item in draft.reflection_questions)
    return "".join(lines).encode("utf-8")


def _bounds(content: bytes) -> tuple[int, int]:
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError("Existing note has no valid generated section")
    start, end = content.index(START) + len(START), content.index(END)
    if start > end:
        raise ValueError("Existing note generated markers are out of order")
    return start, end


def write_daily(config: MachineConfig, day: date, draft: DailyDraft) -> WriteResult:
    target = note_path(config, day)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        return WriteResult(
            status="conflict", path=str(target), message="Daily note is a symbolic link"
        )
    with workspace_lock(config.workspace):
        preparation = prepare_day(config, day)
        if preparation.status != "ready":
            return WriteResult(
                status="conflict", path=str(target), message=preparation.message
            )
        if draft.source_snapshot != preparation.source_snapshot:
            return WriteResult(
                status="conflict",
                path=str(target),
                message="Captures or settings changed; prepare the day again",
            )
        if draft.expected_note_sha256 != preparation.expected_note_sha256:
            return WriteResult(
                status="conflict",
                path=str(target),
                message="Daily note changed; prepare the day again",
            )
        original = target.read_bytes() if target.exists() else None
        try:
            rendered = render_daily(
                day, config, draft, previous_note=preparation.previous_note
            )
        except ValueError as error:
            return WriteResult(status="conflict", path=str(target), message=str(error))
        if original is None:
            prefix = (
                f"---\ndate: {day.isoformat()}\nproject: meditations\ntags:\n"
                "  - meditations\n  - engineering-journal\n"
                "status: awaiting-personal-review\n---\n\n"
            ).encode()
            personal_reflection = (
                f"## {LABELS[config.language]['reflection']}\n\n"
                f"{LABELS[config.language]['no_reflection']}\n"
            ).encode()
            content = (
                prefix + START + b"\n" + rendered + END + b"\n\n" + personal_reflection
            )
        else:
            try:
                start, end = _bounds(original)
            except ValueError as error:
                return WriteResult(
                    status="conflict", path=str(target), message=str(error)
                )
            content = original[:start] + b"\n" + rendered + original[end:]
        if content == original:
            return WriteResult(status="unchanged", path=str(target))
        final_preparation = prepare_day(config, day)
        if (
            final_preparation.status != "ready"
            or final_preparation.source_snapshot != preparation.source_snapshot
            or final_preparation.expected_note_sha256
            != preparation.expected_note_sha256
        ):
            return WriteResult(
                status="conflict",
                path=str(target),
                message=(
                    "Captures or note changed during composition; prepare the day again"
                ),
            )
        atomic_write(target, content, expected=original)
        return WriteResult(
            status="created" if original is None else "updated", path=str(target)
        )
