"""Day-2 promote gate fail-closed + flywheel signal rebase.

Pins the roadmap Day-2 changes: /api/promote routes through _promotion_gate
with two consent modes (SEC-001), resolve_tool closes the quarantine
traversal (SEC-002), Black Tourmaline covers the check_output/check_call/
os.popen/socket bypasses (SEC-005), promote_safe drops the force override,
pytest timeout rises above the suite mean (MEAS-002), and report pushes
become explicit opt-in (MEAS-005).
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _consent_flags_off(monkeypatch):
    monkeypatch.delenv("ETHER_AUTO_PROMOTE", raising=False)
    monkeypatch.delenv("ETHER_FLYWHEEL_PUSH", raising=False)


def _write(path: Path, code: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# SEC-001 — /api/promote routes through the gate (AST contract mirror)
# --------------------------------------------------------------------------


def test_promote_route_calls_gate_ast_contract():
    """Mirror of the audit pack's test_promote_route_calls_gate: the promote
    handler's AST must contain a `_promotion_gate` attribute call."""
    tree = ast.parse((ROOT / "dashboard" / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and dec.args:
                a0 = dec.args[0]
                if isinstance(a0, ast.Constant) and "promote" in str(a0.value):
                    calls = {getattr(getattr(n, "func", None), "attr", "") for n in ast.walk(node)}
                    assert (
                        "_promotion_gate" in calls
                    ), f"{node.name} touches PERSISTENT without the gate"
                    return
    pytest.fail("no promote route found in dashboard/app.py")


# --------------------------------------------------------------------------
# SEC-001 — the gate's two consent modes
# --------------------------------------------------------------------------


def test_gate_daemon_mode_still_env_gated(tmp_path):
    from core.tool_reconcile import _promotion_gate

    tool = _write(tmp_path / "t.py", "def main():\n    return 1\n")
    gate = _promotion_gate(tool)
    assert gate["ok"] is False
    assert "ETHER_AUTO_PROMOTE" in gate["reason"]


def test_gate_operator_mode_clean_file_passes(tmp_path):
    from core.tool_reconcile import _promotion_gate

    tool = _write(tmp_path / "t.py", "def main():\n    return 1\n")
    gate = _promotion_gate(tool, operator_initiated=True)
    assert gate["ok"] is True, gate


def test_gate_operator_mode_still_refuses_risky_code(tmp_path):
    """operator_initiated skips ONLY the env check, not the safety checks."""
    from core.tool_reconcile import _promotion_gate

    tool = _write(tmp_path / "evil.py", "eval('1')\n")
    gate = _promotion_gate(tool, operator_initiated=True)
    assert gate["ok"] is False
    assert gate["reason"]


def test_gate_operator_mode_fails_closed_on_unreadable(tmp_path):
    from core.tool_reconcile import _promotion_gate

    gate = _promotion_gate(tmp_path / "missing.py", operator_initiated=True)
    assert gate["ok"] is False
    assert "unreadable" in gate["reason"]


# --------------------------------------------------------------------------
# SEC-001 — endpoint behavior (direct handler call, stub gate)
# --------------------------------------------------------------------------


def _quarantine(tmp_path, monkeypatch):
    import dashboard.app as dapp

    quar = tmp_path / "quarantine"
    pers = tmp_path / "persistent"
    quar.mkdir()
    monkeypatch.setattr(dapp, "QUARANTINE", quar)
    monkeypatch.setattr(dapp, "PERSISTENT", pers)
    return dapp, quar, pers


def test_promote_endpoint_refused_gate_is_403(tmp_path, monkeypatch):
    import core.tool_reconcile as tr
    from fastapi import HTTPException

    dapp, quar, _pers = _quarantine(tmp_path, monkeypatch)
    _write(quar / "tool.py", "eval('1')\n")
    monkeypatch.setattr(
        tr, "_promotion_gate", lambda *a, **k: {"ok": False, "reason": "audit rejected"}
    )
    with pytest.raises(HTTPException) as exc:
        dapp.promote(dapp.PromoteBody(filename="tool.py"))
    assert exc.value.status_code == 403
    assert "promotion gate refused" in str(exc.value.detail)


def test_promote_endpoint_missing_file_is_404(tmp_path, monkeypatch):
    from fastapi import HTTPException

    dapp, _quar, _pers = _quarantine(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        dapp.promote(dapp.PromoteBody(filename="ghost.py"))
    assert exc.value.status_code == 404


def test_promote_endpoint_bad_extension_is_400(tmp_path, monkeypatch):
    from fastapi import HTTPException

    dapp, _quar, _pers = _quarantine(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        dapp.promote(dapp.PromoteBody(filename="x.txt"))
    assert exc.value.status_code == 400


def test_promote_endpoint_traversal_name_never_promotes(tmp_path, monkeypatch):
    """Path("../x.py").name == "x.py": the traversal is neutralized by the
    basename + regex, so the request degrades to a plain quarantine miss
    (404) — it can never reach outside QUARANTINE or create a file."""
    from fastapi import HTTPException

    dapp, quar, pers = _quarantine(tmp_path, monkeypatch)
    _write(tmp_path / "x.py", "def main():\n    return 1\n")  # outside quarantine
    with pytest.raises(HTTPException) as exc:
        dapp.promote(dapp.PromoteBody(filename="../x.py"))
    assert exc.value.status_code == 404
    assert list(pers.glob("*.py")) == []


def test_promote_endpoint_ok_gate_copies_file(tmp_path, monkeypatch):
    import core.tool_reconcile as tr

    dapp, quar, pers = _quarantine(tmp_path, monkeypatch)
    src = _write(quar / "tool_20260726_123456.py", "def main():\n    return 1\n")
    seen = {}

    def fake_gate(path, *, operator_initiated=False):
        seen["path"] = path
        seen["operator_initiated"] = operator_initiated
        return {"ok": True, "reason": ""}

    monkeypatch.setattr(tr, "_promotion_gate", fake_gate)
    out = dapp.promote(dapp.PromoteBody(filename=src.name))
    assert out == {"ok": True, "from": src.name, "to": "tool.py"}
    assert (pers / "tool.py").read_text(encoding="utf-8") == src.read_text(encoding="utf-8")
    assert seen == {"path": src, "operator_initiated": True}


# --------------------------------------------------------------------------
# SEC-002 — resolve_tool traversal close
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["../quarantine/promote_safe", "../quarantine/whatever", "a/b", "..%2f..%2fetc"],
)
def test_resolve_tool_rejects_traversal(name):
    from gems.grandidierite.registry import resolve_tool

    assert resolve_tool(name) is None


def test_resolve_tool_resolves_real_persistent_tool():
    from gems.grandidierite.registry import PERSISTENT, resolve_tool

    path = resolve_tool("promote_safe")
    assert path is not None
    assert path.parent == PERSISTENT
    assert path.name == "promote_safe.py"


# --------------------------------------------------------------------------
# SEC-005 — Black Tourmaline covers the bypass quartet
# --------------------------------------------------------------------------


def _tourmaline_verdict(code: str):
    from core.schemas import BlackTourmalineRequest, Envelope
    from gems.black_tourmaline.security import BlackTourmaline

    res = BlackTourmaline().execute(
        Envelope(
            task_id=uuid4(),
            target_gem="black-tourmaline",
            payload=BlackTourmalineRequest(artifact=code, artifact_type="code"),
        )
    )
    assert res.error is None
    assert res.payload is not None
    return res.payload


@pytest.mark.parametrize(
    "code",
    [
        "import subprocess\nsubprocess.check_output(['x'])\n",
        "import subprocess\nsubprocess.check_call('x')\n",
        "import os\nos.popen('ls')\n",
        "import socket\nsocket.socket()\n",
    ],
)
def test_tourmaline_flags_new_execution_egress_channels(code):
    payload = _tourmaline_verdict(code)
    assert payload.approved is False
    assert len(payload.violations) >= 1


def test_tourmaline_clean_artifact_stays_approved():
    payload = _tourmaline_verdict("def main():\n    return 1\n")
    assert payload.approved is True
    assert payload.violations == []


# --------------------------------------------------------------------------
# SEC-005 — promote_safe: force override removed, patterns aligned
# --------------------------------------------------------------------------


def _load_promote_safe():
    spec = importlib.util.spec_from_file_location(
        "promote_safe_under_test", ROOT / "tools" / "persistent" / "promote_safe.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _drive_promote_safe(mod, monkeypatch, tmp_path, inp):
    monkeypatch.setattr(mod, "read_input", lambda: inp)
    monkeypatch.setattr(mod, "repo_root", lambda: tmp_path)
    emitted = {}

    def fake_emit(ok, **payload):
        emitted.update({"ok": ok, **payload})
        raise SystemExit(0 if ok else 1)

    monkeypatch.setattr(mod, "emit", fake_emit)
    with pytest.raises(SystemExit):
        mod.main()
    return emitted


def test_promote_safe_force_cannot_override_risky_code(tmp_path, monkeypatch):
    mod = _load_promote_safe()
    _write(tmp_path / "tools" / "quarantine" / "evil.py", "eval('1')\n")
    out = _drive_promote_safe(mod, monkeypatch, tmp_path, {"filename": "evil.py", "force": True})
    assert out["ok"] is False
    assert "no override" in out["error"]
    assert not (tmp_path / "tools" / "persistent" / "evil.py").exists()


def test_promote_safe_clean_file_promotes(tmp_path, monkeypatch):
    mod = _load_promote_safe()
    _write(tmp_path / "tools" / "quarantine" / "good.py", "def main():\n    return 1\n")
    out = _drive_promote_safe(mod, monkeypatch, tmp_path, {"filename": "good.py"})
    assert out["ok"] is True
    assert (tmp_path / "tools" / "persistent" / "good.py").exists()


# --------------------------------------------------------------------------
# MEAS-005 — report pushes are explicit opt-in
# --------------------------------------------------------------------------


def test_compute_do_push_defaults_off():
    from scripts.flywheel import _compute_do_push

    assert _compute_do_push(False) is False


def test_compute_do_push_env_opt_in(monkeypatch):
    from scripts.flywheel import _compute_do_push

    monkeypatch.setenv("ETHER_FLYWHEEL_PUSH", "1")
    assert _compute_do_push(False) is True


def test_compute_do_push_flag_wins_regardless(monkeypatch):
    from scripts.flywheel import _compute_do_push

    assert _compute_do_push(True) is True
    monkeypatch.setenv("ETHER_FLYWHEEL_PUSH", "0")
    assert _compute_do_push(True) is True


def test_autonomous_no_longer_implies_push():
    """main() must derive do_push from _compute_do_push(args.push) only."""
    src = (ROOT / "scripts" / "flywheel.py").read_text(encoding="utf-8")
    assert "do_push = _compute_do_push(args.push)" in src
    assert not re.search(r"do_push\s*=\s*args\.push\s*or\s*args\.autonomous", src)


def test_smart_cycle_push_default_off():
    src = (ROOT / "scripts" / "run_smart_cycle.py").read_text(encoding="utf-8")
    assert 'os.environ.setdefault("ETHER_FLYWHEEL_PUSH", "0")' in src
    assert 'setdefault("ETHER_FLYWHEEL_PUSH", "1")' not in src


# --------------------------------------------------------------------------
# MEAS-002 — pytest timeout above the suite mean
# --------------------------------------------------------------------------


def test_flywheel_pytest_timeout_is_900():
    src = (ROOT / "scripts" / "flywheel.py").read_text(encoding="utf-8")
    assert re.search(
        r"pytest.*timeout=900", src, re.S
    ), "pytest step must allow the ~380s suite mean"
