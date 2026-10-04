import json
import os
import selectors
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from meditations.extraction.contracts import ExtractionResponse, Usage
from meditations.extraction.prompt import request_payload
from meditations.extraction.provider import (
    ExtractionRequest,
    ProviderError,
    ProviderResult,
)


def _failure_category(message: str) -> str:
    lowered = message.lower()
    if any(
        word in lowered
        for word in (
            "not logged in",
            "authentication",
            "unauthorized",
            "login required",
        )
    ):
        return "authentication"
    if any(word in lowered for word in ("rate limit", "usage limit", "quota")):
        return "rate-limit"
    if "refus" in lowered:
        return "refusal"
    return "provider-failure"


def _collect(
    command: list[str], payload: bytes, directory: str, request: ExtractionRequest
) -> tuple[bytes, bytes, int]:
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=directory,
            start_new_session=True,
        )
    except OSError as error:
        raise ProviderError("unavailable") from error
    assert (
        process.stdin is not None
        and process.stdout is not None
        and process.stderr is not None
    )
    output = bytearray()
    errors = bytearray()
    sent = 0
    started = time.monotonic()
    try:
        with selectors.DefaultSelector() as selector:
            for stream, name, event in (
                (process.stdin, "input", selectors.EVENT_WRITE),
                (process.stdout, "output", selectors.EVENT_READ),
                (process.stderr, "error", selectors.EVENT_READ),
            ):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, event, name)
            while selector.get_map():
                if time.monotonic() - started >= request.timeout_seconds:
                    raise ProviderError("timeout")
                for key, _ in selector.select(timeout=0.05):
                    stream = key.fileobj
                    if key.data == "input":
                        try:
                            sent += os.write(key.fd, payload[sent : sent + 8192])
                        except BrokenPipeError:
                            sent = len(payload)
                        if sent == len(payload):
                            selector.unregister(stream)
                            process.stdin.close()
                    else:
                        block = os.read(key.fd, 8192)
                        if not block:
                            selector.unregister(stream)
                        else:
                            (output if key.data == "output" else errors).extend(block)
                            if len(output) + len(errors) > request.output_limit_bytes:
                                raise ProviderError("output-limit")
            remaining = request.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                raise ProviderError("timeout")
            try:
                code = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired as error:
                raise ProviderError("timeout") from error
        return bytes(output), bytes(errors), code
    finally:
        # Descendants can retain pipes or outlive an already exited leader.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderError("malformed-events")
    return cast(dict[str, Any], value)


def _parse(output: bytes, errors: bytes, code: int, elapsed: float) -> ProviderResult:
    usage = Usage(elapsed_seconds=elapsed)
    if code:
        raise ProviderError(
            _failure_category(errors.decode("utf-8", errors="replace")), usage=usage
        )
    final: str | None = None
    completed = False
    observed_model: str | None = None
    try:
        for line in output.decode("utf-8").splitlines():
            event = _object(json.loads(line))
            kind = event.get("type")
            if kind in ("error", "turn.failed"):
                raise ProviderError(_failure_category(json.dumps(event)), usage=usage)
            item = _object(event.get("item", {}))
            if kind in ("item.started", "item.completed") and item.get("type") in (
                "command_execution",
                "mcp_tool_call",
                "web_search",
                "file_change",
            ):
                raise ProviderError("unexpected-tool", usage=usage)
            if kind == "item.completed" and item.get("type") == "agent_message":
                text = item.get("text")
                if not isinstance(text, str):
                    raise ProviderError("malformed-events", usage=usage)
                final = text
            if kind == "turn.completed":
                completed = True
                metrics = _object(event.get("usage", {}))
                usage = Usage(
                    input_tokens=metrics.get("input_tokens"),
                    output_tokens=metrics.get("output_tokens"),
                    cached_input_tokens=metrics.get("cached_input_tokens"),
                    elapsed_seconds=elapsed,
                )
            if kind == "thread.started" and isinstance(event.get("model"), str):
                observed_model = event["model"]
    except ProviderError as error:
        if error.usage is None:
            error.usage = usage
        raise
    except (UnicodeError, json.JSONDecodeError, ValidationError) as error:
        raise ProviderError("malformed-events", usage=usage) from error
    if not completed or final is None:
        raise ProviderError("incomplete", usage=usage)
    try:
        parsed: Any = json.loads(final)
        if isinstance(parsed, dict) and "refusal" in parsed:
            raise ProviderError("refusal", usage=usage)
        response = ExtractionResponse.model_validate(parsed)
    except (json.JSONDecodeError, ValidationError) as error:
        raise ProviderError("validation", usage=usage) from error
    return ProviderResult(response=response, usage=usage, observed_model=observed_model)


class CodexExecProvider:
    def __init__(
        self, executable: str = "codex", runtime_reviewed: bool = False
    ) -> None:
        self.executable = executable
        self.runtime_reviewed = runtime_reviewed

    def extract(self, request: ExtractionRequest) -> ProviderResult:
        if not self.runtime_reviewed:
            raise ProviderError("runtime-unverified")
        if (
            not request.model.strip()
            or not 0 < request.timeout_seconds <= 180
            or not 0 < request.output_limit_bytes <= 2 * 1024 * 1024
        ):
            raise ProviderError("invalid-settings")
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="meditations-extraction-") as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text(
                json.dumps(ExtractionResponse.model_json_schema()), encoding="utf-8"
            )
            command = [
                self.executable,
                "exec",
                "--json",
                "--output-schema",
                str(schema),
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "--model",
                request.model,
                "-",
            ]
            try:
                output, errors, code = _collect(
                    command, request_payload(request).encode(), directory, request
                )
            except ProviderError as error:
                if error.usage is None:
                    error.usage = Usage(elapsed_seconds=time.monotonic() - started)
                raise
        return _parse(output, errors, code, time.monotonic() - started)
