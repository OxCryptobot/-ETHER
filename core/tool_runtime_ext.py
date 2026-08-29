"""Phase G tool extensions — mixin for ToolRuntime.

Implementation is in core.tool_runtime_ext_g so this file can stay a short
shim plus hard-LIVE boot.
"""
from __future__ import annotations

from core.tool_runtime_ext_g import EXTRA_SPECS, ToolExtMixin

__all__ = ["EXTRA_SPECS", "ToolExtMixin"]

try:
    from core.hard_live_boot import patch_runtime

    patch_runtime()
except Exception:
    pass
