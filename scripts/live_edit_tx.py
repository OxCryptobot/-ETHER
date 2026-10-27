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


def _ask(prompt: str, temperature: float = 0, n: int = 220, edit: bool = False) -> str:
    from scripts.live_generate_probe import pick_model

    from core.kernel.agent_prompt import messages

    model = pick_model()
    body = json.dumps({
        "model": model,
        "messages": messages(prompt, edit=edit),
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
    from core.kernel.product_loop import apply_reply, body_key, extract_function

    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "ok": False,
        "honest": False,
        "note": "tool edit then tests. generate-only is not a pass",
    }
    task = next_task(ROOT)
    if task is None:
        if os.name != "nt":
            row["note"] = "observe_only"
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(row))
            return 0
        from core.kernel.repo_fail import run as repo_run
        from core.kernel.self_grow import next_real

        real = next_real(ROOT)
        if real:
            os.environ["ETHER_FIXTURE"] = real["fixture"]
            row["note"] = "self_grow. the system picks the next real failure"
            row["task"] = real["id"]

        row = repo_run(ROOT, _ask)
        row["ts"] = datetime.now(timezone.utc).isoformat()
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps(row, default=str))
        return 0 if row.get("honest") else 1
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
        from core.kernel.read_gate import failure_note

        failed: dict = {}

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
                failed["text"] = ((proc.stdout or "") + (proc.stderr or ""))[-400:]
                return proc.returncode == 0
            return checker_for(task["id"])((workspace / task["file"]).read_text(encoding="utf-8"))

        if task.get("must_read"):
            from core.kernel.read_gate import file_names, for_edit, read_nudge, repair_ask, source_files, take_read

            allowed = file_names(task)
            needed = source_files(task)
            seen = []
            text = _ask(prompt, n=48)
            for _ in range(len(allowed) + 1):
                path = take_read(text, allowed)
                if path and path not in seen:
                    seen.append(path)
                    body = (workspace / path).read_text(encoding="utf-8")
                    prompt = prompt + "\n\n### " + path + "\n" + body
                if all(name in seen for name in needed):
                    break
                text = _ask(prompt + "\n" + read_nudge(allowed, seen), temperature=0.3, n=48)
            row["read"] = seen
            if any(name not in seen for name in needed):
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
                prompt = for_edit(prompt, task["prompt"], list((task.get("parts") or {})))
                from core.kernel.edit_memory import lesson_line, recall_task
                from core.kernel.curriculum import miss_count, prefer

                learned = lesson_line(recall_task(ROOT, task["id"]), str(task.get("banned") or ""))
                if learned:
                    prompt = prompt + "Last failure: " + learned + "\n"
                try:
                    text = _ask(prompt, n=predict, edit=True)
                except Exception as exc:
                    row["ask_error"] = f"{type(exc).__name__}: {exc}"[:300]
                    text = _ask(prompt, n=predict, edit=True)
                if "def " not in text:
                    text = _ask(prompt + "\nDo not reply READ. Reply with the function or functions.\n", temperature=0.4, n=predict, edit=True)
                texts = [text]
                if task.get("cases"):
                    for temp in (0.7, 0.9):
                        src = extract_function(texts[-1]) or ""
                        if miss_count(task, src) == 0:
                            break
                        note = repair_note(task, src) if src else ""
                        texts.append(
                            _ask(
                                prompt + "\n" + (note or "That failed.") + "\nReply with a different function.\n",
                                temperature=temp,
                                n=predict,
                                edit=True,
                            )
                        )
                    chosen = prefer(task, [extract_function(item) or "" for item in texts])
                    if chosen:
                        text = chosen
                text_tail = text
                row["samples"] = len(texts)
                result = apply_reply(workspace, task["file"], text, tests_ok, task.get("parts"))
        else:
            text = _ask(prompt, n=predict, edit=True)
            text_tail = text
            result = apply_reply(workspace, task["file"], text, tests_ok, task.get("parts"))
        seen_bodies = []
        first_key = body_key(extract_function(text) or "")
        if first_key:
            seen_bodies.append(first_key)
        if result.get("reason") != "no_read":
            from core.kernel.read_gate import fresh_note, pick_note, repair_ask

            seen_notes: list = []
            for _ in range(2):
                if result.get("honest"):
                    break
                attempted = extract_function(text) or task["source"]
                note = pick_note(
                    repair_note(task, attempted),
                    failure_note(failing, failed.get("text", ""), str(task.get("banned") or "")),
                    failing,
                )
                note = fresh_note(note, seen_notes, failing)
                if not note:
                    break
                seen_notes.append(note)
                row["repair"] = note
                text = _ask(prompt + "\n" + repair_ask(note, list((task.get("parts") or {}))), temperature=0.4, n=predict, edit=True)
                text_tail = text
                key = body_key(extract_function(text) or "")
                if key and key in seen_bodies:
                    text = _ask(prompt + "\nThat function already failed. Reply with a different function.\n", temperature=0.4, n=predict, edit=True)
                    text_tail = text
                    key = body_key(extract_function(text) or "")
                    if not key or key in seen_bodies:
                        result = {
                            "ok": False,
                            "honest": False,
                            "strategy": "tool_runtime",
                            "mode": "live",
                            "reason": "repeated",
                            "tests_ok": False,
                            "tools": ["replace_file"],
                        }
                        break
                if key:
                    seen_bodies.append(key)
                new_src = extract_function(text) or ""
                new_note = repair_note(task, new_src) if new_src else ""
                old_note = repair_note(task, attempted)
                if (
                    new_note
                    and new_note == old_note
                    and "the test file failed" not in new_note
                    and new_note != "the function raised"
                ):
                    result = {
                        "ok": False,
                        "honest": False,
                        "strategy": "tool_runtime",
                        "mode": "live",
                        "reason": "repeated",
                        "tests_ok": False,
                        "tools": ["replace_file"],
                    }
                    break
                result = apply_reply(workspace, task["file"], text, tests_ok, task.get("parts"))
        row["response_tail"] = text_tail[-240:]
        row.update(result)
        if row.get("honest"):
            mark_passed(ROOT, task["id"])
            if task.get("repo"):
                from core.kernel.worktree import seal

                row["seal"] = seal(ROOT, task["id"], [task["file"], *list(task.get("also") or {})])
        from core.kernel.edit_memory import lesson_line, remember_task

        learned = lesson_line(str(row.get("repair") or ""), str(task.get("banned") or ""))
        line = learned or f"{task['id']}: {'pass' if row.get('honest') else 'fail'}"
        remember_task(ROOT, task["id"], line)
        from core.kernel.curriculum import bench, note_open

        row["bench"] = bench(ROOT, row)
        note_open(ROOT, task["id"])
    except Exception as exc:
        row["error"] = f"{type(exc).__name__}: {exc}"[:300]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(row, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(row, default=str))
    return 0 if row.get("honest") else 1


if __name__ == "__main__":
    raise SystemExit(main())
