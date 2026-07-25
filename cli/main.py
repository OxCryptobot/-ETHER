"""@ETHER CLI entrypoint."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from core.registry import build_default_registry
from core.pipeline import Pipeline
from core.schemas import (
    Envelope,
    SeleniteRequest,
    ClearQuartzRequest,
    RoseQuartzRequest,
    BlackTourmalineRequest,
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
    console.print("[bold cyan]@ETHER[/] v0.1.0")


@app.command()
def status() -> None:
    registry = build_default_registry()
    gems = registry.list_gems()
    table = Table(title="@ETHER Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    for name in ["Core", "Orchestrator", "Registry", "Pipeline"]:
        table.add_row(name, "✓")
    for gem in [
        "clear-quartz", "rose-quartz", "citrine", "selenite",
        "amethyst", "black-tourmaline", "labradorite", "grandidierite",
    ]:
        table.add_row(gem, "✓" if gem in gems else "✗")
    console.print(table)
    console.print(f"[dim]Registered: {len(gems)}/8[/]")


@app.command("run-gem")
def run_gem(gem: str, prompt: str = "Hello") -> None:
    registry = build_default_registry()
    if gem == "selenite":
        payload = SeleniteRequest(user_query=prompt)
    elif gem == "clear-quartz":
        payload = ClearQuartzRequest(code=prompt)
    elif gem == "rose-quartz":
        payload = RoseQuartzRequest(messages=[ChatMessage(role="user", content=prompt)])
    else:
        payload = SeleniteRequest(user_query=prompt)
    req = Envelope(task_id=uuid4(), target_gem=gem, payload=payload)  # type: ignore
    res = registry.execute(req)
    if res.error:
        console.print(f"[red]{res.error.message}[/]")
    else:
        console.print(Panel(str(res.payload), title=gem))


@app.command()
def plan(prompt: str) -> None:
    registry = build_default_registry()
    req = Envelope(task_id=uuid4(), target_gem="selenite", payload=SeleniteRequest(user_query=prompt))
    res = registry.execute(req)
    if res.error:
        console.print(f"[red]{res.error.message}[/]")
        return
    p = res.payload
    if hasattr(p, "plan"):
        for s in p.plan.steps:
            console.print(f"  {s.id}. [{s.action}] {s.description}")


@app.command()
def run(
    objective: str = typer.Argument(...),
    json_out: bool = typer.Option(False, "--json", help="Emit JSON result"),
) -> None:
    """Full pipeline: plan → code → sandbox → audit."""
    result = Pipeline().run(objective)

    if json_out:
        console.print_json(result.model_dump_json())
        if result.status == "error":
            raise typer.Exit(1)
        return

    if result.status == "error":
        console.print(Panel(f"[red]{result.error}[/]", title="Pipeline Error"))
        raise typer.Exit(1)

    if result.plan:
        console.print("[bold]Plan[/]")
        for s in result.plan.steps:
            console.print(f"  {s.id}. [{s.action}] {s.description}")
        console.print()

    if result.generated_code:
        console.print("[bold]Code[/]")
        console.print(Syntax(result.generated_code, "python", theme="monokai", line_numbers=True))
        console.print()

    if result.sandbox:
        console.print("[bold]Sandbox[/]")
        console.print(f"  exit={result.sandbox.exit_code}  time={result.sandbox.execution_time}s")
        console.print(f"  flags={result.sandbox.security_flags or 'clean'}")
        console.print()

    if result.audit:
        tag = "[green]APPROVED[/]" if result.audit.approved else "[red]REJECTED[/]"
        console.print(f"[bold]Audit[/] {tag} risk={result.audit.risk_score}")

    color = "green" if result.confidence >= 0.7 else "yellow" if result.confidence >= 0.4 else "red"
    console.print(f"[bold]Confidence:[/] [{color}]{result.confidence:.3f}[/{color}]")


@app.command()
def audit(
    path: Path = typer.Argument(..., exists=True, readable=True),
) -> None:
    """Run Black Tourmaline security audit on a file."""
    code = path.read_text(encoding="utf-8")
    registry = build_default_registry()
    req = Envelope(
        task_id=uuid4(),
        target_gem="black-tourmaline",
        payload=BlackTourmalineRequest(artifact=code, artifact_type="code"),
    )
    res = registry.execute(req)
    if res.error:
        console.print(f"[red]{res.error.message}[/]")
        raise typer.Exit(1)
    payload = res.payload
    tag = "[green]APPROVED[/]" if payload.approved else "[red]REJECTED[/]"
    console.print(f"{tag}  risk={payload.risk_score}")
    for v in payload.violations:
        console.print(f"  [{v.severity}] {v.rule}: {v.message}")


if __name__ == "__main__":
    app()
