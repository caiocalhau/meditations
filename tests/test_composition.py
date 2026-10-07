from datetime import date
from uuid import uuid4

import pytest

from meditations.composition import (
    CitedText,
    CompositionResponse,
    CompositionResult,
    JournalTopic,
    compose_day,
    validate_composition,
)
from meditations.config import load_workspace
from meditations.extraction.contracts import Usage
from meditations.records import EvidenceRecord
from meditations.store import persist_record


def response_for(records):
    source = records[0].record_id
    point = CitedText(text="Compatibility needs review.", source_record_ids=[source])
    return CompositionResponse(
        overview=[point],
        topics=[JournalTopic(title="Compatibility", paragraphs=[point])],
        open_items=[point],
        learning=[],
        reflection_questions=[
            CitedText(text="Why do older clients matter?", source_record_ids=[source])
        ],
        supporting_only_record_ids=[record.record_id for record in records[1:]],
    )


class FixedComposer:
    def __init__(self):
        self.calls = 0
        self.requests = []

    def compose(self, request):
        self.calls += 1
        self.requests.append(request)
        return CompositionResult(response=response_for(request.records), usage=Usage())


def test_composition_requires_known_citations_and_complete_accounting(record_data):
    records = [EvidenceRecord.model_validate(record_data)]
    valid = response_for(records)
    validate_composition(valid, records)
    point = CitedText(text="Invented source.", source_record_ids=[uuid4()])
    invalid = valid.model_copy(update={"overview": [point]})
    with pytest.raises(ValueError, match="citation"):
        validate_composition(invalid, records)
    other = EvidenceRecord.model_validate(
        record_data | {"record_id": uuid4(), "source_segment_id": "other"}
    )
    with pytest.raises(ValueError, match="coverage"):
        validate_composition(valid, [*records, other])


def test_cache_reuses_complete_day_and_invalidates_changed_evidence(
    workspace, record_data
):
    first = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, first)
    provider = FixedComposer()
    config = load_workspace(workspace)
    first_run = compose_day(
        workspace, config, date(2026, 10, 3), [first], provider, "synthetic"
    )
    assert first_run.reused is False
    again = compose_day(
        workspace, config, date(2026, 10, 3), [first], provider, "synthetic"
    )
    assert again.reused is True
    assert provider.calls == 1
    second = EvidenceRecord.model_validate(
        record_data
        | {
            "record_id": uuid4(),
            "source_segment_id": "second",
            "summary": "A later independent topic.",
        }
    )
    persist_record(workspace, second)
    changed = compose_day(
        workspace, config, date(2026, 10, 3), [first, second], provider, "synthetic"
    )
    assert changed.reused is False
    assert {record.record_id for record in provider.requests[-1].records} == {
        first.record_id,
        second.record_id,
    }
    assert provider.calls == 2


def test_composition_size_limit_fails_before_provider_call(workspace, record_data):
    record = EvidenceRecord.model_validate(
        record_data | {"reasoning": ["x" * (70 * 1024)]}
    )
    persist_record(workspace, record)
    provider = FixedComposer()
    with pytest.raises(ValueError, match="composition.*limit"):
        compose_day(
            workspace,
            load_workspace(workspace),
            date(2026, 10, 3),
            [record],
            provider,
            "synthetic",
        )
    assert provider.calls == 0


def test_concurrent_evidence_change_prevents_composition_publication(
    workspace, record_data
):
    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)

    class ChangingComposer(FixedComposer):
        def compose(self, request):
            changed = EvidenceRecord.model_validate(
                record_data | {"record_id": uuid4(), "source_segment_id": "new"}
            )
            persist_record(workspace, changed)
            return super().compose(request)

    with pytest.raises(ValueError, match="changed"):
        compose_day(
            workspace,
            load_workspace(workspace),
            date(2026, 10, 3),
            [record],
            ChangingComposer(),
            "synthetic",
        )
    assert not list((workspace / "compositions").rglob("*.json"))


def test_cache_is_invalidated_by_prompt_and_privacy_settings(
    workspace, record_data, monkeypatch
):
    import meditations.composition as module
    from meditations.extraction.privacy import PrivacySettings

    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)
    config = load_workspace(workspace)
    provider = FixedComposer()
    day = date(2026, 10, 3)
    compose_day(workspace, config, day, [record], provider, "synthetic")
    monkeypatch.setattr(
        module,
        "COMPOSITION_INSTRUCTIONS",
        module.COMPOSITION_INSTRUCTIONS + "\nChanged composition guidance.",
    )
    assert module.cached_composition(workspace, config, day, [record]) is None
    compose_day(workspace, config, day, [record], provider, "synthetic")
    compose_day(
        workspace,
        config,
        day,
        [record],
        provider,
        "synthetic",
        PrivacySettings(literals=("Older clients",)),
    )
    assert provider.calls == 3
    assert "Older clients" not in provider.requests[-1].records[0].reasoning[0]


def test_corrupt_cache_is_not_replaced_by_another_call(workspace, record_data):
    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)
    provider = FixedComposer()
    config = load_workspace(workspace)
    day = date(2026, 10, 3)
    compose_day(workspace, config, day, [record], provider, "synthetic")
    cache = next((workspace / "compositions").rglob("*.json"))
    cache.write_text("broken private cache")
    with pytest.raises(ValueError, match="cache"):
        compose_day(workspace, config, day, [record], provider, "synthetic")
    assert provider.calls == 1
    assert cache.read_text() == "broken private cache"


def test_cache_settings_and_presentation_boundaries(
    workspace, record_data, monkeypatch
):
    import meditations.composition as module

    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)
    config = load_workspace(workspace)
    provider = FixedComposer()
    day = date(2026, 10, 3)
    compose_day(workspace, config, day, [record], provider, "first")
    monkeypatch.setattr(module, "TEMPLATE_VERSION", "journal-v2")
    assert compose_day(workspace, config, day, [record], provider, "first").reused
    compose_day(workspace, config, day, [record], provider, "second")
    assert provider.calls == 2
    localized = config.model_copy(update={"language": "pt-BR"})
    (workspace / "workspace.json").write_text(localized.model_dump_json())
    compose_day(workspace, localized, day, [record], provider, "second")
    assert provider.calls == 3
    assert provider.requests[-1].language == "pt-BR"


def test_duplicate_ids_and_overlapping_support_are_rejected(record_data):
    record = EvidenceRecord.model_validate(record_data)
    valid = response_for([record])
    duplicate = CitedText(
        text="Repeated source.", source_record_ids=[record.record_id] * 2
    )
    with pytest.raises(ValueError, match="citation"):
        validate_composition(
            valid.model_copy(update={"overview": [duplicate]}), [record]
        )
    with pytest.raises(ValueError, match="coverage"):
        validate_composition(
            valid.model_copy(update={"supporting_only_record_ids": [record.record_id]}),
            [record],
        )


@pytest.mark.parametrize("setting", ["model", "privacy"])
def test_offline_cache_follows_latest_selection_not_creation(
    workspace, record_data, setting
):
    from meditations.composition import cached_composition
    from meditations.extraction.privacy import PrivacySettings

    record = EvidenceRecord.model_validate(record_data)
    persist_record(workspace, record)
    config = load_workspace(workspace)

    class SelectedComposer(FixedComposer):
        def compose(self, request):
            result = super().compose(request)
            point = CitedText(
                text=f"Compatibility: {request.model}.",
                source_record_ids=[record.record_id],
            )
            return CompositionResult(
                response=result.response.model_copy(update={"overview": [point]}),
                usage=result.usage,
            )

    provider = SelectedComposer()
    day = date(2026, 10, 3)
    privacy = (
        PrivacySettings(literals=("Compatibility",))
        if setting == "privacy"
        else PrivacySettings()
    )
    first = compose_day(workspace, config, day, [record], provider, "first", privacy)
    compose_day(
        workspace,
        config,
        day,
        [record],
        provider,
        "second" if setting == "model" else "first",
    )
    assert compose_day(
        workspace, config, day, [record], provider, "first", privacy
    ).reused
    cached = cached_composition(workspace, config, day, [record])
    assert cached is not None
    assert cached.overview == first.response.overview
    assert provider.calls == 2


def test_composition_rejects_unsourced_reading_urls(record_data):
    from meditations.composition import LearningItem

    record = EvidenceRecord.model_validate(record_data)
    valid = response_for([record])
    item = LearningItem(
        concept="Transactions",
        explanation=valid.overview[0],
        suggested_practice=valid.overview[0],
        resource_urls=["https://example.org/invented"],
    )
    with pytest.raises(ValueError, match="resource"):
        validate_composition(valid.model_copy(update={"learning": [item]}), [record])


@pytest.mark.parametrize("case", ["absent", "wrong-citation", "duplicate"])
def test_learning_resource_error_identifies_field_and_source_rule(record_data, case):
    from meditations.composition import LearningItem
    from meditations.records import StudyResource

    url = "https://example.org/reading"
    first = EvidenceRecord.model_validate(record_data)
    other = first.model_copy(
        update={
            "record_id": uuid4(),
            "source_segment_id": "reading",
            "resources": [StudyResource(title="Reading", url=url)],
        }
    )
    if case == "duplicate":
        first = first.model_copy(update={"resources": other.resources})
    records = [first, other]
    response = response_for(records)
    item = LearningItem(
        concept="Compatibility",
        explanation=response.overview[0],
        suggested_practice=response.overview[0],
        resource_urls=[url, url] if case == "duplicate" else [url],
    )
    if case == "absent":
        other = other.model_copy(update={"resources": []})
        records = [first, other]
    with pytest.raises(ValueError) as caught:
        validate_composition(response.model_copy(update={"learning": [item]}), records)
    details = caught.value.details
    expected = {
        "absent": "learning_resource_absent_from_evidence",
        "wrong-citation": "learning_resource_wrong_citation",
        "duplicate": "duplicate_learning_resource",
    }
    assert details["code"] == expected[case]
    index = 1 if case == "duplicate" else 0
    assert details["field"] == f"learning[0].resource_urls[{index}]"
    assert details["resource"] == url
    assert details["cited_record_ids"] == [str(first.record_id)]
    assert str(other.record_id) in details["matching_record_ids"] or case == "absent"
    assert url in str(caught.value)
    assert details["field"] in str(caught.value)


@pytest.mark.parametrize(
    "url,secret",
    [
        (
            "https://example.org/reading?token=private-value#private-value",
            "private-value",
        ),
        ("https://user:private-password@example.org/reading", "private-password"),
        ("not-a-url\nprivate-value", "private-value"),
        ("https://example.org/\x1bprivate-value", "private-value"),
    ],
)
def test_learning_resource_diagnostics_do_not_expose_url_secrets(
    record_data, url, secret
):
    import json

    from meditations.composition import LearningItem

    record = EvidenceRecord.model_validate(record_data)
    response = response_for([record])
    item = LearningItem(
        concept="Reading",
        explanation=response.overview[0],
        suggested_practice=response.overview[0],
        resource_urls=[url],
    )
    with pytest.raises(ValueError) as caught:
        validate_composition(response.model_copy(update={"learning": [item]}), [record])
    assert secret not in str(caught.value)
    assert secret not in json.dumps(caught.value.details)
    assert len(caught.value.details["resource_sha256"]) == 64


def test_resource_diagnostics_locate_failure_after_valid_learning_resources(
    record_data,
):
    from meditations.composition import LearningItem
    from meditations.records import StudyResource

    known = "https://example.org/known"
    record = EvidenceRecord.model_validate(record_data).model_copy(
        update={"resources": [StudyResource(title="Known reading", url=known)]}
    )
    response = response_for([record])
    point = response.overview[0]
    valid = LearningItem(
        concept="Known reading",
        explanation=point,
        suggested_practice=point,
        resource_urls=[known],
    )
    validate_composition(response.model_copy(update={"learning": [valid]}), [record])
    invalid = valid.model_copy(
        update={"resource_urls": [known, "https://example.org/missing"]}
    )
    with pytest.raises(ValueError) as caught:
        validate_composition(
            response.model_copy(update={"learning": [valid, invalid]}), [record]
        )
    assert caught.value.details["field"] == "learning[1].resource_urls[1]"
    assert caught.value.details["matching_record_ids"] == []


def test_composition_payload_uses_lossless_compact_json(record_data):
    import json

    from meditations.composition import CompositionRequest, composition_payload

    record = EvidenceRecord.model_validate(record_data)
    payload = composition_payload(
        CompositionRequest(
            records=(record,),
            day=date(2026, 10, 3),
            timezone="UTC",
            language="en",
            model="synthetic",
        )
    )
    body = payload.split("EVIDENCE JSON:\n", 1)[1]
    data = json.loads(body)
    assert data["records"][0]["summary"] == record.summary
    assert body == json.dumps(
        data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
