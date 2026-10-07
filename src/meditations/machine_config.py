"""Per-machine vault, timezone and note-language settings."""

import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, field_validator

from meditations.files import atomic_write, workspace_lock


class MachineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[2]
    workspace: Path
    timezone: str
    language: Literal["en", "pt-BR"]

    @field_validator("workspace")
    @classmethod
    def absolute_workspace(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("The private workspace path must be absolute")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Use a valid IANA timezone") from error
        return value


def default_config_path(platform: str | None = None) -> Path:
    selected = platform or sys.platform
    if selected == "darwin":
        root = Path.home() / "Library/Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / "meditations/config.json"


def _selected_path(path: Path | None) -> Path:
    selected = (path or default_config_path()).expanduser().absolute()
    if selected.is_symlink():
        raise ValueError("Refusing a symbolic-link machine configuration")
    return selected


def _validate_workspace(path: Path) -> Path:
    workspace = path.expanduser().resolve()
    if not workspace.is_dir():
        raise ValueError("Create the private vault directory before configuring it")
    for parent in (workspace, *workspace.parents):
        if (parent / "pyproject.toml").is_file() and (
            parent / "src/meditations"
        ).is_dir():
            raise ValueError("Choose a private workspace outside the software checkout")
    return workspace


def load_machine_config(path: Path | None = None) -> MachineConfig:
    selected = _selected_path(path)
    if not selected.exists():
        raise ValueError(
            "No default vault configured. Run meditations configure "
            "--workspace /path/to/vault --timezone Region/City."
        )
    try:
        config = MachineConfig.model_validate_json(selected.read_bytes())
    except (ValueError, OSError) as error:
        raise ValueError(
            "Machine configuration is invalid or from an older Meditations version; "
            "configure the private vault again. Existing notes and records were "
            "not changed."
        ) from error
    if _validate_workspace(config.workspace) != config.workspace:
        raise ValueError("Configured vault path changed; configure the vault again")
    return config


def configure(
    workspace: Path,
    *,
    timezone: str,
    language: Literal["en", "pt-BR"],
    path: Path | None = None,
) -> MachineConfig:
    selected = _selected_path(path)
    validated_workspace = _validate_workspace(workspace)
    config = MachineConfig(
        schema_version=2,
        workspace=validated_workspace,
        timezone=timezone,
        language=language,
    )
    with workspace_lock(selected):
        if selected.is_symlink():
            raise ValueError("Refusing a symbolic-link machine configuration")
        original = selected.read_bytes() if selected.exists() else None
        atomic_write(
            selected,
            (config.model_dump_json(indent=2) + "\n").encode(),
            expected=original,
        )
    return config


def resolve_workspace(override: Path | None = None, path: Path | None = None) -> Path:
    if override is not None:
        return _validate_workspace(override)
    return load_machine_config(path).workspace


def resolve_work_date(
    config: MachineConfig, override: date | None, *, now: datetime
) -> date:
    if override is not None:
        return override
    if now.tzinfo is None:
        raise ValueError("Current time must include a timezone")
    return now.astimezone(ZoneInfo(config.timezone)).date()
