"""L1 state single-writer: O_EXCL lockfile + tmp-file atomic replace (D3).

Every read-modify-write on a memory/ state file goes through rmw() or
append_jsonl(); one-shot whole-file writes use write_json() (atomic, lock-free
— per-file single-writer is guaranteed by the caller owning the filename).
"""

from __future__ import annotations

import errno
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, Optional

LOCK_TIMEOUT_S = 30.0
LOCK_STALE_S = 30.0


def _lock_held_error(exc: BaseException) -> bool:
    """True when the OS reports the lock path is already owned.

    Unix: FileExistsError from O_EXCL.
    Windows: often PermissionError (WinError 5 / errno 13) while another
    process still holds the lock file open — treating only FileExistsError
    drops updates under concurrent rmw (test_rmw_concurrent_no_lost_updates).
    """
    if isinstance(exc, FileExistsError):
        return True
    if isinstance(exc, PermissionError):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in (
        errno.EEXIST,
        errno.EACCES,
        errno.EPERM,
    ):
        return True
    return False


@contextmanager
def state_lock(lock_path: Path, timeout: float = LOCK_TIMEOUT_S) -> Iterator[None]:
    """Exclusive cross-platform lock via O_EXCL lockfile; stale recovery after timeout."""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    fd: Optional[int] = None
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            break
        except Exception as exc:
            if not _lock_held_error(exc):
                raise
            if time.time() - start > timeout:
                # Stale lock: holder died without releasing. Older than the
                # timeout means no live writer could still legitimately hold it.
                try:
                    age = time.time() - lock_path.stat().st_mtime
                    if age > timeout:
                        try:
                            lock_path.unlink(missing_ok=True)
                        except PermissionError:
                            # Windows: previous holder may still be closing.
                            time.sleep(0.05)
                        continue
                # why: a vanished/unreadable lockfile must not mask the timeout.
                except Exception:
                    pass
                raise TimeoutError(f"state lock timeout after {timeout}s: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            if fd is not None:
                os.close(fd)
        # why: release is best-effort; the unlink below is the real release.
        except Exception:
            pass
        # Windows: brief retry if AV or delayed handle release blocks unlink.
        for _ in range(10):
            try:
                lock_path.unlink(missing_ok=True)
                break
            except PermissionError:
                time.sleep(0.02)
            except Exception:
                break


def read_json(path: Path, default: Any) -> Any:
    """JSON read with default on missing/corrupt — never raises."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        # why: missing/corrupt state must read as the caller's default, not
        # crash the loop — the writer side repairs it on the next write.
        return default


def write_json(path: Path, data: Any) -> None:
    """Atomic whole-file write: tmp sibling + os.replace, fsync before replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2, default=str))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def rmw(
    path: Path,
    mutator: Callable[[Any], Any],
    default: Any,
    lock_path: Optional[Path] = None,
) -> Any:
    """Read-modify-write under state_lock + write_json. Returns the new value.
    lock_path defaults to path.with_suffix(path.suffix + '.lock')."""
    path = Path(path)
    if lock_path is None:
        lock_path = path.with_suffix(path.suffix + ".lock")
    with state_lock(lock_path):
        value = mutator(read_json(path, default))
        write_json(path, value)
        return value


def append_jsonl(path: Path, record: Dict[str, Any], lock_path: Optional[Path] = None) -> None:
    """Append one JSON line under state_lock."""
    path = Path(path)
    if lock_path is None:
        lock_path = path.with_suffix(path.suffix + ".lock")
    with state_lock(lock_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
