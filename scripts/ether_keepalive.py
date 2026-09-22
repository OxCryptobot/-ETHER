"""1650 keepalive entry — disk host_main only."""
from __future__ import annotations
import json, os, time
from scripts.host_main import tick

def main() -> None:
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
    print(json.dumps(tick(), default=str))
    if os.name == "nt":
        main()
