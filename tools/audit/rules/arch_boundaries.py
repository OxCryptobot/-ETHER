"""ARCH — architectural boundary rules (P2 §1, AST-based)."""

from __future__ import annotations

import ast

from .. import (RuleContext, RuleResult, Violation, call_name, iter_py_files,
                module_stem, qualname, violation)


def _imports_of(tree: ast.AST):
    """Yield (node, dotted_module_root, lineno) for every Import/ImportFrom."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node, alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                yield node, node.module, node.lineno


def check_arch001(ctx: RuleContext, meta: dict) -> RuleResult:
    """ARCH-001: core/ must not import gems.* (A-4, R1).

    One violation per (file, enclosing function) site so the baseline
    tracks sites, not individual import lines.
    """
    res = RuleResult(rule_id="ARCH-001")
    for rel in iter_py_files(ctx, "core"):
        tree = ctx.parse(rel)
        if tree is None:
            continue
        sites: dict = {}
        for node, mod, line in _imports_of(tree):
            if mod == "gems" or mod.startswith("gems."):
                ctx_name = qualname(tree, node) or "<module>"
                sites.setdefault(ctx_name, []).append((node, mod, line))
        for ctx_name, hits in sorted(sites.items()):
            first = hits[0]
            mods = sorted({m for _, m, _ in hits})
            res.violations.append(violation(
                ctx, meta, rel, first[2],
                f"core/ imports gems.* ({len(hits)} imports in {ctx_name}: "
                f"{', '.join(mods[:3])}{'…' if len(mods) > 3 else ''}) — "
                "layering inversion; route through the composition root",
                node=first[0], context=ctx_name))
    res.status = "fail" if res.violations else "pass"
    return res


LEGAL_GEM_CORE_IMPORTS = ("core.schemas", "core.config", "core.pipeline_hooks",
                          "core.learning")


def check_arch002(ctx: RuleContext, meta: dict) -> RuleResult:
    """ARCH-002: gems/ must not import core.pipeline (higher layers).

    Leaf contracts (core.schemas/config/pipeline_hooks/learning) are legal.
    """
    res = RuleResult(rule_id="ARCH-002")
    for rel in iter_py_files(ctx, "gems"):
        tree = ctx.parse(rel)
        if tree is None:
            continue
        for node, mod, line in _imports_of(tree):
            if (mod == "core.pipeline"
                    or (mod.startswith("core.pipeline")
                        and not any(mod == ok or mod.startswith(ok + ".")
                                    for ok in LEGAL_GEM_CORE_IMPORTS))):
                res.violations.append(violation(
                    ctx, meta, rel, line,
                    f"gem imports {mod} — gems are plugins below core; "
                    "only leaf contracts (schemas/config/pipeline_hooks/"
                    "learning) may be imported", node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_arch003(ctx: RuleContext, meta: dict) -> RuleResult:
    """ARCH-003: Pipeline.run line-count budget ratchet (A-1, F2, R1).

    Budget may only be lowered; block when exceeded, report headroom.
    """
    res = RuleResult(rule_id="ARCH-003")
    budget = int(ctx.budgets.get("pipeline_run_lines", 790))
    tree = ctx.parse("core/pipeline.py")
    if tree is None:
        res.status = "skip"
        res.note = "core/pipeline.py not found"
        return res
    span = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Pipeline":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name == "run":
                    span = (item.lineno, item.end_lineno or item.lineno)
    if span is None:
        res.status = "skip"
        res.note = "Pipeline.run not found"
        return res
    actual = span[1] - span[0]
    res.metrics["pipeline_run_lines"] = {"budget": budget, "actual": actual,
                                         "headroom": budget - actual}
    res.note = (f"Pipeline.run spans {actual} lines "
                f"(budget {budget}, headroom {budget - actual})")
    if actual > budget:
        src = ctx.read("core/pipeline.py") or ""
        res.violations.append(violation(
            ctx, meta, "core/pipeline.py", span[0],
            f"Pipeline.run grew to {actual} lines, over budget {budget} — "
            "extract a stage or lower the budget via PR (budgets may only "
            "be lowered)", text=f"Pipeline.run:{actual}"))
        res.status = "fail"
    return res


def check_arch004(ctx: RuleContext, meta: dict) -> RuleResult:
    """ARCH-004: dashboard/*.py must not read memory/ paths outside the
    designated collector API module list (A-7, P-05)."""
    allowed = set(meta.get("collector_api_modules", ["dashboard/collector.py"]))
    res = RuleResult(rule_id="ARCH-004")
    mem_markers = ('"memory', "'memory", "memory/")

    for rel in iter_py_files(ctx, "dashboard"):
        if rel in allowed:
            continue
        tree = ctx.parse(rel)
        src = ctx.read(rel)
        if tree is None or src is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = call_name(node.func)
            if not (fn.endswith(("open", "read_text", "read_bytes", "glob",
                                 "rglob", "_read_json")) or fn == "open"):
                continue
            hay = ast.dump(node)
            if any(m in hay for m in mem_markers):
                res.violations.append(violation(
                    ctx, meta, rel, node.lineno,
                    f"dashboard reads memory/ directly via {fn}() outside "
                    f"the collector API ({', '.join(sorted(allowed))}) — "
                    "route through collect_snapshot()",
                    node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_arch005(ctx: RuleContext, meta: dict) -> RuleResult:
    """ARCH-005: unregistered new core module check vs baseline module list.

    A core/*.py file absent from the baseline module registry must be
    either imported from an existing non-test module or listed in
    core/modules.yaml / the core/__init__ docstring (shim proliferation
    guard, A-6/A-8).
    """
    res = RuleResult(rule_id="ARCH-005")
    current = sorted(module_stem(p).split("/", 1)[1]
                     for p in iter_py_files(ctx, "core")
                     if not p.endswith("__init__.py"))
    known = ctx.baseline.get("module_registry", {}).get("core")
    if known is None:
        res.status = "pass"
        res.note = ("no module registry in baseline; current set admitted "
                    f"({len(current)} modules) — seed baseline to activate")
        res.metrics["core_modules"] = current
        return res
    admitted = set(meta.get("admitted_shims", []))
    new_mods = [m for m in current if m not in known and m not in admitted]
    if not new_mods:
        return res

    imported: set = set()
    manifest = ctx.read("core/modules.yaml") or ""
    init_doc = ctx.read("core/__init__.py") or ""
    for rel in iter_py_files(ctx):
        if rel.startswith("tests/"):
            continue
        tree = ctx.parse(rel)
        if tree is None:
            continue
        for node, mod, _line in _imports_of(tree):
            if mod.startswith("core."):
                imported.add(mod.split(".")[1])
    for m in new_mods:
        if m in imported or m in manifest or m in init_doc:
            continue
        res.violations.append(violation(
            ctx, meta, f"core/{m}.py", 1,
            f"new core module '{m}' is not imported anywhere and not listed "
            "in core/modules.yaml / core/__init__ — unregistered shim",
            text=f"core module {m}", context="<module>"))
    res.status = "fail" if res.violations else "pass"
    return res


def check_arch006(ctx: RuleContext, meta: dict) -> RuleResult:
    """ARCH-006: orchestrator.process_response(...) result discarded (A-1, V-E).

    Flags bare expression statements whose value is the process_response call.
    """
    res = RuleResult(rule_id="ARCH-006")
    rel = "core/pipeline.py"
    tree = ctx.parse(rel)
    if tree is None:
        res.status = "skip"
        res.note = "core/pipeline.py not found"
        return res
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            if call_name(node.value.func).endswith("orchestrator.process_response"):
                res.violations.append(violation(
                    ctx, meta, rel, node.lineno,
                    "orchestrator.process_response(...) Status discarded — "
                    "match/return the Status so degraded states surface",
                    node=node.value, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


RULES = {
    "ARCH-001": check_arch001,
    "ARCH-002": check_arch002,
    "ARCH-003": check_arch003,
    "ARCH-004": check_arch004,
    "ARCH-005": check_arch005,
    "ARCH-006": check_arch006,
}
