# Roadmap and resumption guide

Updated: 2026-10-15.

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

## Current delivery: an explicit weekly review

Status: the owner approved the design and implementation plan on 2026-10-15 after
reviewing a private manual example. The daily pilot was reported ready to extend;
this does not independently certify every checklist item above.

Weekly review is implemented on the feature branch. See the
[weekly contract](architecture/weekly-review.md) for the delivered behavior and
[synthetic examples](../examples/weekly-review/README.md) for the format. It provides
substantive analysis on first run, feedback on later weekly responses, optional
English feedback, and previous-practice context. Feedback stays in the weekly
note; earlier plans to insert corrections beneath daily passages are superseded.

Acceptance still needs owner review of the synthetic outputs and an explicitly
authorized private run after installation. Confirm substantive feedback, correct
source links, protected questions/responses, unchanged reruns, changed-answer
updates and cross-machine operation. Keep private evidence out of this repository.

## What stays deferred

Automatic capture, hooks, scheduling, automatic Git synchronization, monthly
reviews, browsing for new study resources, persistent model memory and support for
other agents remain outside this delivery. Existing sourced study
links can still be discussed. No dependency or runtime change is assumed.

The longer-term vision remains daily automation and broader learning reviews.
The owner chose an explicit weekly review before automation, informed by the pilot
and a focused literature review. Broader automation still requires separate design.

## Next acceptance steps

1. Review the synthetic weekly outputs against the semantic rubric and confirm
   that substantive reasoning feedback and English feedback are useful.
2. Review the implementation checks and approve the integration workflow. Existing
   manual weekly previews require explicit conversion before helper updates.
3. Authorize a private real-note trial after installing the new skill. Check
   protected answers, stable questions, unchanged reruns and later response updates
   on both machines. Retain real trial material only in the private vault.
4. Resolve demonstrated preservation or usability defects before expanding scope.
5. After acceptance, choose the next goal from real usage. Automation and monthly
   analysis remain separate proposals. Each merge records a development delivery
   version; stability declarations and publication require separate owner approval.

This document is a public handoff and planning checkpoint. It does not announce a
release, certify the ongoing pilot, or authorize implementation of future features.
