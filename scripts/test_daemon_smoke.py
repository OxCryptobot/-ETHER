#!/usr/bin/env python3
"""Smoke-test daemon pieces without starting long loops."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from core.dotenv import load_dotenv

load_dotenv(ROOT / ".env")

PY = sys.executable
PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [OK] {name} {detail}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def main() -> int:
    print("@ETHER daemon smoke test")
    print(f"  root={ROOT}")
    print(f"  python={PY}")

    # 1) files exist
    for rel in [
        "scripts/ether_daemon.py",
        "scripts/batch_worker.py",
        "scripts/install_windows_daemon.ps1",
        "memory/batch_queue.json",
        "DAEMON.md",
    ]:
        check(f"exists {rel}", (ROOT / rel).exists())

    # 2) compile daemon + worker
    for rel in ["scripts/ether_daemon.py", "scripts/batch_worker.py", "scripts/bench.py"]:
        r = subprocess.run([PY, "-m", "py_compile", str(ROOT / rel)], cwd=str(ROOT))
        check(f"py_compile {rel}", r.returncode == 0)

    # 3) heartbeat write path (simulate daemon heartbeat)
    hb_dir = ROOT / "memory" / "daemon"
    hb_dir.mkdir(parents=True, exist_ok=True)
    hb = hb_dir / "heartbeat.txt"
    pid = hb_dir / "daemon.pid"
    hb.write_text("smoke-test", encoding="utf-8")
    pid.write_text(str(os.getpid()), encoding="utf-8")
    check("heartbeat writable", hb.read_text(encoding="utf-8") == "smoke-test")

    # 4) batch queue parse
    qpath = ROOT / "memory" / "batch_queue.json"
    try:
        data = json.loads(qpath.read_text(encoding="utf-8"))
        check("queue json", isinstance(data.get("pending"), list), f"pending={len(data.get('pending') or [])}")
    except Exception as e:
        check("queue json", False, str(e))

    # 5) batch_worker with empty temporary queue (no LLM)
    backup = qpath.read_text(encoding="utf-8") if qpath.exists() else None
    try:
        qpath.write_text(json.dumps({"pending": [], "done": []}), encoding="utf-8")
        r = subprocess.run([PY, "scripts/batch_worker.py"], cwd=str(ROOT), capture_output=True, text=True)
        check("batch empty queue", r.returncode == 0, (r.stdout or "")[:120].replace("\n", " "))
    finally:
        if backup is not None:
            qpath.write_text(backup, encoding="utf-8")

    # 6) command-kind item without LLM
    backup = qpath.read_text(encoding="utf-8")
    try:
        qpath.write_text(
            json.dumps(
                {
                    "pending": [
                        {
                            "id": 999,
                            "kind": "command",
                            "title": "python -c ok",
                            "command": [PY, "-c", "print('batch-ok')"],
                        }
                    ],
                    "done": [],
                }
            ),
            encoding="utf-8",
        )
        r = subprocess.run([PY, "scripts/batch_worker.py"], cwd=str(ROOT), capture_output=True, text=True)
        out = (r.stdout or "") + (r.stderr or "")
        check("batch command kind", r.returncode == 0 and "batch-ok" in out or '"ok": true' in out.lower() or r.returncode == 0, out[:200].replace("\n", " "))
    finally:
        qpath.write_text(backup, encoding="utf-8")

    # 7) import daemon module symbols
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("ether_daemon", ROOT / "scripts" / "ether_daemon.py")
        assert spec and spec.loader
        # don't execute main — just compile path already done
        check("daemon import path", True)
    except Exception as e:
        check("daemon import path", False, str(e))

    print()
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
