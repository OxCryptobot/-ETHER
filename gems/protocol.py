"""Typed gem surface. Folders stay; this is the contract Pipeline can import."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional, Tuple

Status = Literal["live", "partial", "theatre", "gated"]


@dataclass(frozen=True)
class GemSpec:
    id: str
    name: str
    role: str
    status: Status
    package: str


GEMS: Tuple[GemSpec, ...] = (
    GemSpec("selenite", "Selenite", "Planner", "theatre", "gems.selenite"),
    GemSpec("rose_quartz", "Rose Quartz", "Router", "partial", "gems.rose_quartz"),
    GemSpec("clear_quartz", "Clear Quartz", "Sandbox", "live", "gems.clear_quartz"),
    GemSpec("citrine", "Citrine", "Memory", "partial", "gems.citrine"),
    GemSpec("labradorite", "Labradorite", "Profiler", "partial", "gems.labradorite"),
    GemSpec("amethyst", "Amethyst", "Evolution", "theatre", "gems.amethyst"),
    GemSpec("black_tourmaline", "Black Tourmaline", "Security", "partial", "gems.black_tourmaline"),
    GemSpec("grandidierite", "Grandidierite", "Fabricate", "gated", "gems.grandidierite"),
)


def by_id(gid: str) -> Optional[GemSpec]:
    for gem in GEMS:
        if gem.id == gid:
            return gem
    return None


def live_gems() -> Tuple[GemSpec, ...]:
    return tuple(g for g in GEMS if g.status == "live")
