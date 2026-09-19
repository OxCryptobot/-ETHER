"""Phase-5 close remaining doctrine holes."""
from core.kernel.agent_pass import finalize_coding_result
from core.kernel.attach import attach_payload
from core.kernel.redact import redact
from core.kernel.tombstone import body
from core.kernel.writer import allow_attach_write
import os

def test_ubuntu_cannot_write_attach() -> None:
    if os.name == "nt":
        assert allow_attach_write(ollama_up=True) is True
        return
    assert allow_attach_write(ollama_up=False) is False
    may, row = attach_payload(ollama_up=False, prev={"writer": "exe", "ollama": True}, cmd="attach")
    assert may is False and row["clobber"] is False and row["writer"] == "exe"

def test_generate_cannot_pass() -> None:
    row = finalize_coding_result({"ok": True, "tools": ["write_file"]}, path="generate")
    assert row["ok"] is False and row["honest"] is False

def test_redact_secrets() -> None:
    assert "[REDACTED]" in redact("api_key=sk-abcdefghijklmnop")

def test_tombstone_is_plain() -> None:
    assert b"410" in body() and b"<html" not in body()
