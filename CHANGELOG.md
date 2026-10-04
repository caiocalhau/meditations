# Changelog

Notable project changes are recorded here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Release numbering: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See the [versioning policy](docs/architecture/versioning.md) for development
versions and release preparation. Merging a change is not a release.

## [Unreleased]

### Added

- Initial Python CLI for private workspace setup, normalized evidence import,
  deterministic daily Markdown rendering, and processing status. ([#1])
- Versioned configuration and evidence contracts with attribution, source revisions,
  validation, repeatable imports, atomic file replacement, and local write locks.
  ([#1])
- Generated-note boundaries that preserve handwritten text and surface conflicts.
  ([#1])
- Synthetic offline examples, failure-case tests, reproducible development
  dependency pins, package boundaries, and a Linux/macOS CI matrix. ([#1])
- Manual conversation preview and extraction contracts, source/role validation,
  privacy filters, and an offline-tested Codex subprocess adapter with explicit
  live-runtime review gates and bounded failures. Live compatibility, isolation,
  and semantic accuracy remain unverified. ([#2])
- Private extraction receipts, recoverable pending publication, active revision
  selection, and a fixed-response offline extraction demo. ([#2])
- Twelve synthetic evaluation cases, separate structural checks, and a human review
  rubric. ([#2])

### Fixed

- Platform-specific installation state selection now passes type checks for both
  Linux and macOS; regression tests cover XDG overrides, macOS paths, and persisted
  installation identities. CI also checks both target platforms explicitly. ([#2])

[Unreleased]: https://github.com/caiocalhau/meditations/commits/main
[#1]: https://github.com/caiocalhau/meditations/pull/1
[#2]: https://github.com/caiocalhau/meditations/pull/2
