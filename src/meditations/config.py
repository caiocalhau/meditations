from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from meditations.files import atomic_write, workspace_directory, workspace_lock


class PresentationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    links: Literal["markdown"] = "markdown"
    expansion: Literal["details"] = "details"


class WorkspaceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    workspace_id: UUID
    timezone: str
    language: Literal["en"] = "en"
    presentation: PresentationSettings = Field(default_factory=PresentationSettings)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Use a valid IANA timezone") from error
        return value


def validate_workspace_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    for candidate in (resolved, *resolved.parents):
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "src/meditations"
        ).is_dir():
            raise ValueError("Choose a private workspace outside the software checkout")
    return resolved


def load_workspace(path: Path) -> WorkspaceConfig:
    path = validate_workspace_path(path)
    if (path / "workspace.json").is_symlink():
        raise ValueError("Refusing a symbolic-link workspace configuration")
    try:
        return WorkspaceConfig.model_validate_json(
            (path / "workspace.json").read_bytes()
        )
    except ValueError as error:
        raise ValueError(
            "Invalid workspace configuration; existing file preserved"
        ) from error


def initialize_workspace(path: Path, timezone: str) -> WorkspaceConfig:
    path = validate_workspace_path(path)
    config = WorkspaceConfig(schema_version=1, workspace_id=uuid4(), timezone=timezone)
    config_path = path / "workspace.json"
    directories = (
        "profile",
        "engineering/daily",
        "engineering/reviews",
        "engineering/concepts",
        "records",
    )
    with workspace_lock(path):
        if config_path.is_symlink():
            raise ValueError("Refusing a symbolic-link workspace configuration")
        if config_path.exists():
            config = load_workspace(path)
            if config.timezone != timezone:
                raise ValueError("Workspace already uses a different timezone")
        for relative in directories:
            target = workspace_directory(path, relative)
            for part in (target, *target.parents):
                if part == path.parent:
                    break
                if part.is_symlink() or (part.exists() and not part.is_dir()):
                    raise ValueError(
                        "Workspace layout contains a link or a file obstruction"
                    )
        for relative in directories:
            (path / relative).mkdir(parents=True, exist_ok=True)
        if not config_path.exists():
            atomic_write(
                config_path, (config.model_dump_json(indent=2) + "\n").encode()
            )
    return config
