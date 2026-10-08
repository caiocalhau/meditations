"""Small local helper for the explicit Codex skill workflow."""

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

from meditations.captures import prepare_day, save_capture
from meditations.contracts import CaptureDraft, DailyDraft
from meditations.machine_config import (
    configure,
    default_config_path,
    load_machine_config,
    resolve_work_date,
    resolve_workspace,
)
from meditations.render import write_daily

SAFE_ERROR_FIELDS = frozenset(
    {
        "body",
        "source_snapshot",
        "expected_note_sha256",
        "overview",
        "topics",
        "title",
        "paragraphs",
        "bullets",
        "steps",
        "table",
        "headers",
        "rows",
        "open_items",
        "learning",
        "concept",
        "explanation",
        "suggested_practice",
        "resource_urls",
        "reading_question",
        "reflection_questions",
    }
)


def _date(value: str) -> date:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise argparse.ArgumentTypeError("Use a date in YYYY-MM-DD form")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use a date in YYYY-MM-DD form") from error


def _read_input() -> bytes:
    stream = getattr(sys.stdin, "buffer", None)
    raw = (
        stream.read(2 * 1024 * 1024 + 1)
        if stream is not None
        else sys.stdin.read().encode()
    )
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("Structured input exceeds the 2 MiB local limit")
    return raw


def _print(model: BaseModel | dict[str, str]) -> None:
    if isinstance(model, BaseModel):
        print(model.model_dump_json())
    else:
        print(json.dumps(model, ensure_ascii=False))


def _validation_message(error: ValidationError) -> str:
    messages: list[str] = []
    for detail in error.errors(
        include_input=False, include_context=False, include_url=False
    ):
        parts: list[str] = []
        for part in detail["loc"]:
            if isinstance(part, int):
                parts.append(str(part))
            elif part in SAFE_ERROR_FIELDS:
                parts.append(part)
            else:
                parts.append("<unknown field>")
        location = ".".join(parts) or "input"
        messages.append(f"{location}: {detail['msg']}")
    return "Invalid structured input: " + "; ".join(messages)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="meditations")
    commands = parser.add_subparsers(dest="command", required=True)

    configure_parser = commands.add_parser(
        "configure", help="Configure this machine's private vault"
    )
    configure_parser.add_argument("--workspace", type=Path, required=True)
    configure_parser.add_argument(
        "--timezone", required=True, help="IANA timezone, for example America/Sao_Paulo"
    )
    configure_parser.add_argument("--language", choices=("en", "pt-BR"), default="en")

    config_parser = commands.add_parser(
        "config", help="Inspect non-path machine defaults"
    )
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    config_commands.add_parser(
        "show", help="Show configured timezone, language and local date"
    )

    schema = commands.add_parser("schema", help="Print a JSON input schema for a skill")
    schema.add_argument("kind", choices=("capture", "daily"))

    capture = commands.add_parser(
        "capture", help="Save one readable session checkpoint"
    )
    capture.add_argument(
        "--date",
        type=_date,
        help="Work date; defaults to today in the configured timezone",
    )
    capture.add_argument(
        "--input", default="-", choices=("-",), help="Read CaptureDraft JSON from stdin"
    )

    daily = commands.add_parser("daily", help="Prepare or update one daily note")
    daily_commands = daily.add_subparsers(dest="daily_command", required=True)
    prepare = daily_commands.add_parser(
        "prepare", help="Read captures and report whether composition is needed"
    )
    prepare.add_argument(
        "--date",
        type=_date,
        help="Work date; defaults to today in the configured timezone",
    )
    write = daily_commands.add_parser(
        "write", help="Validate and publish a structured daily draft"
    )
    write.add_argument("--date", type=_date, required=True)
    write.add_argument(
        "--input", default="-", choices=("-",), help="Read DailyDraft JSON from stdin"
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    machine_config_path: Path | None = None,
    now: datetime | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config_path = machine_config_path or default_config_path()
    current_time = now or datetime.now(timezone.utc)
    try:
        if args.command == "configure":
            config = configure(
                args.workspace,
                timezone=args.timezone,
                language=args.language,
                path=config_path,
            )
            _print({"status": "configured", "workspace": str(config.workspace)})
            return 0

        if args.command == "schema":
            contract = CaptureDraft if args.kind == "capture" else DailyDraft
            print(json.dumps(contract.model_json_schema(), ensure_ascii=False))
            return 0

        workspace = resolve_workspace(path=config_path)
        config = load_machine_config(config_path)
        work_date = resolve_work_date(
            config, getattr(args, "date", None), now=current_time
        )

        if args.command == "config":
            _print(
                {
                    "timezone": config.timezone,
                    "language": config.language,
                    "today": work_date.isoformat(),
                }
            )
            return 0

        if args.command == "capture":
            draft = CaptureDraft.model_validate_json(_read_input())
            saved = save_capture(
                workspace,
                work_date,
                draft,
                captured_at=current_time.astimezone(timezone.utc),
            )
            _print(
                {
                    "status": saved.status,
                    "date": work_date.isoformat(),
                    "path": saved.path,
                    "capture_id": saved.capture_id,
                }
            )
            return 0

        if args.daily_command == "prepare":
            prepared = prepare_day(config, work_date)
            _print(prepared)
            return 1 if prepared.status == "conflict" else 0

        draft = DailyDraft.model_validate_json(_read_input())
        result = write_daily(config, work_date, draft)
        _print(result)
        return 1 if result.status == "conflict" else 0
    except ValidationError as error:
        print(_validation_message(error), file=sys.stderr)
        return 1
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
