"""Experience vault — PASS few-shot + FAIL-kind repair bias."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
VAULT_DIR = ROOT / "memory" / "experience"
PASS_PATH = VAULT_DIR / "pass.jsonl"
FAIL_PATH = VAULT_DIR / "fail.jsonl"


def experience_enabled() -> bool:
    return os.getenv("ETHER_EXPERIENCE", "1") == "1"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]{3,}", (text or "").lower()))


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(1, len(ta | tb))


# Stderr signatures that mean the environment broke, not the generated code.
_INFRA_SIGNATURES = (
    "cannot connect to the docker daemon",
    "failed to connect to the docker api",
    "error while fetching server api version",
    "connection refused",
    "cannot connect to ollama",
    "ollama down",
    "max retries exceeded",
    "name or service not known",
    "no such host",
    "read timed out",
)

# fail_kind values that name a pipeline STAGE rather than a defect class.
# `_fail()` passes the stage name, so "code"/"plan"/"exception" were being
# stored as if they were failure taxonomies.
_INFRA_FAIL_KINDS = ("dependency", "plan", "exception")

_MAX_VAULT_ROWS = 2000


def _is_infra_failure(stderr: str, fail_kind: str) -> bool:
    if (fail_kind or "").strip().lower() in _INFRA_FAIL_KINDS:
        return True
    low = (stderr or "").lower()
    return any(sig in low for sig in _INFRA_SIGNATURES)


def _row_fingerprint(objective: str, code: str) -> str:
    import hashlib

    payload = f"{(objective or '').strip()}\x00{(code or '').strip()}"
    return hashlib.sha256(payload.encode("utf-8", "replace")).hexdigest()[:16]


def _fingerprint_seen(path: Path, fingerprint: str) -> bool:
    if not path.exists():
        return False
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if fingerprint and fingerprint in line:
                return True
    except Exception:
        return False
    return False


def _rotate(path: Path, max_rows: int = _MAX_VAULT_ROWS) -> None:
    """Keep the vault bounded; it was appended to forever and fully re-read."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_rows:
            path.write_text("\n".join(lines[-max_rows:]) + "\n", encoding="utf-8")
    except Exception:
        pass


def record(
    *,
    objective: str,
    code: str,
    success: bool,
    confidence: float = 0.0,
    strategy: str = "",
    stderr: str = "",
    fail_kind: str = "",
    task_id: str = "",
    verification_score: float = 0.0,
    total_tests: int = 0,
    # Verdict from assertions the generator never saw. Recorded so the
    # curriculum's promotion gate can require independent evidence rather than
    # inferring competence from self-graded confidence alone.
    holdout_ok: Optional[bool] = None,
    # Passed so the writer can refuse an artifact carrying its own holdout.
    holdout_test: str = "",
    skip_curriculum: bool = False,
) -> None:
    if not experience_enabled():
        return
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "objective": (objective or "")[:500],
        "code": (code or "")[:4000],
        "success": success,
        "confidence": confidence,
        "verification_score": verification_score,
        "total_tests": total_tests,
        "holdout_ok": holdout_ok,
        "strategy": strategy,
        "stderr": (stderr or "")[:800],
        "fail_kind": fail_kind,
        "task_id": task_id,
    }
    # Never store an artifact carrying its own holdout assertions.
    #
    # `retrieve()` replays this vault into later prompts, so one leaked-era row
    # re-contaminates every future run that retrieves it. save_success_pattern
    # was guarded on its write path; this store was not, and it is the SIXTH
    # distinct channel by which a holdout has reached a prompt — after the
    # curriculum, bench prompts, hidden_quiz's private grader, BM25 retrieval
    # over scripts/, and the few-shot pattern store.
    #
    # Observed live: 7 rows in pass.jsonl and 1 in fail.jsonl carried holdout
    # assertions, which leaked into 3 ether samples mid-ablation.
    if holdout_test:
        try:
            from core.prompt_guard import find_leaks

            if find_leaks(f"{objective}\n{code}", holdout_test):
                return
        except Exception:
            # A guard that cannot run must not silently permit the write.
            return

    # Infrastructure outages are not code failures. Recording "ollama down" or
    # a dead Docker daemon as a FAIL taught the model to avoid a pattern that
    # never existed, and seeded the failure graph with permanent infra nodes:
    # every one of the 26 rows in fail.jsonl was an outage, not a defect.
    if not success and _is_infra_failure(stderr, fail_kind):
        return

    path = PASS_PATH if success else FAIL_PATH

    # Deduplicate on (objective, code). The vault is replayed into prompts as
    # few-shot examples, so an objective run repeatedly filled the block with
    # three copies of one trivial function — 13 of 22 pass rows were the same
    # `write hello` stub, crowding out anything informative.
    fingerprint = _row_fingerprint(objective, code)
    if _fingerprint_seen(path, fingerprint):
        return
    row["fingerprint"] = fingerprint

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    _rotate(path)

    if not success and stderr:
        try:
            from core.failure_graph import observe

            observe(stderr, repaired_ok=False)
        except Exception:
            pass

    # Prefer flywheel/smart_cycle to call curriculum with full scores.
    # Only auto-update curriculum here when explicitly allowed.
    if (
        not skip_curriculum
        and os.getenv("ETHER_CURRICULUM", "1") == "1"
        and os.getenv("ETHER_EXPERIENCE_CURRICULUM", "0") == "1"
    ):
        try:
            from core.curriculum import record_outcome

            record_outcome(
                success,
                task_id=task_id or "",
                verification_score=verification_score,
                total_tests=total_tests,
            )
        except Exception:
            pass


def _read_jsonl(path: Path, limit: int = 500) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        return []
    return rows


def retrieve(objective: str, k: int = 3, fail_kind: Optional[str] = None) -> Dict[str, Any]:
    if not experience_enabled():
        return {"block": "", "n_pass": 0, "n_fail": 0}

    passes = _read_jsonl(PASS_PATH)
    fails = _read_jsonl(FAIL_PATH)
    scored_p = sorted(
        ((_overlap(objective, r.get("objective", "")), r) for r in passes),
        key=lambda x: x[0],
        reverse=True,
    )

    def fail_score(r: Dict[str, Any]) -> float:
        base = _overlap(objective, r.get("objective", ""))
        if fail_kind and (r.get("fail_kind") or "") == fail_kind:
            base += 0.25
        return base

    scored_f = sorted(((fail_score(r), r) for r in fails), key=lambda x: x[0], reverse=True)
    top_p = [r for s, r in scored_p[:k] if s > 0.05]
    top_f = [r for s, r in scored_f[:3] if s > 0.05]

    parts: List[str] = []
    for i, r in enumerate(top_p, 1):
        parts.append(
            f"### Success example {i} (conf={r.get('confidence')})\n"
            f"Objective: {r.get('objective','')}\nCode:\n{r.get('code','')}\n"
        )
    for i, r in enumerate(top_f, 1):
        parts.append(
            f"### Related failure {i} (avoid this pattern)\n"
            f"Objective: {r.get('objective','')}\n"
            f"Fail kind: {r.get('fail_kind') or 'runtime'}\n"
            f"Stderr: {(r.get('stderr') or '')[:220]}\n"
        )
    if fail_kind:
        try:
            from core.failure_graph import repair_hint

            parts.append(f"### Repair directive for {fail_kind}\n{repair_hint(fail_kind)}\n")
        except Exception:
            pass

    return {"block": "\n".join(parts)[:3800], "n_pass": len(top_p), "n_fail": len(top_f)}
