# Extraction evaluations

Twelve synthetic cases describe expected facts, attribution, citations, prohibited
claims, and review notes. Four cases are held out. Annotations are proposals awaiting
owner review; no model has been evaluated or selected using this set yet.

Inventory without inference:

```bash
python scripts/evaluate_extraction.py
```

Check operator-supplied responses without inference:

```bash
python scripts/evaluate_extraction.py --responses /private/responses.json
```

The file maps case IDs to response-schema objects; cases with multiple units use a
list of responses in unit order. `--include-held-out` explicitly includes reserved
cases. Do not use held-out results for prompt tuning. The runner reports structural
errors, missing expected origins/citations, literal prohibited-claim matches,
unexpected candidates for empty cases, and observed/unknown usage. These counters
are not semantic grades. Missing supplied responses are not a passing evaluation.

Live runs require explicit owner/account-use approval and the
[runtime compatibility gate](../../docs/architecture/extraction.md):

```bash
python scripts/evaluate_extraction.py --run-model --model '<approved-model>' \
  --runtime-approval /private/runtime-approval.json \
  --review-output /private/new-review-directory
```

The runner uses synthetic input, filters the fake `PrivateCorp` literal and known
credential patterns. The required new private review directory retains parsed
conceptual candidates, coverage explanations, model identity, fingerprints, and
usage for human inspection; it contains no source transcript or raw provider events.
Source-free stdout reports remain separate. On provider failure, prior reports and
the failed call category/available metrics are emitted before stopping.
No live model runs occur in CI. Compare models only when both are account-available
and separately approved. Report latency, usage, limitations and each error category;
unknown usage is not zero. Human review of actual candidates and provider behavior
is required in addition to these counters; see [the rubric](rubric.md).

The Python 3.10-compatible script runs from an installed project environment. The
wheel contains the CLI; this repository's evaluation script/fixtures are included in
the source distribution, not installed as a second console command.
