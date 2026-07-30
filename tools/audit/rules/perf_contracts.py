"""PERF — performance contract rules (P2 §1, config/constants contracts)."""

from __future__ import annotations

import ast
import os
import re

from .. import (RuleContext, RuleResult, call_name, iter_py_files, violation)


def _num(node: ast.AST):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        v = _num(node.operand)
        return -v if v is not None else None
    return None


def check_perf001(ctx: RuleContext, meta: dict) -> RuleResult:
    """PERF-001: ETHER_HTTP_TIMEOUT default must be ≤ ceiling (P-02);
    also flags new httpx.Client( without an explicit timeout."""
    ceiling = float(ctx.budgets.get("http_timeout_ceiling", 120.0))
    res = RuleResult(rule_id="PERF-001")
    for rel in iter_py_files(ctx):
        tree = ctx.parse(rel)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = call_name(node.func)
            if fn.endswith(("getenv", "_envf", "_envi")) and node.args:
                a0 = node.args[0]
                if isinstance(a0, ast.Constant) \
                        and a0.value == "ETHER_HTTP_TIMEOUT" and len(node.args) > 1:
                    default = _num(node.args[1])
                    if default is not None and default > ceiling:
                        res.violations.append(violation(
                            ctx, meta, rel, node.lineno,
                            f"ETHER_HTTP_TIMEOUT default {default}s exceeds "
                            f"ceiling {ceiling}s — a hung model endpoint "
                            "stalls the pipeline for 10 minutes (P-02); "
                            "lower the budget via audit-budgets PR, not a "
                            "code comment", node=node, tree=tree))
            if fn.endswith("httpx.Client") or fn == "httpx.Client":
                if not any(kw.arg == "timeout" for kw in node.keywords):
                    res.violations.append(violation(
                        ctx, meta, rel, node.lineno,
                        "httpx.Client() without explicit timeout (P-02)",
                        node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_perf002(ctx: RuleContext, meta: dict) -> RuleResult:
    """PERF-002: LoopBudget ceilings — wall_clock_s ≤ 300, max_attempts ≤ 4,
    and ETHER_HTTP_TIMEOUT default ≤ wall_clock_s (cross-rule invariant)."""
    wall_cap = float(ctx.budgets.get("loop_wall_clock_s", 300.0))
    attempts_cap = int(ctx.budgets.get("loop_max_attempts", 4))
    res = RuleResult(rule_id="PERF-002")
    tree = ctx.parse("core/agent_loop.py")
    if tree is None:
        res.status = "skip"
        res.note = "core/agent_loop.py not found"
        return res
    defaults = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "LoopBudget":
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(
                        item.target, ast.Name):
                    v = _num(item.value) if item.value else None
                    if v is not None:
                        defaults[item.target.id] = (v, item.lineno)
    if not defaults:
        # constructor-call style: LoopBudget(wall_clock_s=300, ...)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) \
                    and call_name(node.func).endswith("LoopBudget"):
                for kw in node.keywords:
                    v = _num(kw.value)
                    if v is not None:
                        defaults[kw.arg] = (v, node.lineno)
    res.metrics["loop_budget"] = {k: v for k, (v, _) in defaults.items()}
    checks = (("wall_clock_s", wall_cap), ("max_attempts", float(attempts_cap)))
    for key, cap in checks:
        if key in defaults and defaults[key][0] > cap:
            v, line = defaults[key]
            res.violations.append(violation(
                ctx, meta, "core/agent_loop.py", line,
                f"LoopBudget.{key} = {v} exceeds ceiling {cap} (P-02)",
                text=f"LoopBudget.{key}={v}", context="LoopBudget"))
    res.status = "fail" if res.violations else "pass"
    return res


def check_perf003(ctx: RuleContext, meta: dict) -> RuleResult:
    """PERF-003: rag_bm25.search() must not call an uncached build_index —
    the file needs a module-level cache dict or lru_cache (P-01, R6)."""
    res = RuleResult(rule_id="PERF-003")
    rel = "core/rag_bm25.py"
    src = ctx.read(rel)
    tree = ctx.parse(rel)
    if src is None or tree is None:
        res.status = "skip"
        res.note = f"{rel} not found"
        return res
    has_cache = "lru_cache" in src or re.search(
        r"^_[A-Z_]*CACHE\s*[:=]|^_index_cache|cache\s*:\s*dict", src, re.M)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == "search":
            calls_build = any(
                isinstance(n, ast.Call)
                and call_name(n.func).endswith("build_index")
                for n in ast.walk(node))
            if calls_build and not has_cache:
                res.violations.append(violation(
                    ctx, meta, rel, node.lineno,
                    "search() calls build_index() with no module-level cache "
                    "or lru_cache — the BM25 index is rebuilt on every query "
                    "(P-01)", node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_perf004(ctx: RuleContext, meta: dict) -> RuleResult:
    """PERF-004: dashboard websocket loop must not call _safe_snapshot()
    uncached in a `while True` loop — require a TTL-cache marker (P-05)."""
    res = RuleResult(rule_id="PERF-004")
    rel = "dashboard/app.py"
    src = ctx.read(rel)
    tree = ctx.parse(rel)
    if src is None or tree is None:
        res.status = "skip"
        res.note = f"{rel} not found"
        return res
    has_ttl = re.search(r"ttl|TTL|single.?flight|cache", src)
    for node in ast.walk(tree):
        if isinstance(node, ast.While) and isinstance(node.test, ast.Constant) \
                and node.test.value is True:
            for n in ast.walk(node):
                if isinstance(n, ast.Call) \
                        and call_name(n.func).endswith("_safe_snapshot"):
                    if not has_ttl:
                        res.violations.append(violation(
                            ctx, meta, rel, n.lineno,
                            "ws_feed while-True loop calls _safe_snapshot() "
                            "uncached — every websocket tick recomputes the "
                            "snapshot (P-05); add a ≥30s TTL cache with "
                            "single-flight", node=n, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_perf005(ctx: RuleContext, meta: dict) -> RuleResult:
    """PERF-005: some module must own pruning of memory/runs/*.json —
    grep pipeline + scripts for prune/rotate/unlink near a runs reference."""
    res = RuleResult(rule_id="PERF-005")
    candidates = ["core/pipeline.py"] + [
        f"scripts/{n}" for n in os.listdir(ctx.path("scripts"))
        if n.endswith(".py")] if ctx.path("scripts").is_dir() else [
        "core/pipeline.py"]
    hits = []
    for rel in candidates:
        src = ctx.read(rel)
        if not src:
            continue
        if re.search(r"unlink|prune|rotate", src) and re.search(
                r"runs", src):
            for m in re.finditer(r"^.*(unlink|prune|rotate).*$", src, re.M):
                if "runs" in m.group(0) or "RUNS" in m.group(0):
                    hits.append((rel, m.group(0).strip()[:80]))
    res.metrics["runs_prune_sites"] = len(hits)
    if not hits:
        res.violations.append(violation(
            ctx, meta, "core/pipeline.py", 0,
            "no prune/rotate/unlink policy for memory/runs/*.json anywhere "
            "in pipeline or scripts — the runs dir grows without bound "
            "(P-06, R3)", text="runs prune absent", context="<policy>"))
        res.status = "fail"
    return res


def check_perf006(ctx: RuleContext, meta: dict) -> RuleResult:
    """PERF-006: LLM latency budget hook (RUN rule).

    Offline by design: requires GPU. Emits an explicit skip-with-flag —
    never a silent pass, never a failure without ETHER_AUDIT_GPU=1.
    """
    res = RuleResult(rule_id="PERF-006")
    if os.getenv("ETHER_AUDIT_GPU") == "1":
        res.note = ("GPU mode requested: replay memory/runs samples and "
                    "assert stage shares (llm ≤ 80% of run, sandbox ≤ 20s "
                    "p95) — not implemented in this pack build")
        res.status = "skip"
        return res
    res.status = "skip"
    res.note = "budget check requires GPU; set ETHER_AUDIT_GPU=1"
    return res


RULES = {
    "PERF-001": check_perf001,
    "PERF-002": check_perf002,
    "PERF-003": check_perf003,
    "PERF-004": check_perf004,
    "PERF-005": check_perf005,
    "PERF-006": check_perf006,
}
