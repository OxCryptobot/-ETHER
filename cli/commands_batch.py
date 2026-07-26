"""Batch queue CLI helpers."""

from __future__ import annotations

import json
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from core.batch_queue import enqueue, status as queue_status, seed_smoke, load_queue
from scripts.batch_worker import drain

batch_app = typer.Typer(name="batch", help="Batch queue: enqueue, status, drain")
console = Console(force_terminal=True, soft_wrap=True)


@batch_app.command("status")
def batch_status(json_out: bool = typer.Option(False, "--json")) -> None:
    st = queue_status()
    if json_out:
        console.print_json(json.dumps(st))
        return
    console.print(
        f"pending={st['pending']}  done={st['done']}  "
        f"ok={st['done_ok']}  fail={st['done_fail']}  next={st.get('next')}"
    )
    if st.get("pending_titles"):
        for t in st["pending_titles"]:
            console.print(f"  · {t}")


@batch_app.command("enqueue")
def batch_enqueue(
    title: str = typer.Option(..., "--title", "-t"),
    objective: str = typer.Option("", "--objective", "-o"),
    kind: str = typer.Option("pipeline", "--kind", help="pipeline | command"),
    command: Optional[List[str]] = typer.Option(None, "--cmd", help="Command argv for kind=command"),
    priority: int = typer.Option(100, "--priority", "-p"),
) -> None:
    if kind == "pipeline" and not objective.strip():
        console.print("[red]pipeline requires --objective[/]")
        raise typer.Exit(1)
    if kind == "command" and not command:
        console.print("[red]command requires --cmd[/]")
        raise typer.Exit(1)
    item = enqueue(
        kind=kind,
        title=title,
        objective=objective,
        command=command,
        priority=priority,
    )
    console.print_json(json.dumps(item))


@batch_app.command("run")
def batch_run(
    limit: int = typer.Option(1, "--limit", "-n", help="Max items to process"),
) -> None:
    report = drain(limit=max(1, limit))
    console.print_json(json.dumps(report))
    raise typer.Exit(0 if report.get("ok") else 1)


@batch_app.command("seed")
def batch_seed(force: bool = typer.Option(False, "--force")) -> None:
    out = seed_smoke(force=force)
    console.print_json(json.dumps(out))


@batch_app.command("list")
def batch_list(show_done: bool = typer.Option(False, "--done")) -> None:
    data = load_queue()
    pending = data.get("pending") or []
    table = Table(title="Pending")
    table.add_column("id")
    table.add_column("pri")
    table.add_column("kind")
    table.add_column("title")
    for item in pending:
        table.add_row(
            str(item.get("id", "")),
            str(item.get("priority", "")),
            str(item.get("kind", "")),
            str(item.get("title", ""))[:60],
        )
    console.print(table)
    if show_done:
        done = (data.get("done") or [])[-15:]
        t2 = Table(title="Recent done")
        t2.add_column("id")
        t2.add_column("ok")
        t2.add_column("title")
        t2.add_column("ver")
        for item in done:
            res = item.get("result") or {}
            t2.add_row(
                str(item.get("id", "")),
                "yes" if res.get("ok") else "no",
                str(item.get("title", ""))[:40],
                str(res.get("verification_score", "")),
            )
        console.print(t2)
