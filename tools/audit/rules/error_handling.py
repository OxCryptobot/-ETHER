"""QUAL — code-quality gate rules (P2 §1, AST-based)."""

from __future__ import annotations

import ast

from .. import (RuleContext, RuleResult, call_name, iter_py_files, violation)

SUBPROCESS_CALLS = ("subprocess.run", "subprocess.call", "subprocess.Popen",
                    "subprocess.check_output", "subprocess.check_call", "run")


def _except_sites(ctx: RuleContext, meta: dict, bare_only: bool,
                  exclude_files: set) -> list:
    out = []
    for rel in iter_py_files(ctx):
        if rel in exclude_files:
            continue
        tree = ctx.parse(rel)
        src = ctx.read(rel)
        if tree is None or src is None:
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            is_bare = node.type is None
            if bare_only and not is_bare:
                continue
            if not bare_only:
                # QUAL-002: swallow-without-why — body is pass / return None
                # and no `# why` comment on the except line or previous line.
                body = node.body
                swallow = (len(body) == 1 and (
                    isinstance(body[0], ast.Pass) or
                    (isinstance(body[0], ast.Return) and
                     (body[0].value is None or
                      (isinstance(body[0].value, ast.Constant)
                       and body[0].value.value is None)))))
                if not swallow:
                    continue
                comment = "\n".join(lines[max(0, node.lineno - 2):node.lineno])
                if "# why" in comment:
                    continue
            out.append((rel, node, tree))
    return out


def check_qual001(ctx: RuleContext, meta: dict) -> RuleResult:
    """QUAL-001: bare `except:` (F8, A-3)."""
    res = RuleResult(rule_id="QUAL-001")
    for rel, node, tree in _except_sites(ctx, meta, bare_only=True,
                                         exclude_files=set()):
        res.violations.append(violation(
            ctx, meta, rel, node.lineno,
            "bare `except:` swallows everything including KeyboardInterrupt — "
            "name the exception type", node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_qual002(ctx: RuleContext, meta: dict) -> RuleResult:
    """QUAL-002: except:pass / return None without a `# why` justification.

    Pre-seeded exclusion: core/assert_audit.py — the except patterns there
    are AST *detection subjects*, not real handlers (F8).
    """
    res = RuleResult(rule_id="QUAL-002")
    excluded = set(meta.get("exclude_files", ["core/assert_audit.py"]))
    for rel, node, tree in _except_sites(ctx, meta, bare_only=False,
                                         exclude_files=excluded):
        res.violations.append(violation(
            ctx, meta, rel, node.lineno,
            "exception swallowed (pass/return None) without a `# why:` "
            "justification — silent no-op seam (A-3); emit a degraded "
            "breadcrumb or justify", node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_qual003(ctx: RuleContext, meta: dict) -> RuleResult:
    """QUAL-003: subprocess.* without timeout= (F8)."""
    res = RuleResult(rule_id="QUAL-003")
    for rel in iter_py_files(ctx):
        tree = ctx.parse(rel)
        if tree is None:
            continue
        # collect local import aliases: `from subprocess import run` -> run
        sub_names = set(SUBPROCESS_CALLS)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                for a in node.names:
                    sub_names.add(a.name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = call_name(node.func)
            if fn not in sub_names:
                continue
            if any(kw.arg == "timeout" for kw in node.keywords):
                continue
            res.violations.append(violation(
                ctx, meta, rel, node.lineno,
                f"{fn}() without timeout= — a hung child blocks the loop "
                "forever", node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_qual004(ctx: RuleContext, meta: dict) -> RuleResult:
    """QUAL-004: sys.path.insert/append outside designated bootstrap shims."""
    allowed = set(meta.get("allow_sys_path",
                           ["tests/conftest.py", "tools/_lib/bootstrap.py"]))
    res = RuleResult(rule_id="QUAL-004")
    for rel in iter_py_files(ctx):
        if rel in allowed:
            continue
        tree = ctx.parse(rel)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and call_name(node.func) in (
                    "sys.path.insert", "sys.path.append"):
                res.violations.append(violation(
                    ctx, meta, rel, node.lineno,
                    "sys.path mutation — import-order fragility (F6); use a "
                    "package install or the designated bootstrap shim",
                    node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_qual005(ctx: RuleContext, meta: dict) -> RuleResult:
    """QUAL-005: os.getenv("ETHER_*") outside the allowlisted config modules.

    One violation per file (per-var ledger in the message); a count
    ratchet blocks growth of the total site count (R4 migration meter).
    """
    allowed = set(meta.get("allow_env_modules",
                           ["core/config.py", "core/dotenv.py"]))
    res = RuleResult(rule_id="QUAL-005")
    total = 0
    for rel in iter_py_files(ctx):
        if rel in allowed:
            continue
        tree = ctx.parse(rel)
        if tree is None:
            continue
        vars_found = []
        first_node = None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = call_name(node.func)
            if fn not in ("os.getenv", "os.environ.get", "getenv"):
                continue
            if not node.args:
                continue
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str) \
                    and a0.value.startswith("ETHER_"):
                vars_found.append(a0.value)
                if first_node is None:
                    first_node = node
        # os.environ["ETHER_*"] subscript reads
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript) and \
                    call_name(node.value) == "os.environ":
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str) \
                        and sl.value.startswith("ETHER_"):
                    vars_found.append(sl.value)
                    if first_node is None:
                        first_node = node
        if vars_found:
            total += len(vars_found)
            uniq = sorted(set(vars_found))
            res.violations.append(violation(
                ctx, meta, rel, first_node.lineno,
                f"{len(vars_found)} ETHER_* env read(s) outside the config "
                f"registry ({', '.join(uniq[:4])}"
                f"{'…' if len(uniq) > 4 else ''}) — route through the "
                "env registry (A-5/F6)", node=first_node, tree=tree))
    budget = ctx.budgets.get("env_getenv_sites")
    res.metrics["env_getenv_sites"] = {"budget": budget, "actual": total}
    if budget is not None and total > int(budget):
        res.violations.append(violation(
            ctx, meta, "(repo)", 0,
            f"ETHER_* getenv site count grew to {total}, over budget "
            f"{budget} — the ratchet only moves down",
            text=f"env_getenv_sites:{total}", context="<ratchet>"))
    res.status = "fail" if res.violations else "pass"
    return res


def _is_fence_stripper(fn: ast.FunctionDef) -> bool:
    """Function stripping ``` markdown fences via startswith."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and call_name(node.func).endswith(
                "startswith") and node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str) \
                    and a0.value.strip().startswith("```"):
                return True
    return False


def check_qual006(ctx: RuleContext, meta: dict) -> RuleResult:
    """QUAL-006: duplicated naive fence-stripper pattern (F9, F10).

    Sentinel is duplication-count-based: >1 distinct implementation of the
    ``` + startswith strip across the repo flags every non-canonical site.
    Dies when count == 1 (canonical: core/agent_loop.py).
    """
    canonical = meta.get("canonical", "core/agent_loop.py")
    res = RuleResult(rule_id="QUAL-006")
    sites = []
    for rel in iter_py_files(ctx):
        tree = ctx.parse(rel)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and _is_fence_stripper(node):
                sites.append((rel, node, tree))
    res.metrics["fence_stripper_sites"] = len(sites)
    if len(sites) > 1:
        for rel, node, tree in sites:
            if rel == canonical:
                continue
            res.violations.append(violation(
                ctx, meta, rel, node.lineno,
                f"duplicate naive ``` fence-stripper '{node.name}' — "
                f"{len(sites)} implementations repo-wide; route to the "
                f"canonical helper in {canonical} (F9)",
                node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


RULES = {
    "QUAL-001": check_qual001,
    "QUAL-002": check_qual002,
    "QUAL-003": check_qual003,
    "QUAL-004": check_qual004,
    "QUAL-005": check_qual005,
    "QUAL-006": check_qual006,
}
