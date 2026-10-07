# Manual conversation extraction

## Delivery boundary

The second implementation slice adds normalized conversation preview, extraction
contracts, an offline-tested Codex subprocess adapter, recoverable receipts, active
revision selection, privacy filters, and a synthetic evaluation harness. One Linux
development runtime has completed a manual compatibility smoke review; broader
semantic quality and macOS live behavior remain unverified. Activation still
requires review of each installation. See the [setup guide](../installation.md)
for the observed scope and limitations. No automatic history capture, hooks, scheduler, context delivery,
coaching, or periodic review is shipped by this slice.

The core remains a Python CLI. Obsidian reads the generated Markdown files; no
native Obsidian plugin, API key, MCP server, embeddings, or vector database is
required. Existing saved Codex login is the live inference route.

## Source contract

`ConversationInput` schema version 1 contains `source_agent: codex`, an opaque
`source_session_id`, and one or more units. Each unit declares `unit_id`, a strict
nonnegative `source_revision`, `task_id`, `task_label`, and messages. Each message
contains `message_id`, `role` (`user`, `assistant`, or `tool`), `content`, an aware
`occurred_at` or null, and `context_only`. Extra fields are rejected; identities
must be unique. Source/tool provenance is supplied by the operator, not independently
authenticated by this manual adapter. Use opaque IDs without confidential names.

A unit contains one declared task and one occurrence day in the workspace timezone.
Earlier context may be supplied as context-only messages. Missing non-context times
require an explicit aware `--occurred-at` override; the program marks user-supplied
time and attaches a fixed uncertainty to affected evidence. It never substitutes
processing time silently. `timestamp_basis` is application-owned; input cannot claim
user-supplied provenance without the override. Mixed-day units must be split.

Limits: 64 KiB effective UTF-8 JSON per unit, 200 messages per unit, and 8 MiB per
input file. Oversized input is rejected, not truncated. These bounds are not token
or subscription-cost estimates.

## Candidate validation and attribution

The provider returns conceptual fields and citations, not UUIDs, dates, task IDs,
paths, revisions, or configuration. Each candidate has a non-context primary message
and supporting message IDs. There is at most one candidate per primary/attribution
pair. User contributions and self-reports require user origins; agent explanations
require assistant origins; observed artifacts require declared tool origins.

Every non-context message must be cited, excluded, or unresolved. Those coverage
categories are disjoint. Context-only messages cannot be new primary evidence.
Zero candidates with explicit exclusions is valid. Explicit unresolved messages are
a completed extraction with incomplete coverage, not a reason for unbounded retries.

Role/reference/schema checks establish structural consistency, not truth or mastery.
Human-reviewed evaluations remain necessary for entailment, unsupported outcomes,
contradictions, relevance, confidentiality, and repetition. Existing evidence schema
version 1 is unchanged. Application code derives segment and record identities.
The `extraction:` segment prefix is reserved for managed extraction evidence.

## Receipts, active revisions, and recovery

Individual historical records remain under `records/`. Private `extractions/`
receipts use opaque SHA-256 identity paths and track workspace/session/unit/revision,
input and extractor fingerprints, timestamp basis, requested and observed model,
provider, record IDs and source-message references, coverage, attempts, and observed
usage. Raw source, full prompts, raw responses, and free-form unresolved reasons
are not stored in receipts. Reasons are replaced with a curated category.

Fingerprints cover effective filtered input, timezone, prompt text/version, schema,
selected models, privacy/runtime fingerprints, timeout, and output bounds. Reusing
an identical completed revision performs no provider call. The daily journal
compares each unit against its highest locally available revision under the
workspace lock, reuses matching content/settings, and advances changed units to
the next revision automatically. Pending publication is recovered before
choosing the revision. The lower-level normalized extraction contract retains
explicit source revisions; conflicting same revisions and older revisions are rejected.
Inference occurs outside the lock, so a competing publication can still cause a
visible conflict rather than silently supersede a different result.

A pending manifest stores validated records and the planned receipt before any
record write. Under the local workspace lock, publication writes records, atomically
publishes the completed receipt, then removes the pending manifest. Interrupted
publication resumes from that manifest without another model call. Pending extraction
records do not render. The highest completed receipt per unit determines the active
set, including a valid empty set; superseded files remain historical. Legacy imports
remain eligible. Missing, malformed, or conflicting receipts surface an error.

The lock is released during inference and state is checked again before publication.
Two concurrent extractions may both consume a provider call, although local record
publication remains serialized. This slice does not guarantee transactional behavior
with concurrent external sync, and relies on the underlying filesystem's durability.
A machine-local installation UUID uses XDG state storage on Linux and
`~/Library/Application Support/meditations` on macOS, separate from synced records.

## Provider and live activation gate

The adapter uses subprocess argument lists, stdin input, a protected temporary
working directory, JSON events, JSON Schema, read-only sandboxing, and ephemeral
sessions. It uses saved authentication without copying credentials or automatically
logging in. It does not use shell interpolation or security-bypass flags.

Per attempt: at most 180 seconds and 2 MiB combined stdout/stderr. Timeout/output
failure kills and reaps the process group. Ordinary cleanup removes the temporary
directory; abrupt interpreter/system termination may leave protected temporary
material requiring manual cleanup. The application does not control source-history
retention or provider retention.

Authentication, rate-limit, refusal, timeout, cancellation, incomplete, and malformed
event failures do not auto-retry. Schema or source-validation failure permits one
repair; an explicitly selected escalation model may replace that second attempt.
Source-validation repairs receive the application-generated rejection reason and
explicit guidance that pasted notes and terminal output remain user reports.
Attribution follows the primary message role; only tool-role messages can establish
observed artifacts. Final source-validation failures appear in CLI status without
printing source content. Schema failures receive a generic format explanation.
The total bound is two attempts per unit. Missing token metrics stay unknown; elapsed
time and available metrics are recorded. No subscription currency estimate is made.

Live CLI use requires a private `--runtime-approval` record:

```json
{
  "schema_version": 2,
  "executable_sha256": "<64 lowercase hex characters>",
  "runtime_policy_sha256": "<64 lowercase hex characters>",
  "models": ["<account-available model>"],
  "isolation_reviewed": true
}
```

This is an operator attestation tied to executable bytes and approved models, not
an isolation mechanism. It must only be created after a verified compatibility
probe. A binary hash does not establish that inherited configuration, hooks, skills,
MCP servers, policies, or routing are safe, or detect subsequent changes to them.
Review relevant runtime changes again before use. No approval record is shipped or
created automatically. If adequate isolation preserving required security policies
cannot be established, do not activate this provider.

The adapter rejects observed tool/action events, but detection after an event cannot
undo an action. Actual restrictions must be established before a live call; prompt
instructions and read-only filesystem permissions alone are insufficient.

The current invocation binds approval to a versioned runtime-policy fingerprint. It
ignores personal Codex configuration for this child process, requests the read-only
sandbox and `approval_policy = "never"`, disables the shell tool and other listed
optional capabilities, disables web search and configured MCP servers, and forwards
only a minimal environment allowlist. The child shell environment is set to inherit no variables. It does not
alter the user's Codex configuration. Feature switches are defense in depth: they
do not prove that no tool is available, and managed requirements remain
authoritative. The first live compatibility review must inspect effective tools and
actions; if unrelated or action-capable integrations remain, activation stays
blocked. Read-only mode itself can still permit reading accessible files if an
unexpected tool is exposed.

### Target boundary: text-only analysis

The extraction operation accepts application-selected conversation data and returns
structured evidence candidates. The target is to expose no action tools in this
operation: no shell, file access, browser, connectors, delegated agents, or
model-triggered writes. Application code selects input, validates candidates, assigns
identities and destinations, persists records, and renders notes through its existing rules.
Model output never authorizes commands, configuration changes, or arbitrary paths.

Enforce this boundary for the extraction invocation, preserving saved login and
required security policies. Do not permanently disable the user's development
environment. Configuration or guidance may remain when compatible with this
boundary; blocking every configuration/instruction read is not a requirement.
Hooks or integrations must not cause unrelated actions during extraction.

This is the target contract, not a verified capability of the current adapter.
JSON schemas constrain data shape; they do not guarantee semantic correctness or
prevent actions exposed by the underlying agent. Research using tools, if later
requested, is a separate operation with explicit permissions.

Compatibility checklist, run only with explicit account-use approval and synthetic
material:

1. Record Codex/OS versions and an account-available model; verify saved auth without
   printing or copying credentials.
2. Verify that the extraction invocation exposes no action tools or unrelated
   hook/integration actions, preserving required managed security policy. The
   invocation uses per-process feature overrides and ignores personal config; inspect
   effective capabilities because these switches alone do not establish absence.
3. Run the tiny synthetic example twice sequentially; inspect structured output,
   usage visibility, temporary cleanup, and absence of tools or nested capture.
4. Record observed limitations privately. If any restriction is unsupported, leave
   live activation pending and revise the provider design before continuing.
5. Review evaluation annotations and compare approved available models against the
   reviewed synthetic cases. Subscription availability does not imply unlimited usage.

## Privacy and review

The `journal` command selects supported root sessions across all local repositories
for the requested date unless optional `--repo` filters narrow the scope. Private
workspace `excluded_session_ids` and repeatable `--exclude-session` values are
combined and checked against session metadata before bodies are processed. This
opt-out policy does not delete evidence extracted earlier. Preview displays scope,
configured exclusion count, and selected session IDs without source text by default.

The session reader skips individual entries above the 2 MiB parse limit and reports
`oversized_line` counts plus coverage diagnostics, rather than aborting the entire
day. Skipped entries are not parsed or submitted; their date, type and content remain
unknown. Source message IDs retain original line numbers across omissions. The
64 MiB transcript bound, metadata validation, malformed bounded-line rejection and
snapshot mutation checks still apply.

Including all repositories still sends the selected filtered conversation text to
the provider when model processing is activated; conceptual output does not mean
that input has already been semantically anonymized.

`journal` and normalized `extract` process by default; `--dry-run` prevents inference
and workspace writes. Legacy `--preview` and `--run-model` invocations remain
accepted for compatibility. Model selection and the runtime approval gate still
apply to live calls. The daily journal renders from the full active record store
after successful processing, including when no local transcripts are selected but
stored evidence is available. It creates a missing note or replaces the generated
block in an existing note while preserving handwritten text. Empty new days with
no relevant evidence produce no note; failed extraction leaves existing notes intact.

When `--model` is omitted for processing, resolve only the top-level `model` string
from `$CODEX_HOME/config.toml` (default `~/.codex/config.toml`). Parse TOML as data,
bound the file read to 1 MiB, and report invalid/missing settings without dumping
configuration contents. Explicit overrides bypass the lookup. This is not Codex's
full project/profile/provider configuration resolution. The child process retains
`--ignore-user-config` and receives the resolved model explicitly; runtime approval
checks still require that model in the reviewed list. Dry runs need no model lookup.
Python 3.11+ uses `tomllib`; Python 3.10 uses the existing development-pinned `tomli`,
whose runtime dependency declaration remains pending owner approval.

Sequential cross-machine consolidation requires synchronization of the workspace
identity, records, completed extraction receipts, and notes before the next run.
Each machine selects its own available transcripts, and the renderer uses the full
available active evidence store. Receipt reuse avoids repeat inference only when
source content and extraction settings match. Markdown-only sync cannot preserve
remote generated contributions during regeneration; concurrent synchronization
and conflicting histories remain outside the delivered reconciliation contract.

`--redact-file` accepts a private JSON list of known sensitive literals. Prefiltering
replaces them and recognized credential patterns in source content/task labels;
postfiltering applies to conceptual output and marks changed output omissions.
Sensitive values in identity metadata are rejected rather than renamed silently.
Filters do not guarantee semantic anonymization or confidentiality of employer data.
The operator reviews submitted material. `--show-payload` displays the exact initial
request only in preview mode; it intentionally exposes source to that terminal.

Production preview makes no model calls or writes. The synthetic fake-provider demo
exercises CLI integration without login or inference; it is not semantic evaluation.
Extraction does not automatically render notes. Explicit rendering consumes active
records and preserves handwritten material outside generated markers.

Live evaluation requires a new private `--review-output` directory for parsed
conceptual responses and identifying metadata; source-free usage reports are separate.
Provider failure preserves prior reports and reports the failed call before stopping.

See [the synthetic evaluation rubric](../../evals/extraction/rubric.md). Live acceptance
requires reviewed evidence with zero observed unsupported mastery promotions,
invented verified outcomes, fake-secret leaks, or successful action-injection attacks;
all cited IDs must resolve. A small passing set is not a general accuracy guarantee.

## Daily composition after extraction

Successful journal extraction feeds all active records for the date to the
[composition contract](daily-note-template.md), through the same restricted
`CodexExecProvider` transport and runtime policy. The composition response has its
own typed schema; no action capability is enabled. One new composition call is
bounded to 64 KiB submitted text and 180 seconds. Invalid citations, incomplete
record accounting, changed evidence, or failures preserve the previous note.
`--from-records` skips raw extraction; `--output` writes a private review candidate.
Private `compositions/` receipts are synchronized alongside evidence/extraction
receipts. Offline render needs no model and uses a current matching composition.

## Editorial journal and reading resources

Evidence candidates/records accept an optional `resources` list (title and HTTP(S)
URL). Extraction validates exact URL presence in cited source text, rejects obvious
local/credentialed URLs, and applies configured privacy filters. No resource is
fetched. The extraction prompt/schema fingerprint changes, so automatic revisions
reprocess earlier transcripts on a normal journal run. Old records remain readable.
The daily composition supports prose, bullets, steps, comparison tables and reading
questions. It validates selected learning URLs against cited records and keeps
record citations in private receipts. The reading note contains editorial content,
not the underlying evidence fields. All wire-schema fields are required (nullable
where appropriate); persisted older data can omit newly defaulted fields.
