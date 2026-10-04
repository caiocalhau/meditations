from pathlib import Path

import pytest

from meditations.config import load_workspace
from meditations.extraction.contracts import ExtractionResponse, Usage
from meditations.extraction.provider import ProviderError, ProviderResult
from meditations.extraction.receipts import select_active_records
from meditations.extraction.service import ExtractionSettings, extract_unit
from meditations.extraction.validation import validate_input
from meditations.store import load_records, persist_record

FIXTURES = Path(__file__).parent / "fixtures/extraction"


class FakeProvider:
    def __init__(self, results):
        self.results = list(results)
        self.requests = []

    def extract(self, request):
        self.requests.append(request)
        value = self.results.pop(0)
        if isinstance(value, Exception):
            raise value
        return ProviderResult(
            response=value,
            usage=Usage(input_tokens=10, output_tokens=5),
            provider="synthetic",
        )


@pytest.fixture
def extraction(workspace, tmp_path):
    source = validate_input(
        (FIXTURES / "conversation.json").read_bytes(), load_workspace(workspace)
    )
    response = ExtractionResponse.model_validate_json(
        (FIXTURES / "response.json").read_bytes()
    )
    settings = ExtractionSettings(
        model="synthetic-model", state_directory=tmp_path / "machine-state"
    )
    return source, response, settings


def run(workspace, extraction, provider, unit=None, settings=None):
    source, _, default = extraction
    return extract_unit(
        workspace,
        source.source_session_id,
        unit or source.units[0],
        provider,
        settings or default,
    )


def test_completed_receipt_reuses_without_provider_and_no_raw_text(
    workspace, extraction
):
    source, response, _ = extraction
    provider = FakeProvider([response])
    result = run(workspace, extraction, provider)
    assert result.created == 1 and result.attempts == 1
    stored = load_records(workspace)
    assert len(select_active_records(workspace, stored)) == 1
    result = run(workspace, extraction, provider)
    assert result.reused == 1 and result.attempts == 0
    assert len(provider.requests) == 1
    for path in (workspace / "extractions").glob("*.json"):
        assert source.units[0].messages[0].content not in path.read_text()


@pytest.mark.parametrize("change", ["input", "settings"])
def test_same_revision_change_conflicts_before_inference(workspace, extraction, change):
    source, response, settings = extraction
    provider = FakeProvider([response])
    run(workspace, extraction, provider)
    unit = source.units[0]
    if change == "input":
        unit = unit.model_copy(update={"task_label": "Changed task label"})
    else:
        settings = ExtractionSettings(
            model="different-model", state_directory=settings.state_directory
        )
    with pytest.raises(ValueError, match="revision"):
        run(workspace, extraction, provider, unit, settings)
    assert len(provider.requests) == 1


def test_one_repair_and_optional_escalation_are_bounded(workspace, extraction):
    _, response, settings = extraction
    provider = FakeProvider([ProviderError("validation"), response])
    settings = ExtractionSettings(
        model=settings.model,
        escalation_model="synthetic-stronger",
        state_directory=settings.state_directory,
    )
    result = run(workspace, extraction, provider, settings=settings)
    assert result.attempts == 2 and result.created == 1
    assert [request.model for request in provider.requests] == [
        "synthetic-model",
        "synthetic-stronger",
    ]
    assert provider.requests[1].repair


@pytest.mark.parametrize(
    "category", ["authentication", "rate-limit", "refusal", "timeout", "incomplete"]
)
def test_failures_never_loop_or_publish(workspace, extraction, category):
    provider = FakeProvider([ProviderError(category)])
    result = run(workspace, extraction, provider)
    assert result.failure_category == category and result.attempts == 1
    assert load_records(workspace) == []
    assert len(provider.requests) == 1


def test_validation_failure_stops_at_two_attempts(workspace, extraction):
    provider = FakeProvider([ProviderError("validation"), ProviderError("validation")])
    result = run(workspace, extraction, provider)
    assert result.failure_category == "validation" and result.attempts == 2


def test_unresolved_is_completed_without_escalation(workspace, extraction):
    response = ExtractionResponse(
        candidates=[],
        excluded_message_ids=["a1"],
        unresolved_message_ids=["u1"],
        unresolved=["Insufficient support."],
    )
    provider = FakeProvider([response])
    result = run(workspace, extraction, provider)
    assert result.unresolved_message_ids == ["u1"]
    assert result.failure_category is None
    assert run(workspace, extraction, provider).attempts == 0
    assert len(provider.requests) == 1


def test_new_empty_revision_supersedes_without_deleting(workspace, extraction):
    source, response, _ = extraction
    provider = FakeProvider(
        [
            response,
            ExtractionResponse(
                candidates=[],
                excluded_message_ids=["u1", "a1"],
                unresolved_message_ids=[],
                unresolved=[],
            ),
        ]
    )
    run(workspace, extraction, provider)
    unit = source.units[0].model_copy(update={"source_revision": 1})
    run(workspace, extraction, provider, unit)
    assert len(load_records(workspace)) == 1
    assert select_active_records(workspace, load_records(workspace)) == []


def test_interrupt_recovery_uses_manifest_without_another_call(
    workspace, extraction, monkeypatch
):
    from meditations.extraction import receipts

    _, response, _ = extraction
    provider = FakeProvider([response])
    original = receipts.atomic_write

    def interrupt(path, *args, **kwargs):
        if path.parent.name == "extractions" and not path.name.endswith(
            ".pending.json"
        ):
            raise OSError("simulated crash before receipt publication")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(receipts, "atomic_write", interrupt)
        with pytest.raises(OSError):
            run(workspace, extraction, provider)
    assert len(load_records(workspace)) == 1
    assert select_active_records(workspace, load_records(workspace)) == []
    run(workspace, extraction, provider)
    assert len(select_active_records(workspace, load_records(workspace))) == 1
    assert len(provider.requests) == 1
    assert not list((workspace / "extractions").glob("*.pending.json"))


def test_legacy_imports_remain_eligible(workspace, extraction, record_data):
    from meditations.records import EvidenceRecord

    persist_record(workspace, EvidenceRecord.model_validate(record_data))
    _, response, _ = extraction
    run(workspace, extraction, FakeProvider([response]))
    assert len(select_active_records(workspace, load_records(workspace))) == 2


def test_workspace_lock_is_not_held_during_provider(workspace, extraction):
    import subprocess
    import sys

    _, response, _ = extraction

    class LockCheckingProvider(FakeProvider):
        def extract(self, request):
            command = (
                "from pathlib import Path; "
                "from meditations.files import workspace_lock;\n"
                f"with workspace_lock(Path({str(workspace)!r})): "
                "print('acquired')"
            )
            child = subprocess.run(
                [sys.executable, "-c", command],
                capture_output=True,
                timeout=3,
                env={**__import__("os").environ, "PYTHONPATH": "src"},
            )
            assert child.returncode == 0 and b"acquired" in child.stdout
            return super().extract(request)

    run(workspace, extraction, LockCheckingProvider([response]))


def test_privacy_settings_change_invalidates_same_revision(workspace, extraction):
    _, response, settings = extraction
    provider = FakeProvider([response])
    run(workspace, extraction, provider)
    changed = ExtractionSettings(
        model=settings.model,
        state_directory=settings.state_directory,
        privacy_fingerprint="different-filter",
    )
    with pytest.raises(ValueError, match="revision"):
        run(workspace, extraction, provider, settings=changed)
    assert len(provider.requests) == 1


def test_schema_repair_retains_observed_usage(workspace, extraction):
    _, response, _ = extraction
    provider = FakeProvider(
        [
            ProviderError("validation", usage=Usage(input_tokens=99, output_tokens=12)),
            response,
        ]
    )
    result = run(workspace, extraction, provider)
    assert result.usage[0].input_tokens == 99


def test_partial_record_publication_recovers_without_provider(
    workspace, extraction, monkeypatch
):
    from meditations import store

    source, response, _ = extraction
    second = response.candidates[0].model_copy(
        update={
            "primary_message_id": "a1",
            "source_message_ids": ["a1"],
            "attribution": "agent explanation",
            "summary": "The agent supplied a migration approach.",
        }
    )
    response = response.model_copy(
        update={
            "candidates": [*response.candidates, second],
            "excluded_message_ids": [],
        }
    )
    provider = FakeProvider([response])
    original = store._write_record
    writes = []

    def fail_second(workspace, record):
        writes.append(record.record_id)
        if len(writes) == 2:
            raise OSError("simulated interruption")
        original(workspace, record)

    with monkeypatch.context() as context:
        context.setattr(store, "_write_record", fail_second)
        with pytest.raises(OSError):
            run(workspace, extraction, provider)
    assert len(load_records(workspace)) == 1
    assert select_active_records(workspace, load_records(workspace)) == []
    outcome = run(workspace, extraction, provider)
    assert outcome.created == 1 and outcome.reused == 1
    assert len(select_active_records(workspace, load_records(workspace))) == 2
    assert len(provider.requests) == 1


def test_direct_service_rejects_oversized_effective_unit(workspace, extraction):
    source, response, _ = extraction
    unit = source.units[0]
    message = unit.messages[0].model_copy(update={"content": "x" * 70000})
    unit = unit.model_copy(update={"messages": [message, unit.messages[1]]})
    provider = FakeProvider([response])
    with pytest.raises(ValueError, match="byte limit"):
        run(workspace, extraction, provider, unit)
    assert provider.requests == []
