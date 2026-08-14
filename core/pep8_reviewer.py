"""ETHER PEP 8 reviewer — embedded style gate for faster, consistent quality checks.

Uses ruff when available (project already has test_ruff_gate), falls back to
compile + light manual heuristics. Produces a structured report dict suitable
for scoreboards, host jobs, and GEMS critique intake.

CLI:
  python -m scripts.pep8_review core/ scripts/
  python -m scripts.pep8_review --json artifacts/pep8_report.json core/
"""
from __future__ import annotations

import json
import py_compile
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]

# Align with Black-friendly PEP 8 (same spirit as the pep8-python-reviewer skill).
DEFAULT_RUFF_ARGS = [
    "check",
    "--select",
    "E,W,F,I,B,UP",
    "--ignore",
    "E203,W503",
    "--line-length",
    "88",
]

SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    "dist",
    "build",
}


@dataclass
class Finding:
    path: str
    line: int
    code: str
    message: str
    severity: str  # critical | warning | suggestion


@dataclass
class Pep8Report:
    scope: List[str]
    tool: str
    ok: bool
    n_critical: int = 0
    n_warning: int = 0
    n_suggestion: int = 0
    findings: List[Finding] = field(default_factory=list)
    positive: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    assessment: str = "unknown"
    raw_tool_output: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def _iter_py_files(paths: Sequence[Path]) -> List[Path]:
    out: List[Path] = []
    for p in paths:
        p = p.resolve()
        if p.is_file() and p.suffix == ".py":
            out.append(p)
            continue
        if not p.is_dir():
            continue
        for f in sorted(p.rglob("*.py")):
            if any(part in SKIP_PARTS for part in f.parts):
                continue
            out.append(f)
    # de-dupe preserve order
    seen = set()
    uniq: List[Path] = []
    for f in out:
        key = str(f)
        if key not in seen:
            seen.add(key)
            uniq.append(f)
    return uniq


def _severity_for_code(code: str) -> str:
    c = (code or "").upper()
    if c.startswith("F") or c in {"E9", "E999"}:
        return "critical"
    if c.startswith("E") or c.startswith("B"):
        return "warning"
    return "suggestion"


def _run_ruff(files: List[Path]) -> tuple[List[Finding], str, bool]:
    """Return findings, raw output, and whether ruff ran successfully."""
    cmd = [sys.executable, "-m", "ruff", *DEFAULT_RUFF_ARGS, "--output-format", "json"]
    cmd.extend(str(f) for f in files)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except FileNotFoundError:
        return [], "ruff not installed", False
    except subprocess.TimeoutExpired:
        return [], "ruff timeout", False
    except Exception as e:
        return [], f"ruff error: {type(e).__name__}: {e}", False

    raw = (proc.stdout or "") + (proc.stderr or "")
    findings: List[Finding] = []
    # ruff json is a list of objects when output-format=json
    try:
        data = json.loads(proc.stdout or "[]")
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                code = str(item.get("code") or item.get("rule") or "")
                loc = item.get("location") or {}
                findings.append(
                    Finding(
                        path=str(item.get("filename") or ""),
                        line=int(loc.get("row") or item.get("line") or 0),
                        code=code,
                        message=str(item.get("message") or ""),
                        severity=_severity_for_code(code),
                    )
                )
    except json.JSONDecodeError:
        # plain text fallback parse: path:line:col: CODE message
        for line in (proc.stdout or "").splitlines():
            m = re.match(
                r"^(.+?):(\d+):\d+:\s*([A-Z]\d+)\s+(.+)$",
                line.strip(),
            )
            if not m:
                continue
            findings.append(
                Finding(
                    path=m.group(1),
                    line=int(m.group(2)),
                    code=m.group(3),
                    message=m.group(4),
                    severity=_severity_for_code(m.group(3)),
                )
            )
    return findings, raw[-4000:], True


def _compile_check(files: List[Path]) -> List[Finding]:
    findings: List[Finding] = []
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            findings.append(
                Finding(
                    path=str(f),
                    line=0,
                    code="E999",
                    message=str(e)[:300],
                    severity="critical",
                )
            )
    return findings


def review_paths(
    paths: Sequence[str | Path],
    *,
    max_findings: int = 80,
) -> Pep8Report:
    """Review one or more files/dirs. Prefer ruff; always compile-check."""
    path_objs = [Path(p) for p in paths]
    files = _iter_py_files(path_objs)
    scope = [str(p) for p in path_objs]
    if not files:
        return Pep8Report(
            scope=scope,
            tool="none",
            ok=True,
            assessment="Compliant",
            positive=["No Python files in scope"],
            next_actions=[],
        )

    findings, raw, ruff_ok = _run_ruff(files)
    tool = "ruff" if ruff_ok else "compile"
    if not ruff_ok:
        findings.extend(_compile_check(files))

    # Cap noise
    findings = findings[:max_findings]
    n_crit = sum(1 for f in findings if f.severity == "critical")
    n_warn = sum(1 for f in findings if f.severity == "warning")
    n_sug = sum(1 for f in findings if f.severity == "suggestion")

    if n_crit:
        assessment = "Significant issues" if n_crit > 5 else "Needs work"
    elif n_warn > 10:
        assessment = "Needs work"
    elif n_warn or n_sug:
        assessment = "Mostly compliant"
    else:
        assessment = "Compliant"

    positive: List[str] = []
    if n_crit == 0:
        positive.append("No critical syntax/undefined-name issues")
    if ruff_ok:
        positive.append(f"Ruff ran on {len(files)} file(s)")
    if n_warn + n_crit == 0:
        positive.append("Clean automated style pass")

    next_actions: List[str] = []
    if n_crit:
        next_actions.append("Fix critical findings first (syntax / F-codes)")
    if n_warn:
        next_actions.append("Clear E/W warnings in touched modules before merge")
    if not next_actions:
        next_actions.append("Keep ruff gate green on new commits")

    return Pep8Report(
        scope=scope,
        tool=tool,
        ok=(n_crit == 0),
        n_critical=n_crit,
        n_warning=n_warn,
        n_suggestion=n_sug,
        findings=findings,
        positive=positive,
        next_actions=next_actions,
        assessment=assessment,
        raw_tool_output=raw,
    )


def format_report_md(report: Pep8Report) -> str:
    lines = [
        "## PEP 8 Review Summary",
        "",
        f"- **Scope**: {', '.join(report.scope) or '(empty)'}",
        f"- **Automated tools**: {report.tool}",
        f"- **Overall assessment**: {report.assessment}",
        f"- **Counts**: critical={report.n_critical} warning={report.n_warning} "
        f"suggestion={report.n_suggestion}",
        "",
        "## Findings",
        "",
    ]
    for sev, title in (
        ("critical", "### Critical (must fix)"),
        ("warning", "### Warnings (should fix)"),
        ("suggestion", "### Suggestions (nice to have)"),
    ):
        bucket = [f for f in report.findings if f.severity == sev]
        lines.append(title)
        if not bucket:
            lines.append("- (none)")
        else:
            for f in bucket[:30]:
                lines.append(
                    f"- `{f.path}:{f.line}` — {f.code} {f.message}"
                )
        lines.append("")
    lines.append("## Positive Observations")
    for p in report.positive or ["(none)"]:
        lines.append(f"- {p}")
    lines.append("")
    lines.append("## Recommended Next Actions")
    for i, a in enumerate(report.next_actions or ["(none)"], 1):
        lines.append(f"{i}. {a}")
    return "\n".join(lines) + "\n"
