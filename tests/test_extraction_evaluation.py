import importlib.util
import json
from pathlib import Path

from meditations.config import load_workspace
from meditations.extraction.contracts import ExtractionResponse, Usage
from meditations.extraction.evaluation import evaluate_response, load_cases

FIXTURES = Path(__file__).parent / "fixtures/extraction"


def test_case_set_has_twelve_distinct_cases_four_held_out():
    cases = load_cases(Path("evals/extraction/cases.jsonl"))
    assert len(cases) == 12
    assert len({case.case_id for case in cases}) == 12
    assert sum(case.split == "held-out" for case in cases) == 4
    assert all(
        case.expected_findings or case.expected_input_error or case.expected_empty
        for case in cases
    )


def test_missing_citations_role_mismatch_and_unknown_usage_are_counted(workspace):
    cases = load_cases(Path("evals/extraction/cases.jsonl"))
    case = next(case for case in cases if case.case_id == "agent-only")
    response = ExtractionResponse.model_validate_json(
        (FIXTURES / "response.json").read_bytes()
    )
    report = evaluate_response(case, response, load_workspace(workspace), Usage())
    assert report.source_validation_errors == 1
    assert report.missing_expected_origins > 0
    assert report.usage.input_tokens is None
    assert report.semantic_review == "pending-human-review"
    assert case.source.units[0].messages[0].content not in report.model_dump_json()


def test_harness_is_offline_by_default_and_records_versions(tmp_path, capsys):
    spec = importlib.util.spec_from_file_location(
        "evaluate_extraction", "scripts/evaluate_extraction.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main([]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["cases"] == 12 and output["live_calls"] == 0
    assert output["prompt_version"] and output["schema_fingerprint"]
    assert module.main(["--run-model"]) == 1
    assert "model" in capsys.readouterr().err


def test_literal_prohibited_claims_are_flagged_without_semantic_grading(workspace):
    case = load_cases(Path("evals/extraction/cases.jsonl"))[0]
    response = ExtractionResponse.model_validate_json(
        (FIXTURES / "response.json").read_bytes()
    )
    response = response.model_copy(
        update={
            "candidates": [
                response.candidates[0].model_copy(
                    update={
                        "summary": "User mastered backward compatibility independently."
                    }
                )
            ]
        }
    )
    report = evaluate_response(case, response, load_workspace(workspace), Usage())
    assert report.prohibited_literal_hits >= 1
    assert report.semantic_review == "pending-human-review"


def evaluation_module():
    spec = importlib.util.spec_from_file_location(
        "evaluation_review", "scripts/evaluate_extraction.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_evaluation_retains_private_review_candidates_and_model(
    tmp_path, monkeypatch, capsys
):
    from meditations.extraction.provider import ProviderResult

    module = evaluation_module()
    response = ExtractionResponse.model_validate_json(
        (FIXTURES / "response.json").read_bytes()
    )
    response = response.model_copy(
        update={
            "candidates": [
                response.candidates[0].model_copy(
                    update={"summary": "Distinctive unsupported semantic claim."}
                )
            ]
        }
    )

    class FakeProvider:
        def extract(self, request):
            return ProviderResult(
                response=response,
                usage=Usage(input_tokens=7),
                observed_model="observed-synthetic",
            )

    monkeypatch.setattr(module, "reviewed_provider", lambda *args: FakeProvider())
    directory = tmp_path / "private-review"
    assert (
        module.main(
            ["--run-model", "--model", "synthetic", "--review-output", str(directory)]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert "Distinctive unsupported semantic claim." not in json.dumps(output)
    artifacts = [json.loads(path.read_text()) for path in directory.glob("*.json")]
    assert artifacts and artifacts[0]["observed_model"] == "observed-synthetic"
    assert (
        artifacts[0]["response"]["candidates"][0]["summary"]
        == "Distinctive unsupported semantic claim."
    )
    assert "Expand-contract migrations preserve older clients" not in json.dumps(
        artifacts
    )


def test_evaluation_failure_preserves_prior_reports_and_failed_call_metrics(
    tmp_path, monkeypatch, capsys
):
    from meditations.extraction.provider import ProviderError, ProviderResult

    module = evaluation_module()
    response = ExtractionResponse.model_validate_json(
        (FIXTURES / "response.json").read_bytes()
    )
    calls = []

    class FakeProvider:
        def extract(self, request):
            calls.append(request)
            if len(calls) == 2:
                raise ProviderError("rate-limit", usage=Usage(input_tokens=17))
            return ProviderResult(response=response, usage=Usage(input_tokens=7))

    monkeypatch.setattr(module, "reviewed_provider", lambda *args: FakeProvider())
    assert (
        module.main(
            [
                "--run-model",
                "--model",
                "synthetic",
                "--review-output",
                str(tmp_path / "reviews"),
            ]
        )
        == 1
    )
    output = json.loads(capsys.readouterr().out)
    assert output["live_calls"] == 2
    assert len(output["reports"]) == 2
    assert output["reports"][0]["usage"]["input_tokens"] == 7
    assert output["reports"][1]["failure_category"] == "rate-limit"
    assert output["reports"][1]["usage"]["input_tokens"] == 17
    assert len(calls) == 2
