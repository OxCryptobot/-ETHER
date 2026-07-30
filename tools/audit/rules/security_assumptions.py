"""SEC — security assumption rules (P2 §1, AST/text/git-based)."""

from __future__ import annotations

import ast
import json
import re

from .. import (RuleContext, RuleResult, call_name, violation)

SANDBOX_FLAG = "sandbox_fallback:local"


def check_sec001(ctx: RuleContext, meta: dict) -> RuleResult:
    """SEC-001: every @app.post("/api/promote")-style route touching
    PERSISTENT must call _promotion_gate (S-02, B4)."""
    res = RuleResult(rule_id="SEC-001")
    rel = "dashboard/app.py"
    tree = ctx.parse(rel)
    if tree is None:
        res.status = "skip"
        res.note = "dashboard/app.py not found"
        return res
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        is_promote = False
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and \
                    call_name(dec.func).endswith(".post") and dec.args:
                a0 = dec.args[0]
                if isinstance(a0, ast.Constant) and "promote" in str(a0.value):
                    is_promote = True
        if not is_promote:
            continue
        body_dump = ast.dump(node)
        calls_gate = any(
            isinstance(n, ast.Call) and "_promotion_gate" in call_name(n.func)
            for n in ast.walk(node))
        touches_persistent = "PERSISTENT" in body_dump
        if touches_persistent and not calls_gate:
            res.violations.append(violation(
                ctx, meta, rel, node.lineno,
                f"@app.post promote handler '{node.name}' writes to "
                "PERSISTENT without calling _promotion_gate — quarantined, "
                "unreviewed code reaches production (S-02, B4)",
                node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_sec002(ctx: RuleContext, meta: dict) -> RuleResult:
    """SEC-002: resolve_tool/run_tool must sanitize the name with
    re.fullmatch (or basename+allowlist) before the path join (S-07, B4)."""
    res = RuleResult(rule_id="SEC-002")
    rel = "gems/grandidierite/registry.py"
    tree = ctx.parse(rel)
    if tree is None:
        res.status = "skip"
        res.note = f"{rel} not found"
        return res
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name not in ("resolve_tool", "run_tool"):
            continue
        dump = ast.dump(node)
        joins = "PERSISTENT" in dump
        sanitized = any(
            isinstance(n, ast.Call) and call_name(n.func) in (
                "re.fullmatch", "re.match") and n.args
            for n in ast.walk(node))
        if joins and not sanitized:
            res.violations.append(violation(
                ctx, meta, rel, node.lineno,
                f"{node.name}() joins PERSISTENT / name without a "
                "re.fullmatch ^[A-Za-z_]\\w*$ sanitization — path "
                "traversal executes arbitrary repo files (S-07)",
                node=node, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


def check_sec003(ctx: RuleContext, meta: dict) -> RuleResult:
    """SEC-003: _run_local must not be reachable from execute() without the
    sandbox_fallback:local flag emitted on the same path (S-01, B1).

    Dataflow heuristic: every call site of `_run_local` (or of `_run`,
    which dispatches to `_run_local` when the backend resolves local)
    whose enclosing function never mentions the flag string is a silent
    host-execution path.
    """
    res = RuleResult(rule_id="SEC-003")
    rel = "gems/clear_quartz/sandbox.py"
    tree = ctx.parse(rel)
    if tree is None:
        res.status = "skip"
        res.note = f"{rel} not found"
        return res
    # does _run dispatch to _run_local?
    run_dispatches = False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == "_run":
            run_dispatches = any(
                isinstance(n, ast.Call)
                and call_name(n.func).endswith("_run_local")
                for n in ast.walk(node))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        fn_src = ast.dump(node)
        has_flag = SANDBOX_FLAG in fn_src or SANDBOX_FLAG in (
            ctx.read(rel) or "")[node.lineno - 1:(node.end_lineno or node.lineno)]
        for n in ast.walk(node):
            if not isinstance(n, ast.Call):
                continue
            callee = call_name(n.func)
            direct = callee.endswith("_run_local")
            indirect = run_dispatches and callee.endswith("._run") \
                and node.name == "execute"
            if not (direct or indirect):
                continue
            if not has_flag:
                kind = "_run_local" if direct else "_run→_run_local"
                res.violations.append(violation(
                    ctx, meta, rel, n.lineno,
                    f"{kind} reachable in {node.name}() without "
                    f"'{SANDBOX_FLAG}' emitted on the path — model-authored "
                    "code runs on the host invisibly when backend resolves "
                    "local (S-01, B1)", node=n, tree=tree))
    res.status = "fail" if res.violations else "pass"
    return res


BACKEND_RE = re.compile(r"ETHER_SANDBOX_BACKEND\s*=\s*(local|subprocess|native)")


def check_sec004(ctx: RuleContext, meta: dict) -> RuleResult:
    """SEC-004: deploy/** must not pin ETHER_SANDBOX_BACKEND=local (S-01, B1)."""
    res = RuleResult(rule_id="SEC-004")
    deploy = ctx.path("deploy")
    if not deploy.is_dir():
        res.status = "skip"
        res.note = "deploy/ not found"
        return res
    for p in sorted(deploy.rglob("*")):
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = BACKEND_RE.search(line)
            if m:
                rel = p.relative_to(ctx.repo).as_posix()
                res.violations.append(violation(
                    ctx, meta, rel, i,
                    f"deploy pins ETHER_SANDBOX_BACKEND={m.group(1)} — the "
                    "shipped service runs model code on the host (S-01)",
                    text=line.strip()))
    res.status = "fail" if res.violations else "pass"
    return res


REQUIRED_BT = ("check_output", "popen", "socket")


def check_sec005(ctx: RuleContext, meta: dict) -> RuleResult:
    """SEC-005: black_tourmaline pattern list must cover
    check_output | popen | socket (S-05)."""
    res = RuleResult(rule_id="SEC-005")
    rel = "gems/black_tourmaline/security.py"
    tree = ctx.parse(rel)
    if tree is None:
        res.status = "skip"
        res.note = f"{rel} not found"
        return res
    # collect every string literal in the module (pattern lists, extends,
    # manifest keys) — the file is small and patterns are string-shaped
    patterns: list = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            patterns.append(node.value)
    # also pull manifest-driven patterns from config files if present
    for cfg_rel in ("config/manifest.json", "config/manifest.yaml",
                    "config/security_manifest.json"):
        text = ctx.read(cfg_rel)
        if text:
            patterns += re.findall(r'"([a-z_]+\\\\?\.\w+|\w+\\\\?\.\w+)"', text)
    blob = "\n".join(patterns)
    missing = [k for k in REQUIRED_BT if k not in blob]
    if missing:
        res.violations.append(violation(
            ctx, meta, rel, 1,
            f"black_tourmaline patterns missing coverage: {', '.join(missing)}"
            " — single-gate static safety can be bypassed with "
            "check_output/popen/socket (S-05)", text=" ".join(missing),
            context="BlackTourmaline.__init__"))
    res.status = "fail" if res.violations else "pass"
    return res


def check_sec006(ctx: RuleContext, meta: dict) -> RuleResult:
    """SEC-006: apply_patch.py must enforce is_relative_to containment;
    a BLOCK-substring check alone fails (S-09)."""
    res = RuleResult(rule_id="SEC-006")
    rel = "tools/persistent/apply_patch.py"
    src = ctx.read(rel)
    tree = ctx.parse(rel)
    if src is None or tree is None:
        res.status = "skip"
        res.note = f"{rel} not found"
        return res
    if "is_relative_to" not in src:
        line = 1
        for n in ast.walk(tree):
            if isinstance(n, ast.FunctionDef):
                line = n.lineno
                break
        res.violations.append(violation(
            ctx, meta, rel, line,
            "apply_patch.py resolves targets with substring BLOCK check "
            "only — no Path.resolve().is_relative_to(SCRATCH) containment; "
            "'..memory' / absolute paths slip through (S-09)",
            text="apply_patch no containment", context="apply_patch"))
    res.status = "fail" if res.violations else "pass"
    return res


def check_sec007(ctx: RuleContext, meta: dict) -> RuleResult:
    """SEC-007: tracked files under ignored paths (memory/, tools/persistent/)
    must be in the baseline tracked whitelist (F5, S-03, S-06, D-03)."""
    res = RuleResult(rule_id="SEC-007")
    if ctx.fast:
        res.status = "skip"
        res.note = "git plumbing skipped in --fast mode"
        return res
    tracked = ctx.git_tracked()
    if not tracked:
        res.status = "skip"
        res.note = "git ls-files unavailable"
        return res
    watch = [t for t in tracked if t.startswith("memory/")
             or t.startswith("tools/persistent/")]
    whitelist = set()
    for entry in ctx.baseline.get("tracked_whitelist", []):
        whitelist.add(entry.get("path") if isinstance(entry, dict) else entry)
    res.metrics["tracked_ignored_files"] = {"count": len(watch),
                                            "whitelisted": len(whitelist)}
    for t in watch:
        if t not in whitelist:
            res.violations.append(violation(
                ctx, meta, t, 1,
                "tracked file lives under a gitignored path and is not in "
                "the audit tracked whitelist — state files in git are "
                "un-backed-up secrets/leak surface (F5/S-06/D-03)",
                text=f"tracked:{t.split('/')[-1]}", context="<git>"))
    res.status = "fail" if res.violations else "pass"
    return res


def check_sec008(ctx: RuleContext, meta: dict) -> RuleResult:
    """SEC-008: tracked memory/batch_queue.json may never contain a
    {\"kind\": \"command\"} item (S-03 kill-switch)."""
    res = RuleResult(rule_id="SEC-008")
    rel = "memory/batch_queue.json"
    text = ctx.read(rel)
    if text is None:
        res.status = "skip"
        res.note = f"{rel} not found"
        return res
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        res.violations.append(violation(
            ctx, meta, rel, 0, f"batch_queue.json is not valid JSON: {e}",
            text="batch_queue unparseable", context="<json>"))
        res.status = "fail"
        return res
    items: list = []

    def _collect(obj):
        if isinstance(obj, list):
            for it in obj:
                if isinstance(it, dict):
                    items.append(it)
                else:
                    _collect(it)
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect(v)

    _collect(data)
    for idx, item in enumerate(items):
        if item.get("kind") == "command":
            res.violations.append(violation(
                ctx, meta, rel, idx + 1,
                "tracked batch_queue.json carries a kind=command item — a "
                "committed arbitrary-command kill-switch (S-03)",
                text='{"kind": "command"}', context="<batch_queue>"))
    res.status = "fail" if res.violations else "pass"
    return res


def check_sec009(ctx: RuleContext, meta: dict) -> RuleResult:
    """SEC-009: dependency drift — pyproject deps with >= and no lockfile,
    mutable docker image tags (S-08)."""
    res = RuleResult(rule_id="SEC-009")
    has_lock = any(ctx.path(f).exists() for f in
                   ("requirements.lock", "uv.lock", "poetry.lock",
                    "requirements-lock.txt", "lockfile.json"))
    py = ctx.read("pyproject.toml")
    if py is None:
        reqs = [f for f in ("requirements.txt", "requirements-dev.txt")
                if ctx.read(f)]
        if not reqs:
            res.note = ("no pyproject.toml / requirements*.txt found in the "
                        "scanned tree — manifest drift check deferred to adopt-time")
        for rel in reqs:
            for i, line in enumerate((ctx.read(rel) or "").splitlines(), 1):
                if ">=" in line and not has_lock:
                    res.violations.append(violation(
                        ctx, meta, rel, i,
                        f"unpinned dep '{line.strip()}' with no lockfile — "
                        "resolver drift (S-08)", text=line.strip()))
    else:
        for m in re.finditer(r'"([a-zA-Z0-9_\-\[\]]+>=[^"]+)"', py):
            if not has_lock:
                res.violations.append(violation(
                    ctx, meta, "pyproject.toml", 0,
                    f"dep '{m.group(1)}' has a floor but no upper bound and "
                    "no lockfile (S-08)", text=m.group(1)))
    compose = ctx.read("docker-compose.yml")
    if compose:
        for i, line in enumerate(compose.splitlines(), 1):
            m = re.search(r"image:\s*\S+", line)
            if m and (m.group(0).endswith(":latest")
                      or ":" not in m.group(0).split()[-1]):
                res.violations.append(violation(
                    ctx, meta, "docker-compose.yml", i,
                    f"mutable image tag '{m.group(0).split()[-1]}' — pin a "
                    "digest or version (S-08)", text=line.strip()))
    res.status = "fail" if res.violations else "pass"
    return res


RULES = {
    "SEC-001": check_sec001,
    "SEC-002": check_sec002,
    "SEC-003": check_sec003,
    "SEC-004": check_sec004,
    "SEC-005": check_sec005,
    "SEC-006": check_sec006,
    "SEC-007": check_sec007,
    "SEC-008": check_sec008,
    "SEC-009": check_sec009,
}
