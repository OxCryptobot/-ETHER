"""LoRA via Grok: pack + prompt adapter. No PEFT. No 1650 train."""
from __future__ import annotations

from core.loop.generate_retry import first_prompt
from core.loop.lora_pack import ADAPTER, PACK, apply_adapter, lora_status, train_via_grok
from core.loop.moonshot import lora_ready
from core.model_router import grok_present


def test_train_via_grok_writes_adapter() -> None:
    out = train_via_grok()
    assert out["ok"] is True
    assert out["trainer"] == "grok_bus"
    assert out["local_train"] is False
    assert out["peft"] is False
    assert out["requires_api_key"] is False
    assert PACK.is_file()
    assert ADAPTER.is_file()
    assert out["adapter"].endswith("adapter.json")


def test_lora_ready_prompt_adapter() -> None:
    train_via_grok()
    st = lora_status()
    assert st["ok"] is True
    assert st["peft"] is False
    assert st["peft_file"] is False
    assert st["trainer"] == "grok_bus"
    ready = lora_ready()
    assert ready["ok"] is True
    assert grok_present() is True


def test_apply_adapter_prefixes_prompt() -> None:
    train_via_grok()
    text = apply_adapter("Write Python")
    assert text.startswith("pytest is the judge")
    assert "Write Python" in text
    p = first_prompt("add", "direct", "{}")
    assert "pytest is the judge" in p
