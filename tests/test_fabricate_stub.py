import os

from gems.grandidierite.fabricate import fabricate


def test_fabricate_stub_only(tmp_path, monkeypatch):
    monkeypatch.setenv("ETHER_FABRICATE_STUB_ONLY", "1")
    monkeypatch.setenv("ETHER_AUTO_PROMOTE", "0")
    # redirect quarantine via chdir semantics — fabricate uses ROOT constant;
    # just ensure function returns structured result
    result = fabricate({"name": "demo_stub_tool", "docstring": "demo", "stub_only": True})
    assert result["name"] == "demo_stub_tool"
    assert "stages" in result
    assert result["quarantine_path"].endswith(".py")
