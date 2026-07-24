"""@ETHER CLI entrypoint."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from uuid import uuid4

from core.orchestrator import Orchestrator, Status
from core.schemas import Envelope, ClearQuartzRequest

app = typer.Typer(
    name="ether",
    help="@ETHER — Local-first, self-extending, verified agentic coding system",
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Show version information."""
    console.print("[bold cyan]@ETHER[/] v0.1.0")
    console.print("Local-first super-agentic coding system")


@app.command()
def status() -> None:
    """Show current system status."""
    console.print(Panel.fit(
        "[green]Core foundation loaded[/]\n"
        "• schemas.py ✓\n"
        "• orchestrator.py ✓\n"
        "• manifest.yaml ✓\n\n"
        "[dim]Gems not yet implemented[/]",
        title="@ETHER Status",
        border_style="cyan",
    ))


@app.command()
def try_task(
    prompt: str = typer.Argument(..., help="What do you want @ETHER to do?"),
) -> None:
    """Run a simple task through the orchestrator (skeleton)."""
    console.print(f"[bold]Task:[/] {prompt}")

    orch = Orchestrator()
    task_id = uuid4()
    state = orch.start(task_id)

    console.print(f"[dim]Started task {task_id} in state: {state.status.value}[/]")

    # Skeleton only — real gem dispatch comes later
    console.print("[yellow]Note:[/] Full gem pipeline not yet implemented.")
    console.print("This is the foundation. Next step: implement Clear Quartz + Rose Quartz.")


if __name__ == "__main__":
    app()
