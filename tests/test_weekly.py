from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from meditations.machine_config import configure
from meditations.weekly import MAX_SOURCE_BYTES, prepare_week
from meditations.weekly_contracts import (
    EvidenceReference,
    WeeklyDraft,
    WeeklyFinding,
    WeeklyPractice,
)
from meditations.weekly_render import write_weekly

NOW = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)


def setup_week(tmp_path, language="en"):
    vault = tmp_path / "vault"
    vault.mkdir()
    config = configure(
        vault,
        timezone="America/Sao_Paulo",
        language=language,
        path=tmp_path / "config.json",
    )
    daily = vault / "engineering/daily"
    daily.mkdir(parents=True)
    (daily / "2026-10-13.md").write_text(
        "<!-- meditations:generated:start -->\n# Work\nA retry succeeded.\n"
        "<!-- meditations:generated:end -->\n## My reflection\n"
        "I confused retry with deduplication.\n"
    )
    return config


def draft_for(prepared):
    return WeeklyDraft(
        source_snapshot=prepared.source_snapshot,
        expected_note_sha256=prepared.expected_note_sha256,
        overview=["Retry handling was clarified; application remains untested."],
        findings=[
            WeeklyFinding(
                category="incomplete_reasoning",
                title="Retry and deduplication",
                assessment="The reflection names a distinction worth practising.",
                next_step="Explain which behavior prevents duplicate effects.",
                evidence=[
                    EvidenceReference(
                        source_id="daily:2026-10-13",
                        quote="I confused retry with deduplication.",
                    )
                ],
            )
        ],
        initial_practice=WeeklyPractice(
            questions=["How do retries differ from deduplication?"],
            actions=["Sketch a retry that causes a duplicate effect."],
        )
        if prepared.expected_note_sha256 is None
        else None,
    )


def test_partial_week_reads_full_daily_note_and_reports_coverage(tmp_path):
    config = setup_week(tmp_path)
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    assert prepared.status == "ready"
    assert prepared.week_start == date(2026, 10, 12)
    assert prepared.week_end == date(2026, 10, 18)
    assert prepared.provisional
    assert prepared.available_dates == [date(2026, 10, 13)]
    assert prepared.missing_dates == [
        date(2026, 10, 12),
        date(2026, 10, 14),
        date(2026, 10, 15),
    ]
    assert prepared.pending_dates == [
        date(2026, 10, 16),
        date(2026, 10, 17),
        date(2026, 10, 18),
    ]
    assert "meditations:generated:start" in prepared.sources[0].body
    assert "I confused retry" in prepared.sources[0].body
    assert not (config.workspace / "engineering/weekly").exists()


def test_write_is_immediately_idempotent_and_preserves_answers_and_questions(tmp_path):
    config = setup_week(tmp_path)
    daily = config.workspace / "engineering/daily/2026-10-13.md"
    original_daily = daily.read_bytes()
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    result = write_weekly(config, date(2026, 10, 12), draft_for(prepared), now=NOW)
    assert result.status == "created"
    target = config.workspace / "engineering/weekly/2026-10-12.md"
    assert "Weekly review — 12–18 October 2026" in target.read_text()
    assert prepare_week(config, date(2026, 10, 15), now=NOW).status == "unchanged"
    target.write_bytes(
        target.read_bytes().replace(
            b"My response:\n", b"My response:\nMy own answer.\n", 1
        )
    )
    original_outside = target.read_bytes().split(b"<!-- meditations:generated:end -->")[
        1
    ]
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    assert prepared.status == "ready"
    assert any("My own answer." in source.body for source in prepared.sources)
    assert (
        write_weekly(config, prepared.week_start, draft_for(prepared), now=NOW).status
        == "updated"
    )
    assert (
        target.read_bytes().split(b"<!-- meditations:generated:end -->")[1]
        == original_outside
    )
    assert daily.read_bytes() == original_daily
    assert prepare_week(config, prepared.week_start, now=NOW).status == "unchanged"


@pytest.mark.parametrize(
    "failure", ["quote", "source", "stale_note", "stale_source", "practice"]
)
def test_invalid_or_stale_draft_preserves_existing_files(tmp_path, failure):
    config = setup_week(tmp_path)
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    draft = draft_for(prepared)
    target = config.workspace / "engineering/weekly/2026-10-12.md"
    if failure == "quote":
        draft = draft.model_copy(
            update={
                "findings": [
                    draft.findings[0].model_copy(
                        update={
                            "evidence": [
                                EvidenceReference(
                                    source_id="daily:2026-10-13", quote="invented quote"
                                )
                            ]
                        }
                    )
                ]
            }
        )
    elif failure == "source":
        draft = draft.model_copy(
            update={
                "findings": [
                    draft.findings[0].model_copy(
                        update={
                            "evidence": [
                                EvidenceReference(
                                    source_id="daily:2000-01-01",
                                    quote="A retry succeeded.",
                                )
                            ]
                        }
                    )
                ]
            }
        )
    elif failure == "stale_note":
        target.parent.mkdir(parents=True)
        target.write_text("My handwritten note")
    elif failure == "stale_source":
        (config.workspace / "engineering/daily/2026-10-14.md").write_text("Late source")
    else:
        assert (
            write_weekly(config, prepared.week_start, draft, now=NOW).status
            == "created"
        )
        target.write_bytes(target.read_bytes() + b"\nPersonal addition\n")
        refreshed = prepare_week(config, prepared.week_start, now=NOW)
        draft = draft.model_copy(
            update={
                "source_snapshot": refreshed.source_snapshot,
                "expected_note_sha256": refreshed.expected_note_sha256,
            }
        )
    original = target.read_bytes() if target.exists() else None
    result = write_weekly(config, prepared.week_start, draft, now=NOW)
    assert result.status == "conflict"
    assert (target.read_bytes() if target.exists() else None) == original


def test_size_limit_and_bad_encoding_stop_before_returning_source_text(tmp_path):
    config = setup_week(tmp_path)
    source = config.workspace / "engineering/daily/2026-10-13.md"
    source.write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    assert prepared.status == "conflict"
    assert not prepared.sources
    assert "262145" in prepared.message
    assert "262144" in prepared.message
    source.write_bytes(b"\xff")
    assert prepare_week(config, date(2026, 10, 15), now=NOW).status == "conflict"


def test_next_week_reads_previous_practice_not_previous_generated_analysis(tmp_path):
    config = setup_week(tmp_path)
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    write_weekly(config, prepared.week_start, draft_for(prepared), now=NOW)
    prior = config.workspace / "engineering/weekly/2026-10-12.md"
    prior.write_bytes(
        prior.read_bytes().replace(b"My response:\n", b"My response:\nMy attempt.\n", 1)
    )
    (config.workspace / "engineering/daily/2026-10-19.md").write_text("A new work day.")
    following = prepare_week(
        config, date(2026, 10, 20), now=datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
    )
    context = next(
        source for source in following.sources if source.kind == "previous_practice"
    )
    assert "My attempt." in context.body
    assert "How do retries differ" in context.body
    assert "Retry handling was clarified" not in context.body


def test_local_date_and_year_boundary_and_future_week(tmp_path):
    config = setup_week(tmp_path)
    boundary = prepare_week(
        config, None, now=datetime(2027, 1, 4, 1, tzinfo=timezone.utc)
    )
    assert boundary.week_start == date(2026, 12, 28)
    assert boundary.week_end == date(2027, 1, 3)
    assert boundary.provisional
    assert prepare_week(config, date(2027, 1, 10), now=NOW).status == "empty"


def test_unmarked_and_symlink_targets_are_conflicts(tmp_path):
    config = setup_week(tmp_path)
    target = config.workspace / "engineering/weekly/2026-10-12.md"
    target.parent.mkdir()
    target.write_text("Private original")
    assert prepare_week(config, date(2026, 10, 15), now=NOW).status == "conflict"
    target.unlink()
    target.symlink_to(config.workspace / "engineering/daily/2026-10-13.md")
    assert prepare_week(config, date(2026, 10, 15), now=NOW).status == "conflict"


@pytest.mark.parametrize(
    "body",
    [b"Manual preview\nMy answer: keep it.\n", b"<!-- meditations:generated:start -->"],
)
def test_target_conflict_leaves_elapsed_coverage_unchecked(tmp_path, body):
    config = setup_week(tmp_path)
    ready = prepare_week(config, date(2026, 10, 15), now=NOW)
    draft = draft_for(ready)
    target = Path(ready.path)
    target.parent.mkdir()
    target.write_bytes(body)

    result = prepare_week(config, date(2026, 10, 15), now=NOW)

    assert result.status == "conflict"
    assert result.available_dates == []
    assert result.missing_dates == []
    assert result.unchecked_dates == [date(2026, 10, day) for day in range(12, 16)]
    assert result.pending_dates == [date(2026, 10, day) for day in range(16, 19)]
    assert result.sources == []
    assert write_weekly(config, result.week_start, draft, now=NOW).status == "conflict"
    assert target.read_bytes() == body


@pytest.mark.parametrize(
    "failure", ["encoding", "oversized", "symlink", "filesystem", "suppressed_error"]
)
def test_interrupted_discovery_preserves_only_confirmed_coverage(
    tmp_path, monkeypatch, failure
):
    config = setup_week(tmp_path)
    daily = config.workspace / "engineering/daily"
    failed = daily / "2026-10-14.md"
    later = daily / "2026-10-15.md"
    later.write_text("A later existing note.")
    if failure == "encoding":
        failed.write_bytes(b"\xff")
    elif failure == "oversized":
        failed.write_bytes(b"x" * (MAX_SOURCE_BYTES + 1))
    elif failure == "symlink":
        failed.symlink_to(later)
    else:
        original_lstat = Path.lstat

        def inaccessible(path):
            if path == failed:
                raise PermissionError(13, "Permission denied", str(path))
            return original_lstat(path)

        monkeypatch.setattr(Path, "lstat", inaccessible)
        if failure == "suppressed_error":
            # Python 3.14 path predicates return False for inspection errors.
            for name in ("exists", "is_symlink"):
                original = getattr(Path, name)

                def suppressed(path, predicate=original):
                    return False if path == failed else predicate(path)

                monkeypatch.setattr(Path, name, suppressed)

    result = prepare_week(config, date(2026, 10, 15), now=NOW)

    assert result.status == "conflict"
    assert result.available_dates == [date(2026, 10, 13)]
    assert result.missing_dates == [date(2026, 10, 12)]
    assert result.unchecked_dates == [date(2026, 10, 14), date(2026, 10, 15)]
    assert result.pending_dates == [date(2026, 10, day) for day in range(16, 19)]
    assert result.sources == []
    assert "2026-10-14.md" in result.message
    assert not (config.workspace / "engineering/weekly").exists()


def test_post_discovery_conflict_retains_complete_daily_coverage(tmp_path):
    config = setup_week(tmp_path)
    prior = config.workspace / "engineering/weekly/2026-10-05.md"
    prior.parent.mkdir()
    prior.write_text("<!-- meditations:generated:start -->")

    result = prepare_week(config, date(2026, 10, 15), now=NOW)

    assert result.status == "conflict"
    assert result.available_dates == [date(2026, 10, 13)]
    assert result.missing_dates == [date(2026, 10, day) for day in (12, 14, 15)]
    assert result.unchecked_dates == []
    assert result.sources == []


def test_successful_empty_future_and_unchanged_coverage_is_fully_checked(tmp_path):
    config = setup_week(tmp_path)
    ready = prepare_week(config, date(2026, 10, 15), now=NOW)
    assert ready.unchecked_dates == []
    write_weekly(config, ready.week_start, draft_for(ready), now=NOW)
    unchanged = prepare_week(config, ready.week_start, now=NOW)
    assert unchanged.status == "unchanged"
    assert unchanged.unchecked_dates == []
    assert unchanged.available_dates == ready.available_dates
    assert unchanged.missing_dates == ready.missing_dates

    empty = prepare_week(config, date(2026, 9, 30), now=NOW)
    assert empty.status == "empty"
    assert len(empty.missing_dates) == 7
    assert empty.unchecked_dates == []
    future = prepare_week(config, date(2026, 10, 20), now=NOW)
    assert future.status == "empty"
    assert future.unchecked_dates == future.missing_dates == []
    assert len(future.pending_dates) == 7


@pytest.mark.parametrize(
    ("language", "start", "end", "expected"),
    [
        (
            "en",
            date(2026, 10, 26),
            date(2026, 11, 1),
            "Weekly review — 26 October–1 November 2026",
        ),
        (
            "en",
            date(2026, 12, 28),
            date(2027, 1, 3),
            "Weekly review — 28 December 2026–3 January 2027",
        ),
        (
            "pt-BR",
            date(2026, 10, 12),
            date(2026, 10, 18),
            "Revisão semanal — 12–18 de outubro de 2026",
        ),
    ],
)
def test_readable_weekly_titles(language, start, end, expected):
    from meditations.weekly_render import weekly_title

    assert weekly_title(start, end, language) == expected


def test_english_feedback_requires_saved_opt_in_and_cited_source(tmp_path):
    from meditations.weekly_contracts import EnglishFeedback

    config = setup_week(tmp_path)
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    draft = draft_for(prepared).model_copy(
        update={
            "english_feedback": [
                EnglishFeedback(
                    evidence=EvidenceReference(
                        source_id="daily:2026-10-13",
                        quote="I confused retry with deduplication.",
                    ),
                    suggestion="I confused retries with deduplication.",
                    explanation="The plural can refer to retry attempts in general.",
                )
            ]
        }
    )
    assert (
        write_weekly(config, prepared.week_start, draft, now=NOW).status == "conflict"
    )
    config = config.model_copy(update={"english_feedback": True})
    refreshed = prepare_week(config, date(2026, 10, 15), now=NOW)
    draft = draft.model_copy(update={"source_snapshot": refreshed.source_snapshot})
    assert (
        write_weekly(config, refreshed.week_start, draft, now=NOW).status == "created"
    )
    text = (config.workspace / "engineering/weekly/2026-10-12.md").read_text()
    assert "English feedback" in text
    assert "I confused retries with deduplication." in text


def test_prior_unmarked_notes_warn_and_bad_supported_practice_is_conflict(tmp_path):
    config = setup_week(tmp_path)
    weekly = config.workspace / "engineering/weekly"
    weekly.mkdir()
    (weekly / "2026-10-05.md").write_text("Older handwritten review")
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    assert prepared.status == "ready"
    assert prepared.warnings
    (weekly / "2026-10-05.md").write_text(
        "<!-- meditations:template:weekly-review-v1 -->\nBroken"
    )
    assert prepare_week(config, prepared.week_start, now=NOW).status == "conflict"


def test_aggregate_limit_stops_before_drafting_and_whitespace_citations_work(tmp_path):
    config = setup_week(tmp_path)
    daily = config.workspace / "engineering/daily"
    original = (daily / "2026-10-13.md").read_bytes()
    (daily / "2026-10-13.md").write_bytes(b"a" * (MAX_SOURCE_BYTES // 2 + 1))
    (daily / "2026-10-14.md").write_bytes(b"b" * (MAX_SOURCE_BYTES // 2))
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    assert prepared.status == "conflict"
    assert prepared.sources == []
    assert "262145" in prepared.message
    (daily / "2026-10-14.md").unlink()
    (daily / "2026-10-13.md").write_bytes(
        original.replace(b"confused retry", b"confused\n  retry")
    )
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    assert (
        write_weekly(config, prepared.week_start, draft_for(prepared), now=NOW).status
        == "created"
    )


def test_enabled_english_without_feedback_requires_an_explicit_limitation(tmp_path):
    config = setup_week(tmp_path).model_copy(update={"english_feedback": True})
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    result = write_weekly(config, prepared.week_start, draft_for(prepared), now=NOW)
    assert result.status == "conflict"
    assert "limitation" in result.message
    assert not (config.workspace / "engineering/weekly/2026-10-12.md").exists()


def test_source_change_during_rendering_preserves_note(tmp_path, monkeypatch):
    import meditations.weekly_render as renderer

    config = setup_week(tmp_path)
    prepared = prepare_week(config, date(2026, 10, 15), now=NOW)
    original_render = renderer._analysis

    def change_source(preparation, draft, snapshot):
        (config.workspace / "engineering/daily/2026-10-14.md").write_text(
            "A late daily note."
        )
        return original_render(preparation, draft, snapshot)

    monkeypatch.setattr(renderer, "_analysis", change_source)
    result = renderer.write_weekly(
        config, prepared.week_start, draft_for(prepared), now=NOW
    )
    assert result.status == "conflict"
    assert not (config.workspace / "engineering/weekly/2026-10-12.md").exists()
