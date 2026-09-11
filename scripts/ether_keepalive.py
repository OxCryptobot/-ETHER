"""Persistent local consumer. Matrix Start/Stop LIVE via host_command."""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from scripts.live_host import consume

ROOT = Path(__file__).resolve().parents[1]
CMD = ROOT / "artifacts" / "host_command.json"
LOG = ROOT / "artifacts" / "keepalive.log"


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def _push_attach() -> None:
    try:
        subprocess.run(["git", "add", "artifacts/host_attach.json", "artifacts/keepalive.log"], cwd=str(ROOT), check=False)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(ROOT))
        if diff.returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", "1650 keepalive attach"], cwd=str(ROOT), check=False)
        subprocess.run(["git", "push", "origin", "main"], cwd=str(ROOT), check=False)
    except Exception as exc:
        _log(f"push_fail {type(exc).__name__}")


def tick() -> dict:
    body = {"cmd": "attach"}
    if CMD.is_file():
        try:
            body = json.loads(CMD.read_text(encoding="utf-8"))
        except Exception:
            pass
    out = consume(body)
    out["halt"] = str(body.get("cmd") or "") == "stop"
    _log(json.dumps({"ollama": out.get("ollama"), "lane": out.get("live_lane"), "halt": out.get("halt")}))
    _push_attach()
    return out


def main() -> None:
    _log("keepalive start")
    while True:
        out = tick()
        if out.get("halt"):
            _log("keepalive stop")
            break
        time.sleep(60)


if __name__ == "__main__":
    print(json.dumps(tick()))
    main()
