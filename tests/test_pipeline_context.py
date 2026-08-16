"""pipeline_context strangler contracts."""
from __future__ import annotations


def test_bandit_context_multifile():
    from core.pipeline_context import bandit_context

    c = bandit_context("refactor this module", tier=2, fail_kind="timeout")
    assert c["tier"] == 2
    assert c["fail_kind"] == "timeout"
    assert c["multifile"] is True


def test_hooks_reexports_context():
    from core.pipeline_hooks import bandit_context

    c = bandit_context("hello", tier=0)
    assert "multifile" in c


def test_select_uses_context():
    from core.pipeline_select import select_strategy_with_context

    name, ctx = select_strategy_with_context("simple")
    assert isinstance(name, str)
    assert "tier" in ctx


def test_strangler_context_ok():
    from core.pipeline_strangler import EXTRACTED, compute

    assert "core.pipeline_context" in [e["mod"] for e in EXTRACTED]
    out = compute()
    assert out.get("context_contract_ok") is True
