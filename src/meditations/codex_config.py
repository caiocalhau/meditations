"""Resolve the global model setting without loading Codex integrations or policy."""

import os
import sys
from pathlib import Path

MAX_CONFIG_BYTES = 1024 * 1024


def resolve_model(override: str | None) -> str:
    if override is not None:
        if not override.strip():
            raise ValueError("Use a nonempty --model value")
        return override
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    path = codex_home.expanduser() / "config.toml"
    if not path.is_file():
        raise ValueError(
            "No global Codex model is configured; set model in config.toml "
            "or use --model"
        )
    with path.open("rb") as stream:
        content = stream.read(MAX_CONFIG_BYTES + 1)
    if len(content) > MAX_CONFIG_BYTES:
        raise ValueError("Global Codex configuration exceeds the limit; use --model")
    if sys.version_info >= (3, 11):
        import tomllib as toml
    else:
        try:
            import tomli as toml
        except ImportError as error:
            raise ValueError(
                "Reading global Codex configuration on Python 3.10 requires tomli; "
                "use --model until the runtime dependency is available"
            ) from error
    try:
        data = toml.loads(content.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise ValueError(
            "Invalid global Codex configuration; repair config.toml or use --model"
        ) from error
    model = data.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError(
            "No valid global Codex model is configured; set model in config.toml "
            "or use --model"
        )
    return model
