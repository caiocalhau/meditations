from datetime import datetime

import pytest
from pydantic import ValidationError

from meditations.records import EvidenceRecord


@pytest.mark.parametrize(
    "change",
    [
        {"occurred_at": datetime(2026, 10, 3)},
        {"attribution": "mastery"},
        {"assistance": "expert"},
        {"source_revision": -1},
        {"summary": " "},
        {"unexpected": "ignored?"},
        {"schema_version": 2},
    ],
)
def test_invalid_evidence_rejected(record_data, change):
    with pytest.raises(ValidationError):
        EvidenceRecord.model_validate(record_data | change)
