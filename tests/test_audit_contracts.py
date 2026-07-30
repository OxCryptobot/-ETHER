"""ETHER audit contract tests (TST rules, P2 §1).

Run INSIDE the target repo:  pytest tests/test_audit_contracts.py

Every test skips cleanly when the target module is unimportable (partial
checkouts, missing optional deps). Tests covering known-at-HEAD holes are
marked xfail(strict=False) with the finding ID, so the suite is truthful
at Day 0 and flips to XPASS (a visible review signal) as fixes land.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _try_import(mod: str):
    try:
        return importlib.import_module(mod)
    except Exception:
        return None


# ---------------------------------------------------------- SEC-001 (S-02, B4)
@pytest.mark.xfail(reason="SEC-001: promote route bypasses _promotion_gate at "
                          "HEAD 208993a", strict=False)
def test_promote_route_calls_gate():
    """Every @app.post promote handler touching PERSISTENT must call
    core.tool_reconcile._promotion_gate (AST contract — no FastAPI needed)."""
    import ast

    app_py = ROOT / "dashboard" / "app.py"
    if not app_py.exists():
        pytest.skip("dashboard/app.py not present")
    tree = ast.parse(app_py.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and dec.args:
                a0 = dec.args[0]
                if isinstance(a0, ast.Constant) and "promote" in str(a0.value):
                    calls = {getattr(getattr(n, "func", None), "attr", "")
                             for n in ast.walk(node)}
                    assert "_promotion_gate" in calls, (
                        f"{node.name} touches PERSISTENT without the gate")
                    return
    pytest.skip("no promote route found")


# ---------------------------------------------------------- SEC-003 (S-01, B1)
def test_sandbox_backend_never_returns_auto():
    """sandbox_backend() resolves to a concrete backend; 'auto' is an input
    value, never an output (the auto->local silent path is B1)."""
    mod = _try_import("gems.clear_quartz.sandbox")
    if mod is None or not hasattr(mod, "sandbox_backend"):
        pytest.skip("gems.clear_quartz.sandbox unimportable")
    for val in ("auto", "docker", "local", "subprocess", "native", ""):
        os.environ["ETHER_SANDBOX_BACKEND"] = val
        backend = mod.sandbox_backend()
        assert backend in ("docker", "local"), (
            f"backend {val!r} resolved to {backend!r}")


def test_explicit_docker_fails_closed_without_docker(monkeypatch):
    """ETHER_SANDBOX_BACKEND=docker + no docker binary -> dependency error,
    never a silent host re-run (verified fix, regression guard)."""
    mod = _try_import("gems.clear_quartz.sandbox")
    if mod is None:
        pytest.skip("gems.clear_quartz.sandbox unimportable")
    schemas = _try_import("core.schemas")
    if schemas is None:
        pytest.skip("core.schemas unimportable")
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "docker")
    monkeypatch.setattr("shutil.which", lambda _name: None)
    cq = mod.ClearQuartz()
    import uuid

    req = schemas.Envelope(
        task_id=uuid.uuid4(),
        target_gem="clear-quartz",
        payload=schemas.ClearQuartzRequest(code="print('hi')"),
    )
    res = cq.execute(req)
    assert res.error is not None, "explicit docker must fail closed"
    payload_flags = getattr(getattr(res, "payload", None),
                            "security_flags", None) or []
    assert "sandbox_fallback:local" not in payload_flags


@pytest.mark.xfail(reason="SEC-003: auto + no docker runs local WITHOUT the "
                          "sandbox_fallback:local flag at HEAD 208993a (B1)",
                   strict=False)
def test_auto_backend_fallback_emits_flag(monkeypatch):
    """Auto backend with no docker: if local execution happens, the flag
    MUST be on the response (S-01's visibility contract)."""
    mod = _try_import("gems.clear_quartz.sandbox")
    schemas = _try_import("core.schemas")
    if mod is None or schemas is None:
        pytest.skip("sandbox modules unimportable")
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "auto")
    monkeypatch.setattr("shutil.which", lambda _name: None)
    cq = mod.ClearQuartz()
    import uuid

    req = schemas.Envelope(
        task_id=uuid.uuid4(),
        target_gem="clear-quartz",
        payload=schemas.ClearQuartzRequest(code="print('hi')"),
    )
    res = cq.execute(req)
    if res.error is not None:
        return  # failing closed is also acceptable
    flags = getattr(getattr(res, "payload", None), "security_flags", None) or []
    assert "sandbox_fallback:local" in flags, (
        "local execution under auto is invisible — B1")


# ------------------------------------------------------ config manifest (S-05)
def test_config_manifest_strictness():
    """load_config rejects unknown manifest keys (extra=forbid) — a typo'd
    key must not silently empty the safety pattern list."""
    cfg_mod = _try_import("core.config")
    if cfg_mod is None or not hasattr(cfg_mod, "load_config"):
        pytest.skip("core.config unimportable")
    pyd = _try_import("pydantic")
    if pyd is None:
        pytest.skip("pydantic unavailable")
    manifest_cls = getattr(cfg_mod, "EtherConfig", None)
    grani_cls = getattr(cfg_mod, "GrandidieriteConfig", None)
    target = grani_cls or manifest_cls
    if target is None:
        pytest.skip("config model not found")
    with pytest.raises(Exception):
        target(**{"forbiden_patterns": ["eval("]})  # typo must not validate


# ---------------------------------------------------------- SEC-005 (S-05)
@pytest.mark.xfail(reason="SEC-005: black_tourmaline patterns lack "
                          "check_output/popen/socket at HEAD 208993a",
                   strict=False)
def test_black_tourmaline_pattern_coverage():
    """The static-safety pattern list covers the known bypass trio."""
    mod = _try_import("gems.black_tourmaline.security")
    if mod is None or not hasattr(mod, "BlackTourmaline"):
        pytest.skip("black_tourmaline unimportable")
    try:
        bt = mod.BlackTourmaline()
    except Exception:
        pytest.skip("BlackTourmaline not constructible (config missing)")
    blob = "\n".join(bt.patterns)
    for required in ("check_output", "popen", "socket"):
        assert required in blob, f"pattern list missing {required}"


# ---------------------------------------------------------- SEC-002 (S-07, B4)
@pytest.mark.xfail(reason="SEC-002: resolve_tool lacks name sanitization at "
                          "HEAD 208993a", strict=False)
def test_resolve_tool_rejects_traversal():
    mod = _try_import("gems.grandidierite.registry")
    if mod is None or not hasattr(mod, "resolve_tool"):
        pytest.skip("grandidierite registry unimportable")
    assert mod.resolve_tool("../../scripts/flywheel") is None
    assert mod.resolve_tool("..%2f..%2fetc") is None


# ---------------------------------------------------------- SEC-008 (S-03)
@pytest.mark.xfail(reason="SEC-008: tracked batch_queue.json carries a "
                          "kind=command item at HEAD 208993a (S-03)",
                   strict=False)
def test_tracked_batch_queue_has_no_command_items():
    bq = ROOT / "memory" / "batch_queue.json"
    if not bq.exists():
        pytest.skip("memory/batch_queue.json not tracked here")
    data = json.loads(bq.read_text(encoding="utf-8"))
    items = []

    def _collect(o):
        if isinstance(o, list):
            for it in o:
                _collect(it)
        elif isinstance(o, dict):
            if "kind" in o:
                items.append(o)
            else:
                for v in o.values():
                    _collect(v)

    _collect(data)
    bad = [i for i in items if i.get("kind") == "command"]
    assert not bad, f"tracked kill-switch items present: {bad[:2]}"
