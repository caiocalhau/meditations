import json
from datetime import date
from pathlib import Path

import pytest

from meditations.sessions import read_day


def write_session(
    root: Path,
    session_id: str,
    cwd: Path,
    events: list[dict],
    *,
    metadata: dict | None = None,
    final_newline: bool = True,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"rollout-{session_id}.jsonl"
    rows = [
        {
            "type": "session_meta",
            "payload": {
                "id": session_id,
                "cwd": str(cwd),
                "cli_version": "0.160.0",
                **(metadata or {}),
            },
        },
        *events,
    ]
    content = "\n".join(json.dumps(row) for row in rows)
    path.write_text(content + ("\n" if final_newline else ""))
    return path


def message(timestamp: str, role: str = "user", text: str = "hello") -> dict:
    return {
        "timestamp": timestamp,
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": role,
            "content": [
                {
                    "type": "input_text" if role == "user" else "output_text",
                    "text": text,
                }
            ],
        },
    }


def test_selects_exact_authorized_cwd_and_deduplicates_roots(tmp_path):
    sessions = tmp_path / "sessions"
    repo = tmp_path / "work" / "app"
    neighbor = tmp_path / "work" / "app-copy"
    repo.mkdir(parents=True)
    neighbor.mkdir()
    write_session(sessions, "one", repo, [message("2026-10-06T10:00:00Z")])
    write_session(sessions, "two", neighbor, [message("2026-10-06T10:00:00Z")])

    result = read_day(sessions, (repo, repo), date(2026, 10, 6), "UTC")

    assert [session.session_id for session in result.sessions] == ["one"]
    assert len(result.sessions[0].messages) == 1


def test_empty_repository_selection_includes_all_local_repositories(tmp_path):
    sessions = tmp_path / "sessions"
    for identity in ("work", "home"):
        write_session(
            sessions,
            identity,
            tmp_path / identity,
            [message("2026-10-06T10:00:00Z")],
        )
    result = read_day(sessions, (), date(2026, 10, 6), "UTC")
    assert {session.session_id for session in result.sessions} == {"work", "home"}


def test_excluded_session_is_skipped_before_reading_its_body(tmp_path):
    sessions = tmp_path / "sessions"
    path = write_session(sessions, "excluded", tmp_path / "work", [])
    with path.open("a") as output:
        output.write("invalid transcript body\n")
    write_session(
        sessions,
        "included",
        tmp_path / "home",
        [message("2026-10-06T10:00:00Z")],
    )
    result = read_day(
        sessions,
        (),
        date(2026, 10, 6),
        "UTC",
        excluded_session_ids=frozenset({"excluded"}),
    )
    assert [session.session_id for session in result.sessions] == ["included"]


def test_resumed_session_uses_each_message_day_and_timezone(tmp_path):
    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    write_session(
        sessions,
        "resumed",
        repo,
        [
            message("2026-10-05T23:30:00Z", text="yesterday"),
            message("2026-10-06T04:30:00Z", text="today"),
        ],
    )

    result = read_day(sessions, (repo,), date(2026, 10, 5), "America/Sao_Paulo")

    assert [item.content for item in result.sessions[0].messages] == ["yesterday"]


def test_excludes_subagent_and_reports_missing_metadata_or_timestamp(tmp_path):
    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    write_session(
        sessions,
        "child",
        repo,
        [message("2026-10-06T10:00:00Z")],
        metadata={"parent_thread_id": "parent"},
    )
    write_session(
        sessions,
        "internal",
        repo,
        [message("2026-10-06T10:00:00Z")],
        metadata={"thread_source": "meditations-journal-extraction"},
    )
    write_session(
        sessions,
        "missing",
        repo,
        [message("2026-10-06T10:00:00Z")],
        metadata={"cwd": None},
    )
    write_session(
        sessions,
        "no-time",
        repo,
        [
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "untimed"}],
                },
            }
        ],
    )

    result = read_day(sessions, (repo,), date(2026, 10, 6), "UTC")

    assert [session.session_id for session in result.sessions] == ["no-time"]
    assert result.diagnostics


def test_duplicate_session_ids_are_rejected(tmp_path):
    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    write_session(sessions / "a", "same", repo, [message("2026-10-06T10:00:00Z")])
    write_session(sessions / "b", "same", repo, [message("2026-10-06T11:00:00Z")])

    with pytest.raises(ValueError, match="Duplicate session"):
        read_day(sessions, (repo,), date(2026, 10, 6), "UTC")


def test_text_only_normalization_skips_mirrors_and_reports_other_content(tmp_path):
    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    events = [
        message("2026-10-06T10:00:00Z", text="question"),
        {
            "timestamp": "2026-10-06T10:00:00Z",
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "question"},
        },
        {
            "timestamp": "2026-10-06T10:01:00Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "c1",
                "output": "observed result",
            },
        },
        {
            "timestamp": "2026-10-06T10:02:00Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": "answer"},
                    {"type": "image", "data": "private"},
                    {"type": "reasoning", "text": "hidden"},
                ],
            },
        },
        {
            "timestamp": "2026-10-06T10:03:00Z",
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call",
                "name": "shell",
                "input": "rm -rf /",
            },
        },
    ]
    write_session(sessions, "text", repo, events)

    result = read_day(sessions, (repo,), date(2026, 10, 6), "UTC")
    selected = result.sessions[0]

    assert [item.content for item in selected.messages] == [
        "question",
        "observed result",
        "answer",
    ]
    assert [item.role for item in selected.messages] == ["user", "tool", "assistant"]
    assert len({item.message_id for item in selected.messages}) == 3
    assert all(str(repo) not in item.message_id for item in selected.messages)
    assert selected.omission_counts
    assert "rm -rf /" not in " ".join(item.content for item in selected.messages)


def test_symlink_transcript_is_rejected(tmp_path):
    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    actual = write_session(sessions, "actual", repo, [message("2026-10-06T10:00:00Z")])
    (sessions / "rollout-link.jsonl").symlink_to(actual)

    with pytest.raises(ValueError, match="Symlink"):
        read_day(sessions, (repo,), date(2026, 10, 6), "UTC")


def test_incomplete_final_line_is_reported_and_complete_bad_line_fails(tmp_path):
    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    path = write_session(
        sessions,
        "partial",
        repo,
        [message("2026-10-06T10:00:00Z")],
        final_newline=False,
    )
    path.write_bytes(path.read_bytes() + b'{"timestamp":')
    result = read_day(sessions, (repo,), date(2026, 10, 6), "UTC")
    assert result.diagnostics

    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="malformed"):
        read_day(sessions, (repo,), date(2026, 10, 6), "UTC")


def test_appended_data_after_snapshot_is_ignored(tmp_path, monkeypatch):
    from meditations import sessions as session_reader

    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    write_session(
        sessions, "snapshot", repo, [message("2026-10-06T10:00:00Z", text="initial")]
    )
    original = session_reader._snapshot_changed

    def append_then_compare(source_path, before):
        with source_path.open("a") as output:
            output.write(
                json.dumps(message("2026-10-06T11:00:00Z", text="appended")) + "\n"
            )
        return original(source_path, before)

    monkeypatch.setattr(session_reader, "_snapshot_changed", append_then_compare)
    result = read_day(sessions, (repo,), date(2026, 10, 6), "UTC")

    assert [item.content for item in result.sessions[0].messages] == ["initial"]


def test_truncation_after_snapshot_requests_retry(tmp_path, monkeypatch):
    from meditations import sessions as session_reader

    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    write_session(sessions, "changing", repo, [message("2026-10-06T10:00:00Z")])
    original = session_reader._snapshot_changed

    def truncate_then_compare(source_path, before):
        source_path.write_bytes(source_path.read_bytes()[:10])
        return original(source_path, before)

    monkeypatch.setattr(session_reader, "_snapshot_changed", truncate_then_compare)
    with pytest.raises(ValueError, match="retry"):
        read_day(sessions, (repo,), date(2026, 10, 6), "UTC")


def test_replacement_after_snapshot_requests_retry(tmp_path, monkeypatch):
    from meditations import sessions as session_reader

    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    write_session(sessions, "replaced", repo, [message("2026-10-06T10:00:00Z")])
    original = session_reader._snapshot_changed

    def replace_then_compare(source_path, before):
        replacement = source_path.with_suffix(".tmp")
        replacement.write_bytes(source_path.read_bytes())
        replacement.replace(source_path)
        return original(source_path, before)

    monkeypatch.setattr(session_reader, "_snapshot_changed", replace_then_compare)
    with pytest.raises(ValueError, match="retry"):
        read_day(sessions, (repo,), date(2026, 10, 6), "UTC")


def test_selected_transcript_over_64_mib_is_rejected_before_full_read(tmp_path):
    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    path = write_session(sessions, "too-large", repo, [])
    with path.open("ab") as stream:
        stream.truncate(64 * 1024 * 1024 + 1)

    with pytest.raises(ValueError, match="64 MiB"):
        read_day(sessions, (repo,), date(2026, 10, 6), "UTC")


@pytest.mark.parametrize("oversized_kind", ["image", "text", "old-tool-output"])
def test_oversized_entry_does_not_hide_supported_day_messages(tmp_path, oversized_kind):
    sessions = tmp_path / "sessions"
    repo = tmp_path / "repo"
    repo.mkdir()
    oversized = message("2026-10-06T10:00:00Z", text="x" * (2 * 1024 * 1024 + 1))
    if oversized_kind == "image":
        oversized["payload"]["content"] = [
            {
                "type": "input_image",
                "image_url": "data:image/png;base64," + "x" * (2 * 1024 * 1024),
            }
        ]
    elif oversized_kind == "old-tool-output":
        oversized = {
            "timestamp": "2026-10-05T10:00:00Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "output": "x" * (2 * 1024 * 1024 + 1),
            },
        }
    write_session(
        sessions,
        "s1",
        repo,
        [
            message("2026-10-06T09:00:00Z", text="before"),
            oversized,
            message("2026-10-06T11:00:00Z", text="after"),
        ],
    )
    result = read_day(sessions, (repo,), date(2026, 10, 6), "UTC")
    selected = result.sessions[0]
    assert [item.content for item in selected.messages] == ["before", "after"]
    assert [item.message_id for item in selected.messages] == [
        "codex:s1:2",
        "codex:s1:4",
    ]
    assert selected.omission_counts["oversized_line"] == 1
    assert any(
        "2 MiB" in diagnostic and "omitted" in diagnostic
        for diagnostic in result.diagnostics
    )
