"""One 4B generate smoke test. Not an honest tool-path PASS."""
from __future__ import annotations

import ast
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "live_generate_probe.json"
MODEL = os.environ.get("ETHER_LIVE_MODEL") or "qwen3.5:4b-q4_K_M"


def pick_model() -> str:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=10) as resp:
            names = [str(m.get("name") or "") for m in json.loads(resp.read().decode()).get("models") or []]
    except Exception:
        return MODEL
    if MODEL in names:
        return MODEL
    for name in names:
        if "qwen" in name.lower():
            return name
    return MODEL
PROMPT = "Reply with only a Python function:\ndef add(a, b):\n    return a + b\n"


def extract_code(text: str) -> str:
    raw = text or ""
    if "</think>" in raw:
        raw = raw.split("</think>", 1)[1]
    if "```" in raw:
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("python"):
            raw = raw[len("python"):]
    return raw.strip()


def function_ok(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        return False
    if tree.body[0].name != "add":
        return False
    if any(isinstance(n, (ast.Import, ast.ImportFrom)) for n in ast.walk(tree)):
        return False
    ns: dict = {}
    exec(compile(tree, "<probe>", "exec"), ns, ns)
    return ns["add"](2, 3) == 5 and ns["add"](-1, 1) == 0


def main() -> int:
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "ok": False,
        "honest": False,
        "note": "smoke only. generate is not an honest tool-path PASS",
    }
    if os.name != "nt":
        row["note"] = "observe_only"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(row))
        return 0
    model = pick_model()
    row["model"] = model
    body = json.dumps({
        "model": model,
        "prompt": PROMPT,
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "num_predict": 200},
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            payload = json.loads(resp.read().decode())
        text = str(payload.get("response") or "")
        if not text.strip():
            text = str(payload.get("thinking") or "")
        code = extract_code(text)
        row["response_tail"] = text[-240:]
        row["ok"] = function_ok(code)
        if not text.strip():
            row["error"] = "empty_response"
    except Exception as exc:
        row["error"] = type(exc).__name__
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(row))
    return 0 if row["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
