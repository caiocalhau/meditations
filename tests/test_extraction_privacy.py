from pathlib import Path

from meditations.config import load_workspace
from meditations.extraction.contracts import ExtractionResponse
from meditations.extraction.privacy import (
    PrivacySettings,
    filter_input,
    filter_response,
)
from meditations.extraction.validation import validate_input

FIXTURES = Path(__file__).parent / "fixtures/extraction"


def test_known_literals_and_fake_credentials_are_filtered(workspace):
    source = validate_input(
        (FIXTURES / "conversation.json").read_bytes(), load_workspace(workspace)
    )
    message = (
        source.units[0]
        .messages[0]
        .model_copy(update={"content": "PrivateCorp sk-fakecredential1234567890123456"})
    )
    unit = source.units[0].model_copy(
        update={
            "messages": [message, source.units[0].messages[1]],
            "task_label": "PrivateCorp migration",
        }
    )
    source = source.model_copy(update={"units": [unit]})
    filtered = filter_input(source, PrivacySettings(literals=("PrivateCorp",)))
    serialized = filtered.model_dump_json()
    assert "PrivateCorp" not in serialized and "sk-fakecredential" not in serialized
    assert "[omitted]" in serialized
    assert filtered.units[0].messages[0].message_id == "u1"


def test_output_filter_keeps_citations_and_marks_omissions():
    response = ExtractionResponse.model_validate_json(
        (FIXTURES / "response.json").read_bytes()
    )
    candidate = response.candidates[0].model_copy(
        update={"summary": "PrivateCorp uses sk-fakecredential1234567890123456"}
    )
    response = response.model_copy(update={"candidates": [candidate]})
    filtered = filter_response(response, PrivacySettings(literals=("PrivateCorp",)))
    assert "PrivateCorp" not in filtered.model_dump_json()
    assert filtered.candidates[0].source_message_ids == ["u1"]
    assert filtered.candidates[0].privacy_omissions


def test_sensitive_values_in_identity_metadata_are_rejected(workspace):
    import pytest

    source = validate_input(
        (FIXTURES / "conversation.json").read_bytes(), load_workspace(workspace)
    )
    source = source.model_copy(update={"source_session_id": "PrivateCorp-session"})
    with pytest.raises(ValueError, match="opaque"):
        filter_input(source, PrivacySettings(literals=("PrivateCorp",)))
