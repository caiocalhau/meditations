# Manual conversation extraction

## Delivery boundary

The second implementation slice adds normalized conversation preview, extraction
contracts, an offline-tested Codex subprocess adapter, recoverable receipts, active
revision selection, privacy filters, and a synthetic evaluation harness. Live Codex
compatibility, runtime isolation, account model availability, and semantic quality
remain unverified. No automatic history capture, hooks, scheduler, context delivery,
coaching, or periodic review is shipped by this slice.

The core remains a Python CLI. Obsidian reads the generated Markdown files; no
native Obsidian plugin, API key, MCP server, embeddings, or vector database is
required. Existing saved Codex login is the proposed live inference route.

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
an identical completed revision performs no provider call. Changed input/settings
requires an explicitly increased source revision; older revisions are rejected.

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
The total bound is two attempts per unit. Missing token metrics stay unknown; elapsed
time and available metrics are recorded. No subscription currency estimate is made.

Live CLI use requires a private `--runtime-approval` record:

```json
{
  "schema_version": 1,
  "executable_sha256": "<64 lowercase hex characters>",
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

Compatibility checklist, run only with explicit account-use approval and synthetic
material:

1. Record Codex/OS versions and an account-available model; verify saved auth without
   printing or copying credentials.
2. Establish runtime restrictions preventing unrelated hooks, tools, skills, project
   instructions, and configuration reads while preserving required security policy.
3. Run the tiny synthetic example twice sequentially; inspect structured output,
   usage visibility, temporary cleanup, and absence of tools or nested capture.
4. Record observed limitations privately. If any restriction is unsupported, leave
   live activation pending and revise the provider design before continuing.
5. Review evaluation annotations and compare approved available models against the
   reviewed synthetic cases. Subscription availability does not imply unlimited usage.

## Privacy and review

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
