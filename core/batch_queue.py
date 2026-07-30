"""Batch queue helpers — shared by worker, CLI, and dashboard.

Locking and atomic writes are the Spine single-writer primitives
(core/spine/state_io.py); this module keeps only queue semantics and its
public API/messages exactly as before (D3 migration, stage 1).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from core.spine.state_io import append_jsonl, read_json, state_lock, write_json

ROOT = Path(__file__).resolve().parents[1]
QUEUE_PATH = ROOT / "memory" / "batch_queue.json"
HIST_PATH = ROOT / "memory" / "batch_queue" / "history.jsonl"
LOCK_PATH = ROOT / "memory" / "batch_queue" / ".queue.lock"


@contextmanager
def queue_lock(timeout: float = 30.0) -> Iterator[None]:
    """Exclusive lock for queue RMW. Cross-platform via O_EXCL lock file."""
    cm = state_lock(LOCK_PATH, timeout)
    try:
        cm.__enter__()
    except TimeoutError:
        # state_io's TimeoutError names the lock path; the public contract of
        # batch_queue is this exact message (callers and tests match on it).
        raise TimeoutError(f"batch queue lock timeout after {timeout}s") from None
    try:
        yield
    finally:
        # state_lock suppresses nothing, so a plain exit releases correctly.
        cm.__exit__(None, None, None)


def load_queue() -> Dict[str, Any]:
    data = read_json(QUEUE_PATH, None)
    if not isinstance(data, dict):
        return {"pending": [], "done": []}
    data.setdefault("pending", [])
    data.setdefault("done", [])
    return data


def save_queue(data: Dict[str, Any]) -> None:
    # Callers doing read-modify-write already hold queue_lock; save itself is
    # a lock-free atomic whole-file replace, exactly as before.
    write_json(QUEUE_PATH, data)


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
    append_jsonl(HIST_PATH, row)


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
