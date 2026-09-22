"""1650 keepalive — singleton + host_main."""
from __future__ import annotations
import json, os, time
from pathlib import Path

def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if os.name == "nt":
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False

def _lock(root: Path) -> bool:
    path = root / "artifacts" / "keepalive.pid"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            old = int(path.read_text(encoding="utf-8").strip())
        except Exception:
            old = 0
        if old and old != os.getpid() and _alive(old):
            return False
    path.write_text(str(os.getpid()), encoding="utf-8")
    return True

def main() -> None:
    from scripts.host_main import tick, _root
    root = _root()
    if not _lock(root):
        print(json.dumps({"ok": True, "note": "keepalive_already"}))
        return
    while True:
        try:
            tick()
        except Exception:
            pass
        try:
            from core.kernel.poll import pending_count, poll_seconds
            time.sleep(float(poll_seconds(pending_count())))
        except Exception:
            time.sleep(20)

if __name__ == "__main__":
    from scripts.host_main import tick
    print(json.dumps(tick(), default=str))
    if os.name == "nt":
        main()
