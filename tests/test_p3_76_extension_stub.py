"""p3_76 FAST: Grandidierite template no longer raises NotImplementedError."""
from __future__ import annotations

from gems.grandidierite.extension import Grandidierite
from gems.grandidierite.fabricate import ast_validate


def test_template_has_main_and_no_raise() -> None:
    tmpl = Grandidierite.TEMPLATES["basic_python_tool"]
    code = tmpl.format(docstring="echo", name="echo_tool", args="")
    assert "NotImplementedError" not in code
    assert ast_validate(code)["ok"] is True
