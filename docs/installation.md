# Install Meditations for Codex

Meditations supports Codex on Linux and macOS. The helper is Python; the capture
and journal-writing model is the one already active in the Codex session.

## Install once on each machine

Clone the public repository and run the guided installer from that checkout:

```bash
python3 scripts/install.py
```

Requires Python >=3.10 with `venv` and pip. On first setup, the installer asks for
an existing private vault, IANA timezone and note language. It creates a dedicated
virtual environment in `~/.local/share/meditations/venv`, installs this checkout,
links the helper into `~/.local/bin`, and registers both Codex skill folders.
The first installation needs network access to download the pinned dependencies.
On Linux distributions that package `venv` separately, install the corresponding
Python venv package if `python3 -m venv` is unavailable.

To configure without prompts:

```bash
python3 scripts/install.py \
  --workspace "/path/to/your/vault" \
  --timezone America/Sao_Paulo \
  --language en
```

A repeat run reuses a matching helper environment and valid machine settings;
explicit configuration arguments replace those settings after validation. The
installer requires all three configuration options together, so changing a vault
does not silently reset its timezone or language. The
installer refuses conflicting command/skill destinations instead of overwriting
them. It finishes by checking `meditations config show`. It creates no journal
notes and runs no model. If dependencies change, reinstall with the dedicated
environment's `python -m pip install -e .` before rerunning setup.

Ensure `$HOME/.local/bin` is on your shell's `PATH`. Keep this checkout at a stable
path because the links and editable installation point to it. Restart Codex if
the skills do not appear.
Codex discovers user skills under `$HOME/.agents/skills` and supports symlinked
skill folders. Invoke them explicitly as `$take-note` and `$update-journal`.

## Dotfiles and GNU Stow

Dotfiles can register a portable setup command that calls this installer with
the local checkout path. A Stow package can contain this file:

```text
dotfiles/meditations/.local/bin/setup-meditations
```

```sh
#!/bin/sh
set -eu
meditations_checkout=$1
shift
exec python3 "$meditations_checkout/scripts/install.py" "$@"
```

Then, on each machine:

```bash
cd ~/dotfiles
stow meditations
setup-meditations /path/to/meditations
```

Commit the bootstrap and its instructions to dotfiles. The installer generates
skill links using that machine's checkout path; keep skill definitions in the
Meditations repository instead of copying them. Keep virtual environments,
machine settings and vault content local. Ignore Meditations configuration and
environment directories in dotfiles so Stow tree folding does not accidentally
put generated files into a tracked package. Do not Stow-link `config.json`:
the helper rejects a symbolic-link settings file.

## Configure the private vault

Use an existing Obsidian vault or another private directory outside this checkout.
Choose the IANA timezone that defines your work dates and the language for generated
notes (`en` or `pt-BR`):

```bash
meditations configure \
  --workspace "/path/to/your/vault" \
  --timezone America/Sao_Paulo \
  --language en
meditations config show
```

The setting is stored per machine: Linux uses `$XDG_CONFIG_HOME/meditations/config.json`
or `~/.config/meditations/config.json`; macOS uses
`~/Library/Application Support/meditations/config.json`. It contains the resolved
vault path, timezone, and note language. It stays out of the vault and public repo.
The vault must already exist. Reconfiguration changes only the local settings file;
it does not migrate, import, or delete existing notes or legacy Meditations JSON.

## Use the skills

In a Codex session with the skills installed:

```text
$take-note
$take-note for 2026-10-06
$update-journal
$update-journal for 2026-10-06
```

`$take-note` captures relevant concepts and outcomes from the current session as
readable Markdown. The helper uses today's configured local date unless you name
an older work date. Use `$update-journal` after capturing the sessions you want
included. It reads every valid checkpoint for that date, returns early when there
are none or the report is already current, and asks the active agent to compose
only when an update is needed. It will not infer the date of each message in a
resumed session; name the date when capturing older work.

Captures are stored in
`<vault>/engineering/captures/YYYY-MM-DD/<content-id>-<capture-time>.md` and are
visible in Obsidian. Daily reports are stored in
`<vault>/engineering/daily/YYYY-MM-DD.md`. Repeating the same capture on a machine
reports unchanged. Matching content captured on two machines uses distinct file
names and is consolidated once after sync. Different checkpoints accumulate in
capture-time order. Local clocks can differ; the notes retain their recorded times.

One run of `$update-journal` handles one date, regardless of how many sessions
contributed. Sync the vault before consolidating on another machine. If two machines
write the same daily note concurrently, Git can report a conflict; sync first and
rerun after resolving it. Meditations never commits or pushes your vault.

The daily note follows the [approved structure](architecture/daily-note-template.md).
Handwritten text outside the single generated block is preserved. Notes with
missing or malformed generated markers are reported as conflicts and left intact.
The helper rejects captures that fail identity checks and does not generate from a
partial set. It does not prove that the active agent's summary is complete or true;
review the result before relying on it.

## Troubleshooting

- **`meditations: command not found`:** check that `$HOME/.local/bin` is on `PATH`
  and the symlink points to the dedicated environment's executable.
- **No default vault:** run `meditations configure` again with an existing private
  directory, timezone, and language.
- **Skill absent:** check the two links in `$HOME/.agents/skills`; restart Codex.
- **`empty`:** no checkpoint exists for that date. Return to the relevant session
  and run `$take-note`, naming the older date if needed.
- **`unchanged`:** inputs and settings match the report already stored; no model
  composition or note write is needed.
- **`conflict`:** read the helper's message. It preserves the note and stops when
  captures or generated-note boundaries are invalid or changed during composition.
- **Missing work from another machine:** sync the capture Markdown first, then run
  `$update-journal` once for that day.

## Remove the local installation

Remove only the two Meditations skill links and the helper symlink you created,
then remove `$HOME/.local/share/meditations/venv` if you no longer need it. Keep
your Obsidian captures and notes; uninstalling the helper does not remove them.
