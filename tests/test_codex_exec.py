import json
import os
import time
from pathlib import Path

import pytest

from meditations.config import load_workspace
from meditations.extraction.codex_exec import (
    PROCESS_ENV_ALLOWLIST,
    CodexExecProvider,
    runtime_policy_fingerprint,
)
from meditations.extraction.provider import ExtractionRequest, ProviderError
from meditations.extraction.validation import validate_input

FIXTURES = Path(__file__).parent / "fixtures/extraction"


def executable(tmp_path, body):
    script = tmp_path / "fake-codex"
    script.write_text("#!/usr/bin/env python3\n" + body)
    script.chmod(0o700)
    return str(script)


def request(workspace, **settings):
    source = validate_input(
        (FIXTURES / "conversation.json").read_bytes(), load_workspace(workspace)
    )
    return ExtractionRequest(unit=source.units[0], model="synthetic-model", **settings)


def test_requires_explicit_runtime_review_before_execution(workspace):
    with pytest.raises(ProviderError, match="runtime-unverified"):
        CodexExecProvider(executable="must-not-run").extract(request(workspace))


def test_stdin_arguments_events_and_unknown_usage(workspace, tmp_path):
    response = json.loads((FIXTURES / "response.json").read_text())
    body = f"""
import json, sys
args = sys.argv[1:]
assert args[0] == "exec"
assert "--ephemeral" in args and "--json" in args
assert args[args.index("--sandbox") + 1] == "read-only"
assert "--ignore-rules" not in args and "--full-auto" not in args
assert "Older clients" not in " ".join(args)
assert "Older clients" in sys.stdin.read()
with open(args[args.index("--output-schema") + 1]) as schema:
    assert json.load(schema)["additionalProperties"] is False
result = {response!r}
print(json.dumps({{"type":"item.completed",
    "item":{{"type":"agent_message", "text":json.dumps(result)}}}}))
print(json.dumps({{"type":"turn.completed"}}))
"""
    result = CodexExecProvider(
        executable=executable(tmp_path, body), runtime_reviewed=True
    ).extract(request(workspace))
    assert result.response.candidates[0].primary_message_id == "u1"
    assert result.usage.input_tokens is None
    assert result.observed_model is None
    assert result.usage.elapsed_seconds >= 0


def test_runtime_policy_is_fixed_and_child_environment_is_allowlisted(
    workspace, tmp_path, monkeypatch
):
    response = json.loads((FIXTURES / "response.json").read_text())
    body = f"""import json, os, sys
args = sys.argv[1:]
assert args[:2] == ["exec", "--ignore-user-config"]
assert args[args.index("--thread-source") + 1] == "meditations-journal-extraction"
disabled = [args[i + 1] for i, value in enumerate(args[:-1]) if value == "--disable"]
assert disabled == ["apps", "browser_use", "browser_use_external",
    "browser_use_full_cdp_access", "code_mode_host", "computer_use", "hooks",
    "image_generation", "in_app_browser", "multi_agent", "plugins",
    "remote_plugin", "shell_tool", "skill_mcp_dependency_install",
    "skill_search", "sleep_tool", "tool_suggest", "view_image"]
assert args[args.index("--sandbox") + 1] == "read-only"
assert args[args.index("--model") + 1] == "synthetic-model"
assert args[args.index("-c") + 1] == 'approval_policy="never"'
assert 'web_search="disabled"' in args
assert 'shell_environment_policy.inherit="none"' in args
assert "mcp_servers={{}}" in args
assert os.environ.get("MED_TEST_SECRET") is None
assert os.environ["CODEX_HOME"] == "/synthetic/codex"
assert os.environ["PATH"] == "/usr/bin:/bin"
result = {response!r}
print(json.dumps({{"type":"item.completed", "item":{{
    "type":"agent_message", "text":json.dumps(result)}}}}))
print(json.dumps({{"type":"turn.completed"}}))
"""
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("CODEX_HOME", "/synthetic/codex")
    monkeypatch.setenv("MED_TEST_SECRET", "do-not-forward")
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    CodexExecProvider(
        executable=executable(tmp_path, body), runtime_reviewed=True
    ).extract(request(workspace))
    assert "MED_TEST_SECRET" not in PROCESS_ENV_ALLOWLIST
    assert len(runtime_policy_fingerprint()) == 64


@pytest.mark.parametrize(
    "body,category",
    [
        ("import time; time.sleep(30)", "timeout"),
        ('print("x" * 20000)', "output-limit"),
        ('print("not json")', "malformed-events"),
        (
            'import sys; sys.stderr.write("not logged in: private-secret"); '
            "sys.exit(1)",
            "authentication",
        ),
        (
            'import json; print(json.dumps({"type":"turn.failed", '
            '"error":{"message":"rate limit private-secret"}}))',
            "rate-limit",
        ),
        (
            'import json; print(json.dumps({"type":"item.completed", '
            '"item":{"type":"agent_message", "text":"{}"}})); '
            'print(json.dumps({"type":"turn.completed"}))',
            "validation",
        ),
        (
            'import json; text=json.dumps({"refusal":"private-secret"}); '
            'print(json.dumps({"type":"item.completed", '
            '"item":{"type":"agent_message", "text":text}})); '
            'print(json.dumps({"type":"turn.completed"}))',
            "refusal",
        ),
        ('import json; print(json.dumps({"type":"thread.started"}))', "incomplete"),
        (
            'import json; print(json.dumps({"type":"item.started", '
            '"item":{"type":"command_execution", "command":"private-secret"}}))',
            "unexpected-tool",
        ),
        (
            'import json; print(json.dumps({"type":"item.started", '
            '"item":{"type":"web_search_call"}}))',
            "unexpected-tool",
        ),
        (
            'import json; print(json.dumps({"type":"item.completed", '
            '"item":{"type":"computer_call"}}))',
            "unexpected-tool",
        ),
    ],
)
def test_bounded_categorized_failures_do_not_leak(workspace, tmp_path, body, category):
    before = time.monotonic()
    with pytest.raises(ProviderError) as error:
        CodexExecProvider(
            executable=executable(tmp_path, body), runtime_reviewed=True
        ).extract(request(workspace, timeout_seconds=0.2, output_limit_bytes=4096))
    assert error.value.category == category
    assert "private-secret" not in str(error.value)
    assert time.monotonic() - before < 4


def test_metrics_are_only_observed_values(workspace, tmp_path):
    response = (FIXTURES / "response.json").read_text()
    body = f"""import json
result = {response!r}
print(json.dumps({{"type":"item.completed",
    "item":{{"type":"agent_message", "text":result}}}}))
print(json.dumps({{"type":"turn.completed", "usage":{{
    "input_tokens":123,"output_tokens":45,"cached_input_tokens":20}}}}))
"""
    result = CodexExecProvider(
        executable=executable(tmp_path, body), runtime_reviewed=True
    ).extract(request(workspace))
    assert result.usage.input_tokens == 123
    assert result.usage.output_tokens == 45
    assert result.usage.cached_input_tokens == 20


def test_timeout_reaps_descendant(workspace, tmp_path):
    pid_path = tmp_path / "child-pid"
    body = f"""import subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
open({str(pid_path)!r}, "w").write(str(child.pid))
time.sleep(30)
"""
    with pytest.raises(ProviderError, match="timeout"):
        CodexExecProvider(
            executable=executable(tmp_path, body), runtime_reviewed=True
        ).extract(request(workspace, timeout_seconds=0.3))
    pid = int(pid_path.read_text())
    # Linux reports a killed orphan briefly as a zombie; it must not be running.
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.exists():
        assert proc_stat.read_text().split()[2] == "Z"
    else:
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)


def test_refusal_retains_observed_usage(workspace, tmp_path):
    body = """import json
text=json.dumps({"refusal":"private-secret"})
print(json.dumps({"type":"item.completed", "item":{
    "type":"agent_message", "text":text}}))
print(json.dumps({"type":"turn.completed", "usage":{
    "input_tokens":123,"output_tokens":8}}))
"""
    with pytest.raises(ProviderError) as error:
        CodexExecProvider(
            executable=executable(tmp_path, body), runtime_reviewed=True
        ).extract(request(workspace))
    assert error.value.category == "refusal"
    assert error.value.usage.input_tokens == 123
    assert error.value.usage.output_tokens == 8
    assert error.value.usage.elapsed_seconds >= 0


def test_collection_timeout_retains_elapsed_with_unknown_tokens(workspace, tmp_path):
    with pytest.raises(ProviderError) as error:
        CodexExecProvider(
            executable=executable(tmp_path, "import time; time.sleep(30)"),
            runtime_reviewed=True,
        ).extract(request(workspace, timeout_seconds=0.2))
    assert error.value.category == "timeout"
    assert error.value.usage.elapsed_seconds >= 0.2
    assert error.value.usage.input_tokens is None


def test_nonzero_exit_preserves_measured_elapsed(workspace, tmp_path):
    script = executable(
        tmp_path, 'import sys; sys.stderr.write("not logged in"); sys.exit(1)'
    )
    with pytest.raises(ProviderError) as error:
        CodexExecProvider(executable=script, runtime_reviewed=True).extract(
            request(workspace)
        )
    assert error.value.usage.elapsed_seconds >= 0
    assert error.value.usage.input_tokens is None


def test_composition_uses_same_restricted_runner_with_its_own_schema(
    workspace, record_data, tmp_path
):
    from datetime import date

    from meditations.composition import CompositionRequest
    from meditations.records import EvidenceRecord

    record = EvidenceRecord.model_validate(record_data)
    point = {
        "text": "Compatible writes matter.",
        "source_record_ids": [str(record.record_id)],
    }
    response = {
        "overview": [point],
        "topics": [{"title": "Compatibility", "paragraphs": [point]}],
        "open_items": [],
        "learning": [],
        "reflection_questions": [point],
        "supporting_only_record_ids": [],
    }
    body = f"""import json, sys
args = sys.argv[1:]
assert args[:2] == ["exec", "--ignore-user-config"]
assert args[args.index("--sandbox") + 1] == "read-only"
assert 'approval_policy="never"' in args
assert "--ephemeral" in args
with open(args[args.index("--output-schema") + 1]) as source:
    schema=json.load(source)
assert "overview" in schema["properties"] and "candidates" not in schema["properties"]
assert "Older clients need compatible writes." in sys.stdin.read()
print(json.dumps({{"type":"item.completed","item":{{"type":"agent_message","text":json.dumps({response!r})}}}}))
print(json.dumps({{"type":"turn.completed","usage":{{"input_tokens":42,"output_tokens":12}}}}))
"""
    provider = CodexExecProvider(
        executable=executable(tmp_path, body), runtime_reviewed=True
    )
    request = CompositionRequest(
        records=(record,),
        day=date(2026, 10, 3),
        timezone="UTC",
        language="en",
        model="synthetic",
    )
    result = provider.compose(request)
    assert result.response.overview[0].source_record_ids == [record.record_id]
    assert result.usage.input_tokens == 42


def test_composition_rejects_runtime_gate_and_action_events(
    workspace, record_data, tmp_path
):
    from datetime import date

    from meditations.composition import CompositionRequest
    from meditations.records import EvidenceRecord

    request = CompositionRequest(
        records=(EvidenceRecord.model_validate(record_data),),
        day=date(2026, 10, 3),
        timezone="UTC",
        language="en",
        model="synthetic",
    )
    with pytest.raises(ProviderError, match="runtime-unverified"):
        CodexExecProvider(executable="must-not-run").compose(request)
    body = (
        'import json; print(json.dumps({"type":"item.started",'
        '"item":{"type":"command_execution"}}))'
    )
    with pytest.raises(ProviderError, match="unexpected-tool"):
        CodexExecProvider(
            executable=executable(tmp_path, body), runtime_reviewed=True
        ).compose(request)
