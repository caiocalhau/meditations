# Learning workspace architecture

Status: skill-first daily journal MVP merged into `main`;
owner validation on Linux and macOS and real-session summary review remain open.
Do not describe future reviews or automation as delivered.

## Product purpose and delivery stages

Meditations helps developers revisit engineering decisions, remember where work
stands, notice recurring questions, and choose practical study. The user reads the
AI-assisted note and writes their own reflection. Agent-produced explanations and
reported checks are not proof of independent understanding.

Delivery proceeds in three stages:

1. **Daily journal MVP:** explicit session capture, one consolidated report per
   work date, protected personal writing, Linux/macOS Codex use, and understandable
   local status. Weekly/monthly feedback can still be requested manually from an
   external assistant using selected notes.
2. **Daily automation:** incremental lifecycle capture, recovery, pause/exclusions,
   scheduling and reconciliation reduce repeated manual commands. Unavailable
   sessions/machines remain missing until their data becomes available.
3. **Learning workspace:** integrated skeptical weekly/monthly feedback, review of
   handwritten reflections, reviewed context/memory, focused study/coaching, and
   broader agent support.

The project's portfolio value is in clear behavior, appropriate scope, portable
files, reliable tests and candid limitations. Automatic capture and multi-agent
support are not prerequisites for a useful first release.

## Current components

| Component | Responsibility |
| --- | --- |
| `$take-note` skill | Summarize relevant material available in the explicitly invoked Codex session into a readable private checkpoint |
| `$update-journal` skill | Inspect all checkpoints for one date, synthesize one report, and pass structured data to the helper |
| Python helper | Machine-local timezone/language/vault configuration, checkpoint identity, early unchanged/conflict checks, canonical Markdown and guarded writes |
| Private Obsidian vault | Synchronized capture Markdown, one daily Markdown note/date, and user-owned reflection |

Data flow:

```text
current session --$take-note--> dated Markdown checkpoint
                                      |
                               user-managed sync
                                      |
captures for one date --$update-journal--> daily report + preserved reflection
```

The helper makes no model calls and does not read Codex transcript files. It gets
the selected conceptual note text from the skill through validated JSON input. The
active model, tool availability and file permissions remain those of the current
Codex session. Skills are workflow instructions, not a separate sandbox or security
policy. Access to a vault outside the active workspace still follows Codex's normal
permission controls.

## Dates, storage and repeat runs

Each machine stores the resolved vault path, IANA timezone and note language in
private machine configuration. Linux uses XDG config or `~/.config`; macOS uses
Application Support. The paths are intentionally not synchronized. Explicit past
dates support delayed capture; session-start time does not assign work to a date.

Capture Markdown is visible and synchronized:

```text
<vault>/engineering/captures/YYYY-MM-DD/<content-id>-<UTC-capture-time>.md
<vault>/engineering/daily/YYYY-MM-DD.md
```

A capture identity is the normalized body plus work date. UTC time is in its
filename and frontmatter. Identical bodies with different capture times can be
synced without filename collision; consolidation deduplicates the identity and
orders different checkpoints by recorded time. This records reported capture time,
not proof of session chronology or provenance. Separate checkpoints preserve earlier
reasoning when a later one records resolution.

Preparation validates every checkpoint for the date, calculates a source/settings
snapshot and checks note markers before composition. It returns early for empty or
unchanged days and refuses to compose partial input. Publication rechecks both
captures and note hash after composition, holds a local workspace lock, and uses
atomic compare-before-replace. This protects cooperating writers on one machine;
Git synchronization does not provide a shared lock or guarantee conflict-free
simultaneous writes. Sync before consolidation on another machine.

Python builds the report's Markdown and owns paths, generated markers, resource
presence checks, and preservation of bytes outside the generated block. It rejects
unmarked/malformed notes, bad schemas, URLs absent from captures and reserved
markers. These structural checks do not prove factual support, link authority,
completeness, privacy, or useful coaching. The user reviews the note.

## Privacy and evidence limits

Only the user chooses when to capture and what material the active session includes.
The public repository stores code, synthetic examples and contracts, never personal
captures, employer material, credentials, runtime state, or real evaluation notes.
Captures should preserve concepts and decisions while omitting raw transcript,
source code and private paths. The skill instructs this selection; semantic
confidentiality cannot be guaranteed by a prompt or Markdown format.

Captures provide checkpoint-level context, not per-message evidence IDs or verified
transcript coverage. If a capture is forgotten, that work is absent until captured
later. If context has been compacted, the skill may not have the full session. The
workflow records that limitation when known instead of claiming complete coverage.

The agent can still access any capabilities permitted in its active session. A
skill does not limit the model to text-only tools. Python performs only defined
configuration, validation, formatting and file operations; no model output is
interpreted as a command or a path. Broader runtime isolation may be reconsidered
if unattended processing becomes a requirement.

## Future reviews

Weekly review will compare daily checkpoints and the user's handwritten reflections.
Preserve original writing; put dated, attributed corrections beneath it with
evidence. Distinguish a conceptual error, a writing difficulty and missing evidence.
Offer one or two observable practice actions, not a numeric competence score.

Monthly review will compare available weekly/daily evidence over time. Missing
captures mean missing evidence, not regression. Conclusions should link to source
notes and state uncertainty. Both reviews require separate future designs and
validation; no review skill or automated schedule ships in this MVP.

## Next milestone and handoff

See the [roadmap and resumption guide](../roadmap.md) for the ongoing usage pilot
and the proposed explicit weekly review. The delivery stages describe the broader
vision; their next implementation order remains subject to owner review.
