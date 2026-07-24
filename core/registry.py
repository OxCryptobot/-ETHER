"""Central gem registry for @ETHER."""

from __future__ import annotations

from typing import Dict, Type, Any, Callable

from core.schemas import Envelope, ResponseEnvelope


class GemRegistry:
    """Simple in-process registry that maps gem names to executable instances."""

    def __init__(self):
        self._gems: Dict[str, Any] = {}

    def register(self, name: str, gem: Any) -> None:
        self._gems[name] = gem

    def get(self, name: str) -> Any:
        if name not in self._gems:
            raise KeyError(f"Gem '{name}' is not registered")
        return self._gems[name]

    def execute(self, request: Envelope) -> ResponseEnvelope:
        gem = self.get(request.target_gem)
        return gem.execute(request)

    def list_gems(self) -> list[str]:
        return list(self._gems.keys())


def build_default_registry() -> GemRegistry:
    """Create and populate the default registry with all available gems."""
    registry = GemRegistry()

    try:
        from gems.clear_quartz import ClearQuartz
        registry.register("clear-quartz", ClearQuartz())
    except Exception:
        pass

    try:
        from gems.rose_quartz import RoseQuartz
        registry.register("rose-quartz", RoseQuartz())
    except Exception:
        pass

    try:
        from gems.citrine import Citrine
        registry.register("citrine", Citrine())
    except Exception:
        pass

    try:
        from gems.selenite import Selenite
        registry.register("selenite", Selenite())
    except Exception:
        pass

    try:
        from gems.amethyst import Amethyst
        registry.register("amethyst", Amethyst())
    except Exception:
        pass

    try:
        from gems.black_tourmaline import BlackTourmaline
        registry.register("black-tourmaline", BlackTourmaline())
    except Exception:
        pass

    try:
        from gems.labradorite import Labradorite
        registry.register("labradorite", Labradorite())
    except Exception:
        pass

    try:
        from gems.grandidierite import Grandidierite
        registry.register("grandidierite", Grandidierite())
    except Exception:
        pass

    return registry
