from meditations.extraction.receipts import select_active_records
from meditations.store import load_records


def test_missing_receipt_for_reserved_record_is_visible(workspace, record_data):
    import pytest

    from meditations.records import EvidenceRecord
    from meditations.store import persist_record

    record_data["source_segment_id"] = "extraction:orphan"
    persist_record(workspace, EvidenceRecord.model_validate(record_data))
    with pytest.raises(ValueError, match="receipt"):
        select_active_records(workspace, load_records(workspace))


def test_malformed_receipt_is_not_ignored(workspace):
    import pytest

    directory = workspace / "extractions"
    directory.mkdir()
    (directory / "invalid.json").write_text("{}")
    with pytest.raises(ValueError, match="receipt"):
        select_active_records(workspace, [])
