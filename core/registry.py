"""Central gem registry for @ETHER."""

from __future__ import annotations

from typing import Dict, Any

from core.schemas import Envelope, ResponseEnvelope


class GemRegistry:
    def __init__(self):
        self._gems: Dict[str, Any] = {}

    def register(self, name: str, gem: Any) -> None:
        self._gems[name] = gem

    def get(self, name: str) -> Any:
        if name not in self._gems:
            known = ", ".join(sorted(self._gems)) or "<none>"
            raise KeyError(f"Gem '{name}' is not registered. Known gems: {known}")
        return self._gems[name]

    def execute(self, request: Envelope) -> ResponseEnvelope:
        gem = self.get(request.target_gem)
        return gem.execute(request)

    def list_gems(self) -> list[str]:
        return list(self._gems.keys())


def build_default_registry() -> GemRegistry:
    registry = GemRegistry()
    loaders = [
        ("clear-quartz", "gems.clear_quartz", "ClearQuartz"),
        ("rose-quartz", "gems.rose_quartz", "RoseQuartz"),
        ("citrine", "gems.citrine", "Citrine"),
        ("selenite", "gems.selenite", "Selenite"),
        ("amethyst", "gems.amethyst", "Amethyst"),
        ("black-tourmaline", "gems.black_tourmaline", "BlackTourmaline"),
        ("labradorite", "gems.labradorite", "Labradorite"),
        ("grandidierite", "gems.grandidierite", "Grandidierite"),
    ]
    for name, module_name, cls_name in loaders:
        try:
            mod = __import__(module_name, fromlist=[cls_name])
            registry.register(name, getattr(mod, cls_name)())
        except Exception:
            pass
    return registry
