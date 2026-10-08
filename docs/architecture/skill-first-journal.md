# Skill-first journal decision

Status: MVP design approved on 2026-10-07 and merged into `main` on 2026-10-08.
Owner validation on Linux/macOS and real-session note quality remain pending.

## Decision

Use two explicit Codex skills. `$take-note` saves relevant work from the current
session as a private Markdown checkpoint. `$update-journal` combines all available
checkpoints for one work date into one daily note. A small Python CLI owns machine
configuration, capture identity, input validation, Markdown structure and safe file
updates. The active Codex model writes the checkpoint and structured report using
the current session's permissions.

## Why

The first useful product is a daily engineering journal, not unattended automation
or a complete learning platform. The owner accepts responsibility for remembering
to capture relevant sessions. If capture is missed, the record is incomplete until
the user returns to that session and saves it. This avoids transcript discovery,
nested model execution, per-message extraction, receipts, and a separate runtime
approval system during the MVP.

Captures use the work date, defaulting to today in the configured timezone. A user
can name a past date when recording late. Checkpoints accumulate, while daily
consolidation can state a later result without deleting the earlier reasoning. The
helper preserves the user's reflection and provides an unchanged/empty/conflict
status before asking the agent to compose.

## Boundaries and costs

Skills guide the workflow and output shape. They do not constrain the current
agent's tools or create a separate sandbox. The user's existing permissions still
apply. Instructions to summarize conceptually cannot guarantee anonymization or
truth; review the result and choose appropriate source material.

Readable captures make cross-session and cross-machine context explicit. Users
must sync them before consolidation. Captures not present on the current machine
are omitted. Local locks and hash rechecks reduce accidental overwrite but cannot
coordinate simultaneous Git writers on different machines.

Checkpoint-level provenance is less precise than per-message evidence references.
The skills can omit details, especially after context compaction. There is no
automatic retry from original transcripts. Semantic summary quality requires real
use and owner review; formatting and conflict checks are deterministic.

## Deferred

Automatic session lifecycle capture, scheduling, sync automation, weekly and
monthly review skills, reflection correction, selective memory, other agents and
stronger analysis isolation need separate designs after the daily workflow has
been used. The old Codex transcript/extraction runtime is removed from the active
codebase; Git history retains the prior implementation. Existing private notes and
legacy JSON remain untouched and are not imported by the new helper.

## Next milestone and handoff

See the [roadmap and resumption guide](../roadmap.md) for the ongoing usage pilot
and the proposed explicit weekly review. The delivery stages describe the broader
vision; their next implementation order remains subject to owner review.
