"""Wire leftover 6%: named gem calls, pack fixtures, LoRA fail-closed, scale plane."""
from __future__ import annotations

import inspect

from core.loop.gems_call import audit_execute, rose_complete, sandbox_execute
from core.loop.living import FIXTURES, run_pack_plus
from core.loop.moonshot import lora_ready
from core.model_router import select_backend
from core.pipeline import Pipeline


def test_pipeline_uses_named_gem_calls() -> None:
    src = inspect.getsource(Pipeline.run)
    assert "sandbox_execute" in src
    assert "audit_execute" in src
    assert "rose_complete" in inspect.getsource(Pipeline)


def test_named_entries_exist() -> None:
    assert callable(sandbox_execute)
    assert callable(audit_execute)
    assert callable(rose_complete)


def test_pack_plus_lists_remaining_fixtures() -> None:
    for name in ("merge", "ledger", "lru", "topo", "intervals"):
        assert name in FIXTURES
    pack = run_pack_plus
    assert callable(pack)


def test_lora_and_fast_lane_honest() -> None:
    ready = lora_ready()
    assert ready["ok"] is False
    assert ready.get("trainer") == "grok_bus"
    assert ready.get("local_train") is False
    b = select_backend("fast")
    assert b["backend"] == "ollama"
    assert b["lane"] == "fast"
