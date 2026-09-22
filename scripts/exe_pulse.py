"""1650 exe pulse. Always exec disk host_main, never a frozen copy."""
from __future__ import annotations
import importlib.util
import json, os, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

def _root() -> Path:
    env = os.environ.get("ETHER_ROOT")
    if env and (Path(env) / "scripts").is_dir():
        return Path(env).resolve()
    win = Path(r"C:\Users\Otcde\ETHER")
    if (win / "scripts").is_dir():
        return win.resolve()
    return Path(__file__).resolve().parents[1]

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _disk_tick() -> Dict[str, Any] | None:
    path = _root() / "scripts" / "host_main.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_ether_disk_host_main", path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.tick()

def pulse(push: bool = True) -> Dict[str, Any]:
    try:
        row = _disk_tick()
        if isinstance(row, dict):
            return row
    except Exception:
        pass
    root = _root()
    art = root / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    ollama = False
    attach: Dict[str, Any] = {}
    try:
        from scripts.live_host import consume, ollama_up, start_ollama, write_probe
        start_ollama()
        ollama = bool(ollama_up())
        write_probe({"pulse": True})
        attach = consume({"cmd": "attach"})
    except Exception as exc:
        attach = {"ok": False, "error": type(exc).__name__, "writer": "exe"}
    alive = {"alive": True, "ts": _now(), "root": str(root), "ollama": ollama, "writer": "exe" if os.name == "nt" else "observe", "kernel": "phase6"}
    (art / "app_alive.json").write_text(json.dumps(alive, indent=2) + "\n", encoding="utf-8")
    live: Dict[str, Any] = {}
    try:
        from scripts.drain_live_fifo import drain
        live = drain()
    except Exception as exc:
        live = {"ok": False, "error": type(exc).__name__}
    row = {"ok": True, "ts": _now(), "ollama": ollama, "attach_writer": attach.get("writer"), "attach_ollama": attach.get("ollama"), "live_drain": live.get("n"), "os": os.name}
    (art / "exe_pulse.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    if push and os.name == "nt" and "Otcde" in str(root):
        _push(root)
    return row

def _push(root: Path) -> None:
    git = "git"
    for p in (r"C:\Program Files\Git\cmd\git.exe", r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if Path(p).is_file():
            git = p
            break
    kw: Dict[str, Any] = {"cwd": str(root), "timeout": 90, "creationflags": 0x08000000, "capture_output": True}
    paths = ["artifacts/host_attach.json", "artifacts/app_alive.json", "artifacts/ollama_probe.json", "artifacts/exe_pulse.json", "artifacts/week_tick.json", "artifacts/gem_energy.json", "artifacts/jobs", "artifacts/self_heal.json", "artifacts/git_push.json"]
    try:
        subprocess.run([git, "add", *paths], **kw)
        if subprocess.run([git, "diff", "--cached", "--quiet"], **kw).returncode == 0:
            return
        subprocess.run([git, "-c", "user.email=ether@local", "-c", "user.name=ether-exe", "commit", "-m", "1650 exe pulse"], **kw)
        subprocess.run([git, "push", "origin", "main"], **kw)
    except Exception:
        return

if __name__ == "__main__":
    print(json.dumps(pulse(), indent=2))
