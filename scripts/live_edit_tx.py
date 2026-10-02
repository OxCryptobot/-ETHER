"""One 4B edit transaction on the 1650. Honest only if the tool edit passes tests."""
from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "live_edit_tx.json"


def _ask(prompt: str) -> str:
    from scripts.live_generate_probe import pick_model

    model = pick_model()
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 80},
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode())
    message = payload.get("message") or {}
    return str(message.get("content") or "")


def main() -> int:
    from core.kernel.context_budget import pack
    from core.kernel.product_loop import run_model_edit

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "honest": False,
        "note": "tool edit then tests. generate-only is not a pass",
    }
    if os.name != "nt":
        row["note"] = "observe_only"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(row))
        return 0
    parent = Path(tempfile.mkdtemp(prefix="ether_edit_"))
    workspace = parent / "ws"
    workspace.mkdir()
    (workspace / "add.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    prompt = pack(workspace, "add", ["add.py"], max_chars=800)
    prompt += "\n\nReply with exactly two lines:\nOLD: return a - b\nNEW: return a + b\n"
    try:
        text = _ask(prompt)
        row["response_tail"] = text[-240:]

        def tests_ok() -> bool:
            from scripts.live_generate_probe import function_ok
            return function_ok((workspace / "add.py").read_text(encoding="utf-8"))

        result = run_model_edit(workspace, "add.py", text, tests_ok)
        row.update(result)
        from core.kernel.edit_memory import remember
        remember(ROOT, f"honest={row.get('honest')} ok={row.get('ok')}")
    except Exception as exc:
        row["error"] = type(exc).__name__
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(row, default=str))
    return 0 if row.get("honest") else 1


if __name__ == "__main__":
    raise SystemExit(main())
