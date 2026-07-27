"""Batch queue helpers — shared by worker, CLI, and dashboard."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "memory" / "batch_queue.json"
HIST_PATH = ROOT / "memory" / "batch_queue" / "history.jsonl"
LOCK_PATH = ROOT / "memory" / "batch_queue" / ".queue.lock"


@contextmanager
def queue_lock(timeout: float = 30.0) -> Iterator[None]:
    """Exclusive lock for queue RMW. Cross-platform via O_EXCL lock file."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    start = time.time()
    fd: Optional[int] = None
    while True:
        try:
            fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            break
        except FileExistsError:
            if time.time() - start > timeout:
                # stale lock recovery
                try:
                    age = time.time() - LOCK_PATH.stat().st_mtime
                    if age > timeout:
                        LOCK_PATH.unlink(missing_ok=True)
                        continue
                except Exception:
                    pass
                raise TimeoutError(f"batch queue lock timeout after {timeout}s")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            if fd is not None:
                os.close(fd)
        except Exception:
            pass
        try:
            LOCK_PATH.unlink(missing_ok=True)
        except Exception:
            pass


def load_queue() -> Dict[str, Any]:
    if not QUEUE_PATH.exists():
        return {"pending": [], "done": []}
    try:
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"pending": [], "done": []}
        data.setdefault("pending", [])
        data.setdefault("done", [])
        return data
    except Exception:
        return {"pending": [], "done": []}


def save_queue(data: Dict[str, Any]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = QUEUE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(QUEUE_PATH)


def coerce_int(value: Any, default: int) -> int:
    """Best-effort int, never raises.

    The queue is JSON on disk and is written by several producers, so a
    malformed `priority` (null, "high", "10.5") is reachable. The sort key used
    a bare `int(...)`, which raised TypeError/ValueError out of enqueue(); the
    only caller that matters (`autonomy.enqueue_failure`) swallows exceptions,
    so one bad row silently stopped every failure requeue forever.
    """
    if isinstance(value, bool) or value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def sort_key(item: Any) -> Tuple[int, int]:
    """(priority, id) ordering that tolerates malformed rows."""
    if not isinstance(item, dict):
        return (100, 0)
    return (coerce_int(item.get("priority"), 100), coerce_int(item.get("id"), 0))


def next_id(data: Dict[str, Any]) -> int:
    ids: List[int] = []
    for bucket in ("pending", "done"):
        for item in data.get(bucket) or []:
            if not isinstance(item, dict):
                continue
            try:
                ids.append(int(item.get("id", 0)))
            except Exception:
                continue
    return (max(ids) + 1) if ids else 1


def enqueue(
    *,
    kind: str = "pipeline",
    title: str,
    objective: str = "",
    command: Optional[List[str]] = None,
    priority: int = 100,
) -> Dict[str, Any]:
    """Append one item to pending. Returns the item."""
    with queue_lock():
        data = load_queue()
        item: Dict[str, Any] = {
            "id": next_id(data),
            "kind": kind,
            "title": title,
            "priority": coerce_int(priority, 100),
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        }
        if kind == "pipeline":
            item["objective"] = objective
        elif kind == "command":
            item["command"] = list(command or [])
        else:
            raise ValueError(f"unsupported kind: {kind}")
        data.setdefault("pending", []).append(item)
        data["pending"] = sorted(data["pending"], key=sort_key)
        save_queue(data)
        return item


def status() -> Dict[str, Any]:
    data = load_queue()
    pending = data.get("pending") or []
    done = data.get("done") or []
    ok_n = sum(1 for d in done if (d.get("result") or {}).get("ok"))
    return {
        "pending": len(pending),
        "done": len(done),
        "done_ok": ok_n,
        "done_fail": len(done) - ok_n,
        "next": (pending[0].get("title") if pending else None),
        "pending_titles": [p.get("title") for p in pending[:10]],
    }


def append_history(row: Dict[str, Any]) -> None:
    HIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with HIST_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def mutate(fn) -> Any:
    """Run fn(data) under lock; fn must return (data, result)."""
    with queue_lock():
        data = load_queue()
        data, result = fn(data)
        save_queue(data)
        return result


def seed_smoke(force: bool = False) -> Dict[str, Any]:
    """Seed a small verified smoke set if queue is empty (or force)."""

    def _inner(data: Dict[str, Any]):
        if data.get("pending") and not force:
            return data, {"ok": True, "seeded": 0, "message": "pending not empty — skip"}
        smokes = [
            {
                "kind": "pipeline",
                "title": "smoke is_even",
                "objective": (
                    "Write only Python:\n"
                    "def is_even(n):\n"
                    "    return n % 2 == 0\n"
                    "assert is_even(4) is True\n"
                    "assert is_even(5) is False\n"
                    "print('ok')"
                ),
                "priority": 10,
            },
            {
                "kind": "pipeline",
                "title": "smoke reverse",
                "objective": (
                    "Write only Python:\n"
                    "def reverse_string(s):\n"
                    "    return s[::-1]\n"
                    "assert reverse_string('ether') == 'rehte'\n"
                    "print('ok')"
                ),
                "priority": 10,
            },
            {
                "kind": "pipeline",
                "title": "smoke fib",
                "objective": (
                    "Write only Python:\n"
                    "def fib(n):\n"
                    "    a, b = 0, 1\n"
                    "    for _ in range(n):\n"
                    "        a, b = b, a + b\n"
                    "    return a\n"
                    "assert fib(10) == 55\n"
                    "print('ok')"
                ),
                "priority": 10,
            },
            {
                "kind": "pipeline",
                "title": "smoke clamp",
                "objective": (
                    "Write only Python:\n"
                    "def clamp(x, lo, hi):\n"
                    "    return max(lo, min(hi, x))\n"
                    "assert clamp(5, 0, 10) == 5\n"
                    "assert clamp(-1, 0, 10) == 0\n"
                    "assert clamp(99, 0, 10) == 10\n"
                    "print('ok')"
                ),
                "priority": 20,
            },
        ]
        seeded = 0
        for s in smokes:
            item = {
                "id": next_id(data),
                "kind": s["kind"],
                "title": s["title"],
                "priority": coerce_int(s.get("priority"), 100),
                "objective": s.get("objective", ""),
                "enqueued_at": datetime.now(timezone.utc).isoformat(),
            }
            data.setdefault("pending", []).append(item)
            seeded += 1
        data["pending"] = sorted(data["pending"], key=sort_key)
        return data, {"ok": True, "seeded": seeded}

    return mutate(_inner)
