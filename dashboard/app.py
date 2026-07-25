"""FastAPI app for @ETHER interactive dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from dashboard.collector import collect_snapshot

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"

app = FastAPI(title="@ETHER Dashboard", version="0.1.1")

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/snapshot")
def snapshot() -> dict:
    return collect_snapshot()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "service": "ether-dashboard"}


def main() -> None:
    import uvicorn

    uvicorn.run("dashboard.app:app", host="127.0.0.1", port=8787, reload=False)


if __name__ == "__main__":
    main()
