"""@ETHER CLI."""

from __future__ import annotations

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
    CitrineRequest,
    ChatMessage,
)

app = typer.Typer(name="ether", help="@ETHER agentic coding system", add_completion=False)
console = Console()


@app.command()
def version() -> None:
    console.print("[bold cyan]@ETHER[/] v0.1.0")


@app.command()
def status() -> None:
    gems = build_default_registry().list_gems()
    table = Table(title="@ETHER")
    table.add_column("Component")
    table.add_column("Status")
    for g in ["clear-quartz","rose-quartz","citrine","selenite","amethyst","black-tourmaline","labradorite","grandidierite"]:
        table.add_row(g, "✓" if g in gems else "✗")
    console.print(table)


@app.command()
def plan(prompt: str) -> None:
    res = build_default_registry().execute(Envelope(task_id=uuid4(), target_gem="selenite", payload=SeleniteRequest(user_query=prompt)))
    if res.error:
        console.print(f"[red]{res.error.message}[/]"); return
    for s in res.payload.plan.steps:  # type: ignore
        console.print(f"  {s.id}. [{s.action}] {s.description}")


@app.command()
def run(objective: str, json_out: bool = typer.Option(False, "--json")) -> None:
    result = Pipeline().run(objective)
    if json_out:
        console.print_json(result.model_dump_json())
        raise typer.Exit(1 if result.status == "error" else 0)
    if result.status == "error":
        console.print(Panel(f"[red]{result.error}[/]", title="Error")); raise typer.Exit(1)
    if result.plan:
        for s in result.plan.steps:
            console.print(f"  {s.id}. [{s.action}] {s.description}")
    if result.generated_code:
        console.print(Syntax(result.generated_code, "python", theme="monokai", line_numbers=True))
    if result.sandbox:
        console.print(f"Sandbox exit={result.sandbox.exit_code} time={result.sandbox.execution_time}s")
    if result.audit:
        console.print(f"Audit approved={result.audit.approved} risk={result.audit.risk_score}")
    console.print(f"Confidence: {result.confidence:.3f}")


@app.command()
def audit(path: Path = typer.Argument(..., exists=True)) -> None:
    code = path.read_text(encoding="utf-8")
    res = build_default_registry().execute(Envelope(task_id=uuid4(), target_gem="black-tourmaline", payload=BlackTourmalineRequest(artifact=code)))
    if res.error:
        console.print(f"[red]{res.error.message}[/]"); raise typer.Exit(1)
    p = res.payload
    console.print(f"approved={p.approved} risk={p.risk_score}")  # type: ignore
    for v in p.violations:  # type: ignore
        console.print(f"  [{v.severity}] {v.rule}: {v.message}")


@app.command()
def index(path: Path = typer.Argument(..., exists=True), collection: str = "code") -> None:
    docs = []
    files = [path] if path.is_file() else list(path.rglob("*.py"))
    for f in files:
        try:
            docs.append({"text": f.read_text(encoding="utf-8", errors="ignore"), "metadata": {"path": str(f)}})
        except Exception:
            pass
    if not docs:
        console.print("[yellow]No files[/]"); return
    res = build_default_registry().execute(Envelope(task_id=uuid4(), target_gem="citrine", payload=CitrineRequest(action="add", collection=collection, documents=docs)))
    if res.error:
        console.print(f"[red]{res.error.message}[/]"); raise typer.Exit(1)
    console.print(f"Indexed {len(docs)} docs into '{collection}'")


@app.command()
def search(query: str, collection: str = "code", top_k: int = 5) -> None:
    res = build_default_registry().execute(Envelope(task_id=uuid4(), target_gem="citrine", payload=CitrineRequest(action="search", query=query, collection=collection, top_k=top_k)))
    if res.error:
        console.print(f"[red]{res.error.message}[/]"); raise typer.Exit(1)
    for r in res.payload.results:  # type: ignore
        console.print(f"[{r.score:.3f}] {r.metadata.get('path', r.id)}\n  {r.text[:200]}...\n")


if __name__ == "__main__":
    app()
