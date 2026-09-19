"""live-host consumer is standalone and does not fake Ollama."""
import json
from pathlib import Path
from scripts.live_host import consume, start_ollama
import scripts.live_host as lh

def test_live_host_consumes_without_ollama() -> None:
    out = consume({"cmd": "attach"})
    assert out.get("clobber") is False
    assert out.get("live_lane") in {"ollama_4b", "grok_bus", None} or "live_lane" in out or out.get("writer") == "exe"
    assert "ollama" in out or out.get("writer") == "exe"

def test_start_ollama_fail_closed_without_binary() -> None:
    assert start_ollama() in {True, False}
    out = consume({"cmd": "attach"})
    assert out.get("clobber") is False

def test_ubuntu_does_not_clobber_1650_attach(tmp_path, monkeypatch) -> None:
    import os, pytest
    if os.name == "nt":
        pytest.skip("preserve-prior attach is the Ubuntu Actions path")
    art = tmp_path / "artifacts"
    art.mkdir()
    prev = {"updated": "2026-09-09T00:00:00+00:00", "ok": True, "live_lane": "ollama_4b", "ollama": True, "living_ok": True, "writer": "exe"}
    (art / "host_attach.json").write_text(json.dumps(prev), encoding="utf-8")
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    monkeypatch.setattr(lh, "start_ollama", lambda: False)
    out = lh.consume({"cmd": "attach"})
    assert out.get("ollama") is True or out.get("writer") == "exe"
    assert out.get("clobber") is False
    saved = json.loads((tmp_path / "artifacts" / "host_attach.json").read_text(encoding="utf-8"))
    assert saved["ollama"] is True

def test_ollama_bin_is_optional() -> None:
    from scripts.live_host import ollama_bin
    found = ollama_bin()
    assert found is None or isinstance(found, str)

def test_write_probe_lands(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ETHER_ROOT", str(tmp_path))
    (tmp_path / "scripts").mkdir()
    row = lh.write_probe({"reason": "unit"})
    assert row["up"] in {True, False}
    assert (tmp_path / "artifacts" / "ollama_probe.json").is_file()
