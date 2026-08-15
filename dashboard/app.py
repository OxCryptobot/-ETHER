"""FastAPI app for @ETHER Control Matrix — host-agent first."""

from __future__ import annotations

import asyncio
import re
import shutil
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
QUARANTINE = ROOT / "tools" / "quarantine"
PERSISTENT = ROOT / "tools" / "persistent"

app = FastAPI(title="@ETHER Control Matrix", version="0.5.0")

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class PromoteBody(BaseModel):
    filename: str


class ReconcileBody(BaseModel):
    dry_run: bool = False
    threshold: float = 0.82


class HealthBody(BaseModel):
    skip_sandbox: bool = True


def _safe_snapshot() -> dict:
    try:
        from dashboard.collector import collect_snapshot
        from dashboard.live_feed import build_console

        data = collect_snapshot()
        data["console"] = build_console()
        data["api_version"] = "0.5.0"
        try:
            from dashboard.collector_host_agent import collect_host_agent

            data["host_agent"] = collect_host_agent()
        except Exception as e:
            data["host_agent"] = {"error": str(e)[:120]}
        return data
    except Exception as e:
        return {
            "generated_at": None,
            "project": "@ETHER",
            "error": str(e),
            "traceback": traceback.format_exc()[-1500:],
            "host_agent": {},
            "console": {
                "lines": [{"ts": "", "level": "err", "text": f"snapshot error: {e}"}],
                "active": False,
            },
        }


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    """Primary dashboard is host-agent Control Matrix (no legacy Overview)."""
    path = STATIC / "agent.html"
    if not path.exists():
        raise HTTPException(500, "dashboard/static/agent.html missing — pull latest main")
    return FileResponse(path)


@app.get("/agent", response_class=HTMLResponse)
def agent_page() -> FileResponse:
    path = STATIC / "agent.html"
    if not path.exists():
        raise HTTPException(500, "dashboard/static/agent.html missing — pull latest main")
    return FileResponse(path)


@app.get("/legacy", response_class=HTMLResponse)
def legacy_page() -> FileResponse:
    """Archived multipage UI — not primary health."""
    path = STATIC / "index.html"
    if not path.exists():
        raise HTTPException(404, "legacy index missing")
    return FileResponse(path)


@app.get("/api/host-agent")
def host_agent_api() -> dict:
    try:
        from dashboard.collector_host_agent import collect_host_agent

        return collect_host_agent()
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/api/moonshots")
def moonshots_api() -> dict:
    try:
        from dashboard.collector_moonshots import collect_moonshots

        return collect_moonshots()
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/api/snapshot")
def snapshot() -> dict:
    return _safe_snapshot()


@app.get("/api/infra")
def infra() -> dict:
    try:
        from core.infra_status import collect_infra

        return collect_infra()
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/api/console")
def console() -> dict:
    try:
        from dashboard.live_feed import build_console

        return build_console()
    except Exception as e:
        return {"lines": [{"level": "err", "text": str(e)}], "active": False}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "ether-dashboard", "version": "0.5.0", "truth": "host_agent"}


@app.get("/api/health-check")
def health_check(skip_sandbox: bool = True) -> dict:
    try:
        from core.health_check import run_health_checks

        return run_health_checks(include_sandbox_smoke=not skip_sandbox)
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/api/health-check")
def health_check_post(body: HealthBody) -> dict:
    try:
        from core.health_check import run_health_checks

        return run_health_checks(include_sandbox_smoke=not body.skip_sandbox)
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/api/promote")
def promote(body: PromoteBody) -> dict:
    name = Path(body.filename).name
    if not re.match(r"^[A-Za-z0-9_\-]+\.py$", name):
        raise HTTPException(400, "invalid filename")
    src = QUARANTINE / name
    if not src.exists():
        raise HTTPException(404, f"not in quarantine: {name}")
    from core import tool_reconcile

    gate = tool_reconcile._promotion_gate(src, operator_initiated=True)
    if not gate["ok"]:
        raise HTTPException(403, f"promotion gate refused: {gate['reason']}")
    PERSISTENT.mkdir(parents=True, exist_ok=True)
    m = re.match(r"^(.+?)_\d{8}_\d{6}\.py$", name)
    dest_name = f"{m.group(1)}.py" if m else name
    dest = PERSISTENT / dest_name
    shutil.copy2(src, dest)
    return {"ok": True, "from": name, "to": dest_name}


@app.post("/api/reconcile-tools")
def reconcile_tools(body: ReconcileBody) -> dict:
    try:
        from core.tool_reconcile import reconcile

        return reconcile(promote_threshold=body.threshold, dry_run=body.dry_run)
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.websocket("/ws")
async def ws_feed(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            try:
                from dashboard.collector_host_agent import collect_host_agent

                await ws.send_json(collect_host_agent())
            except Exception as e:
                await ws.send_json({"error": str(e)[:200]})
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass


def main() -> None:
    import uvicorn

    uvicorn.run("dashboard.app:app", host="127.0.0.1", port=8787, reload=False)


if __name__ == "__main__":
    main()
