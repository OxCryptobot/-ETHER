"""Curriculum — failure-driven, holdout-safe, promote only on verified wins."""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
CUR_DIR = ROOT / "memory" / "curriculum"
STATE_PATH = CUR_DIR / "state.json"
MINED_PATH = CUR_DIR / "mined_tasks.json"
SCRATCH_PATH = CUR_DIR / "scratch_tier.json"
HOLDOUT_PATH = ROOT / "memory" / "quizzes" / "holdout_ids.json"
HIDDEN_IDS_PATH = ROOT / "memory" / "quizzes" / "hidden_ids.json"
PASS_PATH = ROOT / "memory" / "experience" / "pass.jsonl"
FAIL_PATH = ROOT / "memory" / "experience" / "fail.jsonl"


def curriculum_enabled() -> bool:
    return os.getenv("ETHER_CURRICULUM", "1") == "1"


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def check_task_leakage(task: Dict[str, Any]) -> List[str]:
    """Report ways a curriculum task gives away its own answer.

    Curriculum objectives used to read, literally:

        Write only Python: def is_even(n):
            return n % 2 == 0
        assert is_even(4) and not is_even(5)

    The prompt contained the implementation *and* the assertions it would be
    graded on, so the task was transcription and the "tests" were the ones
    pasted into the model's own prompt. Any holdout drawn from such a task is
    meaningless, because the model was shown it.

    Returns a list of problems; empty means the task is safe to grade.
    """
    import ast

    problems: List[str] = []
    objective = str(task.get("objective") or "")
    holdout = str(task.get("holdout_test") or "")
    norm_objective = _normalize(objective)

    # 1. The objective must not contain the holdout assertions.
    if holdout:
        for line in holdout.splitlines():
            line = line.strip()
            if not line.startswith("assert "):
                continue
            if _normalize(line) in norm_objective:
                problems.append(f"holdout assertion leaked into objective: {line[:60]}")

    # 2. The objective must not contain a working implementation.
    for block in _code_blocks(objective):
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            body = [
                stmt
                for stmt in node.body
                if not (
                    isinstance(stmt, ast.Pass)
                    or (
                        isinstance(stmt, ast.Expr)
                        and isinstance(stmt.value, ast.Constant)
                    )
                )
            ]
            if body:
                problems.append(f"objective contains an implementation of {node.name}()")

    # 3. A task with no holdout cannot be graded on unseen tests.
    if not holdout.strip():
        problems.append("no holdout_test — nothing can grade this task independently")

    # The same defect can surface via several candidate blocks.
    return list(dict.fromkeys(problems))


def _code_blocks(text: str) -> List[str]:
    """Candidate Python snippets inside an objective (fenced or bare)."""
    blocks: List[str] = []
    fence = False
    current: List[str] = []
    for line in (text or "").splitlines():
        if line.strip().startswith("```"):
            if fence:
                blocks.append("\n".join(current))
                current = []
            fence = not fence
            continue
        if fence:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    blocks.append(text or "")

    # Bare objectives like "Write only Python: def f(n):\n    return ..." do
    # not parse as-is, so also inspect the text from its first `def` onward.
    raw = text or ""
    idx = raw.find("def ")
    if idx != -1:
        tail = raw[idx:]
        blocks.append(tail)
        # Reconstruct indentation when the prose left the def mid-line.
        blocks.append("\n".join(line.rstrip() for line in tail.splitlines()))

    return [b for b in blocks if "def " in b]


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"tier": 0, "wins": 0, "losses": 0, "history": [], "synced": False}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"tier": 0, "wins": 0, "losses": 0, "history": [], "synced": False}


def _save_state(state: Dict[str, Any]) -> None:
    CUR_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _blocked_ids() -> Set[str]:
    ids: Set[str] = set()
    for path in (HOLDOUT_PATH, HIDDEN_IDS_PATH):
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            ids |= set(data.get("ids") or [])
        except Exception:
            pass
    # always block hidden_humaneval ids by prefix
    ids |= {f"he{str(i).zfill(2)}" for i in range(1, 11)}
    return ids


def _tail_jsonl(path: Path, n: int = 40) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-n:]:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    except Exception:
        return []
    return rows


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_verified_pass(row: Dict[str, Any]) -> bool:
    """Is this vault row evidence, or just an exit code?

    `record_outcome()` promotes only on `total_tests > 0 and
    verification_score >= 0.7`. sync_from_vault() used to promote on three
    consecutive pass.jsonl rows with `confidence >= 0.85` and nothing else — it
    never read total_tests, verification_score or holdout_ok — so a run that
    printed something and exited 0 could walk the curriculum up a tier past the
    guarded path.
    """
    min_conf = _float(os.getenv("ETHER_CURRICULUM_MIN_CONF", "0.85"), 0.85)
    min_score = _float(os.getenv("ETHER_CURRICULUM_MIN_VERIFICATION", "0.7"), 0.7)

    if row.get("success") is False:
        return False
    if _float(row.get("confidence")) < min_conf:
        return False
    if _int(row.get("total_tests")) <= 0:
        return False
    if _float(row.get("verification_score")) < min_score:
        return False
    # Only a False verdict disqualifies; absent/None means the task carried no
    # independent holdout (see _failure_driven_objective).
    if "holdout_ok" in row and row.get("holdout_ok") is False:
        return False
    return True


def sync_from_vault() -> Dict[str, Any]:
    """Mirror the experience vault into curriculum tier state.

    Two rules this function broke and now keeps:

    1. Tier promotion needs VERIFIED evidence (see is_verified_pass), the same
       bar `record_outcome()` applies.
    2. It must not touch `state["wins"]` / `state["losses"]`. Those belong to
       `record_outcome()`, and overwriting them on every sample_objective()
       call meant the verified 3-win streak could never accumulate: the
       guarded promotion path was effectively dead code. Sync keeps its own
       `synced_wins` / `synced_losses` counters, and only resets the shared
       ones when it actually moves the tier (the streak restarts either way).
    """
    state = _load_state()
    events: List[tuple] = []
    for r in _tail_jsonl(PASS_PATH, 40):
        events.append((r.get("timestamp") or "", True, is_verified_pass(r)))
    for r in _tail_jsonl(FAIL_PATH, 40):
        events.append((r.get("timestamp") or "", False, False))
    events.sort(key=lambda x: x[0])
    if not events:
        return state

    wins = losses = 0
    last_ok = events[-1][1]
    for _, ok, verified in reversed(events):
        if ok != last_ok:
            break
        if ok:
            if not verified:
                break
            wins += 1
        else:
            losses += 1

    promote_after = int(os.getenv("ETHER_CURRICULUM_PROMOTE_AFTER", "3"))
    demote_after = int(os.getenv("ETHER_CURRICULUM_DEMOTE_AFTER", "3"))
    tiers = load_tiers()
    tier = int(state.get("tier") or 0)
    moved = False

    if last_ok and wins >= promote_after and tier < max(0, len(tiers) - 1):
        tier = min(len(tiers) - 1, tier + 1)
        wins = 0
        moved = True
        state["last_event"] = f"synced_promoted_to_{tier}"
    elif (not last_ok) and losses >= demote_after and tier > 0:
        tier = max(0, tier - 1)
        losses = 0
        moved = True
        state["last_event"] = f"synced_demoted_to_{tier}"

    state["tier"] = tier
    state["synced_wins"] = wins if last_ok else 0
    state["synced_losses"] = losses if not last_ok else 0
    if moved:
        # Tier changed, so record_outcome's streak is spent too.
        state["wins"] = 0
        state["losses"] = 0
    else:
        state.setdefault("wins", 0)
        state.setdefault("losses", 0)
    state["synced"] = True
    _save_state(state)
    return state


def load_tiers() -> List[Dict[str, Any]]:
    path = CUR_DIR / "tiers.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    tiers = list(data.get("tiers") or [])
    if MINED_PATH.exists():
        try:
            mined = json.loads(MINED_PATH.read_text(encoding="utf-8")).get("tasks") or []
            if mined and tiers:
                extra = [
                    {"id": t.get("id"), "title": t.get("title"), "objective": t.get("objective")}
                    for t in mined[:15]
                    if t.get("objective")
                ]
                tiers[-1].setdefault("tasks", []).extend(extra)
        except Exception:
            pass
    if SCRATCH_PATH.exists() and tiers:
        try:
            sc = json.loads(SCRATCH_PATH.read_text(encoding="utf-8"))
            extra = list(sc.get("tasks") or [])
            if extra:
                tiers[-1].setdefault("tasks", []).extend(extra)
        except Exception:
            pass
    return tiers


def current_tier_index() -> int:
    state = _load_state()
    tiers = load_tiers()
    t = int(state.get("tier") or 0)
    return max(0, min(t, max(0, len(tiers) - 1)))


def _failure_driven_objective() -> Optional[Dict[str, Any]]:
    rate = float(os.getenv("ETHER_CURRICULUM_FAIL_RATE", "0.4"))
    if random.random() > rate:
        return None
    fails = _tail_jsonl(FAIL_PATH, 30)
    if not fails:
        return None
    f = random.choice(fails)
    obj = f.get("objective") or ""
    kind = f.get("fail_kind") or "runtime"
    if not obj:
        return None
    return {
        "id": f"repair_{f.get('task_id') or 'x'}",
        "tier": current_tier_index(),
        "tier_name": "failure_repair",
        "title": f"repair:{kind}",
        "objective": (
            f"Fix this previously failed task. Failure class was {kind}.\n"
            f"Write complete executable Python only with asserts.\n{obj}"
        ),
        # Repair tasks are reconstructed from a past failure and carry no
        # independent holdout; the gate falls back to self-graded signals for
        # them, which is why `holdout_ok` is reported as None rather than True.
        "holdout_test": "",
        "source": "failure_vault",
    }


def sample_objective() -> Dict[str, Any]:
    try:
        sync_from_vault()
    except Exception:
        pass

    blocked = _blocked_ids()
    driven = _failure_driven_objective()
    if driven and driven.get("id") not in blocked:
        return driven

    tiers = load_tiers()
    if not tiers:
        return {
            "id": "fallback_even",
            "tier": 0,
            "title": "fallback",
            # Describes the behaviour; does not contain the implementation or
            # the assertions it will be graded on.
            "objective": (
                "Write only Python, no markdown.\n\n"
                "Implement:\n\ndef is_even(n: int) -> bool\n\n"
                "Return True when n is an even integer and False otherwise. "
                "Zero counts as even."
            ),
            "holdout_test": (
                "assert is_even(4) is True\n"
                "assert is_even(5) is False\n"
                "assert is_even(0) is True\n"
                "print('ok')"
            ),
            "source": "fallback",
        }
    idx = current_tier_index()
    tier = tiers[idx]
    tasks = [t for t in (tier.get("tasks") or []) if (t.get("id") or "") not in blocked]

    # Enforced at the point of use, not just in tests. load_tiers() splices
    # scratch_tier.json and mined_tasks.json into the last tier at runtime, so
    # auditing the shipped tiers.json alone is not sufficient — five scratch
    # tasks were still handing the model their own implementation long after
    # tiers.json had been cleaned. A task that gives away its answer teaches
    # transcription and cannot be graded on unseen tests.
    clean = [t for t in tasks if not check_task_leakage(t)]
    if clean:
        tasks = clean

    if not tasks:
        tasks = list(tier.get("tasks") or [])
    if not tasks:
        tasks = [{"id": "empty", "title": "empty", "objective": "print(1)"}]
    task = random.choice(tasks)
    return {
        "id": task.get("id") or f"t{idx}",
        "tier": idx,
        "tier_name": tier.get("name") or f"tier_{idx}",
        "title": task.get("title") or task.get("id") or "task",
        "objective": task.get("objective") or "print(1)",
        # Assertions the generator is never shown. This is the only grading
        # signal a model cannot author for itself; see core/holdout.py.
        "holdout_test": task.get("holdout_test") or "",
        "source": "tier",
    }


def record_outcome(
    success: bool,
    task_id: str = "",
    verification_score: float = 0.0,
    total_tests: int = 0,
) -> Dict[str, Any]:
    """Promote only on verified success (tests + verification_score)."""
    state = _load_state()
    tiers = load_tiers()
    promote_after = int(os.getenv("ETHER_CURRICULUM_PROMOTE_AFTER", "3"))
    demote_after = int(os.getenv("ETHER_CURRICULUM_DEMOTE_AFTER", "3"))

    verified = success and total_tests > 0 and float(verification_score) >= 0.7

    if verified:
        state["wins"] = int(state.get("wins") or 0) + 1
        state["losses"] = 0
    elif success and not verified:
        # soft success does not advance tier
        state["soft_wins"] = int(state.get("soft_wins") or 0) + 1
    else:
        state["losses"] = int(state.get("losses") or 0) + 1
        state["wins"] = 0

    hist = list(state.get("history") or [])
    hist.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "success": success,
            "verified": verified,
            "task_id": task_id,
            "tier": state.get("tier", 0),
            "verification_score": verification_score,
            "total_tests": total_tests,
        }
    )
    state["history"] = hist[-200:]

    tier = int(state.get("tier") or 0)
    if verified and int(state.get("wins") or 0) >= promote_after and tier < max(0, len(tiers) - 1):
        state["tier"] = tier + 1
        state["wins"] = 0
        state["losses"] = 0
        state["last_event"] = f"promoted_to_{state['tier']}_verified"
    elif (not success) and int(state.get("losses") or 0) >= demote_after and tier > 0:
        state["tier"] = tier - 1
        state["wins"] = 0
        state["losses"] = 0
        state["last_event"] = f"demoted_to_{state['tier']}"

    _save_state(state)
    return state
