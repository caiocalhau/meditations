import json
from pathlib import Path

import pytest

from meditations.cli import main
from meditations.extraction.contracts import (
    EvidenceCandidate,
    ExtractionResponse,
    Usage,
)
from meditations.extraction.provider import ProviderResult


def source_event(timestamp: str, text: str, role: str = "user") -> dict:
    kind = "input_text" if role == "user" else "output_text"
    return {
        "timestamp": timestamp,
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [{"type": kind, "text": text}],
        },
    }


def add_session(root: Path, repo: Path, session: str, text: str) -> None:
    folder = root / "2026" / "10" / "05"
    folder.mkdir(parents=True, exist_ok=True)
    entries = [
        {
            "type": "session_meta",
            "payload": {"id": session, "cwd": str(repo), "cli_version": "0.160.0"},
        },
        source_event("2026-10-06T12:00:00Z", text),
    ]
    (folder / f"rollout-{session}.jsonl").write_text(
        "\n".join(json.dumps(item) for item in entries) + "\n"
    )


def command(workspace: Path, sessions: Path, repo: Path, *options: str) -> list[str]:
    return [
        "journal",
        "--workspace",
        str(workspace),
        "--date",
        "2026-10-06",
        "--repo",
        str(repo),
        "--sessions-dir",
        str(sessions),
        *options,
    ]


def test_journal_requires_mode_and_date(workspace, capsys):
    with pytest.raises(SystemExit) as error:
        main(["journal", "--workspace", str(workspace)])
    assert error.value.code == 2
    assert "required" in capsys.readouterr().err


def test_default_selection_and_persistent_and_command_exclusions(
    workspace, tmp_path, capsys
):
    config_path = workspace / "workspace.json"
    config = json.loads(config_path.read_text())
    config["excluded_session_ids"] = ["private"]
    config_path.write_text(json.dumps(config))
    sessions = tmp_path / "sessions"
    for identity in ("work", "home", "private", "temporary"):
        add_session(sessions, tmp_path / identity, identity, identity)
    args = [
        "journal",
        "--workspace",
        str(workspace),
        "--sessions-dir",
        str(sessions),
        "--date",
        "2026-10-06",
        "--preview",
        "--json",
        "--exclude-session",
        "temporary",
    ]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert {item["session_id"] for item in result["sessions"]} == {"work", "home"}
    assert result["selection_scope"] == "all-local-repositories"
    assert result["configured_exclusion_count"] == 2


def test_sequential_machines_consolidate_synced_evidence_and_reuse_receipts(
    tmp_path, capsys
):
    import shutil

    from meditations.config import initialize_workspace

    class ConceptProvider:
        calls = 0

        def extract(self, request):
            self.calls += 1
            message = request.unit.messages[0]
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[
                        EvidenceCandidate(
                            primary_message_id=message.message_id,
                            source_message_ids=[message.message_id],
                            summary=message.content,
                            reasoning=[],
                            alternatives=[],
                            decisions=[],
                            outcomes=[],
                            verification=[],
                            tags=[],
                            concepts=[],
                            attribution="user contribution",
                            assistance="guided",
                            uncertainties=[],
                            privacy_omissions=[],
                        )
                    ],
                    excluded_message_ids=[],
                    unresolved_message_ids=[],
                    unresolved=[],
                ),
                usage=Usage(),
                provider="synthetic",
            )

    provider = ConceptProvider()
    work = tmp_path / "work-notes"
    home = tmp_path / "home-notes"
    initialize_workspace(work, "UTC")
    work_sessions = tmp_path / "work-sessions"
    home_sessions = tmp_path / "home-sessions"
    add_session(
        work_sessions,
        tmp_path / "company-repo",
        "work",
        "Studied transaction isolation.",
    )
    add_session(
        home_sessions, tmp_path / "personal-repo", "home", "Practiced retry strategies."
    )

    def run(notes, sessions, state):
        return main(
            [
                "journal",
                "--workspace",
                str(notes),
                "--date",
                "2026-10-06",
                "--sessions-dir",
                str(sessions),
                "--run-model",
                "--model",
                "synthetic",
                "--json",
            ],
            provider=provider,
            state_directory=state,
        )

    assert run(work, work_sessions, tmp_path / "work-state") == 0
    capsys.readouterr()
    note = Path("engineering/daily/2026-10-06.md")
    with (work / note).open("a") as output:
        output.write("\nMy reflection on today's work.\n")
    shutil.copytree(work, home)
    assert run(home, home_sessions, tmp_path / "home-state") == 0
    result = json.loads(capsys.readouterr().out)
    assert result["note_status"] == "updated"
    combined = (home / note).read_text()
    assert "Studied transaction isolation." in combined
    assert "Practiced retry strategies." in combined
    assert combined.endswith("My reflection on today's work.\n")
    assert len(list((home / "records").glob("*.json"))) == 2

    assert run(home, home_sessions, tmp_path / "home-state") == 0
    assert json.loads(capsys.readouterr().out)["note_status"] == "unchanged"
    shutil.copytree(home, work, dirs_exist_ok=True)
    assert run(work, work_sessions, tmp_path / "work-state") == 0
    assert json.loads(capsys.readouterr().out)["note_status"] == "unchanged"
    assert (work / note).read_text() == combined
    assert provider.calls == 2


@pytest.mark.parametrize("exclusion", ["", "space in ID", "a" * 201])
def test_invalid_session_exclusion_fails_without_workspace_writes(
    workspace, tmp_path, capsys, exclusion
):
    before = {
        path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()
    }
    assert (
        main(
            [
                "journal",
                "--workspace",
                str(workspace),
                "--date",
                "2026-10-06",
                "--sessions-dir",
                str(tmp_path / "sessions"),
                "--preview",
                "--exclude-session",
                exclusion,
            ]
        )
        == 1
    )
    assert "session IDs" in capsys.readouterr().err
    assert before == {
        path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()
    }


def test_preview_hides_source_and_makes_no_writes(workspace, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "private-session", "synthetic transcript secret")
    before = {
        path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()
    }

    assert main(command(workspace, sessions, repo, "--preview", "--json")) == 0

    output = json.loads(capsys.readouterr().out)
    after = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    assert output["mode"] == "preview"
    assert output["message_count"] == 1
    assert "synthetic transcript secret" not in json.dumps(output)
    assert before == after
    assert not list((workspace / "engineering/daily").glob("*.md"))


def test_preview_payload_is_explicit_and_invalid_date_fails(
    workspace, tmp_path, capsys
):
    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "s1", "inspectable source")

    assert main(command(workspace, sessions, repo, "--preview", "--show-payload")) == 0
    assert "inspectable source" in capsys.readouterr().out
    args = command(workspace, sessions, repo, "--preview")
    args[args.index("2026-10-06")] = "not-a-date"
    assert main(args) == 1
    assert "date" in capsys.readouterr().err.lower()


def test_no_authorized_activity_creates_no_note(workspace, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"

    assert main(command(workspace, sessions, repo, "--preview", "--json")) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["unit_count"] == 0
    assert not list((workspace / "engineering/daily").glob("*.md"))


def test_preview_reports_over_limit_units_without_calling_provider(
    workspace, tmp_path, capsys
):
    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "one", "one")
    add_session(sessions, repo, "two", "two")

    assert (
        main(
            command(
                workspace, sessions, repo, "--preview", "--max-units", "1", "--json"
            )
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["unit_count"] == 2
    assert result["run_allowed"] is False
    assert result["maximum_attempts"] == 5


def test_oversized_source_is_reported_without_workspace_persistence(
    workspace, tmp_path, capsys
):
    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    folder = sessions / "2026"
    folder.mkdir(parents=True)
    meta = {"type": "session_meta", "payload": {"id": "huge", "cwd": str(repo)}}
    row = source_event("2026-10-06T12:00:00Z", "x" * (2 * 1024 * 1024 + 1))
    (folder / "rollout-huge.jsonl").write_text(
        json.dumps(meta) + "\n" + json.dumps(row) + "\n"
    )

    assert main(command(workspace, sessions, repo, "--dry-run", "--json")) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["sessions"][0]["omissions"]["oversized_line"] == 1
    assert output["unit_count"] == 0
    assert output["model_calls"] == 0
    assert any("omitted" in diagnostic for diagnostic in output["diagnostics"])
    assert not list((workspace / "records").glob("*.json"))


def test_run_processes_multiple_sessions_then_reuses_receipts(
    workspace, tmp_path, capsys
):
    class ExcludingProvider:
        def __init__(self):
            self.calls = 0

        def extract(self, request):
            self.calls += 1
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[],
                    excluded_message_ids=[
                        message.message_id for message in request.unit.messages
                    ],
                    unresolved_message_ids=[],
                    unresolved=[],
                ),
                usage=Usage(),
                provider="synthetic",
            )

    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "first", "one")
    add_session(sessions, repo, "second", "two")
    provider = ExcludingProvider()
    args = command(
        workspace, sessions, repo, "--run-model", "--model", "synthetic", "--json"
    )

    assert main(args, provider=provider, state_directory=tmp_path / "state") == 0
    assert provider.calls == 2
    capsys.readouterr()
    assert main(args, provider=provider, state_directory=tmp_path / "state") == 0
    output = json.loads(capsys.readouterr().out)
    assert provider.calls == 2
    assert output["units"][0]["reused"] == 0
    assert not list((workspace / "engineering/daily").glob("*.md"))


def test_new_activity_automatically_advances_revision(workspace, tmp_path, capsys):
    class ExcludingProvider:
        calls = 0

        def extract(self, request):
            self.calls += 1
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[],
                    excluded_message_ids=[
                        message.message_id for message in request.unit.messages
                    ],
                    unresolved_message_ids=[],
                    unresolved=[],
                ),
                usage=Usage(),
                provider="synthetic",
            )

    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "resumed", "first message")
    provider = ExcludingProvider()
    base = command(
        workspace, sessions, repo, "--run-model", "--model", "synthetic", "--json"
    )
    state = tmp_path / "state"
    assert main(base, provider=provider, state_directory=state) == 0
    capsys.readouterr()

    transcript = next(sessions.rglob("rollout-resumed.jsonl"))
    with transcript.open("a") as output:
        event = source_event("2026-10-06T13:00:00Z", "new message")
        output.write(json.dumps(event) + "\n")
    assert main(base, provider=provider, state_directory=state) == 0
    assert provider.calls == 2
    capsys.readouterr()

    changed_settings = [
        "different-model" if arg == "synthetic" else arg for arg in base
    ]
    assert main(changed_settings, provider=provider, state_directory=state) == 0
    assert provider.calls == 3
    capsys.readouterr()
    assert main(changed_settings, provider=provider, state_directory=state) == 0
    assert provider.calls == 3
    capsys.readouterr()
    receipts = [
        json.loads(path.read_text())
        for path in (workspace / "extractions").glob("*.json")
    ]
    assert sorted(receipt["source_revision"] for receipt in receipts) == [0, 1, 2]
    assert main(changed_settings, provider=provider, state_directory=state) == 0
    assert provider.calls == 3
    capsys.readouterr()


def test_dry_run_previews_without_execution_mode(workspace, tmp_path, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "s1", "learning material")
    assert main(command(workspace, sessions, repo, "--dry-run", "--json")) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["model_calls"] == 0
    assert output["workspace_writes"] == 0
    assert not list((workspace / "records").glob("*.json"))


def test_journal_uses_global_codex_model_when_not_overridden(
    workspace, tmp_path, capsys, monkeypatch
):
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text('model = "synthetic-default"')
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "s1", "Synthetic learning material.")

    class Provider:
        def extract(self, request):
            assert request.model == "synthetic-default"
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[],
                    excluded_message_ids=[m.message_id for m in request.unit.messages],
                    unresolved_message_ids=[],
                    unresolved=[],
                ),
                usage=Usage(),
                provider="synthetic",
            )

    assert (
        main(
            command(workspace, sessions, repo, "--json"),
            provider=Provider(),
            state_directory=tmp_path / "state",
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["model_calls"] == 1


def test_default_run_creates_note_then_adds_new_evidence_without_duplicates(
    workspace, tmp_path, capsys
):
    class EvidenceProvider:
        calls = 0

        def extract(self, request):
            self.calls += 1
            if self.calls == 2:
                from meditations.extraction.provider import ProviderError

                raise ProviderError("timeout")
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[
                        EvidenceCandidate(
                            primary_message_id=message.message_id,
                            source_message_ids=[message.message_id],
                            summary=message.content,
                            reasoning=[],
                            alternatives=[],
                            decisions=[],
                            outcomes=[],
                            verification=[],
                            tags=[],
                            concepts=[],
                            attribution="user contribution",
                            assistance="guided",
                            uncertainties=[],
                            privacy_omissions=[],
                        )
                        for message in request.unit.messages
                    ],
                    excluded_message_ids=[],
                    unresolved_message_ids=[],
                    unresolved=[],
                ),
                usage=Usage(),
                provider="synthetic",
            )

    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "s1", "Studied isolation.")
    provider = EvidenceProvider()
    args = command(workspace, sessions, repo, "--model", "synthetic", "--json")
    state = tmp_path / "state"
    assert main(args, provider=provider, state_directory=state) == 0
    assert json.loads(capsys.readouterr().out)["note_status"] == "created"
    note = workspace / "engineering/daily/2026-10-06.md"
    with note.open("a") as output:
        output.write("\nMy reflection.\n")
    before_update = note.read_bytes()
    with next(sessions.rglob("*.jsonl")).open("a") as output:
        output.write(
            json.dumps(source_event("2026-10-06T13:00:00Z", "Practiced retries."))
            + "\n"
        )
    assert main(args, provider=provider, state_directory=state) == 1
    assert json.loads(capsys.readouterr().out)["note_status"] == "not-rendered"
    assert note.read_bytes() == before_update
    assert main(args, provider=provider, state_directory=state) == 0
    assert json.loads(capsys.readouterr().out)["note_status"] == "updated"
    combined = note.read_bytes()
    assert b"Studied isolation." in combined and b"Practiced retries." in combined
    assert combined.endswith(b"My reflection.\n")
    from meditations.extraction.receipts import select_active_records
    from meditations.store import load_records

    active = select_active_records(workspace, load_records(workspace))
    assert sorted(record.summary for record in active) == [
        "Practiced retries.",
        "Studied isolation.",
    ]
    assert main(args, provider=provider, state_directory=state) == 0
    assert json.loads(capsys.readouterr().out)["note_status"] == "unchanged"
    assert note.read_bytes() == combined
    assert provider.calls == 3

    note.unlink()
    assert main(args, provider=provider, state_directory=state) == 0
    assert json.loads(capsys.readouterr().out)["note_status"] == "created"
    assert provider.calls == 3

    note.unlink()
    for path in sessions.rglob("*.jsonl"):
        path.unlink()
    assert main(args, provider=provider, state_directory=state) == 0
    assert json.loads(capsys.readouterr().out)["note_status"] == "created"
    assert "Practiced retries." in note.read_text()
    assert provider.calls == 3


def test_max_units_refuses_entire_batch_before_provider_calls(
    workspace, tmp_path, capsys
):
    class NeverCalled:
        calls = 0

        def extract(self, request):
            self.calls += 1
            raise AssertionError("provider must not run")

    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "one", "one")
    add_session(sessions, repo, "two", "two")
    provider = NeverCalled()

    assert (
        main(
            command(
                workspace,
                sessions,
                repo,
                "--run-model",
                "--model",
                "synthetic",
                "--max-units",
                "1",
            ),
            provider=provider,
            state_directory=tmp_path / "state",
        )
        == 1
    )
    assert provider.calls == 0
    assert "above --max-units" in capsys.readouterr().err
    assert not list((workspace / "records").glob("*.json"))


def test_partial_extraction_reports_incomplete_without_rendering_then_recovers(
    workspace, tmp_path, capsys
):
    class SometimesFails:
        def __init__(self):
            self.calls = 0

        def extract(self, request):
            self.calls += 1
            if self.calls == 2:
                from meditations.extraction.provider import ProviderError

                raise ProviderError("timeout")
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[],
                    excluded_message_ids=[
                        message.message_id for message in request.unit.messages
                    ],
                    unresolved_message_ids=[],
                    unresolved=[],
                ),
                usage=Usage(),
                provider="synthetic",
            )

    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "one", "one")
    add_session(sessions, repo, "two", "two")
    provider = SometimesFails()
    args = command(
        workspace, sessions, repo, "--run-model", "--model", "synthetic", "--json"
    )

    assert main(args, provider=provider, state_directory=tmp_path / "state") == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["day_complete"] is False
    assert failed["note_status"] == "not-rendered"
    assert not list((workspace / "engineering/daily").glob("*.md"))

    class Recovered:
        calls = 0

        def extract(self, request):
            self.calls += 1
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[],
                    excluded_message_ids=[
                        message.message_id for message in request.unit.messages
                    ],
                    unresolved_message_ids=[],
                    unresolved=[],
                ),
                usage=Usage(),
                provider="synthetic",
            )

    recovered = Recovered()
    assert main(args, provider=recovered, state_directory=tmp_path / "state") == 0
    assert recovered.calls == 1
    capsys.readouterr()


def test_journal_creates_note_then_reuses_receipt_and_preserves_reflection(
    workspace, tmp_path, capsys, monkeypatch
):
    class CandidateProvider:
        calls = 0

        def extract(self, request):
            self.calls += 1
            message = request.unit.messages[0]
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[
                        EvidenceCandidate(
                            primary_message_id=message.message_id,
                            source_message_ids=[message.message_id],
                            summary="Resolved the synthetic issue.",
                            reasoning=[],
                            alternatives=[],
                            decisions=[],
                            outcomes=[],
                            verification=[],
                            tags=[],
                            concepts=[],
                            attribution="user contribution",
                            assistance="guided",
                            uncertainties=[],
                            privacy_omissions=[],
                        )
                    ],
                    excluded_message_ids=[],
                    unresolved_message_ids=[],
                    unresolved=[],
                ),
                usage=Usage(),
                provider="synthetic",
            )

    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "note-session", "fixed a small bug")
    provider = CandidateProvider()
    args = command(
        workspace, sessions, repo, "--run-model", "--model", "synthetic", "--json"
    )
    state = tmp_path / "state"

    assert main(args, provider=provider, state_directory=state) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["note_status"] == "created"
    note = workspace / "engineering/daily/2026-10-06.md"
    original = note.read_text()
    note.write_text(original + "\nMy handwritten reflection.\n")

    assert main(args, provider=provider, state_directory=state) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["note_status"] == "unchanged"
    assert provider.calls == 1
    assert note.read_text().endswith("My handwritten reflection.\n")

    from meditations import journal as journal_module

    def fail_write(*args, **kwargs):
        raise OSError("synthetic disk error")

    monkeypatch.setattr(journal_module, "update_daily_note", fail_write)
    assert main(args, provider=provider, state_directory=state) == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["note_status"] == "failed"
    assert "failed after extraction" in failed["note_message"]
    assert provider.calls == 1
    assert note.read_text().endswith("My handwritten reflection.\n")


def test_unmarked_daily_note_is_preserved_and_conflict_has_explanation(
    workspace, tmp_path, capsys
):
    class CandidateProvider:
        def extract(self, request):
            message = request.unit.messages[0]
            return ProviderResult(
                response=ExtractionResponse(
                    candidates=[
                        EvidenceCandidate(
                            primary_message_id=message.message_id,
                            source_message_ids=[message.message_id],
                            summary="Synthetic evidence.",
                            reasoning=[],
                            alternatives=[],
                            decisions=[],
                            outcomes=[],
                            verification=[],
                            tags=[],
                            concepts=[],
                            attribution="user contribution",
                            assistance="guided",
                            uncertainties=[],
                            privacy_omissions=[],
                        )
                    ],
                    excluded_message_ids=[],
                    unresolved_message_ids=[],
                    unresolved=[],
                ),
                usage=Usage(),
                provider="synthetic",
            )

    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "conflict-session", "source")
    note = workspace / "engineering/daily/2026-10-06.md"
    note.write_text("A pilot note without generated markers.\n")

    assert (
        main(
            command(
                workspace,
                sessions,
                repo,
                "--run-model",
                "--model",
                "synthetic",
                "--json",
            ),
            provider=CandidateProvider(),
            state_directory=tmp_path / "state",
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert result["note_status"] == "conflict"
    assert "preserved" in result["note_message"]
    assert note.read_text() == "A pilot note without generated markers.\n"


def test_prompt_contains_selected_output_language(workspace):
    from meditations.config import load_workspace
    from meditations.extraction.prompt import request_payload
    from meditations.extraction.provider import ExtractionRequest
    from meditations.extraction.validation import validate_input

    source = validate_input(
        (Path(__file__).parent / "fixtures/extraction/conversation.json").read_bytes(),
        load_workspace(workspace),
    )
    payload = request_payload(
        ExtractionRequest(unit=source.units[0], model="synthetic", language="pt-BR")
    )

    assert "Escreva todos os campos" in payload


def test_unresolved_extraction_preserves_note_without_composition(
    workspace, tmp_path, record_data, monkeypatch, capsys
):
    from datetime import datetime, timezone

    from meditations.extraction.service import ExtractionOutcome
    from meditations.records import EvidenceRecord
    from meditations.render import update_daily_note
    from meditations.store import persist_record

    repo = tmp_path / "repo"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    add_session(sessions, repo, "partial-session", "A substantive unresolved issue.")
    persist_record(
        workspace,
        EvidenceRecord.model_validate(
            record_data
            | {"occurred_at": datetime(2026, 10, 6, 12, tzinfo=timezone.utc)}
        ),
    )
    note = workspace / "engineering/daily/2026-10-06.md"
    update_daily_note(note, "Existing complete note.")
    original = note.read_bytes()
    monkeypatch.setattr(
        "meditations.journal.extract_unit",
        lambda *a, **k: ExtractionOutcome(
            unresolved_message_ids=["important-message"], attempts=1
        ),
    )

    class NoComposer:
        def compose(self, request):
            raise AssertionError("Partial day must not be composed")

    assert (
        main(
            command(workspace, sessions, repo, "--model", "synthetic", "--json"),
            provider=object(),
            composer=NoComposer(),
        )
        == 1
    )
    status = json.loads(capsys.readouterr().out)
    assert status["day_complete"] is False
    assert note.read_bytes() == original


def test_journal_status_explains_validation_failure(capsys):
    from meditations.journal import _emit

    _emit(
        {
            "units": [
                {
                    "unit_id": "synthetic-unit",
                    "failure_category": "validation",
                    "failure_detail": "Invalid or incomplete source coverage",
                }
            ]
        },
        False,
    )
    assert (
        "Validation: Invalid or incomplete source coverage" in capsys.readouterr().out
    )


def test_stored_composition_budget_blocks_new_extraction(
    workspace, record_data, tmp_path, capsys
):
    from datetime import datetime, timezone

    from meditations.composition import MAX_COMPOSITION_BYTES
    from meditations.records import EvidenceRecord
    from meditations.store import persist_record

    record = EvidenceRecord.model_validate(record_data).model_copy(
        update={
            "occurred_at": datetime(2026, 10, 6, 12, tzinfo=timezone.utc),
            "summary": "x" * MAX_COMPOSITION_BYTES,
        }
    )
    persist_record(workspace, record)
    sessions = tmp_path / "sessions"
    add_session(sessions, tmp_path, "new-session", "Additional daily work.")

    class NeverCalled:
        def extract(self, request):
            raise AssertionError("Budget must be checked before extraction")

        def compose(self, request):
            raise AssertionError("Budget must be checked before composition")

    assert (
        main(
            command(workspace, sessions, tmp_path, "--model", "synthetic", "--json"),
            provider=NeverCalled(),
        )
        == 1
    )
    status = json.loads(capsys.readouterr().out)
    assert status["model_calls"] == 0
    assert status["composition_error"]["code"] == "composition_input_limit"
    assert status["units"] == []
