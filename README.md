# Meditations

Turn AI-assisted engineering work into a useful daily journal: what changed, why,
what remains open, and what is worth learning next.

Meditations is a small Python helper and two explicit Codex skills. You capture
relevant work from each session with `$take-note`, then use `$update-journal` to
combine that date's captures into one readable Markdown report. You write your own
reflection in the note.

**MVP status:** the skill-first workflow is implemented on this development branch.
Linux/macOS installation and real-session note quality still need owner validation.
Weekly/monthly reviews and automatic capture are later stages.

## Why this project

I started in software development without much daily technical guidance, learning
by working through real problems. I want a dependable record that helps me recover
the reasoning, notice repeated questions, choose useful study, and discuss my
thinking with mentors. Reflection draws partly on Marcus Aurelius's *Meditations*:
review your judgment and decide what to improve. Evidence matters here: assistant
explanations and reported results do not show what the user understands independently.

The repository is also a portfolio project. It keeps reusable software, public
examples, engineering decisions, and honest limitations. Personal notes, session
content, employer information, and vault settings stay outside the public repo.

## How to use it

The workflow is deliberately explicit. If you forget to capture a session, that
session is missing from the journal until you return and capture it. A capture can
be delayed to the work date it belongs to. A later checkpoint adds progress; it
does not erase the earlier one. Daily consolidation uses all available captures for
that date, preserves your writing, and reports when nothing needs updating.

On Linux and macOS, install the helper and link the two skills into Codex's user
skill directory with the guided installer:

```bash
python3 scripts/install.py
```

The [installation guide](docs/installation.md) covers first setup, Stow/dotfiles,
machine-local settings and synchronization. Once installed, use:

```text
$take-note
$take-note for 2026-10-06
$update-journal
$update-journal for 2026-10-06
```

The date is optional for today. Use an explicit date when recording older work.
The helper stores readable Markdown captures under the private Obsidian vault and
creates or updates `engineering/daily/YYYY-MM-DD.md`. Capture files sync with the
vault, so consolidate on a machine after its captures have arrived.

The [synthetic capture input](examples/capture.json) and [sample daily report](examples/daily-note-target.md)
show the storage and note format. They contain no real session material.

## What the MVP does and does not do

Python stores the user-selected vault path, timezone, and note language locally. It
validates checkpoint identity, prepares a complete date's available captures,
checks whether an update is needed, renders a structured report, and protects text
outside the generated note section. It makes no model calls. The Codex session that
invokes a skill performs the writing using its active model and permissions.

Skills do not create a separate security boundary or remove the current agent's
tools. The user chooses what session material is suitable to capture. A skill's
instructions guide selection; they cannot guarantee that all sensitive meaning is
removed. This workflow does not browse for study material or infer mastery.

There is no automatic transcript collection, scheduler, Git commit/push, or
cross-machine sync service. Weekly reviews will later examine written reflections
and add attributed corrections beneath the originals. Monthly reviews will look
for supported patterns over time. Neither is part of this MVP.

## Development

Requires Python >=3.10. The project uses Pydantic v2 and has no separate Codex CLI
runtime dependency. To work on the helper:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-build-isolation -e .
meditations --help
```

Run the configured checks with `.venv/bin/ruff check .`,
`.venv/bin/ruff format --check .`, `.venv/bin/pyright`, and `.venv/bin/pytest`.
CI covers Linux and macOS with Python 3.10 and 3.14.

See [the implementation architecture](docs/architecture/skill-first-journal.md),
[the approved daily-note structure](docs/architecture/daily-note-template.md),
[the changelog](CHANGELOG.md), and [the versioning policy](docs/architecture/versioning.md).
