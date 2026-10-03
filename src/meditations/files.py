import fcntl
import hashlib
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def workspace_lock(path: Path) -> Generator[None, None, None]:
    directory = Path(tempfile.gettempdir()) / f"meditations-locks-{os.getuid()}"
    directory.mkdir(mode=0o700, exist_ok=True)
    info = directory.lstat()
    if directory.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("Unsafe local lock directory")
    key = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
    descriptor = os.open(directory / key, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def atomic_write(path: Path, content: bytes, expected: bytes | None = None) -> None:
    if path.is_symlink():
        raise ValueError("Refusing to replace a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, filename = tempfile.mkstemp(prefix=".meditations-", dir=path.parent)
    temporary = Path(filename)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        current = path.read_bytes() if path.exists() else None
        if path.is_symlink() or current != expected:
            raise ValueError(
                "File changed while processing; existing content preserved"
            )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def workspace_directory(workspace: Path, relative: str) -> Path:
    target = workspace / relative
    if not target.resolve().is_relative_to(workspace.resolve()):
        raise ValueError("Workspace directory points outside the selected workspace")
    return target
