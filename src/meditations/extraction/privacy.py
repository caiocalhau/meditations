import re
from dataclasses import dataclass

from meditations.extraction.contracts import (
    ConversationInput,
    ConversationUnit,
    EvidenceCandidate,
    ExtractionResponse,
)
from meditations.extraction.provider import (
    ExtractionProvider,
    ExtractionRequest,
    ProviderResult,
)

CREDENTIAL = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?"
    r"-----END [A-Z ]*PRIVATE KEY-----)"
)
OMISSION = "Known sensitive values were filtered; confidentiality is not guaranteed."


@dataclass(frozen=True)
class PrivacySettings:
    literals: tuple[str, ...] = ()


def filter_text(text: str, settings: PrivacySettings) -> str:
    for literal in sorted(settings.literals, key=len, reverse=True):
        if not literal:
            raise ValueError("Privacy literals must be nonempty")
        text = text.replace(literal, "[omitted]")
    return CREDENTIAL.sub("[omitted]", text)


def filter_input(
    source: ConversationInput, settings: PrivacySettings
) -> ConversationInput:
    identities = [source.source_session_id]
    for unit in source.units:
        identities.extend([unit.unit_id, unit.task_id])
        identities.extend(message.message_id for message in unit.messages)
    if any(filter_text(value, settings) != value for value in identities):
        raise ValueError("Use opaque identities without known sensitive values")
    units: list[ConversationUnit] = []
    for unit in source.units:
        units.append(
            unit.model_copy(
                update={
                    "task_label": filter_text(unit.task_label, settings),
                    "messages": [
                        message.model_copy(
                            update={"content": filter_text(message.content, settings)}
                        )
                        for message in unit.messages
                    ],
                }
            )
        )
    return source.model_copy(update={"units": units})


def filter_response(
    response: ExtractionResponse, settings: PrivacySettings
) -> ExtractionResponse:
    candidates: list[EvidenceCandidate] = []
    for candidate in response.candidates:
        updates: dict[str, object] = {}
        changed = False
        for name in (
            "summary",
            "reasoning",
            "alternatives",
            "decisions",
            "outcomes",
            "verification",
            "tags",
            "concepts",
            "uncertainties",
            "privacy_omissions",
        ):
            value = getattr(candidate, name)
            replacement = (
                filter_text(value, settings)
                if isinstance(value, str)
                else [filter_text(item, settings) for item in value]
            )
            updates[name] = replacement
            changed |= replacement != value
        resources = [
            resource.model_copy(update={"title": filter_text(resource.title, settings)})
            for resource in candidate.resources
            if filter_text(resource.url, settings) == resource.url
        ]
        updates["resources"] = resources
        changed |= resources != candidate.resources
        if changed:
            updates["privacy_omissions"] = [
                *[
                    filter_text(value, settings)
                    for value in candidate.privacy_omissions
                ],
                OMISSION,
            ]
        candidates.append(candidate.model_copy(update=updates))
    return response.model_copy(
        update={
            "candidates": candidates,
            "unresolved": [
                filter_text(reason, settings) for reason in response.unresolved
            ],
        }
    )


class FilteringProvider:
    def __init__(self, provider: ExtractionProvider, settings: PrivacySettings) -> None:
        self.provider = provider
        self.settings = settings

    def extract(self, request: ExtractionRequest) -> ProviderResult:
        result = self.provider.extract(request)
        return ProviderResult(
            response=filter_response(result.response, self.settings),
            usage=result.usage,
            provider=result.provider,
            observed_model=result.observed_model,
        )
