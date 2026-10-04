from datetime import datetime, timezone
from uuid import UUID

import pytest

from meditations.config import initialize_workspace


@pytest.fixture
def workspace(tmp_path):
    initialize_workspace(tmp_path, "America/Sao_Paulo")
    return tmp_path


@pytest.fixture
def record_data(workspace):
    from meditations.config import load_workspace

    return {
        "schema_version": 1,
        "record_id": UUID("00000000-0000-0000-0000-000000000001"),
        "workspace_id": load_workspace(workspace).workspace_id,
        "installation_id": UUID("00000000-0000-0000-0000-000000000002"),
        "source_agent": "codex",
        "source_session_id": "synthetic-session",
        "source_segment_id": "segment-1",
        "source_revision": 0,
        "occurred_at": datetime(2026, 10, 3, 12, tzinfo=timezone.utc),
        "captured_at": datetime(2026, 10, 3, 13, tzinfo=timezone.utc),
        "processed_at": datetime(2026, 10, 3, 14, tzinfo=timezone.utc),
        "task_id": "migration",
        "task_label": "Database migration",
        "tags": ["database"],
        "concepts": ["Referential integrity"],
        "summary": "Identified a compatibility concern.",
        "reasoning": ["Older clients need compatible writes."],
        "alternatives": [],
        "decisions": [],
        "outcomes": [],
        "verification": [],
        "attribution": "user contribution",
        "assistance": "guided",
        "uncertainties": ["Rollback was not demonstrated."],
        "privacy_omissions": [],
    }
