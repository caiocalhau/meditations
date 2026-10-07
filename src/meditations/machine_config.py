"""Per-machine defaults, separate from synchronized workspace configuration."""

import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from meditations.config import load_workspace, validate_workspace_path
from meditations.files import atomic_write, workspace_lock


class MachineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    workspace: Path
    runtime_approval: Path | None = None

    @field_validator("workspace")
    @classmethod
    def absolute_workspace(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("The default workspace must be an absolute path")
        return value

    @field_validator("runtime_approval")
    @classmethod
    def absolute_approval(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("The runtime approval must be an absolute path")
        return value


def default_config_path(platform: str) -> Path:
    if platform == "darwin":
        root = Path.home() / "Library/Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return root / "meditations/config.json"


def _configuration_path(path: Path | None) -> Path:
    selected = (path or default_config_path(sys.platform)).expanduser().absolute()
    validate_workspace_path(selected.parent)
    if selected.is_symlink():
        raise ValueError("Refusing a symbolic-link machine configuration")
    return selected


def configure_workspace(
    workspace: Path | None,
    path: Path | None = None,
    *,
    runtime_approval: Path | None = None,
) -> Path:
    """Validate an initialized vault before atomically saving its absolute path."""
    selected = _configuration_path(path)
    with workspace_lock(selected):
        if selected.is_symlink():
            raise ValueError("Refusing a symbolic-link machine configuration")
        original = selected.read_bytes() if selected.exists() else None
        previous: MachineConfig | None = None
        if original is not None:
            try:
                previous = MachineConfig.model_validate_json(original)
            except ValueError as error:
                if workspace is None:
                    raise ValueError(
                        "Invalid machine configuration; configure --workspace again"
                    ) from error
        if workspace is None:
            if previous is None:
                raise ValueError(
                    "Configure --workspace before saving a runtime approval path"
                )
            workspace = previous.workspace
        workspace = validate_workspace_path(workspace)
        load_workspace(workspace)
        approval = (
            runtime_approval.expanduser().absolute()
            if runtime_approval is not None
            else previous.runtime_approval
            if previous is not None
            else None
        )
        config = MachineConfig(
            schema_version=1, workspace=workspace, runtime_approval=approval
        )
        atomic_write(
            selected,
            (config.model_dump_json(indent=2) + "\n").encode(),
            expected=original,
        )
    return workspace


def resolve_runtime_approval(
    override: Path | None, path: Path | None = None
) -> Path | None:
    """Resolve a location only; the live provider still validates the record."""
    if override is not None:
        return override.expanduser().absolute()
    selected = _configuration_path(path)
    if not selected.exists():
        return None
    try:
        config = MachineConfig.model_validate_json(selected.read_bytes())
    except ValueError as error:
        raise ValueError(
            "Invalid machine configuration; repair config.json "
            "or pass --runtime-approval"
        ) from error
    return config.runtime_approval


def resolve_workspace(override: Path | None, path: Path | None = None) -> Path:
    """Prefer explicit selection; never silently fall back to the current folder."""
    if override is not None:
        return validate_workspace_path(override)
    selected = _configuration_path(path)
    if not selected.exists():
        raise ValueError(
            "No default workspace configured. Run meditations configure --workspace "
            "/path/to/vault or pass --workspace."
        )
    try:
        config = MachineConfig.model_validate_json(selected.read_bytes())
    except ValueError as error:
        raise ValueError(
            "Invalid machine configuration; configure a workspace again "
            "or pass --workspace"
        ) from error
    workspace = validate_workspace_path(config.workspace)
    try:
        load_workspace(workspace)
    except (OSError, ValueError) as error:
        raise ValueError(
            "Configured workspace is unavailable or invalid; run meditations configure "
            "--workspace /path/to/vault or pass --workspace."
        ) from error
    return workspace
