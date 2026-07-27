"""Multifile patch loop — apply unified diffs only under memory/scratch."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "memory" / "scratch"


def extract_unified_diff(text: str) -> Optional[str]:
    if not text:
        return None
    if "diff --git" in text or re.search(r"^---\s+", text, re.M):
        # trim markdown fences
        t = text.strip()
        if t.startswith("```"):
            lines = t.split("\n")[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            t = "\n".join(lines)
        return t
    return None


def _strip_ab_prefix(path: str) -> str:
    path = path.replace("\\", "/").strip().strip('"')
    if path.startswith(("a/", "b/")):
        path = path[2:]
    return path


def _diff_paths(diff: str) -> list[str]:
    """Every filesystem path a unified diff would touch.

    Includes rename/copy targets, which the previous substring check never
    looked at — `diff --git a/memory/scratch/x.py b/tools/persistent/evil.py`
    plus `rename to tools/persistent/evil.py` wrote outside scratch while
    still containing the string "memory/scratch".
    """
    paths: list[str] = []
    for line in diff.splitlines():
        if line.startswith(("--- ", "+++ ")):
            # A trailing tab may carry a timestamp or arbitrary comment:
            #   `--- a/core/pipeline.py\t(memory/scratch)`
            rest = line[4:].split("\t")[0].strip()
            if rest == "/dev/null":
                continue
            paths.append(_strip_ab_prefix(rest))
        elif line.startswith("diff --git "):
            rest = line[len("diff --git ") :].strip()
            m = re.match(r'^"?a/(.+?)"?\s+"?b/(.+?)"?$', rest)
            if m:
                paths.extend([m.group(1), m.group(2)])
            else:
                paths.extend(_strip_ab_prefix(tok) for tok in rest.split())
        elif line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
            paths.append(_strip_ab_prefix(line.split(" ", 2)[2]))
    return [p for p in paths if p]


def _safe_paths(diff: str) -> bool:
    """True only if every path the diff touches resolves inside memory/scratch.

    This used to be a substring test for "memory/scratch" anywhere on a header
    line, which any attacker-controlled trailing comment satisfied while
    `git apply` ran with cwd=ROOT against the real working tree.
    """
    paths = _diff_paths(diff)
    if not paths:
        return False  # cannot verify containment -> refuse
    scratch = SCRATCH.resolve()
    for raw in paths:
        if raw.startswith("/") or ".." in Path(raw).parts:
            return False
        try:
            target = (ROOT / raw).resolve()
        except (OSError, ValueError):
            return False
        if not target.is_relative_to(scratch):
            return False
    return True


def apply_scratch_diff(diff: str) -> Dict[str, Any]:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    if not _safe_paths(diff):
        return {"ok": False, "error": "diff paths must stay under memory/scratch"}
    # write as file and git apply --directory if needed; fallback: manual not implemented
    p = subprocess.run(
        ["git", "apply", "--whitespace=nowarn", "-"],
        input=diff,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    return {
        "ok": p.returncode == 0,
        "returncode": p.returncode,
        "stderr": (p.stderr or "")[-500:],
        "stdout": (p.stdout or "")[-500:],
    }


def run_scratch_tests() -> Dict[str, Any]:
    """Run memory/scratch/test_*.py if present."""
    tests = sorted(SCRATCH.glob("test_*.py"))
    if not tests:
        # "nothing was verified" is not a pass. `ran` lets callers tell the
        # difference; `ok` stays False so it cannot be read as evidence.
        return {"ok": False, "ran": False, "detail": "no scratch tests"}
    results = []
    for t in tests[:5]:
        p = subprocess.run(
            # sys.executable, not bare "python" — which does not exist in a
            # venv-only environment, so this raised FileNotFoundError and the
            # error was swallowed into a discarded meta dict.
            [sys.executable, str(t)],
            cwd=str(SCRATCH),
            capture_output=True,
            text=True,
            timeout=60,
        )
        results.append({"file": t.name, "ok": p.returncode == 0, "stderr": (p.stderr or "")[-200:]})
    ok = all(r["ok"] for r in results)
    return {"ok": ok, "ran": True, "results": results}


def maybe_patch_cycle(generated: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """If generated looks like a scratch-scoped diff, apply + test.

    Returns (report, code_for_sandbox).
    If not a diff, sandbox the original generated code.
    """
    # Opt-in. This is the one path where model output is written to the real
    # working tree and executed on the host, and it fires regardless of
    # ETHER_SANDBOX_BACKEND — so container isolation does not cover it. It
    # previously activated silently on any output that merely looked like a
    # diff. Enable deliberately with ETHER_PATCH_LOOP=1.
    if os.getenv("ETHER_PATCH_LOOP", "0") != "1":
        return None, generated

    diff = extract_unified_diff(generated)
    if not diff:
        return None, generated
    if not _safe_paths(diff):
        return {"ok": False, "error": "unsafe patch paths"}, generated
    applied = apply_scratch_diff(diff)
    if not applied.get("ok"):
        return applied, generated
    tested = run_scratch_tests()
    return {"apply": applied, "tests": tested, "ok": bool(tested.get("ok"))}, generated
