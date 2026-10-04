"""Offline response checks and separately gated synthetic live evaluation."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from meditations.config import WorkspaceConfig, validate_workspace_path
from meditations.extraction.cli import reviewed_provider
from meditations.extraction.contracts import ExtractionResponse, Usage
from meditations.extraction.evaluation import evaluate_response, load_cases
from meditations.extraction.privacy import (
    FilteringProvider,
    PrivacySettings,
    filter_input,
)
from meditations.extraction.prompt import INSTRUCTIONS, PROMPT_VERSION
from meditations.extraction.provider import ExtractionRequest, ProviderError
from meditations.extraction.validation import validate_input, validate_unit_size
from meditations.files import atomic_write


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", type=Path, default=Path("evals/extraction/cases.jsonl")
    )
    parser.add_argument(
        "--responses",
        type=Path,
        help="Operator-owned JSON mapping case ID to response; offline only",
    )
    parser.add_argument("--run-model", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--runtime-approval", type=Path)
    parser.add_argument(
        "--review-output",
        type=Path,
        help="New private directory for conceptual responses and identifying metadata",
    )
    parser.add_argument("--include-held-out", action="store_true")
    args = parser.parse_args(argv)
    try:
        cases = load_cases(args.cases)
        config = WorkspaceConfig(
            schema_version=1, workspace_id=UUID(int=1), timezone="America/Sao_Paulo"
        )
        schema_hash = hashlib.sha256(
            json.dumps(ExtractionResponse.model_json_schema(), sort_keys=True).encode()
        ).hexdigest()
        summary: dict[str, Any] = {
            "cases": len(cases),
            "held_out": sum(case.split == "held-out" for case in cases),
            "source_set_fingerprint": hashlib.sha256(
                args.cases.read_bytes()
            ).hexdigest(),
            "prompt_version": PROMPT_VERSION,
            "prompt_fingerprint": hashlib.sha256(INSTRUCTIONS.encode()).hexdigest(),
            "schema_fingerprint": schema_hash,
            "model": args.model,
            "provider": "offline",
            "live_calls": 0,
            "reports": [],
            "semantic_review": "pending-human-review",
        }
        if not args.run_model and args.responses is None:
            print(json.dumps(summary))
            return 0
        if args.run_model and (
            not args.model or args.responses or args.review_output is None
        ):
            raise ValueError(
                "Live evaluation requires a model and private review output"
            )
        review_directory = None
        if args.review_output is not None:
            review_directory = validate_workspace_path(args.review_output)
            if review_directory.exists():
                raise ValueError("Use a new private review output directory")
        responses = json.loads(args.responses.read_bytes()) if args.responses else {}
        if not isinstance(responses, dict):
            raise ValueError("Invalid offline response mapping")
        provider = (
            FilteringProvider(
                reviewed_provider(args.runtime_approval, [args.model]),
                PrivacySettings(literals=("PrivateCorp",)),
            )
            if args.run_model
            else None
        )
        if review_directory is not None:
            review_directory.mkdir(parents=True, mode=0o700)
        reports: list[dict[str, Any]] = []
        failed = False
        for case in cases:
            if case.split == "held-out" and not args.include_held_out:
                continue
            try:
                source = filter_input(
                    validate_input(case.source.model_dump_json().encode(), config),
                    PrivacySettings(literals=("PrivateCorp",)),
                )
                for unit in source.units:
                    validate_unit_size(unit)
            except ValueError:
                reports.append(
                    {
                        "case_id": case.case_id,
                        "input_error": True,
                        "expected_input_error": case.expected_input_error,
                    }
                )
                continue
            for index, unit in enumerate(source.units):
                observed_model = None
                actual_provider = "offline"
                if provider is not None:
                    summary["live_calls"] += 1
                    try:
                        result = provider.extract(
                            ExtractionRequest(unit=unit, model=args.model)
                        )
                    except ProviderError as error:
                        reports.append(
                            {
                                "case_id": case.case_id,
                                "unit_id": unit.unit_id,
                                "failure_category": error.category,
                                "attempts": 1,
                                "usage": (error.usage or Usage()).model_dump(),
                            }
                        )
                        failed = True
                        break
                    response, usage = result.response, result.usage
                    actual_provider, observed_model = (
                        result.provider,
                        result.observed_model,
                    )
                    summary["provider"] = actual_provider
                else:
                    value = responses.get(case.case_id)
                    if value is None:
                        reports.append(
                            {
                                "case_id": case.case_id,
                                "unit_id": unit.unit_id,
                                "status": "missing-supplied-response",
                            }
                        )
                        continue
                    response = ExtractionResponse.model_validate(
                        value[index] if isinstance(value, list) else value
                    )
                    usage = Usage()
                report = evaluate_response(case, response, config, usage, index)
                reports.append(
                    {
                        **report.model_dump(),
                        "provider": actual_provider,
                        "observed_model": observed_model,
                        "attempts": 1 if provider else 0,
                    }
                )
                if review_directory is not None:
                    identity = hashlib.sha256(
                        json.dumps([case.case_id, unit.unit_id]).encode()
                    ).hexdigest()
                    artifact = {
                        "case_id": case.case_id,
                        "unit_id": unit.unit_id,
                        "source_set_fingerprint": summary["source_set_fingerprint"],
                        "prompt_version": PROMPT_VERSION,
                        "prompt_fingerprint": summary["prompt_fingerprint"],
                        "schema_fingerprint": schema_hash,
                        "requested_model": args.model,
                        "observed_model": observed_model,
                        "provider": actual_provider,
                        "attempts": 1 if provider else 0,
                        "usage": usage.model_dump(),
                        "response": response.model_dump(mode="json"),
                        "semantic_review": "pending-human-review",
                    }
                    atomic_write(
                        review_directory / f"{identity}.json",
                        json.dumps(artifact, indent=2).encode(),
                    )
            if failed:
                break
        summary["reports"] = reports
        summary["status"] = "provider-failure" if failed else "completed-checks"
        print(json.dumps(summary))
        return 1 if failed else 0
    except (ValueError, OSError, ProviderError) as error:
        print(
            "Evaluation failed: "
            + (
                str(error)
                if isinstance(error, ProviderError)
                else "invalid model/settings, input, or runtime approval"
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
