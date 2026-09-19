"""Phase G tool extensions — mixin for ToolRuntime."""
from __future__ import annotations
from core.tool_runtime_ext_g import EXTRA_SPECS, ToolExtMixin

__all__ = ["EXTRA_SPECS", "ToolExtMixin"]

try:
    from core.hard_live_boot import patch_runtime
    patch_runtime()
except Exception as exc:  # pragma: no cover
    import sys
    print("hard_live_boot skipped:", type(exc).__name__, exc, file=sys.stderr)

try:
    from core.mutate_doctrine import apply as apply_mutate_doctrine
    apply_mutate_doctrine()
except Exception as exc:  # pragma: no cover
    import sys
    print("mutate_doctrine skipped:", type(exc).__name__, exc, file=sys.stderr)

try:
    from core.tool_runtime import ToolRuntime
    from core.tool_runtime_kernel import install as install_kernel
    install_kernel(ToolRuntime)
except Exception as exc:  # pragma: no cover
    import sys
    print("phase4 kernel wire skipped:", type(exc).__name__, exc, file=sys.stderr)
