"""Exercise extraction CLI and rendering using a synthetic fixed response."""

import argparse
from pathlib import Path

from meditations.cli import main as meditations
from meditations.extraction.contracts import ExtractionResponse, Usage
from meditations.extraction.provider import ExtractionRequest, ProviderResult


class SyntheticProvider:
    def __init__(self, response: ExtractionResponse) -> None:
        self.response = response

    def extract(self, request: ExtractionRequest) -> ProviderResult:
        return ProviderResult(
            response=self.response, usage=Usage(), provider="synthetic-demo"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument(
        "--input", type=Path, default=Path("examples/conversation.json")
    )
    parser.add_argument(
        "--response", type=Path, default=Path("examples/extraction-response.json")
    )
    args = parser.parse_args(argv)
    if meditations(
        ["init", "--workspace", str(args.workspace), "--timezone", "America/Sao_Paulo"]
    ):
        return 1
    response = ExtractionResponse.model_validate_json(args.response.read_bytes())
    if meditations(
        [
            "extract",
            "--workspace",
            str(args.workspace),
            "--input",
            str(args.input),
            "--run-model",
            "--model",
            "synthetic-demo",
        ],
        provider=SyntheticProvider(response),
        state_directory=args.workspace.parent / "synthetic-machine-state",
    ):
        return 1
    return meditations(["render", "--workspace", str(args.workspace)])


if __name__ == "__main__":
    raise SystemExit(main())
