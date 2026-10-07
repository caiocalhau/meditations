# Learning workspace architecture

Status: assisted journal and manual session selection implemented. The CLI supports initialization, normalized record import, synthetic conversation preview, local Codex transcript selection/preview, gated daily processing, cached source-cited daily composition, deterministic rendering, and status. One Linux runtime has completed a manual compatibility smoke review; broader semantic evaluations and macOS live behavior remain unverified. Activation requires per-machine review. Daily automation and the complete learning workspace remain pending.

## Purpose and release scope

Help developers strengthen engineering fundamentals through evidence-based reflection on everyday AI-assisted work. Preserve reasoning, decisions, uncertainty, and observable outcomes so users can revisit their understanding and choose useful practice. Completed agent work is not proof of user mastery.

Delivery proceeds through three useful outcomes:

1. **Assisted journal:** explicitly supplied session material becomes grounded daily
   notes with readable processing feedback and protected personal reflection.
   Manual weekly/monthly feedback may use selected notes in an external assistant;
   integrated review commands are not prerequisites for this delivery.
2. **Daily automation:** incremental capture, end-of-day scheduling, recovery,
   pause/exclusions, safe installation, and synchronized contributions remove
   routine commands. Unavailable machines defer work rather than lose evidence.
3. **Complete learning workspace:** integrated weekly/monthly reviews, skeptical
   longitudinal analysis, reviewed memory, selective context, coaching modes, and
   broader presentation options.

The complete vision includes:

- A Python CLI for setup, status, manual processing, and recovery, also used by hooks and scheduled workers.
- Local Codex integration on Linux and macOS, using existing Codex login for model execution.
- Automatic capture with durable checkpoints, pause/exclusion controls, and engineering relevance filtering.
- Concise daily Markdown notes with expandable reasoning, task/concept links, and protected handwritten reflection.
- Evidence-linked weekly learning reviews and monthly progress assessments.
- Balanced, Focus, and Study coaching modes during connected sessions.
- Selective retrieval of relevant goals, decisions, reviewed memories, and evidence for later sessions.
- Configurable presentation with portable Markdown and an Obsidian preset.
- Reconciliation after user-managed synchronization between machines, including deduplication and visible conflicts.

Off-topic archiving, browser ChatGPT capture, other agent/storage integrations, dashboards, embeddings, leaderboards, progression mechanics, and numeric competence scores are deferred. No hosted service, Obsidian CLI, Notion account, or vector database is required.

## Components and data flow

| Component | Responsibility |
| --- | --- |
| Codex adapter | Read supported saved history for selected dates with session exclusions and optional repository filters; isolate version-specific formats |
| Capture/checkpoint layer | Persist pending work and processing positions without making learning judgments |
| Extraction provider | Use authenticated Codex execution to filter relevance and extract minimized, validated conceptual evidence |
| Record store | Preserve evidence identities, attribution, relationships, and revisions independently of presentation |
| Daily composition and renderer | Cache source-cited daily synthesis, render it deterministically, and preserve user text; offline rendering can use an evidence-only view |
| Review service | Generate weekly/monthly comparisons and learning actions with supporting evidence and uncertainty |
| Context retrieval | Select bounded, relevant reviewed context using metadata and text search |
| Agent skills | Guide coaching, reflection, and review; skills do not guarantee scheduling or execution |

Manual flow: explicitly selected saved history → normalized session/day units → privacy filtering and extraction → durable records → daily notes. Future automated flow: lifecycle checkpoint → normalized segments → relevance filtering and extraction → durable records → daily notes and periodic reviews. Later connected sessions retrieve selected context from reviewed profiles and records.

The delivered manual path selects root Codex JSONL sessions across all local
repositories by default, using per-message event timestamps in the workspace
timezone. Optional repository filters match exact resolved working directories.
Workspace `excluded_session_ids` and repeatable command-line session exclusions
apply before transcript bodies are read; missing exclusion settings default to
an empty list. Exclusions prevent future processing without deleting existing
evidence. It converts supported text messages into bounded session/day units.
`--dry-run` makes no model calls or workspace writes. Normal invocation processes
the day, reusing unchanged receipts and assigning new internal revisions to changed
units automatically. Successful processing rebuilds the note from combined active
evidence, preserving handwritten text; missing notes can be rebuilt from stored
evidence without local transcripts. Subagents and Meditations extraction
sessions are excluded. Unsupported or non-text content is omitted with coverage
diagnostics. This is manual history selection, not an automatic lifecycle capture or
a guarantee that all work from the day appears in the source history.

Short hooks queue work; expensive inference runs outside shutdown-critical handlers. Manual commands, startup reconciliation, and OS scheduling use the same core. Only connected, available activity can be observed; incomplete coverage must remain visible.

## Private storage and evidence contracts

Users select a private directory outside the software checkout. Notes can be read in a text editor or Obsidian. External synchronization is user-managed; the application does not own Git commits, pushes, or a hosted sync service.

```text
<selected-directory>/
  profile/
  engineering/
    daily/
    reviews/
    concepts/
  records/
```

Machine-local checkpoints and operational state remain separate from synchronized records, handwritten notes, and credentials. Folder/file naming, language, date format, timezone, tags, link style, and expansion format are configurable.

`configure --workspace` saves an initialized vault's resolved absolute path in a
schema-1 machine-local configuration, separate from the vault's `workspace.json`.
Linux uses `$XDG_CONFIG_HOME/meditations/config.json` or
`~/.config/meditations/config.json`; macOS uses
`~/Library/Application Support/meditations/config.json`. CLI workspace arguments
are optional after this setup and explicit values take precedence without updating
the default. Configuration writes use the existing lock and atomic replacement
mechanisms. Invalid configuration or unavailable default workspaces produce an
actionable error, with no current-directory fallback. The command validates the
vault before changing the local setting and does not initialize the vault or
activate inference. Each machine configures its own path; these settings contain
no credentials and need not be synchronized.

The same schema accepts an optional absolute `runtime_approval` path. Existing
configurations without it remain valid. `configure --runtime-approval` updates
that setting while preserving the workspace; workspace changes preserve the
approval path. Initial setup requires a valid workspace. Saving a location does
not create, inspect, or attest to an approval record. Live `journal` and `extract`
runs resolve explicit approval paths before the machine default, then retain the
existing executable, policy, model, and review validation. Dry runs do not load
the approval record. The approval file remains machine-local and separate from
these settings.

Evidence records require schema version; globally unique record, workspace, and installation identities; source session/segment identity and revision; occurrence time with timezone; separate capture/processing times; task/tag/concept relationships; summary and supporting reasoning; observed alternatives, decisions, outcomes, and verification; attribution and assistance context; uncertainties and privacy omissions.

Attribution distinguishes user contribution, agent explanation, self-report, and observed artifacts. Assistance distinguishes independent, guided, agent-produced and reviewed, and unknown. Source references use opaque identifiers rather than exposing workstation paths. Minimized evidence remains intelligible when the original source is unavailable; unsupported claims stay unverified.

Keep related engineering questions with their task. Independent tasks get distinct daily sections; later dates link through stable task identities. Exclude unrelated segments without creating an archive. Persist only the exclusion metadata needed to prevent reprocessing. A session without relevant evidence produces no daily entry.

## Rendering, recovery, and synchronization

Without a current composition, offline daily notes separate a bounded reading
view from full expandable evidence per task. The overview selects at most five recently active tasks, using the latest summary
with recorded outcomes or decisions when available. Task digests show the latest
five distinct entries per decision, outcome, and verification field, retaining
attribution and links to evidence anchors. Duplicate text is normalized for
whitespace and case within the same attribution; no semantic deduplication is
claimed. Excerpts are bounded to 240 characters. These entries are historical
reports, not a synthesized final status. Up to five learning concepts are selected
by record frequency with deterministic ties. Every active record and its full
fields remain in the task's expandable section; display bounds do not delete data.

Uncertainty and verification limitations stay attached to their evidence rather
than being presented wholesale as open questions. Localized generic reflection
prompts invite personal writing, without diagnosing competence or inventing
reflection. The renderer performs no inference or research and does not translate
stored text. A missing personal reflection is explicit. Generated sections are
replaceable; text outside their defined markers survives byte-for-byte, including
handwritten reflection and correction annotations.

Partition by occurrence date in the configured timezone, including sessions spanning midnight. Late arrivals may revise earlier daily notes and affected reviews transparently. Deduplicate by source session/segment/revision rather than filenames; retrying a source must not duplicate evidence or assessment counts.

Persist recoverable pending work, serialize local writes, replace files atomically, detect changed inputs, and retry interrupted processing. Recording failures do not block ordinary development. Prevent recursive capture of extraction/review sessions.

Do not synchronize a shared mutable cursor or SQLite database. Reconcile uniquely identified contribution records after external synchronization. Preserve conflicting user edits for resolution and avoid overwriting newer assessments from an incomplete local history. Atomic replacement alone does not resolve concurrent external-sync writers.

## Reviews, coaching, and memory

Assess explanation, application, diagnosis, and transfer with assistance and uncertainty attached. Agent explanations are learning material; they do not establish user competence. Questions may reflect curiosity, verification, or a gap and must not automatically produce negative judgments. Missing activity is missing evidence, not regression.

Weekly reviews propose at most one or two active learning actions with a purpose and observable completion criterion. Monthly assessments compare available evidence over time and revisit strengths and priorities. Substantive conclusions resolve to evidence IDs or daily sections; reviews inspect supporting details, not summaries alone.

The planned weekly review also examines the user's handwritten reflections and
reading answers. Preserve the original wording; place dated, clearly attributed
correction annotations immediately below the relevant passage, with supporting
evidence or sources. Distinguish conceptual errors, expression clarity and missing
evidence; do not infer mastery from agreement or agent output. These checks belong
to weekly review, not routine daily summarization. Annotation writes must follow
the review's explicit authorization and protect intervening edits; daily rendering
must preserve both handwritten text and review annotations. This behavior is
planned, not implemented.

| Mode | Behavior |
| --- | --- |
| Balanced | Brief relevant coaching during work, deeper practice in reviews |
| Focus | Capture evidence and defer coaching, preserving task-critical feedback |
| Study | More explanation, Socratic questions, and practice |

Durable professional-profile conclusions remain candidates until user review. Preserve corrections, disagreement, and superseded memories. Retrieve narrowly by task, project, tags, and concepts rather than injecting the entire history. Retrieved notes are evidence, not executable instructions or higher-priority policies.

## Inference, privacy, and efficiency

Existing Codex login is the selected initial inference route. Verify noninteractive execution, structured output, unattended authentication, available models, usage visibility, timeouts, and recursion prevention before integration. Login does not establish unlimited usage, arbitrary model access, or API entitlement. Local storage does not imply local inference; document the source material submitted to the provider.

Ordinary Python code handles filtering of known patterns, checkpoints, deduplication, scheduling, persistence, rendering, and link formatting. Combine model relevance classification and extraction when evaluations support it. Prefer a lower-cost available model for extraction and a more capable available model for reviews, subject to measured quality and account availability. Do not invent model names or pricing guarantees.

Process new material incrementally with bounded related context, rather than replaying complete growing histories. Bound repair/escalation attempts; use schema/content failures, contradictory evidence, or attribution issues as signals. Missing evidence may remain unknown rather than trigger another call.

Evaluate attribution, relevance, conceptual completeness, unsupported claims, confidentiality omissions, and uncertainty against human-reviewed synthetic examples. Schema validity does not establish factual correctness; a stronger review model cannot recover discarded evidence.

Measure exposed usage fields, latency, retries, and provider/model identity. Unknown usage is not zero. Estimate monetary cost only with verified applicable pricing; subscription consumption and API billing are different. Defer pending work under resource limits and disclose incomplete coverage.

Minimize code, confidential names/schemas, credentials, customer data, and security details. Do not copy raw transcripts by default. Filtering and conceptual abstraction cannot guarantee confidentiality; omit questionable material and label reduced evidence. Embedded instructions in conversations or notes must not alter policy, request tools, or trigger publication.

## Delivery and acceptance

Retain five construction slices: records/rendering; evaluated extraction;
capture/recovery; installation/synchronization; context/coaching/reviews. The first
two support the assisted journal; capture and installation/synchronization support
automation; context/coaching/reviews complete the vision. The former requirement
to finish all five before a first usable delivery is superseded. Do not describe
synthetic/manual-record demos as evaluated real-session extraction.

Assisted-journal acceptance requires useful notes from approved nonsensitive session
material, source-grounded attribution, disclosed uncertainty, readable processing
results, correct occurrence dates, repeatable imports, and preserved user reflection.
Do not invent reflection or diagnose competence from questions alone. Evaluate
contradictions and pressure to agree as well as unsupported praise; skepticism must
not manufacture errors. Prompt instructions are not guarantees of unbiased output.
These semantic/usability gates remain pending; passing offline checks is insufficient.

Acceptance covers task continuity and relevance filtering; multiple sessions consolidated by day; cross-date links; duplicate processing; interrupted writes; absent reflection; synchronized contributions and user edits; timezone/midnight boundaries; correct attribution; traceable and revisable reviews; confidentiality omissions; instruction-like captured content; safe updates; coaching modes; reviewed-memory retrieval; and weekly/monthly learning actions.

Use deterministic tests for code behavior and human-reviewed evaluations for model behavior. Public fixtures and demos are synthetic. Verify live capture and the complete workflow on Linux and macOS with approved nonsensitive examples; synthetic tests alone do not prove end-to-end integration.

## Repository documentation and remaining decisions

Publish reusable source, synthetic fixtures, configuration templates, README, changelog, contribution/license guidance, and durable architecture documents. User records, credentials, operational state, temporary plans, and handoffs remain outside version control and distribution artifacts. Ignore rules are supplementary; inspect staged files and package contents before publication.

Keep documentation in English and accurate to delivered behavior. Update this architecture when contracts or data flow change and record notable changes under `[Unreleased]` with PR links when available. A merge is not a release. Use focused Conventional Commits and obtain required authorization for Git mutations and publication.

The offline slice uses Python >=3.10, pinned Pydantic v2, setuptools packaging, and argparse. Runtime commands are `init`, `configure`, `import-records`, `extract`, `journal`, `render`, and `status`; the README documents synthetic and local-preview workflows. Current settings support English and Brazilian Portuguese generated labels, portable links, HTML details, and a required IANA timezone. Existing schema-1 workspaces without a language continue to load as English. Broader presentation choices remain part of the complete vision.

Persist individual JSON records by UUID and validate source identities independently of filenames. Source identity is workspace/agent/session/segment/revision. Exact duplicates are unchanged; differing content or record IDs for the same revision produce a visible conflict in this slice. Preserve historical revisions and render only the highest revision per source segment. The daily adapter assigns revisions automatically from available receipts; normalized imports retain explicit source revisions. Cross-installation canonicalization and conflicting histories remain synchronization work.

Initialization validates all managed directory paths and configuration before writing, rejects layout symlinks/obstructions, and publishes configuration atomically under a local lock. Persisted configuration must include its schema version and workspace identity; loading cannot invent either. Checkout detection examines the selected path's ancestors independently of package installation location. Imports preflight identity conflicts against both existing and incoming evidence before writing; interrupted valid batches retain completed records for safe retry.

Generated daily content is bounded by `<!-- meditations:generated:start -->` and `<!-- meditations:generated:end -->`; text outside the block is preserved byte-for-byte. Local locks live in a user-owned temporary directory outside synchronized records. Atomic replacement checks the original file content before replacement, detecting intervening edits; this is not a guarantee against simultaneous external synchronization after the check. Changed content or invalid markers produces a conflict rather than a silent choice.

Minimum supported Codex versions, capture formats, scheduler templates, broader configuration, and context-delivery interfaces remain pending. Select a product name and license before release. Local evidence covers Linux/Python 3.10. The journal and manual extraction changes passed Linux/macOS CI on Python 3.10 and 3.14; the manual Linux runtime smoke review does not establish broader live compatibility or semantic acceptance.

## Manual extraction implementation

The extraction pipeline now provides normalized conversation preview and local
Codex session selection, source/role validation, an offline-tested Codex adapter,
bounded repair, private receipts, interruption recovery, and active revision
selection. Existing evidence schema version 1 remains unchanged. Runtime approvals
bind to a versioned invocation policy. One Linux installation has completed
capability inspection and synthetic live calls; each installation still requires
review, and broader semantic quality remains unverified. See [the extraction
contract](extraction.md) for the exact input, privacy boundaries, limits, receipts,
and activation gate. Daily automation and the remaining complete-workspace
capabilities are still pending.

## Assisted daily composition

See [daily-note-template.md](daily-note-template.md) for the delivered narrative
contract. Extraction retains evidence; a separate bounded text-only composition
uses all active daily records. Python validates citations/coverage and owns cache
publication and Markdown writes. Offline formatting remains available; stale
composition cannot replace a thematic note with an evidence-only fallback.
User reflections remain outside generated boundaries. Source-provided resource capture is implemented; research and weekly validation of
reflections/correction annotations remain future work.

The live journal uses the editorial day-five reference rather than exposing records:
metadata and an introductory note, topical explanations with lists/tables as useful,
source-supported study links and contextual questions. Complete evidence and source
IDs stay in the private store. User writing remains outside generated boundaries.
