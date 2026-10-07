from datetime import date, datetime, timezone
from uuid import uuid4

from meditations.config import load_workspace
from meditations.records import EvidenceRecord
from meditations.render import render_daily, task_anchor


def test_multi_task_note_keeps_attribution_and_detail(workspace, record_data):
    first = EvidenceRecord.model_validate(record_data)
    second = EvidenceRecord.model_validate(
        record_data
        | {
            "record_id": uuid4(),
            "source_segment_id": "segment-2",
            "task_id": "tests",
            "task_label": "Test diagnosis",
            "attribution": "agent explanation",
            "summary": "Agent explained fixtures.",
        }
    )
    note = render_daily([second, first], load_workspace(workspace), date(2026, 10, 3))
    assert "Database migration" in note and "Test diagnosis" in note
    assert "user contribution" in note and "agent explanation" in note
    assert "Older clients need compatible writes." in note
    assert "Rollback was not demonstrated." in note
    assert "> [!note]-" in note and str(first.record_id) in note
    assert note == render_daily(
        [first, second], load_workspace(workspace), date(2026, 10, 3)
    )


def test_timezone_midnight_and_cross_date_links(workspace, record_data):
    earlier = EvidenceRecord.model_validate(
        record_data
        | {
            "occurred_at": datetime(2026, 10, 4, 2, 59, tzinfo=timezone.utc),
            "summary": "Before local midnight.",
        }
    )
    later = EvidenceRecord.model_validate(
        record_data
        | {
            "record_id": uuid4(),
            "source_segment_id": "segment-2",
            "occurred_at": datetime(2026, 10, 4, 3, 0, tzinfo=timezone.utc),
            "summary": "After local midnight.",
        }
    )
    records = [earlier, later]
    note = render_daily(records, load_workspace(workspace), date(2026, 10, 3))
    assert "Before local midnight." in note
    assert "After local midnight." not in note
    assert f"2026-10-04.md#^{task_anchor('migration')}" in note


def test_only_latest_source_revision_contributes(workspace, record_data):
    records = [
        EvidenceRecord.model_validate(record_data),
        EvidenceRecord.model_validate(
            record_data
            | {
                "record_id": uuid4(),
                "source_revision": 1,
                "summary": "Corrected summary.",
            }
        ),
    ]
    note = render_daily(records, load_workspace(workspace), date(2026, 10, 3))
    assert "Corrected summary." in note
    assert "Identified a compatibility concern." not in note


def test_content_cannot_inject_generated_markers_or_html(workspace, record_data):
    record = EvidenceRecord.model_validate(
        record_data
        | {"summary": "<!-- meditations:generated:end --> <script>bad()</script>"}
    )
    note = render_daily([record], load_workspace(workspace), date(2026, 10, 3))
    assert "<!-- meditations:generated:end -->" not in note
    assert "<script>" not in note


def test_portuguese_workspace_translates_generated_labels_only(tmp_path, record_data):
    from meditations.config import initialize_workspace

    workspace = tmp_path / "portuguese-workspace"
    initialize_workspace(workspace, "America/Sao_Paulo", "pt-BR")
    note = render_daily(
        [EvidenceRecord.model_validate(record_data)],
        load_workspace(workspace),
        date(2026, 10, 3),
    )
    assert "# Diário de engenharia" in note
    assert "## Visão geral" in note
    assert "**Material de aprendizagem:**" in note
    assert "Identified a compatibility concern." in note
    assert "**Atribuição:** user contribution" in note


def visible_content(note: str) -> str:
    import re

    return re.sub(r"(?m)^>.*(?:\n|$)", "", note)


def test_long_session_has_task_overview_and_full_collapsed_context(
    workspace, record_data
):
    records = [
        EvidenceRecord.model_validate(
            record_data
            | {
                "record_id": uuid4(),
                "source_segment_id": f"segment-{index}",
                "summary": f"Observation {index:02d}.",
                "occurred_at": datetime(2026, 10, 3, 12, index, tzinfo=timezone.utc),
                "decisions": ["Preserve existing clients."],
                "uncertainties": [f"Coverage limitation {index:02d}."],
            }
        )
        for index in range(20)
    ]
    note = render_daily(records, load_workspace(workspace), date(2026, 10, 3))
    visible = visible_content(note)
    overview = visible.split("## Overview", 1)[1].split("## Database migration", 1)[0]
    assert overview.count("\n- ") == 1
    assert note.count("> [!note]-") == len(records)
    assert visible.count("Preserve existing clients.") == 1
    assert "Coverage limitation" not in visible
    assert "Questions for reflection" in visible
    for index, record in enumerate(records):
        assert f"Observation {index:02d}." in note
        assert f"Coverage limitation {index:02d}." in note
        assert str(record.record_id) in note
    assert note == render_daily(
        list(reversed(records)), load_workspace(workspace), date(2026, 10, 3)
    )


def test_overview_is_bounded_without_discarding_tasks(workspace, record_data):
    records = [
        EvidenceRecord.model_validate(
            record_data
            | {
                "record_id": uuid4(),
                "source_segment_id": f"segment-{index}",
                "task_id": f"task-{index}",
                "task_label": f"Task {index}",
                "summary": f"Context {index}.",
            }
        )
        for index in range(8)
    ]
    note = render_daily(records, load_workspace(workspace), date(2026, 10, 3))
    overview = note.split("## Overview", 1)[1].split("\n## Task ", 1)[0]
    assert overview.count("\n- ") == 5
    for record in records:
        assert f"## {record.task_label}" in note
        assert record.summary in note


def test_reported_outcomes_keep_attribution_and_are_not_promoted_to_verification(
    workspace, record_data
):
    record = EvidenceRecord.model_validate(
        record_data
        | {
            "attribution": "agent explanation",
            "outcomes": ["Agent reported checks passing."],
            "decisions": ["Keep the runtime restricted."],
        }
    )
    note = render_daily([record], load_workspace(workspace), date(2026, 10, 3))
    visible = visible_content(note)
    assert "Recorded results" in visible
    assert "Agent reported checks passing." in visible
    assert "agent explanation" in visible
    assert f"#^evidence-{record.record_id}" in visible
    assert "### Verification" not in visible


def test_reformat_preserves_personal_writing_and_annotations(
    tmp_path, workspace, record_data
):
    from meditations.render import END, START, generated_bounds, update_daily_note

    note_path = tmp_path / "test-note.md"
    prefix = b"---\ntags: [personal]\n---\n\n"
    suffix = (
        "\n\n## Minha reflexão\n\nMeu texto original.\n"
        "> Correção anotada para revisão semanal.\n"
    ).encode()
    note_path.write_bytes(prefix + START + b"\nOld generated format\n" + END + suffix)
    original = note_path.read_bytes()
    generated = render_daily(
        [EvidenceRecord.model_validate(record_data)],
        load_workspace(workspace),
        date(2026, 10, 3),
    )
    assert update_daily_note(note_path, generated) == "updated"
    start, end = generated_bounds(note_path.read_bytes())
    old_start, old_end = generated_bounds(original)
    assert note_path.read_bytes()[:start] == original[:old_start]
    assert note_path.read_bytes()[end:] == original[old_end:]
    assert update_daily_note(note_path, generated) == "unchanged"


def test_visible_digest_is_bounded_and_does_not_drop_long_context(
    workspace, record_data
):
    record = EvidenceRecord.model_validate(
        record_data
        | {
            "summary": "A long summary " + "with recorded context " * 30,
            "decisions": [f"Decision {index}." for index in range(12)],
            "outcomes": [f"Outcome {index}." for index in range(12)],
            "concepts": [f"Concept {index}" for index in range(12)],
        }
    )
    note = render_daily([record], load_workspace(workspace), date(2026, 10, 3))
    visible = visible_content(note)
    assert "…" in visible
    assert record.summary in note
    assert "Decision 0." not in visible
    assert "Decision 11." in visible
    for field in (record.decisions, record.outcomes, record.concepts):
        assert all(value in note for value in field)


def test_portuguese_digest_has_localized_reflection_prompts(tmp_path, record_data):
    from meditations.config import initialize_workspace

    portuguese = tmp_path / "portuguese"
    initialize_workspace(portuguese, "America/Sao_Paulo", "pt-BR")
    record = EvidenceRecord.model_validate(
        record_data
        | {
            "decisions": ["Keep compatibility."],
            "outcomes": ["Agent reported success."],
        }
    )
    visible = visible_content(
        render_daily([record], load_workspace(portuguese), date(2026, 10, 3))
    )
    assert "### Decisões registradas" in visible
    assert "### Resultados registrados" in visible
    assert "## Perguntas para reflexão" in visible
    assert "Qual decisão de hoje" in visible
    assert "Questions for reflection" not in visible


def test_composed_note_uses_topics_without_dumping_internal_evidence(
    workspace, record_data
):
    from meditations.composition import CitedText, CompositionResponse, JournalTopic

    record = EvidenceRecord.model_validate(record_data)
    point = CitedText(
        text="Older clients must remain compatible.",
        source_record_ids=[record.record_id],
    )
    composition = CompositionResponse(
        overview=[point],
        topics=[
            JournalTopic(
                title="Compatibility during deployment",
                paragraphs=[
                    CitedText(
                        text=(
                            "A compatibility concern was recorded; "
                            "implementation is not established."
                        ),
                        source_record_ids=[record.record_id],
                    )
                ],
            )
        ],
        open_items=[
            CitedText(
                text="Rollback still needs verification.",
                source_record_ids=[record.record_id],
            )
        ],
        learning=[],
        reflection_questions=[
            CitedText(
                text="Why does overlap between client versions matter?",
                source_record_ids=[record.record_id],
            )
        ],
        supporting_only_record_ids=[],
    )
    note = render_daily(
        [record], load_workspace(workspace), date(2026, 10, 3), composition=composition
    )
    visible = visible_content(note)
    assert "## What changed today" in visible
    assert "## Decisions and reasoning to preserve" in visible
    assert "### Compatibility during deployment" in visible
    assert "## Still open / next steps" in visible
    assert "Why does overlap between client versions matter?" in visible
    assert "A compatibility concern was recorded;" in note
    assert str(record.record_id) not in note
    assert "<!-- meditations:template:journal-v3-editorial -->" in note


def test_composed_note_retains_related_dates(workspace, record_data):
    from datetime import datetime, timezone
    from uuid import uuid4

    from meditations.composition import CitedText, CompositionResponse, JournalTopic

    first = EvidenceRecord.model_validate(record_data)
    second = EvidenceRecord.model_validate(
        record_data
        | {
            "record_id": uuid4(),
            "source_segment_id": "next-day",
            "occurred_at": datetime(2026, 10, 4, 12, tzinfo=timezone.utc),
        }
    )
    point = CitedText(
        text="Compatibility reviewed.", source_record_ids=[first.record_id]
    )
    composition = CompositionResponse(
        overview=[point],
        topics=[JournalTopic(title="Compatibility", paragraphs=[point])],
        open_items=[],
        learning=[],
        reflection_questions=[point],
        supporting_only_record_ids=[],
    )
    note = render_daily(
        [first, second],
        load_workspace(workspace),
        date(2026, 10, 3),
        composition=composition,
    )
    assert "[2026-10-04](2026-10-04.md)" in note


def test_evidence_uses_foldable_markdown_and_native_block_links(workspace, record_data):
    record = EvidenceRecord.model_validate(record_data)
    for response in (None,):
        note = render_daily(
            [record], load_workspace(workspace), date(2026, 10, 3), composition=response
        )
        assert "<details>" not in note and "<summary>" not in note
        assert "> [!note]- 1. Identified a compatibility concern." in note
        assert "> **Reasoning:**\n>\n> - Older clients need compatible writes." in note
        assert f"\n\n^evidence-{record.record_id}\n\n" in note
        assert "<a id=" not in note
    assert "Evidence 1" not in note


def test_generated_block_links_have_real_targets(workspace, record_data):
    import re

    record = EvidenceRecord.model_validate(
        record_data | {"decisions": ["Keep compatibility."]}
    )
    note = render_daily([record], load_workspace(workspace), date(2026, 10, 3))
    targets = re.findall(r"\]\(#\^([a-zA-Z0-9-]+)\)", note)
    assert targets
    for target in targets:
        assert re.search(rf"(?m)(?:^| )\^{re.escape(target)}$", note)
    assert f"](#^{task_anchor(record.task_id)})" in note


def test_editorial_journal_matches_reference_structure(workspace, record_data):
    from meditations.composition import (
        CitedText,
        CompositionResponse,
        JournalTable,
        JournalTableRow,
        JournalTopic,
        LearningItem,
    )

    record = EvidenceRecord.model_validate(
        record_data
        | {
            "resources": [
                {"title": "Transactions", "url": "https://example.org/transactions"}
            ]
        }
    )

    def point(text):
        return CitedText(text=text, source_record_ids=[record.record_id])

    response = CompositionResponse(
        overview=[point("I identified a compatibility concern.")],
        topics=[
            JournalTopic(
                title="Compatibility during deployment",
                paragraphs=[point("Older clients need compatible writes.")],
                bullets=[point("Keep old clients supported.")],
                steps=[point("Check overlapping versions.")],
                table=JournalTable(
                    headers=["Option", "Tradeoff"],
                    rows=[
                        JournalTableRow(
                            cells=["Compatible writes", "Retain old | new clients"],
                            source_record_ids=[record.record_id],
                        )
                    ],
                ),
            )
        ],
        open_items=[point("Validate rollback.")],
        learning=[
            LearningItem(
                concept="Transactions",
                explanation=point("Rollback matters during deployment."),
                suggested_practice=point("Try an interrupted migration."),
                resource_urls=["https://example.org/transactions"],
                reading_question=point("What happens to a partial write?"),
            )
        ],
        reflection_questions=[point("Why does client overlap matter?")],
        supporting_only_record_ids=[],
    )
    note = render_daily(
        [record], load_workspace(workspace), date(2026, 10, 3), composition=response
    )
    assert "> Organized from the day's recorded work" in note
    assert "- I identified a compatibility concern." in note
    assert "| Option | Tradeoff |" in note
    assert "Retain old \\| new clients" in note
    assert "1. Check overlapping versions." in note
    assert "[Transactions](https://example.org/transactions)" in note
    assert "**Reading question:** What happens to a partial write?" in note
    assert "## Questions for reflection" in note
    for internal in (
        str(record.record_id),
        "Attribution:",
        "Assistance:",
        "Supporting evidence",
        "[!note]",
        "#^evidence",
    ):
        assert internal not in note


def test_frontmatter_upgrade_preserves_existing_personal_text(tmp_path):
    from meditations.render import END, START, daily_frontmatter, update_daily_note

    path = tmp_path / "day.md"
    suffix = b"\n\n## My reflection\n\nMy own reasoning.\n"
    path.write_bytes(START + b"\nSame generated text.\n" + END + suffix)
    assert (
        update_daily_note(
            path,
            "Same generated text.\n",
            metadata=daily_frontmatter(date(2026, 10, 6)),
        )
        == "updated"
    )
    assert path.read_text().startswith("---\ndate: 2026-10-06\n")
    assert path.read_bytes().endswith(suffix)
    assert (
        update_daily_note(
            path,
            "Same generated text.\n",
            metadata=daily_frontmatter(date(2026, 10, 6)),
        )
        == "unchanged"
    )
