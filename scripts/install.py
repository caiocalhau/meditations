#!/usr/bin/env python3
"""Install the helper and register its skills once on Linux or macOS."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def destinations(repo: Path, home: Path) -> dict[Path, Path]:
    return {
        home / ".local/bin/meditations": home
        / ".local/share/meditations/venv/bin/meditations",
        home / ".agents/skills/meditations-take-note": repo / "skills/take-note",
        home / ".agents/skills/meditations-update-journal": repo
        / "skills/update-journal",
    }


def check_links(repo: Path, home: Path) -> None:
    for link, target in destinations(repo, home).items():
        if link.is_symlink() and link.resolve() == target.resolve():
            continue
        if link.exists() or link.is_symlink():
            raise ValueError(f"Destination already exists: {link}; inspect it first")


def ensure_links(repo: Path, home: Path) -> None:
    check_links(repo, home)
    for link, target in destinations(repo, home).items():
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.is_symlink():
            link.symlink_to(target)


def choose_settings(
    home: Path,
    workspace: Path | None,
    timezone: str | None,
    language: str | None,
) -> tuple[Path, str, str] | None:
    if workspace is None and (timezone is not None or language is not None):
        raise ValueError("Pass --workspace when changing timezone or language")
    if workspace is not None and (timezone is None or language is None):
        raise ValueError(
            "Pass --timezone and --language with --workspace; "
            "existing settings were not changed"
        )
    if workspace is None:
        root = (
            home / "Library/Application Support"
            if sys.platform == "darwin"
            else Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
        )
        config_path = root / "meditations/config.json"
        if config_path.is_symlink():
            raise ValueError("Keep config.json local; do not Stow-link this file")
        try:
            config = json.loads(config_path.read_bytes())
            if (
                set(config) == {"schema_version", "workspace", "timezone", "language"}
                and config["schema_version"] == 2
                and Path(config["workspace"]).is_absolute()
                and Path(config["workspace"]).is_dir()
                and config["language"] in ("en", "pt-BR")
            ):
                ZoneInfo(config["timezone"])
                return None
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if not sys.stdin.isatty():
            raise ValueError(
                "Pass --workspace /path/to/vault --timezone Region/City "
                "--language en, or run interactively for guided setup"
            )
        workspace = Path(input("Existing private vault directory: ").strip())
        timezone = input("Work-date timezone [UTC]: ").strip() or "UTC"
        language = input("Note language [en / pt-BR; default en]: ").strip() or "en"
    resolved = workspace.expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError("The private vault directory must already exist")
    timezone = timezone or "UTC"
    language = language or "en"
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ValueError("Use a valid IANA timezone") from error
    if language not in ("en", "pt-BR"):
        raise ValueError("Choose en or pt-BR for the note language")
    return resolved, timezone, language


def environment_matches(python: Path, repo: Path) -> bool:
    if not python.exists():
        return False
    result = subprocess.run(
        [
            str(python),
            "-c",
            "import json, meditations, pydantic; "
            "print(json.dumps([meditations.__file__, pydantic.__version__]))",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return False
    try:
        source, version = json.loads(result.stdout)
        return (
            Path(source).resolve() == repo / "src/meditations/__init__.py"
            and version == "2.13.5"
        )
    except (ValueError, TypeError):
        return False


def install(
    repo: Path,
    home: Path,
    workspace: Path | None,
    timezone: str | None,
    language: str | None,
) -> None:
    check_links(repo, home)
    settings = choose_settings(home, workspace, timezone, language)
    if settings is not None and (settings[0] == repo or repo in settings[0].parents):
        raise ValueError("Choose a private vault outside the software checkout")
    environment = home / ".local/share/meditations/venv"
    python = environment / "bin/python"
    if not environment_matches(python, repo):
        print(
            "Installing the helper in its dedicated virtual environment...", flush=True
        )
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        subprocess.run(
            [str(python), "-m", "pip", "install", "-e", str(repo)], check=True
        )
    else:
        print("Reusing the installed helper for this checkout.", flush=True)
    ensure_links(repo, home)
    command = environment / "bin/meditations"
    if settings is not None:
        vault, tz, lang = settings
        subprocess.run(
            [
                str(command),
                "configure",
                "--workspace",
                str(vault),
                "--timezone",
                tz,
                "--language",
                lang,
            ],
            check=True,
        )
    subprocess.run([str(command), "config", "show"], check=True)
    print("Setup complete. In Codex, use $take-note and then $update-journal.")
    print("Restart Codex if the skills do not appear.")
    if str(home / ".local/bin") not in os.environ.get("PATH", "").split(os.pathsep):
        print('Add "$HOME/.local/bin" to your shell PATH to use meditations.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", type=Path, help="Existing private vault directory"
    )
    parser.add_argument(
        "--timezone", help="IANA timezone, for example America/Sao_Paulo"
    )
    parser.add_argument("--language", choices=("en", "pt-BR"))
    args = parser.parse_args()
    if sys.version_info < (3, 10) or sys.platform not in ("linux", "darwin"):
        parser.error("Use Python >=3.10 on Linux or macOS")
    try:
        install(
            Path(__file__).resolve().parents[1],
            Path.home(),
            args.workspace,
            args.timezone,
            args.language,
        )
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Setup failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
