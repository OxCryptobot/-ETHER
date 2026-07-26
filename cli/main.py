"""@ETHER CLI."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

try:
    from core.dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from core.registry import build_default_registry
from core.pipeline import Pipeline
from core.config import load_config
from core.paths import as_posix_str
from core.schemas import (
    Envelope,
    SeleniteRequest,
    BlackTourmalineRequest,
    CitrineRequest,
    GrandidieriteRequest,
)
from cli.helpers import print_error, print_ok

app = typer.Typer(name="ether", help="@ETHER", add_completion=False)
console = Console(force_terminal=True, soft_wrap=True)


def _safe(text: str) -> str:
    if text is None:
        return ""
    return text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")


@app.command()
def version(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    console.print("[bold cyan]@ETHER[/] v0.1.3")


@app.command()
def which() -> None:
    console.print(f"python: {sys.executable}")
    console.print(f"cwd: {Path.cwd()}")


@app.command()
def env() -> None:
    for k in [
        "OLLAMA_BASE_URL",
        "ETHER_PRIMARY_MODEL",
        "ETHER_SANDBOX_BACKEND",
        "ETHER_SANDBOX_PYTHON",
        "ETHER_LEARNING",
        "ETHER_TOOL_ASSIST",
        "ETHER_FLYWHEEL_PUSH",
        "ETHER_BURST",
        "ETHER_ROOT",
    ]:
        console.print(f"{k}={os.getenv(k, '')}")


@app.command()
def status() -> None:
    try:
        load_config()
        print_ok("manifest: ok")
    except Exception as e:
        print_error(f"manifest: {e}")
    gems = build_default_registry().list_gems()
    table = Table(title="@ETHER")
    table.add_column("Gem")
    table.add_column("Registered")
    for g in [
        "clear-quartz", "rose-quartz", "citrine", "selenite",
        "amethyst", "black-tourmaline", "labradorite", "grandidierite",
    ]:
        table.add_row(g, "yes" if g in gems else "no")
    console.print(table)


@app.command()
def doctor(json_out: bool = typer.Option(False, "--json")) -> None:
    backend = (os.getenv("ETHER_SANDBOX_BACKEND") or "auto").strip().lower()
    docker_ok = shutil.which("docker") is not None
    py_local = os.getenv("ETHER_SANDBOX_PYTHON") or ("python3" if sys.platform != "win32" else sys.executable)
    local_ok = shutil.which(py_local) is not None or Path(py_local).exists()
    if backend in ("local", "subprocess", "native"):
        sandbox_ok = local_ok
    elif backend == "docker":
        sandbox_ok = docker_ok
    else:
        sandbox_ok = docker_ok or local_ok

    checks = {
        "sandbox_backend": backend,
        "sandbox_ok": sandbox_ok,
        "docker": docker_ok,
        "local_python": local_ok,
        "ollama": shutil.which("ollama") is not None,
        "manifest": True,
        "registry": True,
        "primary_model": os.getenv("ETHER_PRIMARY_MODEL", ""),
    }
    try:
        load_config()
    except Exception:
        checks["manifest"] = False
    try:
        build_default_registry()
    except Exception:
        checks["registry"] = False

    critical = ["sandbox_ok", "ollama", "manifest", "registry"]
    ok_all = all(bool(checks[k]) for k in critical)

    if json_out:
        console.print_json(json.dumps(checks))
        raise typer.Exit(0 if ok_all else 1)
    for name in ["sandbox_backend", "sandbox_ok", "docker", "local_python", "ollama", "manifest", "registry", "primary_model"]:
        val = checks[name]
        if name in ("sandbox_backend", "primary_model"):
            console.print(f"  [cyan]·[/] {name}={val}")
        else:
            console.print(f"  {'[green]✓[/]' if val else '[red]✗[/]'} {name}")
    if backend in ("local", "auto") and not docker_ok:
        console.print("[dim]tip: Linux no-Docker → ETHER_SANDBOX_BACKEND=local (auto already falls back)[/]")


@app.command()
def gems() -> None:
    reg = build_default_registry()
    for name in reg.list_gems():
        console.print(f"  {name:20} {type(reg.get(name)).__name__}")


@app.command()
def ping() -> None:
    reg = build_default_registry()
    for name in reg.list_gems():
        try:
            reg.get(name)
            console.print(f"  [green]✓[/] {name}")
        except Exception as e:
            console.print(f"  [red]✗[/] {name}: {e}")


@app.command()
def plan(prompt: str) -> None:
    res = build_default_registry().execute(
        Envelope(task_id=uuid4(), target_gem="selenite", payload=SeleniteRequest(user_query=prompt))
    )
    if res.error:
        print_error(res.error.message)
        return
    payload = res.payload
    if getattr(payload, "needs_tool", False):
        console.print(f"[yellow]tool_request[/] {payload.tool_request}")  # type: ignore
    for s in payload.plan.steps:  # type: ignore
        console.print(f"  {s.id}. [{s.action}] {_safe(s.description)}")


@app.command()
def run(
    objective: str,
    json_out: bool = typer.Option(False, "--json"),
    critique: bool = typer.Option(False, "--critique"),
) -> None:
    if not objective.strip():
        print_error("Objective cannot be empty.")
        raise typer.Exit(1)
    result = Pipeline().run(objective, critique=critique)
    if json_out:
        console.print_json(result.model_dump_json())
        raise typer.Exit(0 if result.status == "complete" else 1)
    if result.status == "error":
        console.print(Panel(f"[red]{_safe(result.error or '')}[/]", title="Error"))
        raise typer.Exit(1)
    if result.plan:
        for s in result.plan.steps:
            console.print(f"  {s.id}. [{s.action}] {_safe(s.description)}")
    if result.generated_code:
        console.print(Syntax(_safe(result.generated_code), "python", theme="monokai", line_numbers=True))
    if result.sandbox:
        console.print(f"Sandbox exit={result.sandbox.exit_code} time={result.sandbox.execution_time}s")
        if result.sandbox.stdout:
            console.print(f"  stdout: {_safe(result.sandbox.stdout.strip())[:500]}")
        if result.sandbox.stderr:
            console.print(f"  stderr: {_safe(result.sandbox.stderr.strip())[:500]}")
    if result.audit:
        console.print(f"Audit approved={result.audit.approved} risk={result.audit.risk_score}")
    for st in result.stages:
        console.print(f"  stage:{st.stage:10} ok={st.success} {st.duration_ms:.0f}ms {_safe(st.detail)}")
    console.print(
        f"Confidence: {result.confidence:.3f}  strategy={getattr(result, 'strategy', '')} reward={getattr(result, 'reward', 0):.3f}"
    )


@app.command()
def flywheel(
    push: bool = typer.Option(False, "--push"),
    status: bool = typer.Option(False, "--status"),
    autonomous: bool = typer.Option(False, "--autonomous"),
    min_confidence: float = typer.Option(0.7, "--min-confidence"),
    max_retries: int = typer.Option(3, "--max-retries"),
    interval: int = typer.Option(900, "--interval"),
    no_doctor: bool = typer.Option(False, "--no-doctor"),
) -> None:
    from scripts.flywheel import main as flywheel_main

    argv: list[str] = []
    if status:
        argv.append("--status")
    elif autonomous:
        argv.extend(
            [
                "--autonomous",
                "--interval",
                str(interval),
                "--min-confidence",
                str(min_confidence),
                "--max-retries",
                str(max_retries),
            ]
        )
        if no_doctor:
            argv.append("--no-doctor")
    else:
        argv.extend(["--min-confidence", str(min_confidence), "--max-retries", str(max_retries)])
        if push:
            argv.append("--push")
        if no_doctor:
            argv.append("--no-doctor")
    raise typer.Exit(flywheel_main(argv))


@app.command()
def dashboard(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8787, "--port"),
) -> None:
    console.print(f"[bold cyan]@ETHER Dashboard[/] → http://{host}:{port}")
    import uvicorn

    uvicorn.run("dashboard.app:app", host=host, port=port, reload=False)


@app.command("learn-stats")
def learn_stats_cmd() -> None:
    from cli.commands_learn import learn_stats

    data = learn_stats()
    console.print_json(json.dumps(data))
    ranked = (data.get("bandit") or {}).get("arms") or {}
    table = Table(title="Strategy arms")
    table.add_column("Strategy")
    table.add_column("Pulls")
    table.add_column("Mean reward")
    for name, stats in sorted(ranked.items(), key=lambda kv: kv[1].get("mean_reward", 0), reverse=True):
        table.add_row(name, str(stats.get("pulls", 0)), f"{stats.get('mean_reward', 0):.4f}")
    console.print(table)
    streak = data.get("fail_streak") or {}
    console.print(f"fail_streak={streak.get('streak', 0)} proposed={streak.get('proposed')}")


@app.command()
def fabricate(
    name: str = typer.Option(..., "--name"),
    purpose: str = typer.Option(..., "--purpose"),
    stub_only: bool = typer.Option(False, "--stub-only"),
    auto_promote: bool = typer.Option(False, "--auto-promote"),
) -> None:
    if auto_promote:
        os.environ["ETHER_AUTO_PROMOTE"] = "1"
    if stub_only:
        os.environ["ETHER_FABRICATE_STUB_ONLY"] = "1"
    res = build_default_registry().execute(
        Envelope(
            task_id=uuid4(),
            target_gem="grandidierite",
            payload=GrandidieriteRequest(
                tool_request={
                    "action": "fabricate",
                    "name": name,
                    "docstring": purpose,
                    "purpose": purpose,
                    "stub_only": stub_only,
                }
            ),
        )
    )
    if res.error:
        print_error(res.error.message)
        raise typer.Exit(1)
    raw = res.payload.generated_code  # type: ignore
    try:
        data = json.loads(raw)
    except Exception:
        console.print(raw)
        raise typer.Exit(0)
    console.print_json(json.dumps(data))
    if data.get("validation_status") == "failed":
        raise typer.Exit(1)
    print_ok(f"fabricate status={data.get('validation_status')} quarantine={data.get('quarantine_path')}")


@app.command("tool-list")
def tool_list() -> None:
    from gems.grandidierite.registry import list_tools

    cat = list_tools()
    console.print("[bold]persistent[/]")
    for n in cat["persistent"]:
        console.print(f"  {n}")
    console.print("[bold]quarantine[/]")
    for n in cat["quarantine"]:
        console.print(f"  {n}")


@app.command("tool-run")
def tool_run(
    name: str = typer.Argument(...),
    payload: str = typer.Option("{}", "--payload"),
    payload_file: Path = typer.Option(None, "--payload-file", help="JSON file (avoids PowerShell quoting)"),
) -> None:
    from gems.grandidierite.registry import run_tool

    body: dict
    if payload_file is not None:
        if not payload_file.exists():
            print_error(f"payload file not found: {payload_file}")
            raise typer.Exit(1)
        try:
            body = json.loads(payload_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print_error(f"invalid JSON in file: {e}")
            raise typer.Exit(1)
    else:
        raw = payload
        if raw in ("-", "@-"):
            raw = sys.stdin.read()
        try:
            body = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as e:
            print_error(f"invalid JSON payload: {e}")
            print_error("Tip: ether tool-run NAME --payload-file path.json")
            raise typer.Exit(1)
    if not isinstance(body, dict):
        print_error("payload must be a JSON object")
        raise typer.Exit(1)
    result = run_tool(name, body)
    console.print_json(json.dumps(result))
    raise typer.Exit(0 if result.get("ok") else 1)


@app.command()
def audit(path: Path = typer.Argument(..., exists=True)) -> None:
    code = path.read_text(encoding="utf-8")
    res = build_default_registry().execute(
        Envelope(task_id=uuid4(), target_gem="black-tourmaline", payload=BlackTourmalineRequest(artifact=code))
    )
    if res.error:
        print_error(res.error.message)
        raise typer.Exit(1)
    p = res.payload
    console.print(f"approved={p.approved} risk={p.risk_score}")  # type: ignore
    for v in p.violations:  # type: ignore
        console.print(f"  [{v.severity}] {v.rule}: {_safe(v.message)}")


@app.command()
def index(path: Path = typer.Argument(..., exists=True), collection: str = "code") -> None:
    docs = []
    files = [path] if path.is_file() else list(path.rglob("*.py"))
    for f in files:
        try:
            docs.append({"text": f.read_text(encoding="utf-8", errors="ignore"), "metadata": {"path": as_posix_str(f)}})
        except Exception:
            pass
    res = build_default_registry().execute(
        Envelope(
            task_id=uuid4(),
            target_gem="citrine",
            payload=CitrineRequest(action="add", collection=collection, documents=docs),
        )
    )
    if res.error:
        print_error(res.error.message)
        raise typer.Exit(1)
    print_ok(f"Indexed {len(docs)} docs")


@app.command()
def search(query: str, collection: str = "code", top_k: int = 5) -> None:
    res = build_default_registry().execute(
        Envelope(
            task_id=uuid4(),
            target_gem="citrine",
            payload=CitrineRequest(action="search", query=query, collection=collection, top_k=top_k),
        )
    )
    if res.error:
        print_error(res.error.message)
        raise typer.Exit(1)
    for r in res.payload.results:  # type: ignore
        path = as_posix_str(r.metadata.get("path", r.id))
        console.print(f"[{r.score:.3f}] {path}\n  {_safe(r.text[:200])}\n")


@app.command()
def runs() -> None:
    runs_dir = Path("memory/runs")
    if not runs_dir.exists():
        console.print("[dim]No runs yet.[/]")
        return
    files = sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            console.print(
                f"{data.get('started_at', '?'):25} {data.get('status', '?'):10} {_safe(str(data.get('objective', ''))[:60])}"
            )
        except Exception:
            console.print(f.name)


@app.command("clean-runs")
def clean_runs(force: bool = typer.Option(False, "--force")) -> None:
    runs_dir = Path("memory/runs")
    files = list(runs_dir.glob("*.json")) if runs_dir.exists() else []
    if not files:
        console.print("[dim]No runs to clean.[/]")
        return
    if not force:
        console.print(f"Will delete {len(files)} run files. Re-run with --force to confirm.")
        return
    for f in files:
        f.unlink(missing_ok=True)
    print_ok(f"Deleted {len(files)} runs.")


@app.command()
def promote(filename: str) -> None:
    src = Path("tools/quarantine") / filename
    dst_dir = Path("tools/persistent")
    dst_dir.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        print_error(f"Not found: {src}")
        raise typer.Exit(1)
    dst = dst_dir / src.name
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    print_ok(f"Promoted {src} → {dst}")


@app.command()
def quarantine() -> None:
    d = Path("tools/quarantine")
    files = sorted(p for p in d.glob("*.py")) if d.exists() else []
    if not files:
        console.print("[dim]Quarantine empty.[/]")
        return
    for f in files:
        console.print(f"  {f.name}")


@app.command()
def tools() -> None:
    d = Path("tools/persistent")
    files = sorted(p for p in d.glob("*.py")) if d.exists() else []
    if not files:
        console.print("[dim]No persistent tools.[/]")
        return
    for f in files:
        console.print(f"  {f.name}")


if __name__ == "__main__":
    app()
