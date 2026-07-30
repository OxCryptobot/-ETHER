"""Gem registry."""

from __future__ import annotations

from typing import Dict, List

from core.schemas import Envelope, ResponseEnvelope, GemError, GemErrorType


class GemRegistry:
    def __init__(self) -> None:
        self._gems: Dict[str, object] = {}
        self.degraded: List[str] = []   # capabilities that failed to register (A-3)

    def register(self, name: str, gem: object) -> None:
        self._gems[name] = gem

    def get(self, name: str):
        return self._gems.get(name)

    def list_gems(self) -> List[str]:
        """Return registered gem names (used by health probes and diagnostics)."""
        return sorted(self._gems.keys())

    def execute(self, request: Envelope) -> ResponseEnvelope:
        gem = self._gems.get(request.target_gem)
        if gem is None:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem=request.target_gem,  # type: ignore[arg-type]
                error=GemError(
                    type=GemErrorType.UNKNOWN,
                    message=f"Unknown gem: {request.target_gem}",
                    recoverable=False,
                ),
            )
        return gem.execute(request)  # type: ignore[attr-defined]


def build_default_registry() -> GemRegistry:
    from gems.clear_quartz.sandbox import ClearQuartz
    from gems.rose_quartz.router import RoseQuartz
    from gems.selenite.planner import Selenite
    from gems.black_tourmaline.security import BlackTourmaline
    from gems.labradorite.profiler import Labradorite
    from gems.amethyst.evolution import Amethyst
    from gems.grandidierite.extension import Grandidierite

    reg = GemRegistry()
    reg.register("clear-quartz", ClearQuartz())
    reg.register("rose-quartz", RoseQuartz())
    reg.register("selenite", Selenite())
    reg.register("black-tourmaline", BlackTourmaline())
    reg.register("labradorite", Labradorite())
    reg.register("amethyst", Amethyst())
    reg.register("grandidierite", Grandidierite())
    try:
        from gems.citrine.memory import Citrine

        reg.register("citrine", Citrine())
    except Exception as e:
        # A-3: was a silent pass — a registry without memory looked identical
        # to a healthy one. Surface it; Pipeline seeds every run's degraded
        # list from this.
        reg.degraded.append(f"citrine_unavailable:{type(e).__name__}")

    # A `try: from core.pipeline_boot import apply; apply()` block used to sit
    # here. core.pipeline_boot never defined `apply`, so this raised ImportError
    # on every single call and the bare `except Exception: pass` swallowed it —
    # building the registry silently did nothing extra, and pipeline_boot /
    # pipeline_patch / intel_runtime stayed dead code with zero live callers.
    # The behaviour it was reaching for (contextual bandit selection) is now
    # wired directly where it belongs, in Pipeline.run via core.pipeline_select.
    return reg
