import argparse
import json
import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

from meditations.config import (
    initialize_workspace,
    load_workspace,
    validate_workspace_path,
)
from meditations.files import workspace_directory, workspace_lock
from meditations.render import generated_bounds, render_daily, update_daily_note
from meditations.store import import_records, load_records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meditations")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Initialize a private records directory")
    init.add_argument("--workspace", type=Path, required=True)
    init.add_argument("--timezone", required=True)
    imports = commands.add_parser(
        "import-records", help="Import normalized evidence JSONL"
    )
    imports.add_argument("--workspace", type=Path, required=True)
    imports.add_argument("--input", type=Path, required=True)
    for command in ("render", "status"):
        child = commands.add_parser(command)
        child.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        workspace = validate_workspace_path(args.workspace)
        if args.command == "init":
            initialize_workspace(workspace, args.timezone)
            print("Initialized private workspace")
        elif args.command == "import-records":
            created, unchanged = import_records(workspace, args.input)
            print(json.dumps({"created": created, "unchanged": unchanged}))
        else:
            with workspace_lock(workspace):
                config = load_workspace(workspace)
                records = load_records(workspace)
                directory = workspace_directory(workspace, "engineering/daily")
                if args.command == "render":
                    zone = ZoneInfo(config.timezone)
                    days = {
                        record.occurred_at.astimezone(zone).date() for record in records
                    }
                    for path in directory.glob("*.md"):
                        try:
                            days.add(date.fromisoformat(path.stem))
                        except ValueError:
                            continue
                    conflicts: list[str] = []
                    for day in sorted(days):
                        try:
                            update_daily_note(
                                directory / f"{day}.md",
                                render_daily(records, config, day),
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
                    print(
                        json.dumps(
                            {
                                "records": len(records),
                                "conflicts": conflicts,
                                "capture": "not implemented",
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
