from uuid import uuid4

import pytest

from meditations.records import EvidenceRecord
from meditations.store import import_records, load_records, persist_record


def test_exact_reimport_is_unchanged(workspace, record_data):
    record = EvidenceRecord.model_validate(record_data)
    assert persist_record(workspace, record) == "created"
    assert persist_record(workspace, record) == "unchanged"
    assert len(load_records(workspace)) == 1


@pytest.mark.parametrize(
    "change", [{"summary": "Conflicting account."}, {"record_id": uuid4()}]
)
def test_source_revision_conflict_preserves_original(workspace, record_data, change):
    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)
    with pytest.raises(ValueError):
        persist_record(workspace, EvidenceRecord.model_validate(record_data | change))
    assert load_records(workspace) == [record]


def test_revisions_are_preserved(workspace, record_data):
    persist_record(workspace, EvidenceRecord.model_validate(record_data))
    next_record = EvidenceRecord.model_validate(
        record_data
        | {
            "record_id": uuid4(),
            "source_revision": 1,
            "summary": "Revised observation.",
        }
    )
    persist_record(workspace, next_record)
    assert len(load_records(workspace)) == 2


def test_wrong_workspace_rejected(workspace, record_data):
    with pytest.raises(ValueError):
        persist_record(
            workspace,
            EvidenceRecord.model_validate(record_data | {"workspace_id": uuid4()}),
        )
    assert load_records(workspace) == []


@pytest.mark.parametrize("bad_line", ['{"invalid": true}', "{broken json"])
def test_invalid_batch_has_no_partial_writes(
    workspace, record_data, tmp_path, bad_line
):
    source = tmp_path / "batch.jsonl"
    source.write_text(
        EvidenceRecord.model_validate(record_data).model_dump_json() + "\n" + bad_line
    )
    with pytest.raises(ValueError):
        import_records(workspace, source)
    assert load_records(workspace) == []


def test_interrupted_batch_can_be_retried(workspace, record_data, monkeypatch):
    from meditations import store

    first = EvidenceRecord.model_validate(record_data)
    second = EvidenceRecord.model_validate(
        record_data | {"record_id": uuid4(), "source_segment_id": "segment-2"}
    )
    source = workspace / "synthetic.jsonl"
    source.write_text(first.model_dump_json() + "\n" + second.model_dump_json())
    real_write = store.atomic_write
    calls = 0

    def interrupted_write(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic interruption")
        return real_write(*args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(store, "atomic_write", interrupted_write)
        with pytest.raises(OSError):
            import_records(workspace, source)
    assert len(load_records(workspace)) == 1
    assert import_records(workspace, source) == (1, 1)
    assert len(load_records(workspace)) == 2


@pytest.mark.parametrize("existing", [False, True])
def test_identity_conflicts_are_detected_before_batch_writes(
    workspace, record_data, existing
):
    original = EvidenceRecord.model_validate(record_data)
    if existing:
        persist_record(workspace, original)
        incoming = EvidenceRecord.model_validate(
            record_data | {"record_id": uuid4(), "source_segment_id": "new-segment"}
        )
    else:
        incoming = original
    conflict = EvidenceRecord.model_validate(
        record_data | {"record_id": uuid4(), "summary": "Conflicting revision."}
    )
    source = workspace / "conflicting.jsonl"
    source.write_text(incoming.model_dump_json() + "\n" + conflict.model_dump_json())
    before = load_records(workspace)
    with pytest.raises(ValueError):
        import_records(workspace, source)
    assert load_records(workspace) == before
