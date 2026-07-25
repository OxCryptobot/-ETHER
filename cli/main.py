"""@ETHER CLI."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from core.registry import build_default_registry
from core.pipeline import Pipeline
from core.config import load_config
from core.schemas import Envelope, SeleniteRequest, BlackTourmalineRequest, CitrineRequest
from cli.helpers import print_error, print_ok

app = typer.Typer(name="ether", help="@ETHER", add_completion=False)
console = Console()


@app.command()
def version(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    console.print("[bold cyan]@ETHER[/] v0.1.0")
    if verbose:
        console.print("Pipeline: plan → code → sandbox → audit (+ optional critique)")
        console.print("Gems: 8  |  License: MIT")


@app.command()
def which() -> None:
    console.print(f"python: {sys.executable}")
    console.print(f"cwd: {Path.cwd()}")
    console.print(f"manifest: {Path('config/manifest.yaml').resolve()}")
    console.print(f"runs: {Path('memory/runs').resolve()}")


@app.command()
def env() -> None:
    for k in ["OLLAMA_BASE_URL", "QDRANT_URL", "ETHER_PRIMARY_MODEL", "ETHER_EMBED_MODEL", "ETHER_SANDBOX_TIMEOUT"]:
        console.print(f"{k}={os.getenv(k, '')}")


@app.command()
def status() -> None:
    try:
        load_config(); print_ok("manifest: ok")
    except Exception as e:
        print_error(f"manifest: {e}")
    gems = build_default_registry().list_gems()
    table = Table(title="@ETHER")
    table.add_column("Gem"); table.add_column("Registered")
    for g in ["clear-quartz","rose-quartz","citrine","selenite","amethyst","black-tourmaline","labradorite","grandidierite"]:
        table.add_row(g, "yes" if g in gems else "no")
    console.print(table)


@app.command()
def doctor(json_out: bool = typer.Option(False, "--json")) -> None:
    checks = {
        "docker": shutil.which("docker") is not None,
        "ollama": shutil.which("ollama") is not None,
        "manifest": True,
        "registry": True,
    }
    try:
        load_config()
    except Exception:
        checks["manifest"] = False
    try:
        build_default_registry()
    except Exception:
        checks["registry"] = False
    if json_out:
        console.print_json(json.dumps(checks))
        raise typer.Exit(0 if all(checks.values()) else 1)
    for name, ok in checks.items():
        console.print(f"  {'[green]✓[/]' if ok else '[red]✗[/]'} {name}")


@app.command()
def gems() -> None:
    reg = build_default_registry()
    for name in reg.list_gems():
        console.print(f"  {name:20} {type(reg.get(name)).__name__}")


@app.command()
def ping() -> None:
    """Ping each registered gem with a harmless request where possible."""
    reg = build_default_registry()
    for name in reg.list_gems():
        try:
            reg.get(name)
            console.print(f"  [green]✓[/] {name}")
        except Exception as e:
            console.print(f"  [red]✗[/] {name}: {e}")


@app.command()
def plan(prompt: str) -> None:
    res = build_default_registry().execute(Envelope(task_id=uuid4(), target_gem="selenite", payload=SeleniteRequest(user_query=prompt)))
    if res.error:
        print_error(res.error.message); return
    for s in res.payload.plan.steps:  # type: ignore
        console.print(f"  {s.id}. [{s.action}] {s.description}")


@app.command()
def run(objective: str, json_out: bool = typer.Option(False, "--json"), critique: bool = typer.Option(False, "--critique")) -> None:
    if not objective.strip():
        print_error("Objective cannot be empty."); raise typer.Exit(1)
    result = Pipeline().run(objective, critique=critique)
    if json_out:
        console.print_json(result.model_dump_json()); raise typer.Exit(0 if result.status == "complete" else 1)
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
    if result.critique:
        console.print(f"Critique: {result.critique.critique}")
    for st in result.stages:
        console.print(f"  stage:{st.stage:10} ok={st.success} {st.duration_ms:.0f}ms {st.detail}")
    console.print(f"Confidence: {result.confidence:.3f}")


@app.command()
def audit(path: Path = typer.Argument(..., exists=True)) -> None:
    code = path.read_text(encoding="utf-8")
    res = build_default_registry().execute(Envelope(task_id=uuid4(), target_gem="black-tourmaline", payload=BlackTourmalineRequest(artifact=code)))
    if res.error:
        print_error(res.error.message); raise typer.Exit(1)
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
    res = build_default_registry().execute(Envelope(task_id=uuid4(), target_gem="citrine", payload=CitrineRequest(action="add", collection=collection, documents=docs)))
    if res.error:
        print_error(res.error.message); raise typer.Exit(1)
    print_ok(f"Indexed {len(docs)} docs")


@app.command()
def search(query: str, collection: str = "code", top_k: int = 5) -> None:
    res = build_default_registry().execute(Envelope(task_id=uuid4(), target_gem="citrine", payload=CitrineRequest(action="search", query=query, collection=collection, top_k=top_k)))
    if res.error:
        print_error(res.error.message); raise typer.Exit(1)
    for r in res.payload.results:  # type: ignore
        console.print(f"[{r.score:.3f}] {r.metadata.get('path', r.id)}\n  {r.text[:200]}\n")


@app.command()
def runs() -> None:
    runs_dir = Path("memory/runs")
    if not runs_dir.exists():
        console.print("[dim]No runs yet.[/]"); return
    files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            console.print(f"{data.get('started_at', '?'):25} {data.get('status', '?'):10} {data.get('objective', '')[:60]}")
        except Exception:
            console.print(f.name)


@app.command("clean-runs")
def clean_runs(force: bool = typer.Option(False, "--force")) -> None:
    runs_dir = Path("memory/runs")
    files = list(runs_dir.glob("*.json")) if runs_dir.exists() else []
    if not files:
        console.print("[dim]No runs to clean.[/]"); return
    if not force:
        console.print(f"Will delete {len(files)} run files. Re-run with --force to confirm.")
        return
    for f in files:
        f.unlink(missing_ok=True)
    print_ok(f"Deleted {len(files)} runs.")


@app.command()
def promote(filename: str) -> None:
    src = Path("tools/quarantine") / filename
    dst_dir = Path("tools/persistent"); dst_dir.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        print_error(f"Not found: {src}"); raise typer.Exit(1)
    dst = dst_dir / src.name
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print_ok(f"Promoted {src} → {dst}")


@app.command()
def quarantine() -> None:
    d = Path("tools/quarantine")
    files = sorted(p for p in d.glob("*.py")) if d.exists() else []
    if not files:
        console.print("[dim]Quarantine empty.[/]"); return
    for f in files:
        console.print(f"  {f.name}")


@app.command()
def tools() -> None:
    d = Path("tools/persistent")
    files = sorted(p for p in d.glob("*.py")) if d.exists() else []
    if not files:
        console.print("[dim]No persistent tools.[/]"); return
    for f in files:
        console.print(f"  {f.name}")


if __name__ == "__main__":
    app()
