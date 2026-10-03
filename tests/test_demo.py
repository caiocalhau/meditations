import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    result = subprocess.run(
        [sys.executable, "-m", "meditations.cli", *args],
        env=os.environ | {"PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    return result.stdout


def test_offline_demo_with_reimport_and_reflection(tmp_path):
    workspace = tmp_path / "notes"
    run_cli("init", "--workspace", str(workspace), "--timezone", "America/Sao_Paulo")
    config = json.loads((workspace / "workspace.json").read_text())
    source = tmp_path / "input.jsonl"
    records = [
        json.loads(line)
        for line in (ROOT / "examples/records.jsonl").read_text().splitlines()
    ]
    for record in records:
        record["workspace_id"] = config["workspace_id"]
    source.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    assert json.loads(
        run_cli("import-records", "--workspace", str(workspace), "--input", str(source))
    ) == {"created": 3, "unchanged": 0}
    assert json.loads(
        run_cli("import-records", "--workspace", str(workspace), "--input", str(source))
    ) == {"created": 0, "unchanged": 3}
    run_cli("render", "--workspace", str(workspace))
    note = workspace / "engineering/daily/2026-10-03.md"
    with note.open("a") as stream:
        stream.write("\nI can explain the compatibility concern now.\n")
    before = note.read_bytes()
    run_cli("render", "--workspace", str(workspace))
    assert note.read_bytes() == before
    assert (workspace / "engineering/daily/2026-10-04.md").exists()
    assert "Agent explained rollback." in note.read_text()
    assert "agent explanation" in note.read_text()
    assert json.loads(run_cli("status", "--workspace", str(workspace))) == {
        "records": 3,
        "conflicts": [],
        "capture": "not implemented",
    }
