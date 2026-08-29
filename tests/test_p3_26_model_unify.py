"""P3 wave: Rose uses select_primary_model. No silent 3b. Host fallback not 8b."""
from __future__ import annotations

import os

import pytest

from core.model_select import resolved_fallback, resolved_primary
from gems.rose_quartz.router import RoseQuartz, decode_options


def test_resolved_primary_defaults_to_4b_not_3b(monkeypatch):
    monkeypatch.delenv("ETHER_PRIMARY_MODEL", raising=False)
    monkeypatch.setenv("ETHER_AUTO_MODEL", "0")
    monkeypatch.setenv("ETHER_HW_PROFILE", "host")
    # No Ollama: fallback_host_4b
    got = resolved_primary()
    assert "3b" not in got
    assert "4b" in got or got.startswith("qwen3")


def test_explicit_env_wins(monkeypatch):
    monkeypatch.setenv("ETHER_PRIMARY_MODEL", "qwen3.5:4b-q4_K_M")
    monkeypatch.setenv("ETHER_AUTO_MODEL", "0")
    assert resolved_primary() == "qwen3.5:4b-q4_K_M"


def test_host_rejects_8b_fallback(monkeypatch):
    monkeypatch.setenv("ETHER_HW_PROFILE", "host")
    monkeypatch.delenv("ETHER_PRIMARY_MODEL", raising=False)
    monkeypatch.setenv("ETHER_AUTO_MODEL", "0")
    got = resolved_fallback("deepseek-r1:8b")
    assert "8b" not in got.lower()


def test_rose_init_does_not_default_3b(monkeypatch):
    monkeypatch.delenv("ETHER_PRIMARY_MODEL", raising=False)
    monkeypatch.delenv("ETHER_FALLBACK_MODEL", raising=False)
    monkeypatch.setenv("ETHER_AUTO_MODEL", "0")
    monkeypatch.setenv("ETHER_HW_PROFILE", "host")
    r = RoseQuartz()
    assert r.primary_model != "qwen2.5-coder:3b"
    assert "8b" not in (r.fallback_model or "").lower()


def test_host_num_ctx_default_is_4k():
    opts = decode_options(256)
    assert opts["num_ctx"] == 4096
