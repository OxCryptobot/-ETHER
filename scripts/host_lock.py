"""OS file lock for the 1650 writer. Released by the OS when the process dies.

A pid file alone is not a lock: Windows reuses pids and a crashed writer leaves
the file behind. msvcrt/fcntl locks vanish with the process, so a stale lock is
impossible. The pid goes to `<lock>.pid` only so `host.cmd status` can show it.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class HostLock:
    """Non-blocking exclusive lock on one file. Use as a context manager or acquire()/release()."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._fh: Optional[object] = None

    @property
    def held(self) -> bool:
        return self._fh is not None

    def acquire(self) -> bool:
        if self._fh is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        try:
            # Windows blocks reads of a locked byte, so the pid lives beside the lock.
            pid_path(self.path).write_text(str(os.getpid()) + "\n", encoding="ascii")
        except OSError:
            pass
        self._fh = fh
        return True

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        self._fh = None
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            fh.close()
        except OSError:
            pass

    def __enter__(self) -> "HostLock":
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


def is_locked(path: Path) -> bool:
    """True when another process holds the lock. Never leaves it held."""
    probe = HostLock(path)
    if probe.acquire():
        probe.release()
        return False
    return True


def pid_path(path: Path) -> Path:
    path = Path(path)
    return path.with_name(path.name + ".pid")


def lock_pid(path: Path) -> int:
    """Pid of the last holder. Only meaningful while is_locked(path) is True."""
    try:
        text = pid_path(path).read_text(encoding="ascii").strip()
        return int(text) if text else 0
    except (OSError, ValueError):
        return 0
