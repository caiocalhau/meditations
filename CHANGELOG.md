# Changelog

Notable project changes are recorded here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Release numbering: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
See the [versioning policy](docs/architecture/versioning.md) for development
versions and release preparation. Merging a change is not a release.


## [Unreleased](https://github.com/caiocalhau/meditations/commits/main)

Target version: **0.2.0** — skill-first daily journal.

### Added

- Explicit Codex skills to capture conceptual session checkpoints and consolidate a work date into one daily report. ([#4](https://github.com/caiocalhau/meditations/pull/4))
- Readable Markdown checkpoints that accumulate across sessions and can be synchronized through the user's existing vault workflow. ([#4](https://github.com/caiocalhau/meditations/pull/4))
- Guided Linux/macOS installation with repeatable helper/skill registration, machine-local configuration and GNU Stow bootstrap guidance. ([#4](https://github.com/caiocalhau/meditations/pull/4))

### Changed

- Changed the initial delivery from transcript-driven processing with a separate model runtime to explicit capture and consolidation in the active Codex session. The simpler workflow prioritizes a useful daily journal; automatic capture and weekly/monthly reviews remain part of the longer-term vision. ([#4](https://github.com/caiocalhau/meditations/pull/4))
- Replaced the extraction/receipt architecture with Markdown checkpoints and a small Python helper for validation, formatting and guarded writes. The active session supplies the model and permissions; users capture relevant sessions and synchronize their checkpoints before consolidation on another machine. ([#4](https://github.com/caiocalhau/meditations/pull/4))
- Updated the daily report to group work, reasoning, outcomes, next steps, study resources and reflection questions while preserving personal writing. ([#4](https://github.com/caiocalhau/meditations/pull/4))
- Updated setup, examples, architecture and packaging documentation to describe the skill-first workflow, its compatibility changes and pending validation. ([#4](https://github.com/caiocalhau/meditations/pull/4))

### Removed

- Transcript scanning, nested model execution, runtime approvals/model allowlists, per-message evidence and extraction/composition receipts, superseding the original implementation recorded under the 0.1.0 baseline. ([#4](https://github.com/caiocalhau/meditations/pull/4))
- Previous runtime commands, extraction fixtures and prompt-evaluation workflow. Existing private notes and legacy records are preserved but are not imported by the new workflow. ([#4](https://github.com/caiocalhau/meditations/pull/4))


## [0.1.0](https://github.com/caiocalhau/meditations/tree/5bfdebf4f2b671bd9e977702a0fe5dd7a9578f1c)

Original transcript-based implementation, preserved from `main` for the proposed
first-release baseline. This section is prepared for review; no release date,
release tag or published artifact has been created.

### Added

- Private historical composition failure reports in dry-run and status, with call counts, available composition usage, and evidence-match information. ([#3](https://github.com/caiocalhau/meditations/pull/3))
- Actionable composition resource diagnostics with field locations, redacted URLs, rejection reasons, source record IDs, and structured JSON error details.
- Source-provided study resources with exact cited-text URL validation, privacy filtering, and reading questions; old evidence records remain readable.
- Source-cited whole-day composition with a canonical journal template, contextual reflection questions, complete supporting evidence, and private cached receipts. ([#3](https://github.com/caiocalhau/meditations/pull/3))
- Separate candidate output and stored-evidence composition through `journal --from-records --output`, preserving daily baselines and handwritten reflection.
- Initial Python CLI for private workspace setup, normalized evidence import, deterministic daily Markdown rendering, and processing status. ([#1](https://github.com/caiocalhau/meditations/pull/1))
- Versioned configuration and evidence contracts with attribution, source revisions, validation, repeatable imports, atomic file replacement, and local write locks. ([#1](https://github.com/caiocalhau/meditations/pull/1))
- Generated-note boundaries that preserve handwritten text and surface conflicts. ([#1](https://github.com/caiocalhau/meditations/pull/1))
- Synthetic offline examples, failure-case tests, reproducible development dependency pins, package boundaries, and a Linux/macOS CI matrix. ([#1](https://github.com/caiocalhau/meditations/pull/1))
- Manual conversation preview and extraction contracts, source/role validation, privacy filters, and an offline-tested Codex subprocess adapter with explicit live-runtime review gates and bounded failures. Live compatibility, isolation, and semantic accuracy remain unverified. ([#2](https://github.com/caiocalhau/meditations/pull/2))
- Private extraction receipts, recoverable pending publication, active revision selection, and a fixed-response offline extraction demo. ([#2](https://github.com/caiocalhau/meditations/pull/2))
- Twelve synthetic evaluation cases, separate structural checks, and a human review rubric. ([#2](https://github.com/caiocalhau/meditations/pull/2))
- Local Codex session discovery across all repositories by default, optional exact repository filters, session opt-outs, date filtering, text-only preview, bounded extraction units, explicit daily processing, and readable run status. ([#3](https://github.com/caiocalhau/meditations/pull/3))
- Per-invocation Codex runtime policy fingerprinting, capability switches, and a minimal child-process environment; live compatibility remains unverified.
- English and Brazilian Portuguese generated note labels and extraction language.
- Per-machine default workspace configuration through `meditations configure`, with optional workspace arguments and explicit per-command overrides.
- Per-machine runtime approval path configuration, reused by daily processing and extraction with optional overrides and unchanged per-run approval validation.
- Default model selection from global Codex configuration, with an optional `--model` override; Python 3.10 runtime parser packaging remains pending approval.

### Changed

- Daily notes use a bounded task overview, attributed decisions and results, selected learning topics, reflection prompts, and complete expandable evidence instead of repeating every observation and uncertainty in the reading view. Reformatting preserves all active context and handwritten annotations.
- Test runs isolate home, Codex, and machine configuration directories from real local settings and runtime approval records.
- Installation guidance explains per-machine live setup, missing runtime approval records, review scope, and repeated daily runs; a Linux compatibility smoke review is documented without claiming macOS or semantic validation.
- Daily processing creates or updates notes by default with `--dry-run` for preview, automatically versions changed session material, and reuses unchanged evidence. Normalized extraction also accepts `--dry-run` and defaults to processing; legacy execution-mode flags remain compatible.
- Daily notes can be restored from synchronized evidence without local transcripts.
- Delivery documentation distinguishes the assisted journal, daily automation, and complete learning workspace, with evidence-based review criteria for the initial pilot and operation-scoped, text-only analysis permissions.

### Fixed

- Lossless compact composition JSON and an early check of stored payload limits before extraction calls; dry-run displays payload sizes for planning.
- Source-validation retries now receive the rejection reason and explicit attribution guidance for pasted reports; failed journal runs explain why the note was left unchanged.
- Daily journal generation follows an editorial document structure with metadata, topical prose/lists/tables, guided reading and specific reflection questions; internal evidence fields and record citations remain in private JSON.
- Obsidian note formatting: use native foldable Markdown evidence callouts, spaced lists, compact numbered citations, and matching block-reference links instead of Markdown inside HTML wrappers.
- Oversized Codex transcript entries no longer abort daily selection; they are omitted with coverage warnings while other messages keep stable source references.
- Platform-specific installation state selection now passes type checks for both Linux and macOS; regression tests cover XDG overrides, macOS paths, and persisted installation identities. CI also checks both target platforms explicitly. ([#2](https://github.com/caiocalhau/meditations/pull/2))
