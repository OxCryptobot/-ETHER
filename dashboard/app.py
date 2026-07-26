"""FastAPI app for @ETHER Control Matrix."""

from __future__ import annotations

import asyncio
import re
import shutil
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
QUARANTINE = ROOT / "tools" / "quarantine"
PERSISTENT = ROOT / "tools" / "persistent"

app = FastAPI(title="@ETHER Control Matrix", version="0.4.0")

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class PromoteBody(BaseModel):
    filename: str


class ReconcileBody(BaseModel):
    dry_run: bool = False
    threshold: float = 0.82


def _safe_snapshot() -> dict:
    try:
        from dashboard.collector import collect_snapshot
        from dashboard.live_feed import build_console

        data = collect_snapshot()
        data["console"] = build_console()
        data["api_version"] = "0.4.0"
        return data
    except Exception as e:
        return {
            "generated_at": None,
            "project": "@ETHER",
            "error": str(e),
            "traceback": traceback.format_exc()[-1500:],
            "summary": {},
            "intelligence": {},
            "matrix_steps": [],
            "runs": [],
            "gems": [],
            "console": {"lines": [{"ts": "", "level": "err", "text": f"snapshot error: {e}"}], "active": False},
            "connections": {},
            "policy": {},
            "tools": {"quarantine": [], "persistent": []},
            "history": [],
            "workflow": [],
            "skills": [],
            "benchmarks": {},
            "current_work": {},
            "learning": {},
            "latest": {},
        }


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    path = STATIC / "index.html"
    if not path.exists():
        raise HTTPException(500, "dashboard/static/index.html missing — pull latest main")
    return FileResponse(path)


@app.get("/api/snapshot")
def snapshot() -> dict:
    return _safe_snapshot()


@app.get("/api/console")
def console() -> dict:
    try:
        from dashboard.live_feed import build_console

        return build_console()
    except Exception as e:
        return {"lines": [{"level": "err", "text": str(e)}], "active": False}


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "ether-dashboard", "version": "0.4.0"}


@app.post("/api/promote")
def promote(body: PromoteBody) -> dict:
    name = Path(body.filename).name
    if not re.match(r"^[A-Za-z0-9_\-]+\.py$", name):
        raise HTTPException(400, "invalid filename")
    src = QUARANTINE / name
    if not src.exists():
        raise HTTPException(404, f"not in quarantine: {name}")
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
            await ws.send_json(_safe_snapshot())
            await asyncio.sleep(1.0)
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
