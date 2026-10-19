import io
import json
from datetime import datetime, timezone

from meditations.cli import main
from meditations.machine_config import configure


def test_weekly_prepare_schema_write_and_unchanged_cli(tmp_path, capsys, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    settings = tmp_path / "settings.json"
    configure(vault, timezone="UTC", language="en", path=settings)
    daily = vault / "engineering/daily"
    daily.mkdir(parents=True)
    (daily / "2026-10-14.md").write_text(
        "My answer: retry is delivery, not deduplication."
    )
    now = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
    assert main(["weekly", "prepare"], machine_config_path=settings, now=now) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert prepared["week_start"] == "2026-10-12"
    assert main(["schema", "weekly"], machine_config_path=settings) == 0
    assert "initial_practice" in json.loads(capsys.readouterr().out)["properties"]
    draft = {
        "source_snapshot": prepared["source_snapshot"],
        "expected_note_sha256": prepared["expected_note_sha256"],
        "overview": ["A written answer distinguished two mechanisms."],
        "findings": [
            {
                "category": "sound_reasoning",
                "title": "Distinction",
                "assessment": "The answer distinguishes the two mechanisms.",
                "evidence": [
                    {
                        "source_id": "daily:2026-10-14",
                        "quote": "retry is delivery, not deduplication.",
                    }
                ],
            }
        ],
        "initial_practice": {
            "questions": ["Give an example."],
            "actions": ["Try it locally."],
        },
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(draft)))
    assert (
        main(
            ["weekly", "write", "--date", "2026-10-12"],
            machine_config_path=settings,
            now=now,
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "created"
    assert main(["weekly", "prepare"], machine_config_path=settings, now=now) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unchanged"


def test_weekly_prepare_conflict_exposes_unchecked_dates_without_sources(
    tmp_path, capsys
):
    vault = tmp_path / "vault"
    vault.mkdir()
    settings = tmp_path / "settings.json"
    configure(vault, timezone="UTC", language="en", path=settings)
    daily = vault / "engineering/daily"
    daily.mkdir(parents=True)
    (daily / "2026-10-16.md").write_text("Existing daily evidence.")
    target = vault / "engineering/weekly/2026-10-12.md"
    target.parent.mkdir()
    original = b"Manual preview\nMy original response.\n"
    target.write_bytes(original)
    now = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)

    assert (
        main(
            ["weekly", "prepare", "--date", "2026-10-16"],
            machine_config_path=settings,
            now=now,
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "conflict"
    assert result["available_dates"] == result["missing_dates"] == []
    assert result["unchecked_dates"] == [f"2026-10-{day}" for day in range(12, 19)]
    assert result["pending_dates"] == result["sources"] == []
    assert target.read_bytes() == original
