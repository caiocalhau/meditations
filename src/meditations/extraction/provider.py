from dataclasses import dataclass
from typing import Protocol

from meditations.extraction.contracts import ConversationUnit, ExtractionResponse, Usage


class ProviderError(Exception):
    def __init__(self, category: str, usage: Usage | None = None) -> None:
        self.category = category
        self.usage = usage
        super().__init__(f"Extraction provider failed: {category}")


@dataclass(frozen=True)
class ExtractionRequest:
    unit: ConversationUnit
    model: str
    timeout_seconds: float = 180
    output_limit_bytes: int = 2 * 1024 * 1024
    repair: bool = False


@dataclass(frozen=True)
class ProviderResult:
    response: ExtractionResponse
    usage: Usage
    provider: str = "codex-exec"
    observed_model: str | None = None


class ExtractionProvider(Protocol):
    def extract(self, request: ExtractionRequest) -> ProviderResult: ...
