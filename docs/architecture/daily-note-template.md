# Daily journal template

Status: implemented for the assisted journal. Semantic quality remains subject to
user review; offline rendering without composition retains the evidence-only view.

## Problem and intended result

A compact extraction report is not necessarily a useful daily journal. Selecting
only the latest decisions or results can hide earlier important work and describe
the note-generation process instead of the day. Frequency-ranked concepts and
fixed reflection questions are not contextual learning guidance.

The intended note helps the reader remember what changed, revisit reasoning,
identify unresolved issues, and write a personal reflection. Group related
exchanges by meaning, across sessions when appropriate. Preserve source evidence
without presenting every request, approval, explanation, and test count as a
separate event in the reading view. A longer section is acceptable when needed to
preserve a consequential decision or correction.

The [synthetic target example](../../examples/daily-note-target.md) illustrates
the intended writing style. It is an editorial review artifact, not a live model
output or an exact rendering snapshot.
Private user notes are reference material for local review, never public fixtures.

## Canonical sections

| Section | Content | Boundary |
| --- | --- | --- |
| What changed today | One to six substantive bullets (usually three to six) covering the whole day | Changes and outcomes, not a chronological list of messages or a selection of the latest exchanges |
| Decisions and reasoning to preserve | One to five meaningful topics, with the problem, chosen direction, rationale, and relevant alternatives | Cite evidence; distinguish a proposal from an adopted decision and an explanation from demonstrated understanding |
| Still open / next steps | Concrete unresolved issues and agreed follow-ups | Resolve earlier pending states when supported by later evidence; disclose conflicts rather than silently choosing a version |
| Learning and reading | One to three relevant concepts or practice suggestions, explaining why they matter today | Include source-supported public reading links when available; omit missing links rather than inventing or claiming to verify them |
| Questions for my reflection | One to four questions grounded in today's reasoning or uncertainties | Invite the user's explanation; do not supply feelings or conclusions on their behalf |
| Private evidence store | Complete active evidence retained in JSON, outside the reading note | Retain attribution, uncertainty, corrections, source IDs and provenance without exposing their storage layout as journal sections |
| My reflection | User-owned writing outside generated markers | Preserve byte-for-byte, including later correction annotations |

Section labels follow the configured language. Portuguese labels would be:
“O que mudou hoje”, “Decisões e raciocínios que quero preservar”, “Pendências e
próximos passos”, “Aprendizagem e leitura”, “Perguntas para minha reflexão”,
and “Minha reflexão”. Language is not inferred from the
machine or translated by the deterministic formatter.

## Implementation boundary

Keep extraction and immutable evidence storage. Add a separate daily composition
step over all active evidence for the selected date, then let Python render a
validated structured response through the canonical template. The model produces
content, not Markdown, file paths, commands, or write instructions. Continue using
the reviewed text-only Codex route; do not enable research/action tools.

The composition response needs typed sections and source record IDs for each
substantive item. Python validates IDs, section bounds, duplicates, and output
shape. Human review still checks entailment, completeness, factual interpretation,
and usefulness; citation existence and schema validity do not prove those qualities.
All full evidence remains available privately even when the composition is short.
The reading note does not print record UUIDs, attribution/assistance fields,
revision numbers, inline record citations, or a record-by-record evidence appendix.

Evidence accepts an optional `resources` list of title/URL pairs. Existing records
without resources remain readable. Extraction only accepts URLs that occur exactly
in the candidate's cited source messages. Obvious local addresses, unsupported URL
schemes and credentials in URLs are rejected; configured privacy filters remove
resources whose URLs contain filtered values. These checks are not a guarantee
that an unknown hostname is appropriate for publication. Composition selects only
resource URLs present in its explanation's cited records. No URL is fetched or
independently verified. Old records cannot recover discarded links; a normal
journal run re-extracts current transcripts after the contract change. Automated
research remains separate. Missing resources do not prevent an otherwise useful note.

Resource validation failures carry structured diagnostics: a stable reason code,
learning/resource field indices, a redacted resource label, the complete URL's
SHA-256 fingerprint, explanation citation IDs, and IDs of evidence records that
contain the exact URL. Distinguish duplicates, URLs absent from all supplied
evidence, and URLs present in evidence but not in the learning item's explanation
citations. Human CLI status explains the rejection; JSON status includes
`composition_error`. Redact URL query strings/fragments, credentialed or invalid
URLs, and control characters; bound labels and human-readable ID lists. Validation
still stops at the first failure, publishes no invalid cache and preserves the
existing note. No rejected full model response is persisted by this change.

Use bounded inputs. The complete submitted text is capped at 64 KiB; a new evidence/settings
fingerprint uses one composition call with a 180-second timeout. Concurrent calls
can duplicate inference, although cache publication is locally locked. If the complete day exceeds it, preserve the previous note and report
that composition is incomplete; do not silently summarize only the latest records.
A subsequent bounded multi-stage composition design may address larger days.

Preflight and inference use the same privacy-filtered request builder and compact
JSON encoding, preserving every submitted field/value. Dry-run measures stored
composition input for both transcript and stored-evidence modes. When current
stored evidence exceeds the limit, a normal run returns before further extraction
inference; this can defer an extraction revision that might have reduced that
payload. Newly extracted evidence is checked again before composition inference.
No source evidence is truncated to force a day below the bound.

The latest composition failure per day is saved atomically with owner-only file
permissions under private `diagnostics/composition`. The bounded report contains
workspace/day identity, report timestamp, evidence fingerprint, safe structured
resource or budget diagnostics, extraction/composition call counts, and available
composition usage. Other failures receive a generic safe reason. It does not
contain raw source text, the rejected full response, or free-form provider errors.
Report-save failures do not hide the primary error. Read-only dry-run and status
surface these historical reports, with evidence-match status; they neither write
reports nor retry inference. Successful runs retain the report as history. Reports
from another workspace/day, symlinks, oversized files and corrupt contracts are
rejected. Diagnostic metadata is independent of the validated composition cache.

## Template changes and repeatability

Separate extraction settings, composition prompt/schema version, and presentation
template version. A formatting change should reuse evidence and an existing valid
composition. A composition change can regenerate only the composition from stored
evidence, without re-extracting raw sessions. New active evidence changes the
composition input fingerprint and requires an updated daily composition.

Cache composition with the active evidence fingerprint, language, requested model,
and composition contract version. Keep it private with the evidence workspace so
sequential synchronized runs can reuse it. Formatting alone should make no model
call. Repeating unchanged generation should preserve the note byte-for-byte.
Template versions describe presentation; they are not software release versions.

The normal daily command remains the single create/update entry point. A review
workflow should write a proposed reformatted note to a separate destination and
show its differences before replacing the real generated block. Previewing a
note format is different from today's `--dry-run`, which previews session selection.
Use `journal --from-records --output /private/path/candidate.md` to compose stored
evidence into a separate candidate. Candidate paths cannot target managed daily
notes or JSON directories. The baseline's text outside generated markers is copied
when creating a candidate and remains protected on later updates. `--dry-run`
reports selection/budget without inference or writes. Both evidence and composition
receipts remain in the private workspace, never in this public repository.

## Validation and acceptance

1. Use public synthetic examples for a short day, several topics in one session,
   multiple sessions, an unresolved issue later resolved, conflicting reports,
   no study links, and a day with only agent explanations.
2. Compare the full rendered synthetic note with the canonical target. Check
   section order, source links, output escaping, missing-data behavior, privately preserved
   evidence, and preserved handwritten text.
3. Review semantic composition: does the overview represent the whole day, do
   topics preserve the reasoning, are proposals/statuses distinguished, and are
   reflection questions relevant? Do not rely on byte-for-byte equality for model
   wording or on the model grading itself as the only acceptance evidence.
4. In local private validation, retain an untouched baseline, save the candidate
   separately, and compare before applying. Never add private validation notes to
   source control or distribution artifacts.
5. Test unchanged repeats, new evidence, a formatting-only change, a composition
   version change, invalid citations, failures, and concurrent personal edits.
   Rendering must not delete evidence, overwrite user writing, or replace a good
   note with an invalid or incomplete composition.

Passing deterministic checks proves the software boundaries, not journal quality.
A user-reviewed private candidate is required before treating this template as an
accepted replacement for the current presentation.

## Stored composition contract

`compositions/YYYY-MM-DD/<fingerprint>.json` contains a schema-1 composition receipt,
its source/settings/contract fingerprints, date, language, requested model, usage,
and structured response. Each narrative item references known record UUIDs.
Every active record must appear in a citation or in `supporting_only_record_ids`,
with no overlap or missing IDs. Supporting-only records remain in private JSON;
this accounting checks retention, not whether the model selected the right topics.
Corrupt cache entries fail visibly instead of triggering silent paid replacement.
Evidence/configuration changes during inference prevent publication. Presentation
uses `journal-v3-editorial`, independent of the composition prompt/schema fingerprint.

A small `.selected` file records the last successfully selected receipt, including
cache hits. Offline rendering follows that identity rather than choosing the
newest-created cache. Switching back to a previous privacy/model setting therefore
cannot be undone by offline rendering. Synchronize this file with the composition
receipts. Relevant unresolved or pending extraction receipts block composition,
including stored-evidence runs; no partial narrative is published as a complete day.

## Editorial Markdown rendering

The day-five reference defines the document structure: date/project/tags/status
frontmatter, one introductory attribution note, a brief overview, substantive
reasoning by topic, context-specific learning/reading, concrete next steps,
reflection questions, and protected personal writing. It is not a transcript audit.
The model can supply paragraphs, bullets, numbered steps and a bounded comparison
table for each topic. Python owns Markdown construction and escapes source text,
including pipe characters in table cells. Internal citations remain in the private
composition receipt, rather than appearing after every sentence in the note.
A study entry can include a recorded URL, why it matters, a reading question and a
suggested practice. No reflection or demonstrated mastery is inferred for the user.

New journal notes receive YAML frontmatter. Existing generated notes without a
prefix receive it during regeneration; existing nonempty prefixes/frontmatter and
all text following generated boundaries remain untouched. Handwritten notes without
valid markers still fail visibly. The offline evidence-only renderer remains a
separate diagnostic view; it is not the live journal's editorial template.

The composition prompt/schema change invalidates earlier cached compositions;
regenerating the corrected journal requires inference. Subsequent formatting-only
changes can reuse an unchanged valid composition.
