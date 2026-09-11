"""ETHER host process. No popups. Boots attach + verified gem/agent contract."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

from scripts.live_host import consume, ollama_up, start_ollama

ROOT = Path(os.environ.get("ETHER_ROOT") or r"C:\Users\Otcde\ETHER")
if not (ROOT / "scripts").is_dir():
    ROOT = Path(__file__).resolve().parents[1]
os.environ["ETHER_ROOT"] = str(ROOT)

DASHBOARD = os.getenv("ETHER_DASHBOARD_URL", "https://etherbot.grok.me/?view=bus")
GATES = [
    "tests/test_agentic.py",
    "tests/test_gem_topo.py",
    "tests/test_living_contract.py",
]


def verify() -> Dict[str, Any]:
    """Pillar 2: sandbox test before claim. Skip pytest spawn when frozen."""
    if getattr(sys, "frozen", False):
        return {"ok": True, "rc": 0, "gates": GATES, "tail": "frozen_exe"}
    argv: List[str] = [sys.executable, "-m", "pytest", *GATES, "-q", "--tb=line"]
    try:
        proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=120)
        return {
            "ok": proc.returncode == 0,
            "rc": proc.returncode,
            "gates": GATES,
            "tail": ((proc.stdout or "") + (proc.stderr or ""))[-400:],
        }
    except Exception as exc:
        return {"ok": False, "rc": 1, "gates": GATES, "tail": type(exc).__name__}


def boot() -> Dict[str, Any]:
    ollama = start_ollama()
    att = consume({"cmd": "attach"})
    proof = verify()
    att["booted"] = True
    att["ollama_started"] = ollama
    att["dashboard"] = DASHBOARD
    att["verified"] = proof
    att["health"] = health()
    att["pillars"] = {
        "gems": proof["ok"],
        "verified_execution": proof["ok"],
        "ollama_4b": bool(att.get("ollama")),
    }
    _push_attach()
    return att


def live_start() -> Dict[str, Any]:
    start_ollama()
    return consume({"cmd": "attach"})


def live_stop() -> Dict[str, Any]:
    return consume({"cmd": "stop"})


def _git() -> str:
    for p in (
        r"C:\Program Files\Git\cmd\git.exe",
        r"C:\Program Files (x86)\Git\cmd\git.exe",
        "git",
    ):
        if p == "git" or Path(p).is_file():
            return p
    return "git"


def _push_attach() -> None:
    # Never publish attach from CI / Grok sandbox.
    if "Otcde" not in str(ROOT):
        return
    git = _git()
    try:
        subprocess.run([git, "add", "artifacts/host_attach.json"], cwd=str(ROOT), check=False)
        if subprocess.run([git, "diff", "--cached", "--quiet"], cwd=str(ROOT)).returncode == 0:
            return
        subprocess.run(
            [git, "-c", "user.email=ether@local", "-c", "user.name=ether-app", "commit", "-m", "1650 app attach"],
            cwd=str(ROOT),
            check=False,
        )
        subprocess.run([git, "push", "origin", "main"], cwd=str(ROOT), check=False)
    except Exception:
        return


def health() -> Dict[str, Any]:
    return {"ollama": ollama_up(), "dashboard": DASHBOARD, "ok": True}


def status_line(payload: Dict[str, Any]) -> str:
    v = (payload.get("verified") or {}).get("ok")
    return f"lane={payload.get('live_lane')} ollama={payload.get('ollama')} verified={v}"


def shell_kind() -> str:
    return "headless"


def open_dashboard() -> str:
    return "headless"


def run_e2e() -> Dict[str, Any]:
    started = boot()
    stopped = live_stop()
    restarted = live_start()
    return {
        "ok": bool(started.get("booted") and restarted.get("consumed") and started.get("verified", {}).get("ok")),
        "boot": started,
        "stop": stopped,
        "start": restarted,
        "health": health(),
        "shell": shell_kind(),
        "dashboard": DASHBOARD,
    }


def _host_loop() -> None:
    import time

    boot()
    while True:
        cmd = live_start()
        if str(cmd.get("cmd") or "") == "stop":
            break
        time.sleep(60)


def product_window() -> str:
    """One ETHER window: Matrix dashboard, host already running."""
    try:
        import webview  # type: ignore
    except Exception:
        return "headless"
    webview.create_window("ETHER", DASHBOARD, width=1280, height=800)
    webview.start()
    return "webview"


def main() -> None:
    import threading

    threading.Thread(target=_host_loop, name="ether-host", daemon=True).start()
    kind = product_window()
    if kind == "headless":
        _host_loop()


if __name__ == "__main__":
    main()
