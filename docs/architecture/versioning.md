# Changelog and versioning

## Current status

Meditations has no published release or release tag. The changelog currently
separates the original implementation from the next delivery for owner review:

- `[0.1.0]` records the original transcript-based implementation from `main` as
  the proposed first-release baseline. Its existing entries are preserved.
- `[Unreleased]` targets `0.2.0` and records the skill-first replacement.

The `0.1.0` section is release preparation, not evidence of a published release.
Its release date, tag and matching package metadata still require approval and
release preparation. Do not invent a date or claim either version is released.

The package metadata currently uses `0.1.0.dev0`. This is a Python development
version under [PEP 440](https://packaging.python.org/en/latest/specifications/version-specifiers/),
ordered before `0.1.0`. It is not a literal Semantic Versioning release number
and does not announce a published `0.1.0` release. Merging a PR does not require a
version bump. Development builds must not be published repeatedly under the same
version; preparing one for publication requires a distinct version and approval.

## Changelog structure

Follow [Keep a Changelog](https://keepachangelog.com/en/1.1.0/):

- Keep `[Unreleased]` at the top, followed by released versions newest first.
- Group entries under `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, or
  `Security`. Omit empty categories.
- Describe notable behavior changes for users. PR links provide traceability;
  PR numbers, implementation stages, and merge dates do not define releases.
- Record a release as `## [X.Y.Z] - YYYY-MM-DD`, using its actual release date.
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

Before the first release, the `[Unreleased]` link points to `main`'s commit history.
Afterward, it compares the latest release tag with `HEAD`. The first release links
to its tag; later releases link to comparisons between consecutive release tags.

## Release numbering and compatibility

Release numbers follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Normal Python release metadata uses `X.Y.Z`; Git release tags use `vX.Y.Z`.

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

## Preparing a release

Releases require explicit owner approval; merging a PR does not publish anything.

1. Review the intended release scope and compatibility, then choose its version.
2. Update `pyproject.toml`, move the included `[Unreleased]` entries into the dated
   version section, and retain `[Unreleased]` for subsequent work.
3. Update changelog comparison links and verify documentation, configured checks,
   and distribution contents before publication.
4. With approval, commit the release preparation, tag the reviewed commit, and
   publish the intended release artifacts.

Published artifact contents and release tags must remain unchanged. Corrections
to the software require a new version; editorial changelog corrections do not
authorize replacing an existing release.
