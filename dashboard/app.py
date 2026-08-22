"""FastAPI app for @ETHER Control Matrix — host-agent first. Single UI at /.

Hardened 2026-08-22 / UX 0.7 → 0.7.1:
- Chat orchestrator + Clear Chat (POST /api/chat/clear)
- Turn-first chat UI
"""

from __future__ import annotations

import asyncio
import re
import shutil
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
QUARANTINE = ROOT / "tools" / "quarantine"
PERSISTENT = ROOT / "tools" / "persistent"
UPLOADS = ROOT / "artifacts" / "uploads"

app = FastAPI(title="@ETHER Control Matrix", version="0.7.1")

if STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


class PromoteBody(BaseModel):
    filename: str


class ReconcileBody(BaseModel):
    dry_run: bool = False
    threshold: float = 0.82


class HealthBody(BaseModel):
    skip_sandbox: bool = True


class ChatPostBody(BaseModel):
    message: str
    job_id: Optional[str] = None
    orchestrate: bool = True
    allow_write: bool = False
    force_channel: Optional[str] = None


class ChatClearBody(BaseModel):
    keep_archive: bool = True


class TestEnqueueBody(BaseModel):
    fixture: str
    live: bool = False
    arm: str = "direct"
    max_steps: int = 8
    timeout: int = 280


class SpeechBody(BaseModel):
    text: str
    job_id: Optional[str] = None


def json_load_safe(path: Path) -> dict:
    import json

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _safe_snapshot() -> dict:
    try:
        from dashboard.collector import collect_snapshot
        from dashboard.live_feed import build_console

        data = collect_snapshot()
        data["console"] = build_console()
        data["api_version"] = "0.7.1"
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


@app.get("/")
def index() -> FileResponse:
    path = STATIC / "agent.html"
    if not path.exists():
        raise HTTPException(500, "dashboard/static/agent.html missing — pull latest main")
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
        },
    )


@app.get("/agent")
def agent_gone() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=301)


@app.get("/legacy")
def legacy_gone() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=301)


@app.get("/api/host-agent")
def host_agent_api() -> dict:
    try:
        from dashboard.collector_host_agent import collect_host_agent

        return collect_host_agent()
    except Exception as e:
        return {
            "error": str(e)[:200],
            "agent_alive": False,
            "status": {},
            "queue": {
                "pending": [],
                "done": [],
                "failed": [],
                "counts": {"pending": 0, "done": 0, "failed": 0},
            },
            "log_lines": [f"collector error: {e}"],
        }


@app.get("/api/moonshots")
def moonshots_api() -> dict:
    try:
        from dashboard.collector_moonshots import collect_moonshots

        return collect_moonshots()
    except Exception as e:
        return {"error": str(e)[:160], "tiles": []}


@app.get("/api/snapshot")
def snapshot() -> dict:
    return _safe_snapshot()


@app.get("/api/infra")
def infra() -> dict:
    try:
        from core.infra_status import collect_infra

        return collect_infra()
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@app.get("/api/console")
def console() -> dict:
    try:
        from dashboard.live_feed import build_console

        return build_console()
    except Exception as e:
        return {"lines": [{"level": "err", "text": str(e)}], "active": False}


@app.get("/api/health")
def health() -> dict:
    host: dict = {}
    try:
        from core.host_health import compute as host_compute

        host = host_compute()
    except Exception as e:
        host = {"ok": False, "error": str(e)[:160]}
    eligible: dict = {}
    try:
        p = ROOT / "artifacts" / "eligible_rates.json"
        if p.exists():
            eligible = json_load_safe(p)
    except Exception:
        pass
    return {
        "ok": True,
        "service": "ether-dashboard",
        "version": "0.7.1",
        "truth": "host_agent_local",
        "git_required": False,
        "chat_orchestrator": True,
        "chat_clear": True,
        "host": {
            "alive": host.get("alive"),
            "age_s": host.get("age_s"),
            "phase": host.get("phase"),
            "last_job": host.get("last_job"),
            "ok": host.get("ok"),
        },
        "eligible": {
            "timeout_rate_eligible": eligible.get("timeout_rate_eligible"),
            "honest_rate_eligible": eligible.get("honest_rate_eligible"),
            "live_eligible_n": eligible.get("live_eligible_n"),
        },
    }


@app.get("/api/health-check")
def health_check(skip_sandbox: bool = True) -> dict:
    try:
        from core.health_check import run_health_checks

        return run_health_checks(include_sandbox_smoke=not skip_sandbox)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.post("/api/health-check")
def health_check_post(body: HealthBody) -> dict:
    try:
        from core.health_check import run_health_checks

        return run_health_checks(include_sandbox_smoke=not body.skip_sandbox)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


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
        return {"ok": False, "error": str(e)[:200]}


@app.get("/api/rates")
def rates_api() -> dict:
    try:
        from core.operator_surface import rates

        return rates()
    except Exception as e:
        return {"error": str(e)[:200], "updated": None}


@app.get("/api/operator")
def operator_api() -> dict:
    try:
        from core.operator_surface import status, doctor

        return {"status": status(), "doctor": doctor()}
    except Exception as e:
        return {
            "status": {},
            "doctor": {"ok": False, "issues": [f"operator error: {e}"]},
            "error": str(e)[:200],
        }


@app.get("/api/llm")
def llm_api() -> dict:
    try:
        from core.multi_llm import publish

        return publish()
    except Exception as e:
        return {
            "error": str(e)[:200],
            "fast": None,
            "live": None,
            "latency": {"n": 0},
            "keep_alive": False,
        }


@app.get("/api/chat")
def chat_list(limit: int = 40) -> dict:
    try:
        from core.chat_bus import receive, summary
        from core.chat_orchestrator import recent_turns, latest_turn

        return {
            "summary": summary(),
            "inbox": receive(from_grok=True, limit=limit),
            "outbox": receive(from_grok=False, limit=limit),
            "turns": recent_turns(limit=min(limit, 30)),
            "latest_turn": latest_turn(),
            "orchestrator": True,
        }
    except Exception as e:
        return {
            "summary": {"inbox_n": 0, "outbox_n": 0, "error": str(e)[:120]},
            "inbox": [],
            "outbox": [],
            "turns": [],
            "error": str(e)[:200],
        }


@app.post("/api/chat")
def chat_post(body: ChatPostBody) -> dict:
    try:
        from core.operator_surface import chat_post as cp

        result = cp(
            body.message,
            job_id=body.job_id,
            orchestrate=body.orchestrate,
            allow_write=body.allow_write,
            force_channel=body.force_channel,
        )
        if result.get("schema") == "ether_chat_turn_v1" or "reply" in result:
            return {"ok": bool(result.get("ok", True)), "turn": result, "orchestrator": True}
        return {"ok": True, "envelope": result, "orchestrator": False}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.post("/api/chat/clear")
def chat_clear_api(body: ChatClearBody = ChatClearBody()) -> dict:
    """Clear Chat — archive bus + wipe turns. Default keeps archive history."""
    try:
        from core.operator_surface import chat_clear

        return chat_clear(keep_archive=body.keep_archive)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.get("/api/chat/turns")
def chat_turns_api(limit: int = 20) -> dict:
    try:
        from core.chat_orchestrator import recent_turns, latest_turn

        return {
            "turns": recent_turns(limit=limit),
            "latest": latest_turn(),
            "orchestrator": True,
        }
    except Exception as e:
        return {"turns": [], "error": str(e)[:200]}


@app.post("/api/test")
def test_enqueue(body: TestEnqueueBody) -> dict:
    try:
        from core.operator_surface import run_test

        path = run_test(
            body.fixture,
            live=body.live,
            arm=body.arm,
            max_steps=body.max_steps,
            timeout=body.timeout,
        )
        return {"ok": True, "job": path.name}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.get("/api/skills")
def skills_api() -> dict:
    try:
        from core.operator_surface import skill_list

        return {"skills": skill_list()}
    except Exception as e:
        return {"skills": [], "error": str(e)[:200]}


@app.get("/api/mcp")
def mcp_api() -> dict:
    try:
        from core.operator_surface import mcp_list

        return mcp_list()
    except Exception as e:
        return {"error": str(e)[:200], "local_tools": {}, "gems": []}


@app.post("/api/speech")
def speech_api(body: SpeechBody) -> dict:
    try:
        from core.operator_surface import speech_to_chat

        return speech_to_chat(body.text, job_id=body.job_id)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _register_upload_routes() -> None:
    try:
        from fastapi import File, UploadFile
    except Exception:
        UploadFile = None  # type: ignore
        File = None  # type: ignore

    if UploadFile is None or File is None:

        @app.post("/api/upload")
        async def upload_unavailable() -> dict:
            return {
                "ok": False,
                "error": "python-multipart not installed — pip install python-multipart",
            }

        return

    try:

        @app.post("/api/upload")
        async def upload_api(
            file: UploadFile = File(...),
            dest: str = "uploads",
        ) -> dict:
            name = Path(file.filename or "upload.bin").name
            if not re.match(r"^[A-Za-z0-9_\-.]+$", name):
                raise HTTPException(400, "invalid filename")
            if dest == "quarantine":
                target = QUARANTINE
            else:
                target = UPLOADS
            target.mkdir(parents=True, exist_ok=True)
            path = target / name
            data = await file.read()
            path.write_bytes(data)
            return {
                "ok": True,
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "bytes": len(data),
                "dest": dest,
            }

    except RuntimeError as e:
        msg = str(e)

        @app.post("/api/upload")
        async def upload_stub() -> dict:
            return {"ok": False, "error": msg[:200]}


_register_upload_routes()


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
