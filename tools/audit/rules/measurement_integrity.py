"""MEAS — measurement integrity rules (P2 §1, holdout/assertion lint)."""

from __future__ import annotations

import ast
import json
import re

from .. import (RuleContext, RuleResult, call_name, iter_py_files, violation)

ASSERT_STYLE_RE = re.compile(r"assert\b.*==\s*(True|False)\b")
LOOSE_EQ_RE = re.compile(r"assert\b[^\n]*(?<![=!<>])==(?![=])")


def check_meas001(ctx: RuleContext, meta: dict) -> RuleResult:
    """MEAS-001: holdout assertion style lint over quiz JSONs (T3, R7).

    `== True/False` is flagged hard; any `==`-style assert is flagged as
    `is`/type-style recommended — a degenerate `__eq__ -> True` solution
    grades ok=True against ==-style holdouts (verifier probe V-B).
    """
    res = RuleResult(rule_id="MEAS-001")
    qdir = ctx.path("memory/quizzes")
    if not qdir.is_dir():
        res.status = "skip"
        res.note = "memory/quizzes not found"
        return res
    for p in sorted(qdir.glob("*.json")):
        rel = p.relative_to(ctx.repo).as_posix()
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = data if isinstance(data, list) else data.get("tasks",
                data.get("quizzes", data.get("rows", [])))
        if isinstance(rows, dict):
            rows = list(rows.values())
        strict_hits = loose_hits = 0
        first_line = 0
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            blob = "\n".join(str(row.get(k, "")) for k in
                             ("holdout_test", "assertions", "tests", "test"))
            if ASSERT_STYLE_RE.search(blob):
                strict_hits += 1
            elif LOOSE_EQ_RE.search(blob):
                loose_hits += 1
        if strict_hits or loose_hits:
            res.violations.append(violation(
                ctx, meta, rel, first_line,
                f"{rel}: {strict_hits} `== True/False` and {loose_hits} "
                "loose `==`-style holdout assertions — a degenerate "
                "__eq__→True solution grades ok=True (V-B); use `is`/"
                "type()-style comparisons", text=f"quiz-style:{rel}",
                context="<holdout-corpus>"))
    res.status = "fail" if res.violations else "pass"
    return res


PER_ROW_KEYS = ("per_task", "per_sample")


def check_meas002(ctx: RuleContext, meta: dict) -> RuleResult:
    """MEAS-002: docs/results/ablation_*.json must contain per-sample rows
    (per_task/per_sample) — aggregates alone are unfalsifiable (T2, R2)."""
    res = RuleResult(rule_id="MEAS-002")
    rdir = ctx.path("docs/results")
    if not rdir.is_dir():
        res.status = "skip"
        res.note = "docs/results not found"
        return res
    for p in sorted(rdir.glob("ablation_*.json")):
        rel = p.relative_to(ctx.repo).as_posix()
        try:
            data = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError) as e:
            res.violations.append(violation(
                ctx, meta, rel, 0, f"ablation result is not valid JSON: {e}",
                text="ablation unparseable", context="<json>"))
            continue
        if isinstance(data, dict) and not any(k in data for k in PER_ROW_KEYS):
            res.violations.append(violation(
                ctx, meta, rel, 1,
                "ablation result lacks per_task[]/per_sample[] rows — "
                "aggregate-only results cannot be re-audited (T2, R2); "
                "rows need {task_id, seed, arm, passed, "
                "discordant_pair_id}", text=f"ablation:{p.name}",
                context="<ablation-schema>"))
    res.status = "fail" if res.violations else "pass"
    return res


def check_meas003(ctx: RuleContext, meta: dict) -> RuleResult:
    """MEAS-003: ban pytest.mark.parametrize arguments computed at collection
    time from I/O (load_tiers()/_all_tasks() at module scope) — parametrize
    args must be literals or lazy (T1, D-09, B5)."""
    res = RuleResult(rule_id="MEAS-003")
    for rel in iter_py_files(ctx, "tests"):
        tree = ctx.parse(rel)
        if tree is None:
            continue
        for node in tree.body:  # module scope only
            fn = None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn = node
            if fn is None:
                continue
            for dec in fn.decorator_list:
                if not (isinstance(dec, ast.Call)
                        and call_name(dec.func).endswith("parametrize")):
                    continue
                if len(dec.args) < 2:
                    continue
                arg = dec.args[1]
                # a Call at module scope = collection-time computation
                inner = arg
                if isinstance(inner, ast.Call):
                    res.violations.append(violation(
                        ctx, meta, rel, dec.lineno,
                        f"pytest.mark.parametrize args computed by "
                        f"{call_name(inner.func)}() at collection time — "
                        "collection does I/O and the test count drifts with "
                        "state files (T1/B5); use literals or "
                        "pytest_generate_tests with a cached fixture",
                        node=dec, tree=tree, context=fn.name))
    res.status = "fail" if res.violations else "pass"
    return res


def check_meas004(ctx: RuleContext, meta: dict) -> RuleResult:
    """MEAS-004: curriculum empty-tier fallback reinstates unfiltered tasks —
    AST pattern `if not tasks: tasks = list(tier.get(...))` (T6, R7)."""
    res = RuleResult(rule_id="MEAS-004")
    rel = "core/curriculum.py"
    tree = ctx.parse(rel)
    if tree is None:
        res.status = "skip"
        res.note = f"{rel} not found"
        return res
    for node in ast.walk(tree):
        if not isinstance(node, ast.If) or not node.body:
            continue
        # test: `not <name>`
        test = node.test
        if not (isinstance(test, ast.UnaryOp)
                and isinstance(test.op, ast.Not)
                and isinstance(test.operand, ast.Name)):
            continue
        var = test.operand.id
        stmt = node.body[0]
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 \
                and isinstance(stmt.targets[0], ast.Name) \
                and stmt.targets[0].id == var \
                and isinstance(stmt.value, ast.Call) \
                and call_name(stmt.value.func) == "list":
            res.violations.append(violation(
                ctx, meta, rel, node.lineno,
                f"empty-tier fallback reinstantiates unfiltered `{var}` via "
                "list(tier.get(...)) — when ALL tasks are blocked the "
                "sampler silently serves the blocked tier (T6 hole); "
                "return empty / advance to the next tier",
                node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_meas005(ctx: RuleContext, meta: dict) -> RuleResult:
    """MEAS-005: flywheel pytest gate timeout must be ≥ 600 (suite ≈ 380s —
    a 300s gate kills green runs and cries wolf, T5/B3)."""
    res = RuleResult(rule_id="MEAS-005")
    rel = "scripts/flywheel.py"
    tree = ctx.parse(rel)
    if tree is None:
        res.status = "skip"
        res.note = f"{rel} not found"
        return res
    minimum = int(ctx.budgets.get("pytest_timeout_min", 600))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg != "timeout":
                continue
            v = kw.value
            if not (isinstance(v, ast.Constant)
                    and isinstance(v.value, (int, float))):
                continue
            # is this the pytest step? look at nearby string constants
            dump = ast.dump(node)
            if "pytest" not in dump:
                continue
            if v.value < minimum:
                res.violations.append(violation(
                    ctx, meta, rel, node.lineno,
                    f"flywheel pytest gate timeout={int(v.value)}s < "
                    f"{minimum}s — the gate times out green suites and "
                    "trains everyone to ignore FAIL (T5, B3)",
                    node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


RULES = {
    "MEAS-001": check_meas001,
    "MEAS-002": check_meas002,
    "MEAS-003": check_meas003,
    "MEAS-004": check_meas004,
    "MEAS-005": check_meas005,
}
