# Daily note structure

Status: canonical structure for the skill-first daily journal. The
[synthetic target](../../examples/daily-note-target.md) illustrates the format;
semantic quality still requires owner review.

## One report for the day

The note should let the reader recall the day's work and resume it, then provide
space for personal reflection. It combines a short overview with enough context to
understand grouped decisions and outcomes. It is one report, not a transcript and
not a short note paired with a second, exhaustive report.

| Section | Content | Boundary |
| --- | --- | --- |
| The day at a glance | Usually three to five bullets with the day's main outcomes | Quick scan; details belong in topic sections and are not repeated |
| Work and outcomes | One to five grouped topics covering problem/goal, changes, result or current state, and important rationale | Group by subject, not message order; distinguish proposal, decision, report and observation |
| Where to resume | Concrete unresolved items and next steps | Include only useful follow-ups |
| Study connected to the work | Up to three concepts or practices and why they matter | Use relevant links already present in captures; omit links that are absent |
| Questions for my reflection | One to four questions grounded in decisions or uncertainty | Invite the user's explanation; do not supply a conclusion for them |
| My reflection | User-owned writing outside generated markers | Preserve byte-for-byte, including later annotations |

The overview, topics, next steps, study and questions contribute distinct information.
Typical length depends on the day; sparse days should be shorter. The approved
private example is the writing reference; do not copy it into public fixtures.
English is the default. The user configures English or Brazilian Portuguese per
machine. The formatter localizes section labels and does not translate content.

## Checkpoint and composition contract

`$take-note` uses relevant material available in the current session. Preserve
decisions, rationale, results/current state, uncertainty and study already present.
Separate user contribution, assistant explanation and reported result in prose.
Avoid raw transcripts, code, credentials, employer names and private paths. Do not
infer user mastery or claim a tool result without direct evidence. If the session
context is incomplete, say so where relevant.

`$update-journal` starts with a read-only helper preparation. The helper validates
all checkpoints for the requested date, checks note boundaries, computes an input
fingerprint and detects unchanged input. `empty`, `unchanged`, invalid captures,
malformed notes and conflicts stop before composition. A successful preparation
provides all unique capture bodies in recorded timestamp order and the current note
hash. The skill creates a typed draft; Python validates it, renders Markdown and
chooses the destination. The helper makes no model calls.

The draft has typed overview, topic paragraphs/bullets/steps/tables, follow-ups,
learning items/resources, and reflection questions. Bounds prevent unbounded or
malformed document sections; they do not ensure the agent chose the right content.
Learning links must be public HTTP(S) URLs already found in a capture. They are not
fetched or independently verified. No web research occurs during daily update.

The helper stores capture Markdown and daily Markdown only. It does not produce
private evidence JSON, per-message citations, model-call receipts or transcript
coverage reports. Checkpoint identity helps avoid identical saves; it does not
prove distinct learning activity or semantic equivalence.

## Note boundaries and repeatability

New reports include date/project/tags/status frontmatter and one generated section
between `<!-- meditations:generated:start -->` and
`<!-- meditations:generated:end -->`. The generated block records source and
template fingerprints. Personal reflection remains after the generated section.
Updates replace only the content between a single valid marker pair. Prefix,
frontmatter and suffix are preserved as bytes. Missing, reversed or repeated markers
are conflicts. Existing unmarked notes are not adopted automatically.

The helper computes the previous-note link from the latest earlier ISO-dated file
in the same daily directory. It reports `created`, `updated`, `unchanged` or
`conflict`. Before writing it rechecks the input snapshot and expected note hash.
Local atomic writes cannot coordinate with Git on another machine; sync before
consolidation and resolve external conflicts before retrying.

## Review criteria

Use synthetic days that cover multiple sessions, several related topics, an issue
that is later resolved, contradictory reports, no study links and agent-only
explanations. Check that the note groups ideas without erasing a useful earlier
problem, distinguishes status from outcome, offers specific questions, and leaves
personal writing untouched. Deterministic tests establish storage and formatting
behavior. Owner review establishes whether the real note is concise and helpful.
