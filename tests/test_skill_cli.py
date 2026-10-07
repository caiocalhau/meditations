import io
import json
from datetime import datetime, timezone

import meditations.cli as cli
from meditations.captures import save_capture
from meditations.cli import main
from meditations.contracts import CaptureDraft, DailyDraft, JournalTopic
from meditations.machine_config import configure


def test_configure_capture_prepare_and_schema_commands(tmp_path, monkeypatch, capsys):
    vault = tmp_path / "vault"
    vault.mkdir()
    settings = tmp_path / "machine" / "config.json"
    assert (
        main(
            [
                "configure",
                "--workspace",
                str(vault),
                "--timezone",
                "America/Sao_Paulo",
                "--language",
                "en",
            ],
            machine_config_path=settings,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "configured"

    assert (
        main(
            ["config", "show"],
            machine_config_path=settings,
            now=datetime(2026, 10, 8, 2, 0, tzinfo=timezone.utc),
        )
        == 0
    )
    local = json.loads(capsys.readouterr().out)
    assert local == {
        "timezone": "America/Sao_Paulo",
        "language": "en",
        "today": "2026-10-07",
    }

    monkeypatch.setattr(
        "sys.stdin",
        io.StringIO(json.dumps({"body": "Reviewed an implementation choice."})),
    )
    assert (
        main(
            ["capture", "--date", "2026-10-07", "--input", "-"],
            machine_config_path=settings,
            now=datetime(2026, 10, 7, 12, tzinfo=timezone.utc),
        )
        == 0
    )
    capture_result = json.loads(capsys.readouterr().out)
    assert capture_result["status"] == "created"
    assert "vault" in capture_result["path"]

    assert (
        main(
            ["daily", "prepare", "--date", "2026-10-07"],
            machine_config_path=settings,
        )
        == 0
    )
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["status"] == "ready"
    assert "Reviewed an implementation choice." in prepared["captures"][0]["body"]

    assert main(["schema", "capture"], machine_config_path=settings) == 0
    assert json.loads(capsys.readouterr().out)["properties"] == {
        "body": {"maxLength": 65536, "minLength": 1, "title": "Body", "type": "string"}
    }


def test_daily_prepare_unchanged_exits_without_returning_capture_bodies(
    tmp_path, monkeypatch, capsys
):
    vault = tmp_path / "vault"
    vault.mkdir()
    settings = tmp_path / "machine.json"
    assert (
        main(
            ["configure", "--workspace", str(vault), "--timezone", "UTC"],
            machine_config_path=settings,
        )
        == 0
    )
    capsys.readouterr()
    monkeypatch.setattr("sys.stdin", io.StringIO('{"body":"Work recorded."}'))
    main(["capture", "--date", "2026-10-07"], machine_config_path=settings)
    capsys.readouterr()

    assert (
        main(
            ["daily", "prepare", "--date", "2026-10-07"],
            machine_config_path=settings,
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ready"
    (vault / "engineering/daily").mkdir(parents=True)
    target = vault / "engineering/daily/2026-10-07.md"
    target.write_text(
        "<!-- meditations:generated:start -->\n"
        f"<!-- meditations:sources:{payload['source_snapshot']} -->\n"
        "existing generated report\n<!-- meditations:generated:end -->\n"
    )

    assert (
        main(
            ["daily", "prepare", "--date", "2026-10-07"],
            machine_config_path=settings,
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "unchanged"
    assert payload["captures"] == []


def test_cli_daily_write_publishes_only_a_matching_prepared_draft(
    tmp_path, capsys, monkeypatch
):
    vault = tmp_path / "vault"
    vault.mkdir()
    settings = tmp_path / "machine.json"
    config = configure(vault, timezone="UTC", language="en", path=settings)
    save_capture(
        vault,
        datetime(2026, 10, 7).date(),
        CaptureDraft(body="A useful project decision."),
        captured_at=datetime(2026, 10, 7, 12, tzinfo=timezone.utc),
    )
    main(["daily", "prepare", "--date", "2026-10-07"], machine_config_path=settings)
    prepared = json.loads(capsys.readouterr().out)
    draft = DailyDraft(
        source_snapshot=prepared["source_snapshot"],
        expected_note_sha256=prepared["expected_note_sha256"],
        overview=["One decision clarified the implementation."],
        topics=[JournalTopic(title="Design", paragraphs=["The next step is clear."])],
        reflection_questions=["What made this step appropriate?"],
    )
    monkeypatch.setattr(cli.sys, "stdin", io.StringIO(draft.model_dump_json()))
    assert (
        main(
            ["daily", "write", "--date", "2026-10-07"],
            machine_config_path=settings,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "created"
    assert (config.workspace / "engineering/daily/2026-10-07.md").is_file()


def test_cli_validation_errors_do_not_echo_submitted_session_text(
    tmp_path, monkeypatch, capsys
):
    vault = tmp_path / "vault"
    vault.mkdir()
    settings = tmp_path / "machine.json"
    configure(vault, timezone="UTC", language="en", path=settings)
    private_text = "private-session-content-7f4c"
    monkeypatch.setattr(
        cli.sys,
        "stdin",
        io.StringIO(json.dumps({"body": " ", f"{private_text}-field": private_text})),
    )

    result = main(["capture", "--date", "2026-10-07"], machine_config_path=settings)

    output = capsys.readouterr().err
    assert result == 1
    assert private_text not in output
    assert "body" in output
    assert "at least 1 character" in output


def test_cli_requires_documented_iso_date_form():
    from argparse import ArgumentTypeError

    import pytest

    with pytest.raises(ArgumentTypeError, match="YYYY-MM-DD"):
        cli._date("20261007")
