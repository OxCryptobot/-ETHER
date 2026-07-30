"""ETHER continuous-audit engine (P2) — stdlib only.

Layout:
  audit_runner.py      CLI: dispatch rules, emit JSONL + audit_health.json
  fingerprint.py       P3-canonical fingerprinting + classification
  rules/               rule implementations (ARCH/QUAL/SEC/PERF/STATE/MEAS)
  regression_tracker.py  P3: classify vs baseline, trends, suggestions
  alerts.py            CI annotation / Slack / email renderers + digest dedup
  fp_feedback.py       false-positive CLI (# audit-fp, denylist, FP rate)
  ingest.py            validate/normalize incoming violations JSONL
  findings_baseline.json  grandfathered fingerprints (seeded at 208993a)

No third-party imports anywhere under tools/audit/.
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from .fingerprint import Violation, fingerprint as make_fp

PACK_ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = PACK_ROOT / "findings_baseline.json"
DEFAULT_RULES_CONFIG = PACK_ROOT.parent.parent / "config" / "audit-rules.yaml"

SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules", "__pycache__",
             ".mypy_cache", ".ruff_cache", ".pytest_cache", "dist", "build"}

# Suppression markers:
#   # audit:allow RULE-ID <reason>   (same or previous line)
#   # audit-fp: RULE-ID <reason>     (false positive, recorded by fp_feedback)
ALLOW_RE = re.compile(r"#\s*audit:allow\s+([A-Z]+-\d+)")
FP_RE = re.compile(r"#\s*audit-fp:\s*([A-Z]+-\d+)\s*(.*)")


@dataclass
class RuleContext:
    """Everything a rule check needs. `repo` is the target repo root."""

    repo: Path
    budgets: dict = field(default_factory=dict)
    baseline: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)  # this rule's yaml entry
    fast: bool = False

    def path(self, rel: str) -> Path:
        return self.repo / rel

    def read(self, rel: str) -> Optional[str]:
        p = self.path(rel)
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def parse(self, rel: str) -> Optional[ast.Module]:
        src = self.read(rel)
        if src is None:
            return None
        try:
            return ast.parse(src, filename=rel)
        except SyntaxError:
            return None

    def git_tracked(self) -> list:
        """Tracked files via git plumbing; empty list if unavailable."""
        import subprocess

        try:
            out = subprocess.run(
                ["git", "ls-files"], cwd=str(self.repo),
                capture_output=True, text=True, timeout=30)
            if out.returncode != 0:
                return []
            return [ln for ln in out.stdout.splitlines() if ln.strip()]
        except (OSError, subprocess.SubprocessError):
            return []


@dataclass
class RuleResult:
    rule_id: str
    status: str = "pass"           # pass | fail | skip
    note: str = ""
    violations: list = field(default_factory=list)  # list[Violation]
    metrics: dict = field(default_factory=dict)     # ratchet values


def iter_py_files(ctx: RuleContext, subdir: str = "") -> list:
    """Repo-relative paths of all .py files (skipping venvs/caches)."""
    root = ctx.path(subdir) if subdir else ctx.repo
    out = []
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if fn.endswith(".py"):
                p = Path(dirpath) / fn
                out.append(p.relative_to(ctx.repo).as_posix())
    return sorted(out)


def module_stem(rel: str) -> str:
    """Module path without extension — dirs + filename stem (P3 §2 step 3)."""
    return rel[:-3] if rel.endswith(".py") else rel


def qualname(tree: ast.AST, target: ast.AST) -> str:
    """Enclosing qualname chain for a node, e.g. 'Pipeline.run'."""
    chain: list = []
    found = False

    def visit(node, names):
        nonlocal found
        if node is target:
            names and chain.extend(names)
            found = True
            return
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                visit(child, names + [child.name])
            else:
                visit(child, names)
            if found:
                return

    visit(tree, [])
    return ".".join(chain)


def violation(ctx: RuleContext, rule: dict, rel: str, line: int,
              message: str, node: Optional[ast.AST] = None,
              text: Optional[str] = None, context: str = "",
              tree: Optional[ast.AST] = None) -> Violation:
    """Build a Violation with a P3-canonical fingerprint attached."""
    if tree is not None and node is not None and not context:
        context = qualname(tree, node)
    fp = make_fp(rule["id"], node=node, text=text,
                 context=context, module=module_stem(rel))
    return Violation(
        rule_id=rule["id"],
        category=rule["category"],
        severity=rule["severity"],
        file=rel,
        line=line,
        message=message,
        fingerprint=fp["fp"],
        pattern_hash=fp["pattern_hash"],
        context=fp["context"],
        module=fp["module"],
        finding_ids=list(rule.get("finding_ids", [])),
    )


def suppression_lines(src_lines: list, line: int) -> str:
    """Comment text of the violation line and the previous line."""
    out = []
    for ln in (line - 1, line - 2):
        if 0 <= ln < len(src_lines):
            out.append(src_lines[ln])
    return "\n".join(out)


def is_suppressed(src_lines: list, line: int, rule_id: str) -> tuple:
    """(allowed, fp_reason) from # audit:allow / # audit-fp markers."""
    block = suppression_lines(src_lines, line)
    if rule_id in ALLOW_RE.findall(block):
        return True, ""
    m = FP_RE.search(block)
    if m and m.group(1) == rule_id:
        return True, m.group(2).strip()
    return False, ""


def call_name(func: ast.AST) -> str:
    """Dotted name of a call target: os.getenv / self._run_local / Path.write_text."""
    parts = []
    node = func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))
