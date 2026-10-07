# Installation and live Codex setup

## Install the CLI

From a checkout on Linux or macOS, with Python >=3.10:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
meditations --help
```

Python 3.11+ includes the TOML parser needed to inherit the global Codex model.
On Python 3.10, runtime packaging of `tomli` is still pending dependency approval.
Until that is delivered, use an environment that already includes `tomli`, or
provide `--model` explicitly. Installing the CLI does not install or log in to Codex.

## Select a private vault

Keep the vault outside the public software checkout. For a new workspace:

```bash
meditations init --workspace "/path/to/vault" --timezone America/Sao_Paulo
meditations configure --workspace "/path/to/vault"
```

For an existing initialized vault, run only `configure`. Do not replace an
existing `workspace.json` to move between machines. Machine settings live in
`~/.config/meditations/config.json` on Linux, or under `$XDG_CONFIG_HOME` when set,
and `~/Library/Application Support/meditations/config.json` on macOS.

## Prepare Codex

Install Codex separately following the [official CLI guide](https://developers.openai.com/codex/cli/).
Then check the installed version and saved login:

```bash
codex --version
codex login status
```

If needed, run `codex login`. Meditations uses that saved authentication. It reads
only the top-level `model` in `$CODEX_HOME/config.toml` or `~/.codex/config.toml`
as its default model; `--model` overrides this choice. It does not import the
user configuration into the extraction subprocess. Managed security requirements
still apply. See [Codex configuration](https://learn.chatgpt.com/docs/config-file/config-basic).

## Review the runtime before activation

This is currently a manual operator review, not an automated installation command.
`configure` does not perform it, and no preapproved record is shipped. The review
must precede creating a record claiming `isolation_reviewed: true`.

Follow the [runtime compatibility checklist](architecture/extraction.md#provider-and-live-activation-gate):

1. Inspect the exact installed binary and the invocation in
   `src/meditations/extraction/codex_exec.py`. Verify support for its options and
   effective capability restrictions, preserving required managed policies.
2. Inspect the tools registered in a synthetic request. Feature flags alone, a
   model's claim that it cannot use tools, or an absence of observed tool calls
   are insufficient. A local mock Responses endpoint can inspect request tool
   names without paid inference. Document any transport overrides used for this
   inspection; this is not a capture of the request sent to the live service.
3. With explicit account-use permission, run a small synthetic conversation twice
   through the adapter. Check structured output, event types, usage, and temporary
   cleanup. Explain any startup warnings before approval. These calls consume
   account usage. Never bootstrap review using real private session material.
4. Only after satisfactory review, create a private schema-2 record containing
   the SHA-256 of the resolved executable bytes, `runtime_policy_fingerprint()`
   from the adapter, the reviewed model names, and `isolation_reviewed: true`.
   The record format is in the linked architecture document. This is an operator
   attestation; the subprocess restrictions provide the actual controls.

The development review on 2026-10-06 inspected Codex 0.160.0 on Linux. A local
mock-provider request registered zero tools; two calls through the actual adapter
returned parseable structured output and no observed tool/action events. Both
reported a Code Mode startup notice: its disabled host caused that capability to
fail closed. Do not enable the host to suppress this notice. These observations
are limited to that reviewed setup, not a guarantee for another machine, a later
binary, or summary quality. macOS live execution and broader semantic evaluations
remain unverified. Private review reports and approval records stay outside this
repository.

## Save the reviewed record's location

Choose a machine-local path. On Linux, for example:

```bash
meditations configure --runtime-approval "$HOME/.config/meditations/runtime-approval.json"
```

This saves a path, not an approval. It accepts a location before the file exists,
so configuration can succeed while live processing still fails with a missing-file
error. Keep the record private; do not put it in the public checkout or synchronize
it blindly to another machine.

## Preview, create, and update a note

Use the desired date in the workspace timezone:

```bash
meditations journal --date 2026-10-06 --dry-run
meditations journal --date 2026-10-06
```

The first command selects source text without inference or workspace writes. The
second validates the approval record, processes selected material, composes all active daily evidence, and renders the
note. Repeat the second command after more activity: changed inputs are processed
and the generated section is updated; unchanged evidence is reused. Handwritten
reflection outside generated markers is preserved. Read the reported status: no
evidence or unresolved extraction is not a successful populated note.

The approval is validated before inference on every run. A Codex binary update,
a Meditations runtime-policy change, or a model not listed in the record requires
review and an updated record. New machines require their own review and local
paths. Routine note generation does not require a new review when these checks
continue to match; review relevant managed-policy or integration changes as well.

## Troubleshooting

| Symptom | Meaning and next step |
| --- | --- |
| No default workspace configured | Run `configure --workspace` for an initialized vault. |
| No global Codex model configured | Set the global `model` or pass `--model`; ensure the chosen model is reviewed. |
| Missing `runtime-approval.json` | The saved location has no record. Complete runtime review and create the record; repeating `configure` only saves its path. |
| Invalid runtime approval file | The record does not satisfy the documented schema. Inspect it locally without exposing private values. |
| Approval does not cover executable, policy, and models | At least one reviewed value differs. Review the new runtime; do not merely replace hashes to bypass the check. |
| Authentication or usage failure | Check saved Codex login and account availability. Runtime approval does not grant account access or usage allowance. |

A guided review/setup command remains a usability gap. Until it is implemented,
do not treat installation or a successful preview as proof that live generation
is ready on a new machine.

## Compare a template safely

```bash
meditations journal --date 2026-10-06 --from-records --dry-run
meditations journal --date 2026-10-06 --from-records \
  --output "$HOME/meditations-preview/2026-10-06-candidate.md"
```

The first command reports stored evidence and the composition budget without
inference. The second writes a separate candidate and preserves the actual daily
note. It skips raw transcripts but may use one composition call (64 KiB submitted
text, 180 seconds). Unchanged repeats reuse the cache. Review source citations,
earlier topics, open questions, and learning suggestions before adopting a format.
All underlying evidence remains in private JSON; protected personal reflection is
retained in Markdown. Normal journal runs capture source-provided study URLs after
the extraction contract change. Stored-evidence runs cannot recover links that
older extraction discarded. Missing resources are reported rather than invented.
Keep `compositions/` with `records/` and `extractions/` when synchronizing the
private workspace. Runtime approval remains machine-local.
