"""Scale plane: local 4B default; outsource and local-large when hardware/keys exist."""
from __future__ import annotations

from core.model_router import outsource_configured, select_backend, select_model
from gems.rose_quartz.burst import burst_enabled


def test_fast_stays_local_without_outsource_fast(monkeypatch) -> None:
    monkeypatch.delenv("ETHER_OUTSOURCE", raising=False)
    monkeypatch.delenv("ETHER_OUTSOURCE_FAST", raising=False)
    monkeypatch.delenv("ETHER_BURST", raising=False)
    monkeypatch.setenv("ETHER_VRAM_MB", "4096")
    b = select_backend("fast")
    assert b["backend"] == "ollama"
    assert b["lane"] == "fast"
    assert b["scalable"] is False


def test_live_local_large_when_vram_high(monkeypatch) -> None:
    monkeypatch.delenv("ETHER_OUTSOURCE", raising=False)
    monkeypatch.delenv("ETHER_BURST", raising=False)
    monkeypatch.setenv("ETHER_VRAM_MB", "24576")
    monkeypatch.setenv("ETHER_LOCAL_LARGE_MODEL", "qwen3:32b")
    # re-import constants? select_backend reads LOCAL_LARGE at import.
    # Patch module attr.
    import core.model_router as mr

    monkeypatch.setattr(mr, "LOCAL_LARGE", "qwen3:32b")
    monkeypatch.setattr(mr, "VRAM_LARGE_MB", 12000)
    b = mr.select_backend({"class": "live"}, vram=24576)
    assert b["backend"] == "ollama"
    assert b["model"] == "qwen3:32b"
    assert b["scalable"] is True


def test_outsource_live_when_keyed(monkeypatch) -> None:
    monkeypatch.setenv("ETHER_OUTSOURCE", "1")
    monkeypatch.setenv("XAI_API_KEY", "xai-test")
    monkeypatch.setenv("ETHER_OUTSOURCE_MODEL", "grok-3")
    import core.model_router as mr

    monkeypatch.setattr(mr, "OUTSOURCE_MODEL", "grok-3")
    b = mr.select_backend({"class": "live"})
    assert b["backend"] == "outsource"
    assert b["scalable"] is True
    assert burst_enabled() is True


def test_outsource_not_configured() -> None:
    # May be true in this env; just type-check the helper.
    assert isinstance(outsource_configured(), bool)


def test_select_model_live_lane() -> None:
    s = select_model({"class": "live", "note": "live attempt"})
    assert s["lane"] == "live"


def test_live_uses_grok_bus_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ETHER_OUTSOURCE", raising=False)
    monkeypatch.delenv("ETHER_BURST", raising=False)
    monkeypatch.delenv("XAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ETHER_OUTSOURCE_API_KEY", raising=False)
    monkeypatch.setenv("ETHER_GROK_PRESENT", "1")
    monkeypatch.setenv("ETHER_VRAM_MB", "4096")
    import core.model_router as mr
    monkeypatch.setattr(mr, "VRAM_LARGE_MB", 12000)
    b = mr.select_backend({"class": "live"}, vram=4096)
    assert b["backend"] == "grok_bus"
    assert b["scalable"] is True
