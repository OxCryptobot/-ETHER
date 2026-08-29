"""Self-improve dual-window PoC — compose, do not parallel."""
from __future__ import annotations

from core.improvement_proposal import make_proposal, write_allowed
from core.self_improve import cycle, worked_example
from core.self_mod_gate import decide_deploy, validate_proposal


def test_write_policy():
    assert write_allowed("artifacts/self_improve/proposals/x.json") is True
    assert write_allowed("memory/ether_apprentice/lessons/030.json") is True
    assert write_allowed("core/tool_runtime.py") is False
    assert write_allowed("scripts/ether_host.py") is False


def test_gate_rejects_core_apply():
    p = make_proposal(
        gap="x",
        hypothesis="y",
        metric="z",
        why="because",
        files=["core/tool_runtime.py"],
    )
    p["apply_core"] = True
    g = validate_proposal(p)
    assert g["ok"] is False
    assert any("apply_core" in e or "forbidden" in e for e in g["errors"])


def test_deploy_stays_tutor_gated_under_wheels():
    d = decide_deploy(tests_ok=True, proposal_ok=True, wheels=True)
    assert d["deploy"] is False
    assert d.get("persist_proposal") is True


def test_cycle_does_not_soft_launch_or_train():
    out = cycle(escalate=False)
    assert out.get("soft_launch") is False
    assert out.get("lora_trained") is False
    assert out.get("training_wheels") is True
    assert out.get("proposal", {}).get("id")
    assert out.get("path")


def test_worked_example_is_the_real_week():
    ex = worked_example()
    assert "p1_242" in ex["validation"] or "PASS" in str(ex["validation"])
    assert ex["metric_optimized"]
