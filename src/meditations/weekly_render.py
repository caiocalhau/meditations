"""Render cited weekly analysis while protecting practice and personal responses."""

from datetime import date, datetime
from pathlib import Path

from meditations.captures import END, START
from meditations.contracts import WriteResult
from meditations.files import atomic_write, workspace_lock
from meditations.machine_config import MachineConfig
from meditations.render import inline_text, valid_resource
from meditations.weekly import (
    MAX_NOTE_BYTES,
    MAX_SOURCE_BYTES,
    PRACTICE_END,
    PRACTICE_START,
    TEMPLATE,
    prepare_week,
    read_note,
    review_snapshot,
    split_weekly,
)
from meditations.weekly_contracts import (
    EvidenceReference,
    WeeklyDraft,
    WeeklyPractice,
    WeeklySource,
    WeekPreparation,
)

EN_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
PT_MONTHS = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)
LABELS = {
    "en": {
        "title": "Weekly review",
        "overview": "The week at a glance",
        "sound": "What was sound",
        "gaps": "Corrections, gaps and open questions",
        "english": "English feedback",
        "practice_feedback": "Practice feedback",
        "limits": "Evidence and limits",
        "personal": "Practice and my responses",
        "actions": "Practice actions",
        "response": "My response:",
        "assistance": "Assistance used (or unknown):",
        "reflection": "My reflection",
        "provisional": "Provisional: this week is still in progress.",
        "missing": "Missing daily notes",
        "pending": "Dates not yet elapsed",
        "sources": "Daily notes reviewed",
        "next": "Next step",
        "suggestion": "Suggested wording",
        "no_english": (
            "No English feedback was supplied. "
            "The review must explain any evidence limitation below."
        ),
    },
    "pt-BR": {
        "title": "Revisão semanal",
        "overview": "A semana em resumo",
        "sound": "O que foi bem fundamentado",
        "gaps": "Correções, lacunas e questões abertas",
        "english": "Feedback de inglês",
        "practice_feedback": "Feedback da prática",
        "limits": "Evidências e limites",
        "personal": "Prática e minhas respostas",
        "actions": "Ações de prática",
        "response": "Minha resposta:",
        "assistance": "Ajuda utilizada (ou desconhecida):",
        "reflection": "Minha reflexão",
        "provisional": "Provisório: esta semana ainda está em andamento.",
        "missing": "Notas diárias ausentes",
        "pending": "Datas ainda não decorridas",
        "sources": "Notas diárias revisadas",
        "next": "Próximo passo",
        "suggestion": "Redação sugerida",
        "no_english": (
            "Nenhum feedback de inglês foi fornecido. "
            "A revisão deve explicar as limitações abaixo."
        ),
    },
}


def weekly_title(start: date, end: date, language: str) -> str:
    months = PT_MONTHS if language == "pt-BR" else EN_MONTHS
    joiner = " de " if language == "pt-BR" else " "

    def month_day(day: date) -> str:
        return f"{day.day}{joiner}{months[day.month - 1]}"

    def full(day: date) -> str:
        return f"{month_day(day)}{joiner}{day.year}"

    if start.year != end.year:
        interval = f"{full(start)}–{full(end)}"
    elif start.month != end.month:
        interval = f"{month_day(start)}–{full(end)}"
    else:
        interval = f"{start.day}–{full(end)}"
    return f"{LABELS[language]['title']} — {interval}"


def _citation(reference: EvidenceReference, sources: dict[str, WeeklySource]) -> str:
    source = sources.get(reference.source_id)
    if source is None:
        raise ValueError(
            f"Citation refers to an unselected source: {reference.source_id}"
        )
    quote = " ".join(reference.quote.split())
    if quote not in " ".join(source.body.split()):
        raise ValueError(f"Citation quote not found in source: {reference.source_id}")
    return f"> {inline_text(reference.quote)} — {source.link}\n\n"


def _practice(practice: WeeklyPractice, language: str) -> bytes:
    labels = LABELS[language]
    lines = [PRACTICE_START.decode() + "\n", f"## {labels['personal']}\n\n"]
    for index, question in enumerate(practice.questions, 1):
        lines.extend(
            [
                f"### Q{index}\n\n{inline_text(question)}\n\n",
                f"{labels['assistance']}\n\n{labels['response']}\n\n",
            ]
        )
    lines.append(f"## {labels['actions']}\n\n")
    lines.extend(f"- {inline_text(action)}\n" for action in practice.actions)
    lines.append("\n")
    lines.extend(f"- {url}\n" for url in practice.resource_urls)
    lines.extend([f"\n## {labels['reflection']}\n\n", PRACTICE_END.decode() + "\n"])
    return "".join(lines).encode()


def _analysis(prepared: WeekPreparation, draft: WeeklyDraft, snapshot: str) -> bytes:
    labels = LABELS[prepared.language]
    sources = {source.source_id: source for source in prepared.sources}
    if draft.english_feedback and not prepared.english_feedback:
        raise ValueError("English feedback is disabled in machine settings")
    if (
        prepared.english_feedback
        and not draft.english_feedback
        and not draft.limitations
    ):
        raise ValueError(
            "English feedback is enabled: provide feedback or an evidence limitation"
        )
    lines = [
        f"<!-- meditations:sources:{snapshot} -->\n",
        TEMPLATE.decode() + "\n",
        "# "
        f"{weekly_title(prepared.week_start, prepared.week_end, prepared.language)}"
        "\n\n",
    ]
    if prepared.provisional:
        lines.append(f"> {labels['provisional']}\n\n")
    links = [source.link for source in prepared.sources if source.kind == "daily"]
    lines.append(f"**{labels['sources']}:** {', '.join(links)}\n\n")
    for key, values in (
        ("missing", prepared.missing_dates),
        ("pending", prepared.pending_dates),
    ):
        if values:
            lines.append(
                f"**{labels[key]}:** {', '.join(day.isoformat() for day in values)}\n\n"
            )
    lines.append(f"## {labels['overview']}\n\n")
    lines.extend(f"- {inline_text(item)}\n" for item in draft.overview)
    lines.append("\n")
    groups = (
        (
            "sound",
            [item for item in draft.findings if item.category == "sound_reasoning"],
        ),
        (
            "gaps",
            [
                item
                for item in draft.findings
                if item.category not in {"sound_reasoning", "practice_feedback"}
            ],
        ),
        (
            "practice_feedback",
            [item for item in draft.findings if item.category == "practice_feedback"],
        ),
    )
    for label, findings in groups:
        if findings:
            lines.append(f"## {labels[label]}\n\n")
        for finding in findings:
            lines.append(
                f"### {inline_text(finding.title)}\n\n"
                f"{inline_text(finding.assessment)}\n\n"
            )
            for reference in finding.evidence:
                lines.append(_citation(reference, sources))
            if finding.next_step:
                lines.append(
                    f"**{labels['next']}:** {inline_text(finding.next_step)}\n\n"
                )
    if prepared.english_feedback:
        lines.append(f"## {labels['english']}\n\n")
        if not draft.english_feedback:
            lines.append(labels["no_english"] + "\n\n")
        for feedback in draft.english_feedback:
            lines.extend(
                [
                    _citation(feedback.evidence, sources),
                    f"**{labels['suggestion']}:** "
                    f"{inline_text(feedback.suggestion)}\n\n",
                    f"{inline_text(feedback.explanation)}\n\n",
                ]
            )
    if draft.limitations or prepared.warnings:
        lines.append(f"## {labels['limits']}\n\n")
        lines.extend(
            f"- {inline_text(item)}\n"
            for item in [*draft.limitations, *prepared.warnings]
        )
    return "".join(lines).encode()


def write_weekly(
    config: MachineConfig,
    selected: date,
    draft: WeeklyDraft,
    *,
    now: datetime,
) -> WriteResult:
    prepared = prepare_week(config, selected, now=now)
    target = Path(prepared.path)

    def conflict(message: str | None) -> WriteResult:
        return WriteResult(status="conflict", path=str(target), message=message)

    with workspace_lock(config.workspace):
        prepared = prepare_week(config, selected, now=now)
        if prepared.status != "ready":
            if (
                prepared.status == "unchanged"
                and draft.source_snapshot == prepared.source_snapshot
                and draft.expected_note_sha256 == prepared.expected_note_sha256
            ):
                return WriteResult(
                    status="unchanged", path=str(target), message=prepared.message
                )
            return conflict(prepared.message)
        if draft.source_snapshot != prepared.source_snapshot:
            return conflict(
                "Weekly sources or settings changed; prepare the week again"
            )
        if draft.expected_note_sha256 != prepared.expected_note_sha256:
            return conflict("Weekly note changed; prepare the week again")
        try:
            original = read_note(target) if target.exists() else None
            if original is None:
                if draft.initial_practice is None:
                    return conflict("A new weekly note requires initial practice")
                bodies = [source.body for source in prepared.sources]
                for url in draft.initial_practice.resource_urls:
                    if not valid_resource(url, bodies):
                        return conflict(
                            "Practice resource is not a public URL "
                            "found in a selected source"
                        )
                prefix = (
                    f"---\nweek-start: {prepared.week_start}\n"
                    f"week-end: {prepared.week_end}\n"
                    "project: meditations\ntags:\n  - meditations\n"
                    "  - weekly-review\n---\n\n"
                ).encode() + START
                suffix = (
                    END + b"\n\n" + _practice(draft.initial_practice, config.language)
                )
            else:
                if draft.initial_practice is not None:
                    return conflict(
                        "Existing practice and responses cannot be replaced by a draft"
                    )
                prefix, _, suffix = split_weekly(original)
            personal = prefix + suffix
            projected_bytes = sum(
                len(source.body.encode())
                for source in prepared.sources
                if source.kind != "current_personal"
            ) + len(personal)
            if projected_bytes > MAX_SOURCE_BYTES:
                return conflict(
                    f"Weekly sources including practice: {projected_bytes} bytes "
                    f"exceeds the {MAX_SOURCE_BYTES} byte limit"
                )
            stored_snapshot = review_snapshot(
                config,
                prepared.week_start,
                prepared.review_through,
                prepared.sources,
                personal,
                prepared.warnings,
            )
            content = (
                prefix + b"\n" + _analysis(prepared, draft, stored_snapshot) + suffix
            )
            if len(content) > MAX_NOTE_BYTES:
                return conflict(
                    f"Weekly note exceeds the {MAX_NOTE_BYTES} byte local storage limit"
                )
            final = prepare_week(config, selected, now=now)
            if (
                final.source_snapshot != prepared.source_snapshot
                or final.expected_note_sha256 != prepared.expected_note_sha256
                or final.status != "ready"
            ):
                return conflict(
                    "Weekly sources or note changed during rendering; prepare again"
                )
            atomic_write(target, content, expected=original)
        except (ValueError, OSError) as error:
            return conflict(str(error))
    return WriteResult(
        status="created" if original is None else "updated", path=str(target)
    )
