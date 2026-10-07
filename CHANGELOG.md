# Changelog

Notable project changes are recorded here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Release numbering: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See the [versioning policy](docs/architecture/versioning.md). Merging a PR is not a release.

## [Unreleased]

### Added

- Guided Linux/macOS installation with repeatable helper/skill registration,
  machine-local configuration and GNU Stow bootstrap guidance.
- Explicit Codex skills for saving private session checkpoints and consolidating
  one date into a readable daily report, with a small Python helper for local
  configuration, validation, formatting, and guarded note updates.
- Markdown checkpoints that preserve dated additions across sessions and can be
  synchronized through the user's existing vault workflow.

### Changed

- Daily journaling now uses the active Codex session and its existing permissions.
  Users capture each relevant session explicitly; daily consolidation uses every
  available checkpoint for that work date and preserves personal reflection.
- README, installation guidance, architecture, examples, package contents and CI
  describe the skill-first MVP, its limits, and the later review/automation roadmap.

### Removed

- Transcript scanning, nested Codex execution, runtime approvals/model allowlists,
  structured per-message evidence, extraction/composition receipts, and their
  runtime commands have been removed from the active implementation. The earlier
  work remains in Git history. ([#1], [#2], [#3])
- The prior extraction fixtures, prompt evaluations and model-runtime verification
  workflow have been removed from the active package and CI. Private vault notes
  and legacy user data are untouched and are not imported.

[Unreleased]: https://github.com/caiocalhau/meditations/commits/main
[#1]: https://github.com/caiocalhau/meditations/pull/1
[#2]: https://github.com/caiocalhau/meditations/pull/2
[#3]: https://github.com/caiocalhau/meditations/pull/3
