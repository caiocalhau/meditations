# Changelog and versioning

## Current status

Meditations has no published release or release tag. All notable changes belong
under `[Unreleased]`, including changes already merged into `main`.

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

Unreleased entries can be edited or consolidated after merge while retaining
their meaning and PR references. Older release text can be corrected for accuracy
or formatting, but corrections must preserve which changes shipped in which
release. Git retains the editing history; the changelog is a curated release
history rather than a chronological list of commits.

Before the first release, the `[Unreleased]` link points to `main`'s commit history.
Afterward, it compares the latest release tag with `HEAD`. The first release links
to its tag; later releases link to comparisons between consecutive release tags.

## Release numbering and compatibility

Release numbers follow [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
Normal Python release metadata uses `X.Y.Z`; Git release tags use `vX.Y.Z`.

Compatibility review covers documented CLI commands and options, configuration
and evidence contracts, and persisted workspace data. Internal implementation
details are not a promised public API. Record `schema_version` values describe
data formats and are independent of the package version.

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
