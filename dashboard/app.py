"""FastAPI app for @ETHER interactive dashboard."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from dashboard.collector import collect_snapshot
from dashboard.live_feed import build_console

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
QUARANTINE = ROOT / "tools" / "quarantine"
PERSISTENT = ROOT / "tools" / "persistent"

app = FastAPI(title="@ETHER Dashboard", version="0.2.0")

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class PromoteBody(BaseModel):
    filename: str


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/snapshot")
def snapshot() -> dict:
    data = collect_snapshot()
    data["console"] = build_console()
    return data


@app.get("/api/console")
def console() -> dict:
    return build_console()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "ether-dashboard", "version": "0.2.0"}


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


@app.websocket("/ws")
async def ws_feed(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = collect_snapshot()
            data["console"] = build_console()
            await ws.send_json(data)
            await asyncio.sleep(0.9)  # near real-time
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
