# Meditations: agent guidance

- Read README.md for delivered behavior and docs/architecture/learning-workspace.md
  for the product contract. Do not describe planned MVP features as shipped.
- Use Python >=3.10, typed functions, Pydantic v2 contracts, and the existing CLI
  boundaries. Keep code and repository documentation in English.
- Run `ruff check .`, `ruff format --check .`, `pyright`, and `pytest` in the
  project environment after code changes. Use test-first changes for deterministic
  behavior and synthetic evaluations for future model behavior.
- Update README when delivered behavior or setup changes and architecture when
  contracts change. Record notable changes under CHANGELOG.md's `[Unreleased]`,
  adding PR links when known. A merge is not a release.
- Follow Keep a Changelog: group unreleased changes by category, place released
  versions newest first, and use actual release dates. Unreleased entries may be
  consolidated after merge. Preserve release facts when correcting older text;
  never alter published artifacts or move tags. See docs/architecture/versioning.md.
- Keep docs/superpowers local and ignored; never force-add it. Never commit user
  notes, conversations, employer material, credentials, runtime state, or private
  evaluations. Inspect package contents as well as staged files.
- Dependencies are pinned in pyproject.toml and requirements-dev.txt. Ask before
  adding/installing dependencies or changing the selected runtime approach.
- Ask before commits, branch changes, pushes, PRs, releases, destructive operations,
  or live integration activation. Use Conventional Commits and preserve Git identity;
  omit AI authorship and attribution.
