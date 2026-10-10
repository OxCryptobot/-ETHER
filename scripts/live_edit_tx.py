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


def _ask(prompt: str, temperature: float = 0, n: int = 220) -> str:
    from scripts.live_generate_probe import pick_model

    model = pick_model()
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": temperature, "num_predict": n},
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(raw[:180]) from exc
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        raise RuntimeError(raw[:180])
    return str(message.get("content") or "")


def main() -> int:
    from core.kernel.context_budget import pack
    from core.kernel.curriculum import checker_for, diagnose, mark_passed, next_task, repair_note, write_task
    from core.kernel.product_loop import extract_function, run_model_edit

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "honest": False,
        "note": "tool edit then tests. generate-only is not a pass",
    }
    task = next_task(ROOT)
    if task is None:
        from core.kernel.curriculum import hold_status

        row.update(hold_status(ROOT))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(row))
        return 0
    row["task"] = task["id"]
    row["repo"] = bool(task.get("repo"))
    if os.name != "nt":
        row["note"] = "observe_only"
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(row))
        return 0
    if task.get("repo"):
        from core.kernel.worktree import ensure_tree

        workspace = ensure_tree(ROOT)
    else:
        parent = Path(tempfile.mkdtemp(prefix="ether_edit_"))
        workspace = parent / "ws"
        workspace.mkdir()
    also = task.get("also") or {}
    write_task(workspace, task)
    predict = int(task.get("predict") or 220)
    failing = diagnose(task, task["source"])
    if failing:
        row["failing"] = failing
    if task.get("must_read"):
        from core.kernel.read_gate import blind_prompt

        prompt = blind_prompt(task, failing)
    else:
        prompt = pack(workspace, task["id"], [task["file"], *also.keys()], max_chars=int(task.get("budget") or 800))
        if failing:
            prompt += "\n\nFailing cases:\n" + failing
        prompt += "\n\n" + task["prompt"]
    try:
        def tests_ok() -> bool:
            if task.get("test"):
                import subprocess
                import sys
                proc = subprocess.run(
                    [sys.executable, str(workspace / task["test"])],
                    cwd=str(workspace),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                return proc.returncode == 0
            return checker_for(task["id"])((workspace / task["file"]).read_text(encoding="utf-8"))

        if task.get("must_read"):
            from core.kernel.read_gate import file_names, take_read

            allowed = file_names(task)
            seen = []
            text = _ask(prompt, n=48)
            for _ in range(3):
                path = take_read(text, allowed)
                if path and path not in seen:
                    seen.append(path)
                    body = (workspace / path).read_text(encoding="utf-8")
                    prompt = prompt + "\n\n### " + path + "\n" + body
                    if path == task["file"]:
                        break
                text = _ask(prompt + "\nReply with one READ line for a file not opened yet.\n", temperature=0.3, n=48)
            row["read"] = seen
            if task["file"] not in seen:
                text_tail = text
                result = {
                    "ok": False,
                    "honest": False,
                    "strategy": "generate",
                    "mode": "live",
                    "generate_fallback": True,
                    "reason": "no_read",
                    "tests_ok": False,
                }
            else:
                prompt = prompt + "\n\n" + task["prompt"]
                try:
                    text = _ask(prompt, n=predict)
                except Exception as exc:
                    row["ask_error"] = f"{type(exc).__name__}: {exc}"[:300]
                    text = _ask(prompt, n=predict)
                text_tail = text
                result = run_model_edit(workspace, task["file"], text, tests_ok)
        else:
            text = _ask(prompt, n=predict)
            text_tail = text
            result = run_model_edit(workspace, task["file"], text, tests_ok)
        if not result.get("honest") and result.get("reason") != "no_read":
            attempted = extract_function(text) or task["source"]
            note = repair_note(task, attempted)
            if note and note != failing:
                row["repair"] = note
                text = _ask(prompt + "\n\nYour last function " + note + "\nReply with a complete function only.\n", temperature=0.4, n=predict)
                text_tail = text
                result = run_model_edit(workspace, task["file"], text, tests_ok)
        row["response_tail"] = text_tail[-240:]
        row.update(result)
        if row.get("honest"):
            mark_passed(ROOT, task["id"])
            if task.get("repo"):
                from core.kernel.worktree import seal

                row["seal"] = seal(ROOT, task["id"])
        from core.kernel.edit_memory import recall, remember
        prior = recall(ROOT)
        line = f"{task['id']}: {'pass' if row.get('honest') else 'fail'}"
        remember(ROOT, (prior + " | " + line)[-400:] if prior else line)
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(row, default=str))
    return 0 if row.get("honest") else 1


if __name__ == "__main__":
    raise SystemExit(main())
