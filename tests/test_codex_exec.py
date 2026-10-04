import json
import os
import time
from pathlib import Path

import pytest

from meditations.config import load_workspace
from meditations.extraction.codex_exec import CodexExecProvider
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
