"""Gem registry — import side-effect wires pipeline boot hooks."""

from __future__ import annotations

from typing import Dict

from core.schemas import Envelope, ResponseEnvelope, GemError, GemErrorType


class GemRegistry:
    def __init__(self) -> None:
        self._gems: Dict[str, object] = {}

    def register(self, name: str, gem: object) -> None:
        self._gems[name] = gem

    def get(self, name: str):
        return self._gems.get(name)

    def execute(self, request: Envelope) -> ResponseEnvelope:
        gem = self._gems.get(request.target_gem)
        if gem is None:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem=request.target_gem,  # type: ignore
                error=GemError(
                    type=GemErrorType.UNKNOWN,
                    message=f"Unknown gem: {request.target_gem}",
                    recoverable=False,
                ),
            )
        return gem.execute(request)  # type: ignore


def build_default_registry() -> GemRegistry:
    from gems.clear_quartz.sandbox import ClearQuartz
    from gems.rose_quartz.router import RoseQuartz
    from gems.selenite.planner import Selenite
    from gems.black_tourmaline.auditor import BlackTourmaline
    from gems.labradorite.critic import Labradorite
    from gems.amethyst.logger import Amethyst
    from gems.grandidierite.fabricator import Grandidierite

    # optional citrine
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
    except Exception:
        pass

    try:
        from core.pipeline_boot import apply

        apply()
    except Exception:
        pass

    return reg
