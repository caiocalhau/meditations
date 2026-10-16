# Weekly learning review

Status: implemented on the weekly-review feature branch. Synthetic helper checks
and owner acceptance of a manual preview do not establish learning effectiveness
or completed native macOS validation of the new feature.

## One note, substantive analysis

`$weekly-review` reads daily notes for a Monday–Sunday week, using the active Codex
session's model and permissions. The first run analyses available work, decisions
and personal answers immediately. Later invocations incorporate saved weekly
responses and earlier practice. The Python helper never invokes a model.

The generated analysis includes a short orientation, supported decisions,
corrections/incomplete reasoning, optional English feedback, practice feedback and
evidence limits. Findings cite a selected source and excerpt. Python verifies
source membership and whitespace-normalized excerpt presence, then builds links.
This establishes traceability, not truth, authorship or independent mastery. Agent
proposals are not an answer key; missing explanation can mean insufficient evidence.

Daily notes are read in full, including legacy handwritten notes and answers
inside generated sections. No captures or transcripts are loaded. A later review
also reads the practice/response section of the latest earlier supported weekly
note; it does not load that earlier note's generated analysis. Unmarked prior
notes produce warnings and are skipped; malformed supported notes are conflicts.

## Dates, titles and storage

The default is the week containing today in the configured timezone. An explicit
ISO date selects its containing week. Only days through today are selected;
future weeks and weeks with no daily notes return `empty`. Coverage distinguishes
available notes, absent notes through today and dates not yet elapsed. A current
week remains provisional, including Sunday. Gaps do not establish lack of work.

The filename is Monday: `engineering/weekly/YYYY-MM-DD.md`. Visible titles use
readable ranges, such as `Weekly review — 12–18 October 2026`,
`Weekly review — 26 October–1 November 2026`, or
`Weekly review — 28 December 2026–3 January 2027`. Brazilian Portuguese settings
localize the labels and month names.

## Personal responses and repeat runs

A new note has one generated analysis block followed by practice questions,
actions and personal response space. Practice is bounded by
`<!-- meditations:weekly:practice:start -->` and
`<!-- meditations:weekly:practice:end -->`. Write answers and reflections in that
area. The entire prefix/suffix outside the analysis block is preserved byte for
byte; automatic review updates cannot replace questions already answered.

Answer from memory when practical, and record whether notes or assistance were
used. Invoke `$weekly-review` again when ready for feedback. The first report
already analyses existing daily answers; it does not withhold useful analysis
until new practice is completed. Later attempts after reading feedback must not
be described as initial unaided recall.

The source fingerprint includes full daily content, selected prior practice,
current text outside analysis, review-through date, preferences and template.
Generated analysis is excluded to prevent self-triggering updates. First creation
stores the fingerprint for its new practice scaffolding; an immediate repeat is
unchanged. New answers, changed daily notes or changed preferences trigger review.

## Local helper contract

- `meditations weekly prepare [--date YYYY-MM-DD]`: read-only preflight returning
  `ready`, `empty`, `unchanged` or `conflict`, calendar coverage, settings, bytes,
  warnings, source fingerprint and target hash. Only `ready` returns source bodies.
- `meditations schema weekly`: print the structured draft schema.
- `meditations weekly write --date YYYY-MM-DD --input -`: validate a prepared draft
  and publish the note, returning its actual status/path.

Combined source text is bounded to 256 KiB before drafting. The structured draft
uses the existing 2 MiB input ceiling and bounded text fields. These are local
engineering budgets, not token or subscription predictions. Do not silently
truncate or proceed with unreadable selected sources. Write validates the selected
quotes and configured feedback, rechecks inputs/target under the local lock and
uses atomic replacement. Symlinks, unsupported target formats, malformed boundaries
and stale drafts are conflicts. Locks do not coordinate Git writers on two machines.

Existing unmarked weekly notes, including manual previews, are preserved as
conflicts rather than automatically adopted. Any conversion requires explicit
owner authorization. Sync the vault before reviewing on another machine.

## English feedback

Enable once per machine with `meditations config set --english-feedback on`;
disable with `off`. The default is disabled. Existing configurations remain
readable without being rewritten on load. Repeat installation preserves the
setting; first interactive setup offers it. Older helper versions may reject
extended settings, so update the checkout before using them on that machine.

Explanations use the note language, while English examples stay in English.
Review only identifiable personal writing, preserve intended meaning and explain
selected corrections. Technical interpretation belongs in technical findings.
A small sample does not justify a general language-proficiency score. No English
feedback is expected when the preference is disabled.

## Research basis and evaluation

This is a research-informed adaptation, not a scientifically validated journal
intervention. Findings are prioritized without a quota. One to three questions
and one or two actions are practical readability defaults; a weekly interval is
not established here as an optimal spacing schedule.

- [Yang et al. (2021): retrieval practice in classrooms](https://pubmed.ncbi.nlm.nih.gov/33683913/)
  supports active recall under studied conditions; it does not establish developer
  performance gains from reading an AI report.
- [Bisra et al. (2018): self-explanation](https://link.springer.com/article/10.1007/s10648-018-9434-x)
  supports prompts about causal/conceptual relationships. The focused review used
  the publisher abstract, not inaccessible full text.
- [Tannenbaum and Cerasoli (2013): debriefing](https://pubmed.ncbi.nlm.nih.gov/23516804/)
  supports structured review of experience, with causal limitations in the included
  quasi-experimental studies.
- [Wisniewski et al. (2020): feedback](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2019.03087/full)
  emphasizes variation across feedback forms and information content.
- [Dunlosky et al. (2013): learning techniques](https://acs.ist.psu.edu/ist521/dunloskyRMNW13.pdf)
  reviews retrieval and distributed practice; this product does not optimize an
  individual repetition schedule.

The [synthetic examples](../../examples/weekly-review/README.md) show the expected
shape. [Semantic evaluation criteria](../../evals/weekly-review/README.md) complement
deterministic tests. Owner review should assess independent explanation or
application, useful corrections and manageable effort—not report length alone.

## Existing daily-note limitation

Answers written inside a daily-generated section can be replaced by a later daily
update. Keep personal writing outside daily-generated boundaries. Weekly review
can read existing inline answers, but does not move them or fix this separate
preservation issue. Daily files are never modified by weekly processing.
