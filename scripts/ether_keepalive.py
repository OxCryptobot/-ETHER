"""1650 keepalive: pull, Ollama, pulse, drain LIVE. No Grok. No operator shell."""
from __future__ import annotations
import json, os, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "artifacts" / "keepalive.log"
FLAGS = 0x08000000 if os.name == "nt" else 0

def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(msg[:500] + "\n")

def _run(argv: list[str], timeout: int = 90) -> None:
    kw = {"cwd": str(ROOT), "timeout": timeout, "capture_output": True}
    if FLAGS:
        kw["creationflags"] = FLAGS
    subprocess.run(argv, **kw)

def _pull() -> None:
    git = "git"
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(p).is_file():
            git = p
            break
    try:
        _run([git, "pull", "--ff-only", "origin", "main"], timeout=120)
    except Exception:
        pass

def tick() -> dict:
    _pull()
    out: dict = {"ok": True}
    try:
        from scripts.live_host import consume, start_ollama
        start_ollama()
        out["attach"] = consume({"cmd": "attach"})
    except Exception as exc:
        out["attach_error"] = type(exc).__name__
    try:
        from core.kernel.autonomy import tick as auto_tick
        out["auto"] = auto_tick()
    except Exception:
        try:
            from scripts.exe_pulse import pulse
            out["pulse"] = pulse(push=True)
        except Exception as exc:
            out["pulse_error"] = type(exc).__name__
        try:
            from scripts.drain_live_fifo import drain
            out["live"] = drain()
        except Exception as exc:
            out["live_error"] = type(exc).__name__
    _log(json.dumps({"ollama": (out.get("attach") or {}).get("ollama"), "auto": bool(out.get("auto"))}))
    return out

def _sleep() -> float:
    try:
        from core.kernel.poll import pending_count, poll_seconds
        return float(poll_seconds(pending_count()))
    except Exception:
        return 20.0

def main() -> None:
    _log("keepalive start")
    while True:
        try:
            tick()
        except Exception as exc:
            _log(f"tick_fail {type(exc).__name__}")
        time.sleep(_sleep())

if __name__ == "__main__":
    print(json.dumps(tick(), default=str))
    if os.name == "nt":
        main()
