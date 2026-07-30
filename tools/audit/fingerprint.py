"""Canonical fingerprinting + reappearance classification (P3 §2).

P3 owns the fingerprint algorithm so reappearance semantics are stable
across rule-engine changes. Fingerprints must survive renaming,
reformatting and bot edit churn — therefore they never contain
file paths or line numbers.

Canonical fingerprint = rule_id + normalized-AST pattern hash only.
Context (qualname chain) and module (path stem) are stored alongside
but excluded from the hash so that pattern *migration* is visible.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Reappearance classes (P3 §2)
TRUE_REGRESSION = "true_regression"
PATTERN_MIGRATION = "pattern_migration"
NEW_VIOLATION = "new_violation"
STILL_OPEN = "still_open"
SUPPRESSED = "suppressed"

BASE_SCORE = {"blocker": 100.0, "high": 50.0, "med": 20.0, "low": 5.0, "warn": 20.0}
MULTIPLIER = {TRUE_REGRESSION: 1.5, PATTERN_MIGRATION: 1.25, NEW_VIOLATION: 1.0}


class _Normalizer(ast.NodeTransformer):
    """Strip identifiers and literals, keep attribute structure.

    - identifiers -> "ID" (Name, arg, FunctionDef.name, ClassDef.name, ...)
    - attribute roots and attribute *names* are kept: `os.getenv` vs
      `os.environ` is semantically load-bearing (P3 §2).
    - literals -> "LIT:<type>"; values stripped.
    - statement order preserved; comments/docstrings dropped by parse.
    """

    def visit_Name(self, node: ast.Name) -> ast.Name:
        return ast.copy_location(ast.Name(id="ID", ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.arg:
        node.arg = "ID"
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        node.name = "ID"
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        node.name = "ID"
        self.generic_visit(node)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        kind = type(node.value).__name__
        return ast.copy_location(ast.Constant(value=f"LIT:{kind}"), node)


def normalize_node(node: ast.AST) -> str:
    """Normalized AST dump of a subtree (identifiers/literals stripped)."""
    import copy

    clone = copy.deepcopy(node)
    clone = _Normalizer().visit(clone)
    ast.fix_missing_locations(clone)
    return ast.dump(clone)


_TOKEN_RE = re.compile(r"[A-Za-z_]\w*|\d+(?:\.\d+)?")


def normalize_text(text: str) -> str:
    """Regex-level normalization for CFG/text rules (no AST available).

    Keeps attribute structure (dotted names), strips identifiers that
    stand alone and all numeric literals.
    """

    def _sub(m: re.Match) -> str:
        tok = m.group(0)
        if tok[0].isdigit():
            return "LIT"
        return "ID"

    return _TOKEN_RE.sub(_sub, text)


def _sha(text: str, n: int = 12) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:n]


def pattern_hash(rule_id: str, node: Optional[ast.AST] = None,
                 text: Optional[str] = None) -> str:
    """Pattern hash: sha1[:12] of the normalized pattern."""
    if node is not None:
        return _sha(normalize_node(node))
    if text is not None:
        return _sha(normalize_text(text))
    return _sha(rule_id + "|unit")


def fingerprint(rule_id: str, node: Optional[ast.AST] = None,
                text: Optional[str] = None,
                context: str = "", module: str = "") -> dict:
    """Canonical fingerprint record (P3 §2 step 4).

    fp = sha1(rule_id | pattern_hash) — context/module excluded so a
    moved violation keeps the same fp and is classifiable as migration.
    """
    ph = pattern_hash(rule_id, node=node, text=text)
    return {
        "fp": _sha(f"{rule_id}|{ph}", 16),
        "pattern_hash": ph,
        "context": context,
        "module": module,
    }


@dataclass
class Violation:
    """One emitted audit finding. Schema per P2 §4 / task contract."""

    rule_id: str
    category: str
    severity: str
    file: str
    line: int
    message: str
    fingerprint: str
    finding_ids: list = field(default_factory=list)
    pattern_hash: str = ""
    context: str = ""
    module: str = ""
    baseline: bool = False
    suppressed: bool = False

    def to_row(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "fingerprint": self.fingerprint,
            "finding_ids": list(self.finding_ids),
            "pattern_hash": self.pattern_hash,
            "context": self.context,
            "module": self.module,
            "baseline": self.baseline,
            "suppressed": self.suppressed,
        }

    @classmethod
    def from_row(cls, row: dict) -> "Violation":
        return cls(
            rule_id=row["rule_id"],
            category=row.get("category", ""),
            severity=row.get("severity", "warn"),
            file=row.get("file", ""),
            line=int(row.get("line", 0) or 0),
            message=row.get("message", ""),
            fingerprint=row.get("fingerprint", ""),
            finding_ids=list(row.get("finding_ids", [])),
            pattern_hash=row.get("pattern_hash", ""),
            context=row.get("context", ""),
            module=row.get("module", ""),
            baseline=bool(row.get("baseline", False)),
            suppressed=bool(row.get("suppressed", False)),
        )


def site_key(rec: dict) -> tuple:
    """Identity of a violation *site*: pattern + where it lives."""
    return (rec.get("rule_id", ""), rec.get("pattern_hash", ""),
            rec.get("module", ""), rec.get("context", ""))


def classify(record: dict, baseline: dict, fixed_commit_known: bool = True) -> str:
    """Classify a new run record against the baseline (P3 §2).

    record: dict with rule_id, pattern_hash, module, context.
    baseline: findings_baseline.json content.
    """
    ph = record.get("pattern_hash", "")
    rid = record.get("rule_id", "")
    deny = {(d.get("rule_id"), d.get("pattern_hash"))
            for d in baseline.get("fp_denylist", [])}
    if (rid, ph) in deny or ("*", ph) in deny:
        return SUPPRESSED

    same_pattern = [v for v in baseline.get("violations", [])
                    if v.get("rule_id") == rid and v.get("pattern_hash") == ph]
    if not same_pattern:
        return NEW_VIOLATION

    same_site = [v for v in same_pattern
                 if v.get("module") == record.get("module")
                 and v.get("context") == record.get("context")]
    if same_site:
        statuses = {v.get("status", "open") for v in same_site}
        if statuses & {"fixed", "verified"} and fixed_commit_known:
            return TRUE_REGRESSION
        return STILL_OPEN

    # same rule + same pattern, different module or context
    statuses = {v.get("status", "open") for v in same_pattern}
    if statuses & {"fixed", "verified"}:
        return TRUE_REGRESSION if same_site else PATTERN_MIGRATION
    return PATTERN_MIGRATION


def score_event(event_class: str, severity: str, rule_in_review: bool = False) -> float:
    """Regression score (P3 §3)."""
    base = BASE_SCORE.get(severity, 20.0)
    mult = MULTIPLIER.get(event_class, 1.0)
    score = base * mult
    if rule_in_review:
        score *= 0.5
    return score
