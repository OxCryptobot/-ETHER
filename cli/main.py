"""@ETHER CLI entrypoint."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from uuid import uuid4

from core.registry import build_default_registry
from core.pipeline import Pipeline
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
    table.add_row("Pipeline", "✓")

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
        icon = "✓" if gem in gems else "✗"
        table.add_row(gem, icon)

    console.print(table)
    console.print(f"\n[dim]Registered gems: {len(gems)}/8[/]")


@app.command("run-gem")
def run_gem(
    gem: str = typer.Argument(..., help="Gem name"),
    prompt: str = typer.Option("Hello from @ETHER", help="Input"),
) -> None:
    """Run a single gem directly."""
    registry = build_default_registry()

    try:
        if gem == "selenite":
            payload = SeleniteRequest(user_query=prompt)
        elif gem == "clear-quartz":
            payload = ClearQuartzRequest(code=prompt)
        elif gem == "rose-quartz":
            payload = RoseQuartzRequest(messages=[ChatMessage(role="user", content=prompt)])
        else:
            payload = SeleniteRequest(user_query=prompt)

        request = Envelope(task_id=uuid4(), target_gem=gem, payload=payload)  # type: ignore
        response = registry.execute(request)

        if response.error:
            console.print(Panel(f"[red]{response.error.message}[/]", title="Error"))
        else:
            console.print(Panel(str(response.payload), title=f"{gem} Response"))
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
            deps = f" (deps {step.deps})" if step.deps else ""
            console.print(f"  {step.id}. [{step.action}] {step.description}{deps}")
        console.print(f"\n[dim]{plan_data.plan.reasoning}[/]")
    else:
        console.print(plan_data)


@app.command()
def run(
    objective: str = typer.Argument(..., help="What should @ETHER accomplish?"),
) -> None:
    """Run full pipeline: plan → code → sandbox → audit."""
    console.print(f"[bold cyan]@ETHER[/] running: {objective}\n")

    pipeline = Pipeline()
    result = pipeline.run(objective)

    if result.status == "error":
        console.print(Panel(f"[red]{result.error}[/]", title="Pipeline Error"))
        raise typer.Exit(code=1)

    # Plan
    if result.plan:
        console.print("[bold]Plan[/]")
        for step in result.plan.steps:
            console.print(f"  {step.id}. [{step.action}] {step.description}")
        console.print()

    # Code
    if result.generated_code:
        console.print("[bold]Generated Code[/]")
        console.print(Syntax(result.generated_code, "python", theme="monokai", line_numbers=True))
        console.print()

    # Sandbox
    if result.sandbox:
        console.print("[bold]Sandbox[/]")
        console.print(f"  exit_code : {result.sandbox.exit_code}")
        console.print(f"  time      : {result.sandbox.execution_time}s")
        console.print(f"  security  : {result.sandbox.security_flags or 'clean'}")
        if result.sandbox.stdout:
            console.print(f"  stdout    : {result.sandbox.stdout[:300]}")
        if result.sandbox.stderr:
            console.print(f"  stderr    : {result.sandbox.stderr[:300]}")
        console.print()

    # Audit
    if result.audit:
        status = "[green]APPROVED[/]" if result.audit.approved else "[red]REJECTED[/]"
        console.print(f"[bold]Audit[/] {status}  risk={result.audit.risk_score}")
        for v in result.audit.violations:
            console.print(f"  - [{v.severity}] {v.rule}: {v.message}")
        console.print()

    # Confidence
    color = "green" if result.confidence >= 0.7 else "yellow" if result.confidence >= 0.4 else "red"
    console.print(f"[bold]Confidence:[/] [{color}]{result.confidence:.3f}[/{color}]")


if __name__ == "__main__":
    app()
