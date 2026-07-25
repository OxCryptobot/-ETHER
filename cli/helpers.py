"""Small CLI helpers."""

from __future__ import annotations

from rich.console import Console

console = Console()


def print_error(msg: str) -> None:
    console.print(f"[red]{msg}[/]")


def print_ok(msg: str) -> None:
    console.print(f"[green]{msg}[/]")
