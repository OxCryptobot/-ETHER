"""Phase B — repo oracle: apply edits in a staging tree, score with project pytest.

The product scoreboard for the self-improving hypothesis. Repository tests are
the oracle: they cannot be leaked into a generation prompt the way holdout
strings can, because they are *executed*, not shown.

Safety:
- Never writes the live working tree unless explicitly opted in (default: temp staging).
- Blocks path segments: .git, .venv, memory, node_modules, secrets-ish names.
- Timeout-bounded pytest subprocess.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]

BLOCKED_SEGMENTS = {
    ".git",
    ".venv",
    "venv",
    "memory",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ether_staging",
}
BLOCKED_NAMES = {"credentials.json", ".env", "id_rsa", "id_ed25519"}

FILE_MARKER = re.compile(r"(?m)^#\s*file:\s*(\S+)\s*$")


def parse_file_markers(text: str) -> Dict[str, str]:
    """Split model output with `# file: path` markers into path → body.

    Paths are normalized to forward slashes and must be relative.
    """
    text = text or ""
    matches = list(FILE_MARKER.finditer(text))
    if not matches:
        return {}
    out: Dict[str, str] = {}
    for i, m in enumerate(matches):
        rel = m.group(1).strip().replace("\\", "/")
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip("\n")
        if body.startswith("\n"):
            body = body[1:]
        out[rel] = body
    return out


def _is_blocked(rel: str) -> Optional[str]:
    rel = rel.replace("\\", "/")
    if rel.startswith("/") or re.match(r"^[A-Za-z]:/", rel):
        return "absolute path refused"
    if ".." in Path(rel).parts:
        return "parent traversal refused"
    parts_lower = {p.lower() for p in Path(rel).parts}
    for seg in BLOCKED_SEGMENTS:
        if seg.lower() in parts_lower:
            return f"blocked segment: {seg}"
    if Path(rel).name.lower() in BLOCKED_NAMES:
        return f"blocked name: {Path(rel).name}"
    return None


def validate_file_map(file_map: Mapping[str, str]) -> Dict[str, Any]:
    """Fail closed on empty or blocked paths."""
    if not file_map:
        return {"ok": False, "error": "empty file_map"}
    for rel in file_map:
        reason = _is_blocked(rel)
        if reason:
            return {"ok": False, "error": f"{rel}: {reason}"}
    return {"ok": True, "n": len(file_map)}


def seed_staging(
    source_root: Path,
    *,
    include_globs: Sequence[str] = ("**/*",),
) -> Path:
    """Copy a fixture/package tree into a fresh temp staging dir."""
    source_root = source_root.resolve()
    staging = Path(tempfile.mkdtemp(prefix="ether_repo_oracle_"))
    for pattern in include_globs:
        for src in source_root.glob(pattern):
            if not src.is_file():
                continue
            rel = src.relative_to(source_root)
            if any(p in BLOCKED_SEGMENTS for p in rel.parts):
                continue
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    return staging


def apply_file_map(
    staging_root: Path,
    file_map: Mapping[str, str],
) -> Dict[str, Any]:
    """Write path→content into staging. Creates parents. Never touches live ROOT."""
    gate = validate_file_map(file_map)
    if not gate["ok"]:
        return gate
    written: List[str] = []
    for rel, body in file_map.items():
        dest = (staging_root / rel).resolve()
        try:
            dest.relative_to(staging_root.resolve())
        except ValueError:
            return {"ok": False, "error": f"path escapes staging: {rel}"}
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        written.append(rel.replace("\\", "/"))
    return {"ok": True, "written": written, "staging": str(staging_root)}


def run_project_pytest(
    cwd: Path,
    *,
    test_args: Optional[Sequence[str]] = None,
    timeout: int = 60,
    python: Optional[str] = None,
) -> Dict[str, Any]:
    """Run pytest inside cwd. Returns ok/score from process exit + summary."""
    py = python or sys.executable
    args = [py, "-m", "pytest", "-q", "--tb=line"]
    if test_args:
        args.extend(test_args)
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=max(5, int(timeout)),
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "score": 0.0,
            "returncode": -1,
            "error": f"pytest timeout after {timeout}s",
            "stdout": "",
            "stderr": "",
        }
    except Exception as e:
        return {
            "ok": False,
            "score": 0.0,
            "returncode": -1,
            "error": str(e)[:300],
            "stdout": "",
            "stderr": "",
        }

    stdout = (proc.stdout or "")[-4000:]
    stderr = (proc.stderr or "")[-2000:]
    ok = proc.returncode == 0
    # crude pass ratio from pytest -q summary line e.g. "3 passed" / "1 failed, 2 passed"
    score = 1.0 if ok else _parse_pytest_score(stdout + "\n" + stderr)
    return {
        "ok": ok,
        "score": float(score),
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def _parse_pytest_score(text: str) -> float:
    passed = failed = 0
    m_pass = re.search(r"(\d+)\s+passed", text)
    m_fail = re.search(r"(\d+)\s+failed", text)
    if m_pass:
        passed = int(m_pass.group(1))
    if m_fail:
        failed = int(m_fail.group(1))
    total = passed + failed
    if total <= 0:
        return 0.0
    return round(passed / total, 3)


def score_repo_edit(
    file_map: Mapping[str, str],
    *,
    fixture_root: Optional[Path] = None,
    test_args: Optional[Sequence[str]] = None,
    timeout: int = 60,
    cleanup: bool = True,
) -> Dict[str, Any]:
    """Full Phase B path: seed staging → apply map → project pytest → score.

    If fixture_root is None, staging starts empty and only file_map files exist
    (self-contained multi-file packages). Prefer a fixture with real tests.
    """
    gate = validate_file_map(file_map)
    if not gate["ok"]:
        return {"ok": False, "score": 0.0, "error": gate.get("error"), "stages": [gate]}

    staging: Optional[Path] = None
    stages: List[Dict[str, Any]] = []
    try:
        if fixture_root is not None:
            staging = seed_staging(Path(fixture_root))
            stages.append({"stage": "seed", "ok": True, "staging": str(staging)})
        else:
            staging = Path(tempfile.mkdtemp(prefix="ether_repo_oracle_"))
            stages.append({"stage": "seed", "ok": True, "staging": str(staging), "empty": True})

        applied = apply_file_map(staging, file_map)
        stages.append({"stage": "apply", **applied})
        if not applied.get("ok"):
            return {"ok": False, "score": 0.0, "error": applied.get("error"), "stages": stages}

        result = run_project_pytest(
            staging, test_args=test_args, timeout=timeout
        )
        stages.append({"stage": "pytest", **{k: result[k] for k in ("ok", "score", "returncode")}})
        return {
            "ok": bool(result.get("ok")),
            "score": float(result.get("score") or 0.0),
            "returncode": result.get("returncode"),
            "stdout": result.get("stdout", "")[-2000:],
            "stderr": result.get("stderr", "")[-1000:],
            "written": applied.get("written"),
            "stages": stages,
            "oracle": "project_pytest",
        }
    finally:
        if cleanup and staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def score_from_marked_code(
    code: str,
    *,
    fixture_root: Optional[Path] = None,
    test_args: Optional[Sequence[str]] = None,
    timeout: int = 60,
) -> Dict[str, Any]:
    """Parse `# file:` markers then score_repo_edit."""
    file_map = parse_file_markers(code)
    if not file_map:
        return {
            "ok": False,
            "score": 0.0,
            "error": "no # file: markers found",
            "oracle": "project_pytest",
        }
    return score_repo_edit(
        file_map,
        fixture_root=fixture_root,
        test_args=test_args,
        timeout=timeout,
    )
