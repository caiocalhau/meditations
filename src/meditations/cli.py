import argparse
import json
import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from meditations.composition import CompositionProvider, cached_composition
from meditations.config import (
    initialize_workspace,
    load_workspace,
)
from meditations.diagnostics import saved_composition_failures
from meditations.extraction.cli import add_extract_command, extract_command
from meditations.extraction.provider import ExtractionProvider
from meditations.extraction.receipts import select_active_records
from meditations.files import workspace_directory, workspace_lock
from meditations.journal import add_journal_command, journal_command
from meditations.machine_config import (
    configure_workspace,
    resolve_runtime_approval,
    resolve_workspace,
)
from meditations.render import generated_bounds, render_daily, update_daily_note
from meditations.store import import_records, load_records


def main(
    argv: list[str] | None = None,
    *,
    provider: ExtractionProvider | None = None,
    state_directory: Path | None = None,
    machine_config_path: Path | None = None,
    composer: CompositionProvider | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="meditations")
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser(
        "configure",
        help="Set this machine's default workspace and runtime approval path",
    )
    configure.add_argument("--workspace", type=Path)
    configure.add_argument("--runtime-approval", type=Path)
    init = commands.add_parser("init", help="Initialize a private records directory")
    init.add_argument("--workspace", type=Path)
    init.add_argument("--timezone", required=True)
    init.add_argument("--language", choices=("en", "pt-BR"))
    imports = commands.add_parser(
        "import-records", help="Import normalized evidence JSONL"
    )
    imports.add_argument("--workspace", type=Path)
    imports.add_argument("--input", type=Path, required=True)
    for command in ("render", "status"):
        child = commands.add_parser(command)
        child.add_argument("--workspace", type=Path)
    add_extract_command(commands.add_parser)
    add_journal_command(commands.add_parser)
    args = parser.parse_args(argv)
    if args.command == "configure" and not (args.workspace or args.runtime_approval):
        configure.error("provide --workspace or --runtime-approval")
    try:
        if args.command == "configure":
            workspace = configure_workspace(
                args.workspace,
                machine_config_path,
                runtime_approval=args.runtime_approval,
            )
            print(f"Configured default workspace: {workspace}")
            if args.runtime_approval is not None:
                print(
                    "Saved runtime approval path; the record is validated "
                    "before inference"
                )
            return 0
        workspace = resolve_workspace(args.workspace, machine_config_path)
        args.workspace = workspace
        if (
            args.command in ("extract", "journal")
            and provider is None
            and not (args.preview if args.command == "extract" else args.dry_run)
        ):
            args.runtime_approval = resolve_runtime_approval(
                args.runtime_approval, machine_config_path
            )
        if args.command == "extract":
            return extract_command(args, provider, state_directory)
        if args.command == "journal":
            return journal_command(args, provider, state_directory, composer=composer)
        if args.command == "init":
            initialize_workspace(workspace, args.timezone, args.language)
            print("Initialized private workspace")
        elif args.command == "import-records":
            created, unchanged = import_records(workspace, args.input)
            print(json.dumps({"created": created, "unchanged": unchanged}))
        else:
            with workspace_lock(workspace):
                config = load_workspace(workspace)
                records = load_records(workspace)
                active_records = select_active_records(workspace, records)
                directory = workspace_directory(workspace, "engineering/daily")
                if args.command == "render":
                    zone = ZoneInfo(config.timezone)
                    days = {
                        record.occurred_at.astimezone(zone).date()
                        for record in active_records
                    }
                    for path in directory.glob("*.md"):
                        try:
                            days.add(date.fromisoformat(path.stem))
                        except ValueError:
                            continue
                    conflicts: list[str] = []
                    for day in sorted(days):
                        try:
                            composition = cached_composition(
                                workspace, config, day, active_records
                            )
                            target = directory / f"{day}.md"
                            if (
                                composition is None
                                and target.exists()
                                and b"<!-- meditations:template:" in target.read_bytes()
                            ):
                                raise ValueError(
                                    "No current composition; run journal to refresh it"
                                )
                            update_daily_note(
                                directory / f"{day}.md",
                                render_daily(
                                    active_records, config, day, composition=composition
                                ),
                            )
                        except ValueError:
                            conflicts.append(day.isoformat())
                    print(json.dumps({"days": len(days), "conflicts": conflicts}))
                    if conflicts:
                        return 1
                else:
                    conflicts = []
                    for path in directory.glob("*.md"):
                        try:
                            if path.is_symlink():
                                raise ValueError("Symbolic link")
                            generated_bounds(path.read_bytes())
                        except ValueError:
                            conflicts.append(path.name)
                    failures = saved_composition_failures(
                        args.workspace, config, active_records
                    )
                    print(
                        json.dumps(
                            {
                                "records": len(records),
                                "conflicts": conflicts,
                                "capture": "not implemented",
                                "saved_composition_failures": failures,
                            }
                        )
                    )
                    if conflicts:
                        return 1
        return 0
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
