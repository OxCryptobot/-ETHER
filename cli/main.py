"""@ETHER CLI entrypoint."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from uuid import uuid4

from core.orchestrator import Orchestrator, Status
from core.registry import build_default_registry
from core.schemas import (
    Envelope,
    SeleniteRequest,
    ClearQuartzRequest,
    RoseQuartzRequest,
    ChatMessage,
)

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
    """Show system status and registered gems."""
    registry = build_default_registry()
    gems = registry.list_gems()

    table = Table(title="@ETHER Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")

    table.add_row("Core Schemas", "✓")
    table.add_row("Orchestrator", "✓")
    table.add_row("Registry", "✓")

    for gem in [
        "clear-quartz",
        "rose-quartz",
        "citrine",
        "selenite",
        "amethyst",
        "black-tourmaline",
        "labradorite",
        "grandidierite",
    ]:
        status_icon = "✓" if gem in gems else "✗"
        table.add_row(gem, status_icon)

    console.print(table)
    console.print(f"\n[dim]Registered gems: {len(gems)}/8[/]")


@app.command("run-gem")
def run_gem(
    gem: str = typer.Argument(..., help="Gem name (e.g. selenite, clear-quartz)"),
    prompt: str = typer.Option("Hello from @ETHER", help="Input for the gem"),
) -> None:
    """Run a single gem directly (for testing)."""
    registry = build_default_registry()

    try:
        if gem == "selenite":
            payload = SeleniteRequest(user_query=prompt)
        elif gem == "clear-quartz":
            payload = ClearQuartzRequest(code=prompt)
        elif gem == "rose-quartz":
            payload = RoseQuartzRequest(
                messages=[ChatMessage(role="user", content=prompt)]
            )
        else:
            console.print(f"[yellow]Direct testing for {gem} not fully wired yet. Using generic path.[/]")
            payload = SeleniteRequest(user_query=prompt)

        request = Envelope(
            task_id=uuid4(),
            target_gem=gem,  # type: ignore
            payload=payload,
        )

        response = registry.execute(request)

        if response.error:
            console.print(Panel(f"[red]{response.error.message}[/]", title="Error"))
        else:
            console.print(Panel(str(response.payload), title=f"{gem} Response"))

    except KeyError:
        console.print(f"[red]Gem '{gem}' is not registered.[/]")
    except Exception as e:
        console.print(f"[red]Failed: {e}[/]")


@app.command()
def plan(
    prompt: str = typer.Argument(..., help="What should @ETHER plan?"),
) -> None:
    """Generate a plan using Selenite."""
    registry = build_default_registry()

    request = Envelope(
        task_id=uuid4(),
        target_gem="selenite",
        payload=SeleniteRequest(user_query=prompt),
    )

    response = registry.execute(request)

    if response.error:
        console.print(f"[red]Error: {response.error.message}[/]")
        return

    plan_data = response.payload
    console.print(Panel(f"[bold]Query:[/] {prompt}", title="Selenite Plan"))

    if hasattr(plan_data, "plan"):
        for step in plan_data.plan.steps:
            deps = f" (depends on {step.deps})" if step.deps else ""
            console.print(f"  {step.id}. [{step.action}] {step.description}{deps}")
        console.print(f"\n[dim]{plan_data.plan.reasoning}[/]")
    else:
        console.print(plan_data)


if __name__ == "__main__":
    app()
