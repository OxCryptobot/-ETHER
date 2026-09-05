"""leftover 3%: LoRA pack via Grok. No local train. No fake adapter."""
from __future__ import annotations

from core.loop.lora_pack import PACK, build_pack, lora_status, train_via_grok
from core.loop.moonshot import lora_ready
from core.model_router import grok_present


def test_train_via_grok_writes_pack() -> None:
    out = train_via_grok()
    assert out["ok"] is True
    assert out["trainer"] == "grok_bus"
    assert out["local_train"] is False
    assert out["adapter"] is None
    assert out["requires_api_key"] is False
    assert PACK.is_file()
    assert build_pack()["n"] >= 1


def test_lora_ready_is_grok_trainer() -> None:
    st = lora_status()
    assert st["trainer"] == "grok_bus"
    assert st["local_train"] is False
    assert st["ok"] is False  # no adapter.safetensors yet
    ready = lora_ready()
    assert ready["trainer"] == "grok_bus"
    assert grok_present() is True
