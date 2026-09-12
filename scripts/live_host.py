"""Consume host_command. Start Ollama when the binary is on this machine."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def ollama_up() -> bool:
    url = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as res:
            return int(getattr(res, "status", 200) or 200) < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


_OLLAMA_PROC = None

def start_ollama() -> bool:
    global _OLLAMA_PROC
    if ollama_up():
        return True
    bin_ = shutil.which("ollama")
    if not bin_:
        return False
    try:
        flags = 0
        si = None
        if os.name == "nt":
            flags = 0x08000000 | 0x00000008
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
        _OLLAMA_PROC = subprocess.Popen(
            [bin_, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            creationflags=flags,
            startupinfo=si,
        )
    except OSError:
        return False
    for _ in range(8):
        time.sleep(0.5)
        if ollama_up():
            return True
    return ollama_up()


def stop_ollama() -> None:
    global _OLLAMA_PROC
    proc = _OLLAMA_PROC
    _OLLAMA_PROC = None
    if proc and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass


def consume(command: Dict[str, Any] | None = None) -> Dict[str, Any]:
    ollama = start_ollama()
    live_lane = "ollama_4b" if ollama else "grok_bus"
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "fast_lane": "matrix-worker",
        "live_lane": live_lane,
        "living_ok": True,
        "ollama": ollama,
        "grok_bus": not ollama,
        "cmd": (command or {}).get("cmd") or "attach",
        "consumed": True,
        "note": "Starts ollama serve when binary exists. Else grok_bus.",
    }
    root = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1])
    out = root / "artifacts" / "host_attach.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["path"] = str(out)
    return payload


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "host_command.json"
    body = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"cmd": "attach"}
    print(json.dumps(consume(body), indent=2))
