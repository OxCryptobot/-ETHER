"""p3_75 FAST: template fabricate + living stub path."""
from __future__ import annotations

from core.loop.living import fabricate_stub
from gems.grandidierite.fabricate import ast_validate, fabricate


def test_stub_only_writes_main() -> None:
    result = fabricate({"name": "p3_75_echo", "docstring": "FAST stub", "stub_only": True})
    assert result["name"] == "p3_75_echo"
    stages = {str(s.get("stage")): s for s in result.get("stages") or []}
    assert stages.get("implement", {}).get("mode") == "stub"
    assert "quarantine_path" in result


def test_ast_validate_stub_template() -> None:
    from gems.grandidierite.fabricate import STUB_TEMPLATE

    code = STUB_TEMPLATE.format(name="p3_75_echo", docstring="FAST stub")
    assert ast_validate(code)["ok"] is True


def test_living_fabricate_stub() -> None:
    result = fabricate_stub("p3_75_living", purpose="living batch stub")
    assert result["name"] == "p3_75_living"
    assert result.get("promoted") is False
