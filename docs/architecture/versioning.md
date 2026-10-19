# Changelog and versioning

## Current status

Every merged delivery to `main` receives a minor or patch version increment,
including before the first stable release. This is the owner's integration
policy; Semantic Versioning determines the kind of increment, not merge timing.

The owner adopted the existing main through PR #5 as the `0.2.0` development
baseline. Its changelog section is assigned retrospectively and uses that merge's
actual date. The older `0.1.0` section retains its original baseline description;
neither baseline establishes a published artifact or tag. No intermediate
historical version numbers are invented.

PR #7 prepares `0.2.1`, a compatible correction to weekly coverage diagnostics.
`pyproject.toml` contains the version prepared by the current branch. A branch
can therefore declare its next version before it reaches main. Version numbers,
changelog entries and distribution metadata must agree.

Development delivery, stable interface and publication are separate decisions.
Merging does not authorize creating tags, publishing packages or announcing a
GitHub release. Versions below `1.0.0` remain in initial development even when
their version strings contain no pre-release suffix.

## Changelog structure

Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/):

- Keep `[Unreleased]` at the top for the pending delivery, followed by completed
  development deliveries newest first. Label retrospective baselines explicitly.
- Group entries under `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, or
  `Security`. Omit empty categories.
- Describe notable behavior changes for users and link their PRs.
- Record a completed delivery as `## [X.Y.Z] - YYYY-MM-DD`, using its actual merge
  date. While a PR is open, keep its entries under Unreleased with its target
  version; do not invent a future merge or publication date.
- Keep plans and unimplemented features in the README and architecture documents.
  Include relevant limitations beside implemented features.

Preserve entries for already-merged work, including work under `[Unreleased]`.
When an architecture or workflow is superseded, append `Changed` and `Removed`
entries explaining the transition and linking the new PR. Do not replace the
earlier entries with a description of only the current implementation.
Entries introduced by the current unmerged PR can be edited or consolidated.
Corrections to merged entries require owner approval and must preserve their
meaning, PR references and release facts. Git history complements the changelog;
it does not replace the readable record of the project's evolution.

Use actual merge commits for changelog links until approved tags exist. Unreleased
compares the last completed delivery with `HEAD`; baseline sections link to their
recorded commits. With tags available, use tag comparisons for subsequent versions.
Never link to an uncreated tag.

## Release numbering and compatibility

Release numbers follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Python package metadata uses `X.Y.Z`; approved Git release tags use `vX.Y.Z`.

Prepare one version increment per PR targeting main, regardless of the number of
commits in that PR. Choose the highest applicable change category:

- Compatible bug fixes increment patch: `0.2.0` to `0.2.1`.
- Compatible new features increment minor and reset patch: `0.2.1` to `0.3.0`.
- Documentation-only and internal maintenance deliveries increment patch by
  project convention so each main delivery has a distinct version.

Recheck main before integration. If another delivery changed its version, update
the pending version and changelog against that new baseline; do not reuse a version.

Compatibility review covers documented helper commands/options, machine
configuration, capture Markdown, generated-note boundaries, and the skill workflows.
Internal implementation details are not a promised public API. Data `schema_version`
values are independent of the package version.

While the package is below `1.0.0`, interfaces are still developing. Our policy is
to use patch releases for compatible fixes and minor releases for features or
breaking changes, documenting any required migration. Version `1.0.0` requires
an explicitly declared stable public interface. From then on, incompatible public
interface changes increment the major version, compatible features increment the
minor version, and compatible fixes increment the patch version.

Agents may recommend declaring `1.0.0` when the public interface and validation
support stability. The first stable version and every later major increment
require explicit owner approval; never infer it from a merge or publication request.

## Preparing and recording a development delivery

1. Classify the PR's changes and increment `pyproject.toml` from main's version.
2. Prepare its Unreleased entries and target version, keeping prior delivery
   entries intact. Verify configured checks and distribution metadata.
3. When preparing the next delivery, finalize the previous merged delivery's dated
   section using its actual merge date and commit, then add the new Unreleased
   target. Include this bookkeeping in the next normal PR rather than opening
   recursive bookkeeping-only PRs. No background automation is assumed.
4. Commit, push and merge only with the owner's authorization. A version increment
   does not itself authorize any of these Git operations.

## Publishing artifacts

Tagging, package publication and GitHub releases require explicit approval.
Publishing an approved `0.y.z` version does not declare it stable or increase its
major version. Check that the selected commit, changelog and built metadata match
before creating a `vX.Y.Z` tag or publishing its artifacts.

Published artifact contents and release tags must remain unchanged. Corrections
to the software require a new version; editorial changelog corrections do not
authorize replacing an existing release.
