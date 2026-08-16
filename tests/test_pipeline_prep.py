"""pipeline_prep strangler contracts."""
from __future__ import annotations


def test_no_code_prep_bypasses():
    from core.pipeline_prep import no_code_prep, prepare_code_for_sandbox

    with no_code_prep():
        code, meta = prepare_code_for_sandbox("print(1)", "any")
    assert code == "print(1)"
    assert meta.get("bypassed") is True


def test_hooks_reexports_prep():
    from core import pipeline_hooks

    assert callable(pipeline_hooks.prepare_code_for_sandbox)
    assert callable(pipeline_hooks.no_code_prep)
    assert callable(pipeline_hooks.code_prep_disabled)


def test_strangler_includes_prep():
    from core.pipeline_strangler import EXTRACTED, compute

    mods = [e["mod"] for e in EXTRACTED]
    assert "core.pipeline_prep" in mods
    out = compute()
    assert out.get("prep_contract_ok") is True
    assert out.get("extracted_ok") == out.get("extracted_n")
