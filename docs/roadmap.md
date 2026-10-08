# Roadmap and resumption guide

Updated: 2026-10-08.

## Where we stopped

PR #4 merged the skill-first daily journal into `main`. The current workflow is
explicit: `$take-note` records each relevant session, and `$update-journal`
consolidates available captures for one work date. Python validates, formats and
stores the files; the active Codex session supplies the model and permissions.

The owner is taking a development break while using the MVP. macOS capture and
cross-machine synchronization/consolidation are being tested. These are ongoing
user tests, not completed acceptance checks. The break does not require new
features or background operations.

See the [product contract](architecture/learning-workspace.md),
[current architecture](architecture/skill-first-journal.md), and
[daily-note template](architecture/daily-note-template.md).

## Immediate milestone: establish a dependable daily workflow

**Goal:** use the journal in normal work on macOS and Linux, then resume with
specific evidence of what needs improvement.

During the pilot, check:

- [ ] Capture two different sessions for the same work date and confirm both
  contributions appear after consolidation.
- [ ] Capture on macOS, synchronize the vault, and consolidate on Linux. Confirm
  earlier contributions survive and machine-local vault paths remain independent.
- [ ] Add a later checkpoint and consolidate again. Confirm the note incorporates
  new outcomes without duplicating earlier work or losing important reasoning.
- [ ] Repeat consolidation with unchanged captures. Confirm it reports unchanged
  without recomposing the note.
- [ ] Write a personal reflection, update the generated report, and confirm the
  reflection remains unchanged.
- [ ] Check date assignment, previous-note links, note language, length, study
  material and reflection questions during ordinary use.

Synchronize captures and daily notes before switching machines; avoid simultaneous
writes to the same daily note. Git conflicts still need normal resolution.

Keep actual notes, reflections, screenshots and session material in the private
vault. For a useful issue report, record the expected behavior, observed behavior,
platform and reproducible steps; provide sanitized or synthetic examples in this
public repository. No fixed number of days is required: collect enough material
to assess repeatability and recurring friction.

**Exit criterion:** the owner confirms the workflow is useful on both machines,
with no unresolved loss/overwrite defects. Record which checks actually passed
and which remain untested. Fix demonstrated defects before expanding scope.

## Recommended next feature: an explicit weekly review

Status: proposal for review when development resumes; not implemented or approved
for implementation by this roadmap.

**Goal:** turn the accumulated daily reports and personal reflections into useful,
evidence-based feedback with concrete study or practice actions.

The proposed workflow follows the MVP's boundaries: an explicitly invoked skill
uses the active session, reads a user-selected date range from the private vault,
and produces a review linked to its source notes. Keep Python responsible for
validated selection and guarded storage where those operations are needed. Do not
reintroduce transcript scanning, nested model execution or model approval lists.

Proposed first scope:

- Summarize recurring questions, decisions, unresolved work and reported progress.
- Examine the user's own reflections separately from AI-written explanations.
- Distinguish a supported conceptual error, unclear wording, contradictory evidence
  and insufficient evidence. Agreement with an assistant does not prove mastery.
- Cite the relevant daily note and passage for substantive feedback; acknowledge
  missing days instead of claiming complete coverage.
- Recommend one or two practical exercises or study actions tied to the evidence.
- Preserve original reflections. The owner previously requested dated, attributed
  corrections directly beneath the original passage. Design their identity and
  repeat-run behavior before allowing any write to a daily note.

Before implementation, review and approve these decisions:

1. Invocation name, explicit date-range handling and timezone semantics.
2. Whether daily notes suffice as review inputs or captures are needed in specific
   cases; avoid loading the same evidence twice without a reason.
3. One synthetic review example that establishes length, sections, source links,
   uncertainty and the correction format.
4. Weekly output location, preservation of personal writing, repeat-run behavior
   and handling of late-arriving or changed daily notes.
5. Whether corrections are written in the first delivery or presented for approval
   before a separate write. No silent replacement of the original text.
6. Input-size boundaries and early error/status reporting before model drafting.

Validate deterministic date/selection, preservation, conflict and repeat-run
behavior with tests. Evaluate feedback quality using synthetic cases with known
mistakes, ambiguous wording, missing reflections and unsupported claims of mastery.
Use private notes only in owner-authorized local acceptance tests.

## What stays deferred

Automatic capture, hooks, scheduling, automatic Git synchronization, monthly
reviews, browsing for new study resources, persistent model memory and support for
other agents remain outside the next feature proposal. Existing sourced study
links can still be discussed. No dependency or runtime change is assumed.

The longer-term vision remains daily automation and broader learning reviews.
The recommendation to try a manual weekly review before automation is a proposed
sequencing change, motivated by learning from the current pilot; it requires owner
agreement when choosing the next implementation scope.

## How to resume

1. Update the local `main` checkout and read this document plus the current product
   contract. Check repository status before making changes.
2. Review the owner's pilot feedback privately; record a sanitized summary of
   passed checks, reproducible defects and remaining questions.
3. Prioritize any data-preservation or daily-usability fixes. If the pilot is
   satisfactory, confirm whether the weekly review is still the next goal.
4. Agree on the review example and unresolved decisions above, then write the
   detailed implementation plan against the actual code at that time.
5. Obtain implementation approval before creating the feature branch and coding.
   Update setup/product documentation and append changelog entries for delivered
   changes, preserving historical entries.

This document is a public handoff and planning checkpoint. It does not announce a
release, certify the ongoing pilot, or authorize implementation of future features.
