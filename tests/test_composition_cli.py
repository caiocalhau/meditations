import json
from datetime import date
from uuid import uuid4

import pytest

from meditations.cli import main
from meditations.composition import (
    CitedText,
    CompositionResponse,
    CompositionResult,
    JournalTopic,
)
from meditations.config import load_workspace
from meditations.extraction.contracts import Usage
from meditations.records import EvidenceRecord
from meditations.render import render_daily, update_daily_note
from meditations.store import persist_record


class Composer:
    def __init__(self):
        self.calls = 0

    def compose(self, request):
        self.calls += 1
        ids = [record.record_id for record in request.records]
        point = CitedText(
            text="Kept client compatibility in view.", source_record_ids=ids
        )
        return CompositionResult(
            response=CompositionResponse(
                overview=[point],
                topics=[JournalTopic(title="Compatibility", paragraphs=[point])],
                open_items=[],
                learning=[],
                reflection_questions=[point],
                supporting_only_record_ids=[],
            ),
            usage=Usage(input_tokens=30, output_tokens=20),
        )


def command(workspace, *extra):
    return [
        "journal",
        "--workspace",
        str(workspace),
        "--date",
        "2026-10-03",
        "--from-records",
        "--model",
        "synthetic",
        "--json",
        *extra,
    ]


def test_composition_candidate_preserves_original_and_reuses_cache(
    workspace, record_data, tmp_path, capsys
):
    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)
    baseline = workspace / "engineering/daily/2026-10-03.md"
    update_daily_note(
        baseline, render_daily([record], load_workspace(workspace), date(2026, 10, 3))
    )
    with baseline.open("a") as output:
        output.write(
            "\nMy handwritten reflection.\n> Existing correction annotation.\n"
        )
    original = baseline.read_bytes()
    candidate = tmp_path / "candidate.md"
    composer = Composer()
    assert main(command(workspace, "--output", str(candidate)), composer=composer) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["composition_status"] == "created"
    assert status["model_calls"] == 1
    assert candidate.read_text().endswith(
        "My handwritten reflection.\n> Existing correction annotation.\n"
    )
    assert "## What changed today" in candidate.read_text()
    assert baseline.read_bytes() == original
    assert main(command(workspace, "--output", str(candidate)), composer=composer) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["composition_status"] == "reused"
    assert status["model_calls"] == 0
    assert status["note_status"] == "unchanged"
    assert composer.calls == 1
    assert baseline.read_bytes() == original


def test_invalid_composition_does_not_replace_existing_note(
    workspace, record_data, capsys
):
    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)
    baseline = workspace / "engineering/daily/2026-10-03.md"
    update_daily_note(baseline, "Existing generated note.")
    original = baseline.read_bytes()

    class InvalidComposer(Composer):
        def compose(self, request):
            result = super().compose(request)
            bad = CitedText(text="Unknown source.", source_record_ids=[uuid4()])
            return CompositionResult(
                response=result.response.model_copy(update={"overview": [bad]}),
                usage=result.usage,
            )

    assert main(command(workspace), composer=InvalidComposer()) == 1
    status = json.loads(capsys.readouterr().out)
    assert status["day_complete"] is False
    assert status["composition_status"] == "failed"
    assert status["model_calls"] == 1
    assert baseline.read_bytes() == original


def test_offline_render_reuses_composition_and_refuses_stale_fallback(
    workspace, record_data, capsys
):
    first = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, first)
    assert main(command(workspace), composer=Composer()) == 0
    capsys.readouterr()
    baseline = workspace / "engineering/daily/2026-10-03.md"
    original = baseline.read_bytes()
    assert main(["render", "--workspace", str(workspace)]) == 0
    capsys.readouterr()
    assert baseline.read_bytes() == original
    second = EvidenceRecord.model_validate(
        record_data | {"record_id": uuid4(), "source_segment_id": "new"}
    )
    persist_record(workspace, second)
    assert main(["render", "--workspace", str(workspace)]) == 1
    capsys.readouterr()
    assert baseline.read_bytes() == original


def test_invalid_baseline_stops_before_composition(workspace, record_data, capsys):
    persist_record(workspace, EvidenceRecord.model_validate(record_data))
    note = workspace / "engineering/daily/2026-10-03.md"
    note.write_text("Personal note without generated boundaries.")
    composer = Composer()
    assert main(command(workspace), composer=composer) == 1
    capsys.readouterr()
    assert composer.calls == 0
    assert note.read_text() == "Personal note without generated boundaries."


def test_candidate_cannot_target_another_daily_note(workspace, record_data, capsys):
    persist_record(workspace, EvidenceRecord.model_validate(record_data))
    other = workspace / "engineering/daily/2026-10-02.md"
    update_daily_note(other, "Previous day.")
    original = other.read_bytes()
    composer = Composer()
    assert main(command(workspace, "--output", str(other)), composer=composer) == 1
    capsys.readouterr()
    assert composer.calls == 0
    assert other.read_bytes() == original


def test_from_records_dry_run_reports_composition_budget_without_writes(
    workspace, record_data, tmp_path, capsys
):
    persist_record(workspace, EvidenceRecord.model_validate(record_data))
    output = tmp_path / "candidate.md"
    composer = Composer()
    assert (
        main(
            command(workspace, "--dry-run", "--output", str(output)), composer=composer
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["evidence_record_count"] == 1
    assert preview["maximum_attempts"] == 1
    assert preview["model_calls"] == 0
    assert not output.exists()
    assert composer.calls == 0


def test_stored_unresolved_day_cannot_bypass_completion_gate(
    workspace, tmp_path, capsys
):
    from datetime import datetime, timezone

    from meditations.extraction.contracts import (
        ConversationUnit,
        ExtractionResponse,
        SourceMessage,
    )
    from meditations.extraction.provider import ProviderResult
    from meditations.extraction.service import ExtractionSettings, extract_unit

    unit = ConversationUnit(
        unit_id="journal:session:2026-10-03:0",
        source_revision=0,
        task_id="task",
        task_label="Task",
        messages=[
            SourceMessage(
                message_id="unresolved",
                role="user",
                content="Substantive unresolved content.",
                occurred_at=datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
                context_only=False,
            )
        ],
    )

    class UnresolvedProvider:
        def extract(self, request):
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[],
                    excluded_message_ids=[],
                    unresolved_message_ids=["unresolved"],
                    unresolved=["Needs review."],
                ),
                usage=Usage(),
            )

    extract_unit(
        workspace,
        "session",
        unit,
        UnresolvedProvider(),
        ExtractionSettings(model="synthetic", state_directory=tmp_path / "state"),
    )
    composer = Composer()
    assert main(command(workspace), composer=composer) == 1
    capsys.readouterr()
    assert composer.calls == 0
    assert not (workspace / "engineering/daily/2026-10-03.md").exists()


@pytest.mark.parametrize("json_output", [True, False])
def test_resource_failure_reports_details_and_preserves_note(
    workspace, record_data, capsys, json_output
):
    from meditations.composition import LearningItem

    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)
    baseline = workspace / "engineering/daily/2026-10-03.md"
    update_daily_note(baseline, "Existing generated note.")
    original = baseline.read_bytes()

    class UnsourcedComposer(Composer):
        def compose(self, request):
            result = super().compose(request)
            point = result.response.overview[0]
            item = LearningItem(
                concept="Reading",
                explanation=point,
                suggested_practice=point,
                resource_urls=["https://example.org/unsourced"],
            )
            return CompositionResult(
                response=result.response.model_copy(update={"learning": [item]}),
                usage=result.usage,
            )

    composer = UnsourcedComposer()
    args = command(workspace)
    if not json_output:
        args.remove("--json")
    assert main(args, composer=composer) == 1
    output = capsys.readouterr().out
    if json_output:
        status = json.loads(output)
        error = status["composition_error"]
        assert error["code"] == "learning_resource_absent_from_evidence"
        assert error["field"] == "learning[0].resource_urls[0]"
        assert error["resource"] == "https://example.org/unsourced"
        assert "https://example.org/unsourced" in status["note_message"]
        assert status["model_calls"] == 1
    else:
        assert "learning[0].resource_urls[0]" in output
        assert "https://example.org/unsourced" in output
        assert "does not occur in any supplied evidence record" in output
    assert composer.calls == 1
    assert baseline.read_bytes() == original
    assert not list((workspace / "compositions").rglob("*.json"))


def test_saved_resource_failure_is_visible_without_model_calls(
    workspace, record_data, capsys
):
    from meditations.composition import LearningItem

    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)

    class Failing(Composer):
        def compose(self, request):
            result = super().compose(request)
            point = result.response.overview[0]
            item = LearningItem(
                concept="Reading",
                explanation=point,
                suggested_practice=point,
                resource_urls=["https://example.org/missing"],
            )
            return CompositionResult(
                result.response.model_copy(update={"learning": [item]}), result.usage
            )

    composer = Failing()
    assert main(command(workspace), composer=composer) == 1
    capsys.readouterr()
    before = {
        path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()
    }
    assert main(command(workspace, "--dry-run"), composer=composer) == 0
    preview = json.loads(capsys.readouterr().out)
    failure = preview["last_composition_failure"]
    assert failure["historical"] is True
    assert failure["evidence_matches"] is True
    assert failure["details"]["field"] == "learning[0].resource_urls[0]"
    assert failure["usage"]["input_tokens"] == 30
    assert failure["composition_calls"] == 1
    assert preview["model_calls"] == 0
    assert composer.calls == 1
    assert {
        path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()
    } == before
    assert main(["status", "--workspace", str(workspace)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["saved_composition_failures"][0]["day"] == "2026-10-03"


def test_over_budget_stored_evidence_stops_before_any_model_call(
    workspace, record_data, capsys
):
    from meditations.composition import MAX_COMPOSITION_BYTES

    record = EvidenceRecord.model_validate(record_data).model_copy(
        update={"summary": "x" * MAX_COMPOSITION_BYTES}
    )
    persist_record(workspace, record)
    composer = Composer()
    assert main(command(workspace), composer=composer) == 1
    status = json.loads(capsys.readouterr().out)
    assert status["composition_error"]["code"] == "composition_input_limit"
    assert status["composition_error"]["input_bytes"] > MAX_COMPOSITION_BYTES
    assert status["model_calls"] == composer.calls == 0
    assert main(command(workspace, "--dry-run"), composer=composer) == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["run_allowed"] is False
    assert preview["last_composition_failure"]["code"] == "composition_input_limit"


def test_saved_failure_is_historical_when_evidence_changes(workspace, record_data):
    from meditations.composition import CompositionBudgetError
    from meditations.diagnostics import (
        load_composition_failure,
        save_composition_failure,
    )

    record = EvidenceRecord.model_validate(record_data)
    config = load_workspace(workspace)
    day = date(2026, 10, 3)
    save_composition_failure(
        workspace, config, day, [record], CompositionBudgetError(70000)
    )
    changed = record.model_copy(update={"summary": "Changed evidence"})
    report = load_composition_failure(workspace, config, day, [changed])
    assert report["historical"] is True
    assert report["evidence_matches"] is False
    assert (
        record.summary
        not in (workspace / "diagnostics/composition/2026-10-03.json").read_text()
    )


def test_diagnostic_save_error_does_not_hide_primary_failure(
    workspace, record_data, capsys, monkeypatch
):
    from meditations.composition import MAX_COMPOSITION_BYTES

    record = EvidenceRecord.model_validate(record_data).model_copy(
        update={"summary": "x" * MAX_COMPOSITION_BYTES}
    )
    persist_record(workspace, record)

    def blocked(*args, **kwargs):
        raise OSError("private error detail")

    monkeypatch.setattr("meditations.journal.save_composition_failure", blocked)
    assert main(command(workspace), composer=Composer()) == 1
    status = json.loads(capsys.readouterr().out)
    assert status["composition_error"]["code"] == "composition_input_limit"
    assert (
        status["diagnostic_report_error"]
        == "Could not save private failure report; primary failure preserved"
    )
    assert "private error detail" not in json.dumps(status)


def test_diagnostic_report_symlink_is_rejected(workspace, record_data, tmp_path):
    from meditations.composition import CompositionBudgetError
    from meditations.diagnostics import (
        load_composition_failure,
        save_composition_failure,
    )

    config = load_workspace(workspace)
    record = EvidenceRecord.model_validate(record_data)
    day = date(2026, 10, 3)
    directory = workspace / "diagnostics/composition"
    directory.mkdir(parents=True)
    target = tmp_path / "untouched.json"
    target.write_text("private file")
    (directory / "2026-10-03.json").symlink_to(target)
    with pytest.raises(ValueError, match="Unsafe"):
        load_composition_failure(workspace, config, day, [record])
    with pytest.raises(ValueError):
        save_composition_failure(
            workspace, config, day, [record], CompositionBudgetError(70000)
        )
    assert target.read_text() == "private file"


def test_preflight_measures_the_filtered_payload(
    workspace, record_data, tmp_path, capsys
):
    record = EvidenceRecord.model_validate(record_data).model_copy(
        update={"summary": "sensitive-value" * 6000}
    )
    persist_record(workspace, record)
    redactions = tmp_path / "redactions.json"
    redactions.write_text(json.dumps(["sensitive-value"]))
    composer = Composer()
    assert (
        main(
            command(workspace, "--dry-run", "--redact-file", str(redactions)),
            composer=composer,
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["composition_input_bytes"] < 65536
    assert preview["run_allowed"] is True
    assert (
        main(command(workspace, "--redact-file", str(redactions)), composer=composer)
        == 0
    )
    assert composer.calls == 1
