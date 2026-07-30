"""STATE — state integrity rules (P2 §1, AST-based).

Path detection is name-based heuristic (per P2): a write targets audit
state if the path expression references memory/, MEMORY, vault, ledger,
failure_graph, curriculum, runs or quiz state files. Whitelist exact
fingerprints via the baseline, not files.
"""

from __future__ import annotations

import ast

from .. import (RuleContext, RuleResult, call_name, iter_py_files, violation)

STATE_HINTS = ("memory", "MEMORY", "vault", "ledger", "failure_graph",
               "GRAPH_PATH", "STATE_PATH", "curriculum", "runs", "quiz",
               "VAULT", "LEDGER", "GRAPH", "STATE")

WRITE_NAMES = ("write_text", "write_bytes", "json.dump", "dump")

# Blessed writers: queue_lock + tmp.replace pattern (core/batch_queue.py:19-52)
DEFAULT_WRITER_ALLOWLIST = ["core/batch_queue.py", "core/state_spine.py"]

LOCK_MARKERS = ("queue_lock", '"xb"', "'xb'", ".replace(", "tmp_path",
                ".tmp", "flock", "lockfile")


def _targets_state(node: ast.Call) -> bool:
    dump = ast.dump(node)
    return any(h in dump for h in STATE_HINTS)


def _is_write_call(node: ast.Call) -> bool:
    fn = call_name(node.func)
    if fn.endswith(WRITE_NAMES):
        return True
    if fn.endswith("open") or fn == "open":
        for a in list(node.args[1:]) + [k.value for k in node.keywords
                                        if k.arg == "mode"]:
            if isinstance(a, ast.Constant) and isinstance(a.value, str) \
                    and any(m in a.value for m in ("w", "a", "+")):
                return True
    if fn.endswith(".replace"):  # atomic rename target
        return True
    return False


def check_state001(ctx: RuleContext, meta: dict) -> RuleResult:
    """STATE-001: writes targeting memory/ state outside the allowlisted
    writer modules (P-07, R3)."""
    allowed = set(meta.get("writer_allowlist", DEFAULT_WRITER_ALLOWLIST))
    res = RuleResult(rule_id="STATE-001")
    for rel in iter_py_files(ctx):
        if rel in allowed or rel.startswith("tests/"):
            continue
        tree = ctx.parse(rel)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_write_call(node) \
                    and _targets_state(node):
                res.violations.append(violation(
                    ctx, meta, rel, node.lineno,
                    f"state write ({call_name(node.func)} on memory/-rooted "
                    "path) outside the designated writer modules — use the "
                    "queue_lock + tmp.replace atomic pattern "
                    "(core/batch_queue.py:19-52)", node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_state002(ctx: RuleContext, meta: dict) -> RuleResult:
    """STATE-002: read-modify-write (load then dump same state path) without
    a lock / atomic-replace marker in the enclosing function (P-07)."""
    allowed = set(meta.get("writer_allowlist", DEFAULT_WRITER_ALLOWLIST))
    res = RuleResult(rule_id="STATE-002")
    for rel in iter_py_files(ctx):
        if rel in allowed or rel.startswith("tests/"):
            continue
        src = ctx.read(rel)
        tree = ctx.parse(rel)
        if tree is None or src is None:
            continue
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            reads = writes = False
            for node in ast.walk(fn):
                if not isinstance(node, ast.Call):
                    continue
                name = call_name(node.func)
                if name.endswith(("json.load", "load", "read_text")) \
                        and _targets_state(node):
                    reads = True
                if _is_write_call(node) and _targets_state(node):
                    writes = True
            if not (reads and writes):
                continue
            span = src.splitlines()[fn.lineno - 1:(fn.end_lineno or fn.lineno)]
            body = "\n".join(span)
            if any(m in body for m in LOCK_MARKERS) or "# audit:rotation" in body:
                continue
            res.violations.append(violation(
                ctx, meta, rel, fn.lineno,
                f"{fn.name}() reads then rewrites memory/ state with no "
                "lock and no atomic tmp.replace — torn-JSON RMW (P-07); "
                "reuse the queue_lock pattern", node=fn, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_state003(ctx: RuleContext, meta: dict) -> RuleResult:
    """STATE-003: no ledger/state writes on dashboard read paths (P-05).

    Dashboard modules are read-only views; any write call targeting
    ledger/memory paths in dashboard/ violates the collector contract.
    """
    res = RuleResult(rule_id="STATE-003")
    for rel in iter_py_files(ctx, "dashboard"):
        tree = ctx.parse(rel)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _is_write_call(node) \
                    and _targets_state(node):
                res.violations.append(violation(
                    ctx, meta, rel, node.lineno,
                    f"dashboard write-on-read ({call_name(node.func)}) — "
                    "read paths must never mutate the ledger (P-05)",
                    node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


RULES = {
    "STATE-001": check_state001,
    "STATE-002": check_state002,
    "STATE-003": check_state003,
}
