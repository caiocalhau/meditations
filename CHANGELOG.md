# Changelog

Notable changes are recorded here. Merging a change is not a release.

## [Unreleased]

The initial offline journal slice is tracked in
[#1](https://github.com/caiocalhau/meditations/pull/1).

### Added

- Initial Python CLI for private workspace setup, normalized evidence import,
  deterministic daily Markdown rendering, and processing status.
- Versioned configuration and evidence contracts with attribution, source revisions,
  validation, repeatable imports, atomic file replacement, and local write locks.
- Generated-note boundaries that preserve handwritten text and surface conflicts.
- Synthetic offline examples, failure-case tests, reproducible development
  dependency pins, package boundaries, and a Linux/macOS CI matrix.

Automatic capture, Codex inference, coaching, context retrieval, and weekly/monthly
reviews are still required for the MVP and are not implemented in this slice.

### Manual conversation extraction — 2026-10-04

Tracked in [#2](https://github.com/caiocalhau/meditations/pull/2).

#### Added

- Manual conversation preview and extraction contracts, source/role validation,
  privacy filters, and an offline-tested Codex subprocess adapter with explicit
  live-runtime review gates and bounded failures.
- Private extraction receipts, recoverable pending publication, active revision
  selection, and a fixed-response offline extraction demo.
- Twelve synthetic evaluation cases, separate structural checks, and a human review
  rubric. Live compatibility and semantic results remain unverified.

Automatic capture, coaching, context retrieval, and weekly/monthly reviews remain
required for the MVP. Live Codex inference is gated on compatibility, isolation,
and reviewed evaluation results.

### Platform validation correction — 2026-10-04

Tracked in [#2](https://github.com/caiocalhau/meditations/pull/2).

#### Fixed

- Platform-specific installation state selection now passes type checks for both
  Linux and macOS; regression tests cover XDG overrides, macOS paths, and persisted
  installation identities. CI also checks both target platforms explicitly.
