#!/usr/bin/env python3
"""One Dual-chat drain. FAST-safe. Optional git commit of outbox."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from core.chat_bus import tick_once  # noqa: E402


def _maybe_commit(paths: list[str], message: str) -> None:
    if os.getenv("ETHER_CHAT_PUSH", "1") != "1":
        return
    try:
        subprocess.run(["git", "add", "--", *paths], cwd=str(ROOT), check=False, timeout=30)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(ROOT),
            timeout=30,
        )
        if staged.returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", message], cwd=str(ROOT), check=False, timeout=30)
        subprocess.run(["git", "push", "origin", "HEAD"], cwd=str(ROOT), check=False, timeout=60)
    except Exception:
        return


def main() -> int:
    result = tick_once(ROOT)
    print(json.dumps(result, indent=2), flush=True)
    if result.get("wrote"):
        _maybe_commit(
            [
                "artifacts/chat/outbox",
                "artifacts/chat/pending_host.json",
            ],
            f"chat bus: outbox {result.get('from')} {result.get('id')}",
        )
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
