import hashlib
import html
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from zoneinfo import ZoneInfo

from meditations.composition import (
    TEMPLATE_VERSION,
    CompositionResponse,
    validate_composition,
)
from meditations.config import WorkspaceConfig
from meditations.files import atomic_write, workspace_lock
from meditations.records import EvidenceRecord, latest_records

START = b"<!-- meditations:generated:start -->"
END = b"<!-- meditations:generated:end -->"
DigestField = Literal["decisions", "outcomes", "verification"]

_LABELS = {
    "en": {
        "title": "Engineering journal",
        "overview": "Overview",
        "learning": "Key learning material",
        "questions": "Open questions",
        "evidence": "Reasoning and evidence",
        "source": "Evidence",
        "attribution": "Attribution",
        "assistance": "Assistance",
        "tags": "Tags",
        "concepts": "Concepts",
        "reasoning": "Reasoning",
        "alternatives": "Alternatives",
        "decisions": "Decisions",
        "outcomes": "Outcomes",
        "verification": "Verification",
        "uncertainty": "Uncertainty",
        "privacy": "Privacy omissions",
        "related": "Related dates",
        "empty": "No relevant evidence available for this date.",
        "not_recorded": "Not recorded.",
        "recorded_decisions": "Recorded decisions",
        "recorded_results": "Recorded results",
        "reflection_heading": "Questions for reflection",
        "scope": (
            "Selected entries are shown below; full context and verification "
            "limits remain in the expandable evidence. Recorded reports are not "
            "proof of independent understanding or verified success."
        ),
        "more_tasks": "Additional tasks appear below.",
        "changed": "What changed today",
        "preserve": "Decisions and reasoning to preserve",
        "pending": "Still open / next steps",
        "study": "Learning and reading",
        "supporting": "Supporting evidence",
        "practice": "Suggested practice",
        "no_learning": "No learning material was identified in the supplied evidence.",
        "no_open": "No concrete open issue was recorded in this composition.",
        "no_links": "No reading link was recorded for this topic.",
        "intro": "Organized from the day's recorded work for reading and reflection. "
        "Assistant explanations and reported results "
        "do not establish independent mastery.",
        "reading_question": "Reading question",
    },
    "pt-BR": {
        "title": "Diário de engenharia",
        "overview": "Visão geral",
        "learning": "Material de aprendizagem",
        "questions": "Questões em aberto",
        "evidence": "Raciocínio e evidências",
        "source": "Evidência",
        "attribution": "Atribuição",
        "assistance": "Assistência",
        "tags": "Tags",
        "concepts": "Conceitos",
        "reasoning": "Raciocínio",
        "alternatives": "Alternativas",
        "decisions": "Decisões",
        "outcomes": "Resultados",
        "verification": "Verificação",
        "uncertainty": "Incertezas",
        "privacy": "Omissões de privacidade",
        "related": "Datas relacionadas",
        "empty": "Nenhuma evidência relevante disponível para esta data.",
        "not_recorded": "Não registrado.",
        "recorded_decisions": "Decisões registradas",
        "recorded_results": "Resultados registrados",
        "reflection_heading": "Perguntas para reflexão",
        "scope": (
            "As entradas abaixo são uma seleção; o contexto completo e os limites "
            "de verificação permanecem nas evidências expansíveis. Relatos "
            "registrados não comprovam compreensão independente ou sucesso verificado."
        ),
        "more_tasks": "As demais tarefas aparecem abaixo.",
        "changed": "O que mudou hoje",
        "preserve": "Decisões e raciocínios que quero preservar",
        "pending": "Pendências e próximos passos",
        "study": "Aprendizagem e leitura",
        "supporting": "Evidências de apoio",
        "practice": "Prática sugerida",
        "no_learning": (
            "Nenhum material de aprendizagem foi identificado "
            "nas evidências fornecidas."
        ),
        "no_open": "Nenhuma pendência concreta foi registrada nesta composição.",
        "no_links": "Nenhum link de leitura foi registrado para este assunto.",
        "intro": "Anotação organizada a partir do trabalho registrado no dia, "
        "para leitura e reflexão. Explicações e resultados relatados pelo agente "
        "não demonstram domínio independente.",
        "reading_question": "Pergunta de leitura",
    },
}

_REFLECTION_QUESTIONS = {
    "en": (
        "Which decision from today can I explain in my own words, "
        "and why was it chosen?",
        "What remains unclear, and what concrete check would help me understand it?",
        "Which concept from today should I revisit or practice next?",
    ),
    "pt-BR": (
        "Qual decisão de hoje consigo explicar com minhas palavras, "
        "e por que ela foi escolhida?",
        "O que ainda não está claro, e qual verificação concreta "
        "ajudaria a compreender?",
        "Qual conceito de hoje devo revisitar ou praticar em seguida?",
    ),
}


def task_anchor(task_id: str) -> str:
    return "task-" + hashlib.sha256(task_id.encode()).hexdigest()[:16]


def _text(value: str) -> str:
    escaped = html.escape(" ".join(value.split()), quote=False)
    return re.sub(r"([\\`*_\[\]])", r"\\\1", escaped)


def _excerpt(value: str) -> str:
    value = " ".join(value.split())
    return value if len(value) <= 240 else value[:237].rsplit(" ", 1)[0] + "…"


def _field_bullets(items: list[EvidenceRecord], field: DigestField) -> list[str]:
    entries: dict[tuple[str, str], tuple[str, EvidenceRecord]] = {}
    for item in items:
        values: list[str] = getattr(item, field)
        for value in values:
            key = (" ".join(value.split()).casefold(), item.attribution)
            entries[key] = (value, item)
    ordered = sorted(
        entries.values(),
        key=lambda entry: (entry[1].occurred_at, str(entry[1].record_id)),
    )
    return [
        f"- {_text(_excerpt(value))} — {_text(item.attribution)} "
        f"[↗](#^evidence-{item.record_id})"
        for value, item in ordered[-5:]
    ]


def _learning_topics(items: list[EvidenceRecord]) -> list[str]:
    frequencies: Counter[str] = Counter()
    spelling: dict[str, str] = {}
    for item in items:
        concepts = {
            " ".join(value.split()).casefold(): value for value in item.concepts
        }
        frequencies.update(concepts.keys())
        for key, value in concepts.items():
            spelling.setdefault(key, value)
    return [
        spelling[key]
        for key in sorted(frequencies, key=lambda key: (-frequencies[key], key))[:5]
    ]


def _evidence_details(
    items: list[EvidenceRecord],
    labels: dict[str, str],
    numbers: dict[str, int] | None = None,
) -> list[str]:
    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        if numbers is not None:
            index = numbers[str(item.record_id)]
        body = [
            f"**{labels['source']}:** `{item.record_id}` "
            f"(revision {item.source_revision})",
            "",
            f"**{labels['attribution']}:** {_text(item.attribution)}",
            "",
            f"**{labels['assistance']}:** {_text(item.assistance)}",
        ]
        for label, values in (
            (labels["tags"], item.tags),
            (labels["concepts"], item.concepts),
            (labels["reasoning"], item.reasoning),
            (labels["alternatives"], item.alternatives),
            (labels["decisions"], item.decisions),
            (labels["outcomes"], item.outcomes),
            (labels["verification"], item.verification),
            (labels["uncertainty"], item.uncertainties),
            (labels["privacy"], item.privacy_omissions),
        ):
            if values:
                body += ["", f"**{label}:**", ""]
                body.extend(f"- {_text(value)}" for value in values)
        lines += [
            f"> [!note]- {index}. {_text(item.summary)}",
            ">",
            *(f"> {line}" if line else ">" for line in body),
            "",
            f"^evidence-{item.record_id}",
            "",
        ]
    return lines


def render_daily(
    records: list[EvidenceRecord],
    config: WorkspaceConfig,
    day: date,
    *,
    composition: CompositionResponse | None = None,
) -> str:
    zone = ZoneInfo(config.timezone)
    labels = _LABELS[config.language]
    current = latest_records(records)
    selected = [
        item for item in current if item.occurred_at.astimezone(zone).date() == day
    ]
    tasks: dict[str, list[EvidenceRecord]] = {}
    for item in selected:
        tasks.setdefault(item.task_id, []).append(item)
    if composition is not None:
        validate_composition(composition, selected)
        return _render_composed(composition, tasks, labels, day, current, zone)
    lines = [
        f"# {labels['title']} — {day.isoformat()}",
        "",
        f"## {labels['overview']}",
        "",
    ]
    if not selected:
        lines.append(labels["empty"])
    highlights = sorted(
        tasks.items(), key=lambda task: (task[1][-1].occurred_at, task[0]), reverse=True
    )[:5]
    for task_id, items in reversed(highlights):
        item = next(
            (item for item in reversed(items) if item.outcomes or item.decisions),
            items[-1],
        )
        lines.append(
            f"- [{_text(items[-1].task_label)}](#^{task_anchor(task_id)}): "
            f"{_text(_excerpt(item.summary))}"
        )
    if len(tasks) > 5:
        lines += ["", labels["more_tasks"]]
    if selected:
        lines += ["", labels["scope"]]
    for task_id, items in tasks.items():
        lines += [
            "",
            f"## {_text(items[-1].task_label)}",
            "",
            f"{labels['evidence']} ({len(items)}). ^{task_anchor(task_id)}",
            "",
        ]
        sections: tuple[tuple[DigestField, str], ...] = (
            ("decisions", labels["recorded_decisions"]),
            ("outcomes", labels["recorded_results"]),
            ("verification", labels["verification"]),
        )
        for field, label in sections:
            bullets = _field_bullets(items, field)
            if bullets:
                lines += [f"### {label}", "", *bullets, ""]
        concepts = _learning_topics(items)
        lines += [
            f"**{labels['learning']}:** "
            + ("; ".join(_text(value) for value in concepts) or labels["not_recorded"]),
            "",
        ]
        lines.extend(_evidence_details(items, labels))
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
                f"{labels['related']}: "
                + ", ".join(
                    f"[{other.isoformat()}]({other.isoformat()}.md#^{task_anchor(task_id)})"
                    for other in other_days
                )
            )
    if selected:
        lines += ["", f"## {labels['reflection_heading']}", ""]
        lines.extend(
            f"- {question}" for question in _REFLECTION_QUESTIONS[config.language]
        )
    return "\n".join(lines).rstrip() + "\n\n"


def _table_cell(value: str) -> str:
    return _text(value).replace("|", "\\|")


def _render_composed(
    composition: CompositionResponse,
    tasks: dict[str, list[EvidenceRecord]],
    labels: dict[str, str],
    day: date,
    current: list[EvidenceRecord],
    zone: ZoneInfo,
) -> str:
    resources = {
        resource.url: resource
        for items in tasks.values()
        for record in items
        for resource in record.resources
    }
    lines = [
        f"<!-- meditations:template:{TEMPLATE_VERSION} -->",
        f"# {labels['title']} — {day.isoformat()}",
        "",
        f"> {labels['intro']}",
        "",
    ]
    earlier = sorted(
        {record.occurred_at.astimezone(zone).date() for record in current} - {day}
    )
    previous = [value for value in earlier if value < day]
    following = [value for value in earlier if value > day]
    related = previous[-1:] + following[:1]
    if related:
        lines += [
            f"{labels['related']}: "
            + ", ".join(
                f"[{value.isoformat()}]({value.isoformat()}.md)" for value in related
            ),
            "",
        ]
    lines += [f"## {labels['changed']}", ""]
    lines.extend(f"- {_text(point.text)}" for point in composition.overview)
    lines += ["", f"## {labels['preserve']}", ""]
    for topic in composition.topics:
        lines += [f"### {_text(topic.title)}", ""]
        for paragraph in topic.paragraphs:
            lines += [_text(paragraph.text), ""]
        if topic.bullets:
            lines.extend(f"- {_text(point.text)}" for point in topic.bullets)
            lines.append("")
        if topic.steps:
            lines.extend(
                f"{index}. {_text(point.text)}"
                for index, point in enumerate(topic.steps, 1)
            )
            lines.append("")
        if topic.table:
            lines += [
                "| "
                + " | ".join(_table_cell(value) for value in topic.table.headers)
                + " |",
                "| " + " | ".join("---" for _ in topic.table.headers) + " |",
            ]
            lines.extend(
                "| " + " | ".join(_table_cell(value) for value in row.cells) + " |"
                for row in topic.table.rows
            )
            lines.append("")
    lines += [f"## {labels['pending']}", ""]
    lines.extend(f"- {_text(point.text)}" for point in composition.open_items)
    if not composition.open_items:
        lines.append(labels["no_open"])
    lines += ["", f"## {labels['study']}", ""]
    for item in composition.learning:
        lines += [f"### {_text(item.concept)}", "", _text(item.explanation.text), ""]
        for url in item.resource_urls:
            lines += [
                f"[{_text(resources[url].title)}]({quote(url, safe=':/?#=&%')})",
                "",
            ]
        if not item.resource_urls:
            lines += [labels["no_links"], ""]
        if item.reading_question:
            lines += [
                f"**{labels['reading_question']}:** "
                f"{_text(item.reading_question.text)}",
                "",
            ]
        lines += [
            f"**{labels['practice']}:** {_text(item.suggested_practice.text)}",
            "",
        ]
    if not composition.learning:
        lines += [labels["no_learning"], ""]
    lines += [f"## {labels['reflection_heading']}", ""]
    lines.extend(f"- {_text(point.text)}" for point in composition.reflection_questions)
    return "\n".join(lines).rstrip() + "\n\n"


def daily_frontmatter(day: date) -> str:
    return (
        "---\n"
        f"date: {day.isoformat()}\n"
        "project: meditations\n"
        "tags:\n  - meditations\n  - engineering-journal\n"
        "status: awaiting-personal-review\n"
        "---\n\n"
    )


def generated_bounds(content: bytes) -> tuple[int, int]:
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError("Daily note needs exactly one generated block; file preserved")
    start, end = content.index(START) + len(START), content.index(END)
    if start > end:
        raise ValueError("Daily note markers are out of order; file preserved")
    return start, end


def update_daily_note(
    path: Path, generated: str, *, metadata: str | None = None
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
        if metadata is not None and content.startswith(START):
            content = metadata.encode() + content
        if content == original:
            return "unchanged"
        atomic_write(path, content, expected=original)
        return "created" if original is None else "updated"
