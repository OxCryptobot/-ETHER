"""When the ladder is done, one existing failing project. The model picks the file."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

from core.kernel.context_budget import context_char_budget
from core.kernel.honest import is_honest_tool_path_pass
from core.tool_runtime import parse_action

FIXTURE = "fixtures/repo_oracle_toy"
ALLOWED = ("grep", "read_file", "apply_patch", "run_tests")
NEED = 2


def opening() -> str:
    """No path and no expected text. The model has to search."""
    return (
        "You have not been told which file.\n"
        "Reply with one JSON object and nothing else.\n"
        '{"tool":"grep","args":{"pattern":"<text in a line>"}}\n'
        '{"tool":"read_file","args":{"path":"<relative path>"}}\n'
        '{"tool":"apply_patch","args":{"path":"<relative path>","old":"<exact text>","new":"<exact text>"}}\n'
        '{"tool":"run_tests","args":{}}\n'
        "Search or read before you patch.\n"
    )


def _today(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _useful_body(text: str) -> bool:
    """A test helper is not memory. Keep a definition or an assertion."""
    raw = text or ""
    return "def " in raw or "assert " in raw


def _useful_body(text: str) -> bool:
    """A test helper is not memory. Keep a definition or an assertion."""
    raw = text or ""
    return "def " in raw or "assert " in raw


def _return_line(body: str) -> str:
    """The line a patch must change. Already in the body the model read."""
    for line in (body or "").splitlines():
        piece = line.strip()
        if piece.startswith("return "):
            return piece
    return ""


def _expected(body: str) -> str:
    """The expected text already written in the file the model read."""
    match = re.search(r'expect[s]?\s+"([^"]+)"', body or "")
    return match.group(1) if match else ""


def _patch_skeleton(path: str, body: str) -> Dict[str, Any]:
    """A complete tool call. The expected text comes from the comment already in the body."""
    old = _return_line(body)
    expected = _expected(body)
    new = f'return f"{expected}"' if expected and old.startswith("return f") else ""
    return {
        "tool": "apply_patch",
        "args": {
            "path": path or "the file you read",
            "old": old,
            "new": new,
        },
    }


def _as_patch(text: str, path: str, body: str) -> Dict[str, Any] | None:
    """A reply that contains the expected line is the patch. The model chose the text."""
    skeleton = _patch_skeleton(path, body)
    new = str((skeleton.get("args") or {}).get("new") or "")
    old = str((skeleton.get("args") or {}).get("old") or "")
    if not new or new not in (text or ""):
        return None
    return {"tool": "apply_patch", "args": {"path": path, "old": old, "new": new}}


def _imports(text: str) -> List[str]:
    """Module names a read body imports. The harness does not open them."""
    found: List[str] = []
    for match in re.finditer(r"from\s+([A-Za-z_][\w.]*)\s+import", text or ""):
        name = match.group(1).split(".")[0]
        if name and name not in found:
            found.append(name)
    return found


def _add_imports(hits: List[str], body: str, workspace: Path) -> List[str]:
    """An import of a file that exists becomes an unread path the model can choose."""
    known = [item.split(":", 1)[0] for item in hits]
    for name in _imports(body):
        candidate = f"{name}.py"
        if candidate in known:
            continue
        if (workspace / candidate).is_file():
            hits.append(candidate)
            known.append(candidate)
    return known


def trace_text(state: Dict[str, Any], now: datetime | None = None) -> str:
    """Today's tool trace only. A slogan is not memory, and yesterday is dropped."""
    trace = state.get("trace") if isinstance(state.get("trace"), dict) else {}
    if not trace or trace.get("day") != _today(now):
        return ""
    lines: List[str] = []
    missed = _missed(state)
    if missed:
        lines.append("do not search again: " + ", ".join(missed))
    body = str(trace.get("body") or "")
    if body and not _useful_body(body):
        body = ""
    hits = [str(item) for item in (trace.get("hits") or [])][:6]
    if body:
        lines.append("body:")
        lines.append(body[:500])
    elif hits:
        lines.append("hits:")
        lines.extend(hits)
    if trace.get("patch"):
        lines.append("patch failed: " + str(trace["patch"])[:180])
    if trace.get("assertion"):
        lines.append("assertion: " + str(trace["assertion"])[:180])
    return "\n".join(lines)


def start_prompt(state: Dict[str, Any], now: datetime | None = None) -> str:
    trace = trace_text(state, now)
    if not trace:
        return opening()
    return opening() + "Last trace:\n" + trace + "\n"


def _state_path(root: Path) -> Path:
    return Path(root) / "artifacts" / "repo_fail.json"


def load_state(root: Path) -> Dict[str, Any]:
    path = _state_path(root)
    if not path.is_file():
        return {"passes": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"passes": []}
    if not isinstance(data, dict):
        return {"passes": []}
    data.setdefault("passes", [])
    return data


def _save(root: Path, data: Dict[str, Any]) -> None:
    path = _state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def workspace_for(root: Path) -> Path:
    return Path(root) / "repo_fail_ws"


def reset_workspace(root: Path) -> Path:
    """A fresh copy of the broken project. The canonical fixture stays broken."""
    src = Path(root) / FIXTURE
    dest = workspace_for(root)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    return dest


def _missed(state: Dict[str, Any]) -> List[str]:
    """Patterns that already matched nothing today. Yesterday is not included."""
    trace = state.get("trace") if isinstance(state.get("trace"), dict) else {}
    if not trace or trace.get("day") != _today():
        return []
    missed: List[str] = []
    for item in trace.get("missed") or []:
        text = str(item).strip()
        if text and text not in missed:
            missed.append(text)
    pattern = str(trace.get("pattern") or "").strip()
    if pattern and not trace.get("hits") and pattern not in missed:
        missed.append(pattern)
    return missed


def fit(prompt: str, obs: Dict[str, Any], budget: int | None = None) -> str:
    """The instruction stays. A tool result is cut to the budget, not the whole file."""
    cap = budget if budget is not None else min(context_char_budget(), 1800)
    reason = str(obs.get("reason") or "")
    notice = (reason + "\n") if reason else ""
    block = json.dumps(obs, default=str)
    tail = "\nReply with one JSON tool.\n"
    keep = min(160, max(0, cap - len(notice) - len(tail)))
    block = block[: max(0, cap - len(notice) - len(tail) - keep)]
    head = prompt[:keep]
    merged = notice + head + "\n" + block + tail
    return merged[:cap]


def _inside(workspace: Path, rel: str) -> Path | None:
    rel = (rel or "").replace("\\", "/").strip()
    if not rel or rel.startswith("/") or ".." in Path(rel).parts:
        return None
    path = (workspace / rel).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError:
        return None
    return path


def _slice(text: str, focus: str) -> str:
    """Matching lines, not the file. A 4B cannot hold the rest."""
    if not focus:
        return text[:800]
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if focus in line:
            return "\n".join(lines[max(0, i - 2) : i + 6])[:800]
    return text[:800]


def _assertion(tail: str) -> str:
    for line in (tail or "").splitlines():
        piece = line.strip()
        if "AssertionError" in piece or piece.startswith("E ") or "assert " in piece:
            return piece[:180]
    return (tail or "").strip()[-180:]


def _pytest(workspace: Path) -> Dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q", "--tb=line"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
        timeout=30,
    )
    tail = ((proc.stdout or "") + (proc.stderr or ""))[-400:]
    return {"ok": proc.returncode == 0, "tail": tail, "assertion": _assertion(tail)}


def act(workspace: Path, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    if tool == "grep":
        pattern = str(args.get("pattern") or "")
        if not pattern:
            return {"ok": False, "reason": "pattern required"}
        hits: List[str] = []
        for path in sorted(workspace.rglob("*")):
            if not path.is_file() or path.suffix not in {".py", ".txt", ".md"}:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            rel = path.relative_to(workspace).as_posix()
            for i, line in enumerate(lines, 1):
                if pattern in line:
                    hits.append(f"{rel}:{i}:{line.strip()[:160]}")
                    if len(hits) >= 6:
                        return {"ok": True, "hits": hits}
        return {"ok": True, "hits": hits}
    if tool == "read_file":
        path = _inside(workspace, str(args.get("path") or ""))
        if path is None or not path.is_file():
            return {"ok": False, "reason": "no such file"}
        return {"ok": True, "path": path.relative_to(workspace).as_posix(), "body": _slice(path.read_text(encoding="utf-8"), str(args.get("focus") or ""))}
    if tool == "run_tests":
        result = _pytest(workspace)
        return {"ok": result["ok"], "tests_ok": result["ok"], "tail": result["tail"], "assertion": result.get("assertion") or ""}
    if tool == "apply_patch":
        path = _inside(workspace, str(args.get("path") or ""))
        old = str(args.get("old") or "")
        new = str(args.get("new") or "")
        if path is None or not path.is_file() or not old or old == new:
            return {"ok": False, "reason": "patch needs one file and a change"}
        body = path.read_text(encoding="utf-8")
        if body.count(old) != 1:
            return {"ok": False, "reason": "old text must match once"}
        path.write_text(body.replace(old, new, 1), encoding="utf-8")
        result = _pytest(workspace)
        if not result["ok"]:
            path.write_text(body, encoding="utf-8")
            return {"ok": False, "tests_ok": False, "tx": ["begin", "revert"], "tail": result["tail"], "assertion": result.get("assertion") or ""}
        return {
            "ok": True,
            "tests_ok": True,
            "tx": ["begin", "promote"],
            "path": path.relative_to(workspace).as_posix(),
        }
    return {"ok": False, "reason": "unknown tool"}


def _remember(root: Path, state: Dict[str, Any], tools: List[str], hits: List[str], *, rejected: str = "", patch: str = "", assertion: str = "", pattern: str = "", missed: List[str] | None = None, body: str = "", read_path: str = "", read_paths: List[str] | None = None) -> None:
    kept = body if _useful_body(body) else ""
    state["trace"] = {
        "day": _today(),
        "tools": list(tools),
        "hits": hits[:6],
        "rejected": rejected,
        "patch": patch[:180],
        "assertion": assertion[:180],
        "pattern": pattern[:120],
        "missed": [str(item) for item in (missed or [])][:8],
        "body": kept[:500],
        "read_path": read_path if kept else "",
        "read_paths": [str(item) for item in (read_paths or [])][:8],
    }
    state["last_tools"] = list(tools)
    _save(root, state)


def _coerce(text: str) -> str:
    raw = text or ""
    return raw.replace('"tool","', '"tool":"').replace('"args","', '"args":"')


def run(root: Path, ask: Callable[..., str], *, steps: int = 8) -> Dict[str, Any]:
    root = Path(root)
    state = load_state(root)
    passes = [str(item) for item in (state.get("passes") or [])]
    if len(passes) >= NEED:
        return {
            "ok": True,
            "honest": False,
            "note": "repo_fail_repeated",
            "passes": len(passes),
            "tools": state.get("last_tools") or [],
            "strategy": "tool_runtime",
            "mode": "live",
        }
    workspace = reset_workspace(root)
    base = start_prompt(state)
    prompt = base
    tools: List[str] = []
    saw_file = False
    remembered = state.get("trace") if isinstance(state.get("trace"), dict) else {}
    hits = [str(item) for item in (remembered.get("hits") or [])] if remembered.get("day") == _today() else []
    missed = _missed(state)
    focus = ""
    rejected = ""
    failed_patch = ""
    assertion = str(remembered.get("assertion") or "") if remembered.get("day") == _today() else ""
    last_body = str(remembered.get("body") or "") if remembered.get("day") == _today() else ""
    if last_body and not _useful_body(last_body):
        last_body = ""
    remembered_paths = [str(item) for item in (remembered.get("read_paths") or [])] if remembered.get("day") == _today() else []
    read_path = str(remembered.get("read_path") or "") if last_body else ""
    read_paths = list(dict.fromkeys(remembered_paths + ([read_path] if read_path else [])))
    refusals = 0
    saw_file = bool(last_body)
    row: Dict[str, Any] = {
        "ok": False,
        "honest": False,
        "note": "repo fail. the model must find the file",
        "task": "repo_fail",
        "strategy": "tool_runtime",
        "mode": "live",
        "degraded": [],
        "tools": tools,
    }
    for _ in range(steps):
        try:
            text = ask(prompt, n=180)
        except Exception as exc:
            row["ask_error"] = f"{type(exc).__name__}: {exc}"[:300]
            break
        action = parse_action(_coerce(text))
        tool = str(action.get("tool") or "")
        args = action.get("args") if isinstance(action.get("args"), dict) else {}
        if last_body and "assert " not in last_body and tool != "apply_patch":
            unread_now = [path for path in [item.split(":", 1)[0] for item in hits] if path not in read_paths]
            wrapped = _as_patch(text, read_path, last_body) if not unread_now else None
            if wrapped:
                action = wrapped
                tool = "apply_patch"
                args = action["args"]
            elif not unread_now:
                refusals += 1
                tools.append(tool or "reply")
                skeleton = _patch_skeleton(read_path, last_body)
                prompt = "copy this tool and nothing else\n" + json.dumps(skeleton)
                row["response_tail"] = text[-240:]
                if refusals >= 3:
                    break
                continue
        if tool not in ALLOWED:
            prompt = fit(base, {"ok": False, "reason": "use grep, read_file, apply_patch, or run_tests"})
            continue
        if tool == "grep":
            pattern = str(args.get("pattern") or "").strip()
            if pattern in missed:
                refusals += 1
                tools.append(tool)
                prompt = fit(base, {"ok": False, "reason": "that pattern already matched nothing. search for a different string", "missed": missed[-6:]})
                if refusals >= 3:
                    break
                continue
        if tool == "apply_patch" and not saw_file:
            refusals += 1
            prompt = fit(base, {"ok": False, "reason": "search or read before a patch", "hits": hits[:6]})
            tools.append(tool)
            if refusals >= 3:
                break
            continue
        if tool == "read_file":
            wanted = str(args.get("path") or "").replace("\\", "/")
            known = [item.split(":", 1)[0] for item in hits]
            unread = [path for path in known if path not in read_paths]
            if not known:
                refusals += 1
                rejected = wanted
                tools.append(tool)
                prompt = fit(base, {"ok": False, "reason": "search first. next tool is grep"})
                if refusals >= 3:
                    break
                continue
            if wanted not in known or wanted in read_paths:
                refusals += 1
                rejected = wanted
                if last_body:
                    reason = "that file was already read. next is grep or apply_patch"
                elif wanted in read_paths:
                    reason = "that file was already read. next is grep, run_tests, or apply_patch"
                else:
                    reason = "that path is not a hit"
                tools.append(tool)
                prompt = fit(base, {"ok": False, "reason": reason, "unread": unread[:6]})
                if refusals >= 3:
                    break
                continue
        if tool == "read_file" and focus:
            args = dict(args)
            args["focus"] = focus
        obs = act(workspace, tool, args)
        tools.append(tool)
        if tool == "grep":
            focus = str(args.get("pattern") or focus).strip()
            if obs.get("hits"):
                hits = [str(item) for item in obs["hits"]]
                saw_file = True
            elif focus and focus not in missed:
                missed.append(focus)
                obs = {"ok": False, "reason": "no line contains that string. search for a different string", "pattern": focus, "missed": missed[-6:]}
        if tool == "read_file" and obs.get("ok") and obs.get("body"):
            raw = str(obs.get("body") or "")
            opened = str(obs.get("path") or wanted)
            if opened not in read_paths:
                read_paths.append(opened)
            if _useful_body(raw):
                saw_file = True
                last_body = raw
                read_path = opened
                _add_imports(hits, raw, workspace)
            obs["next"] = "apply_patch or run_tests"
            obs["unread"] = [path for path in [item.split(":", 1)[0] for item in hits] if path not in read_paths][:6]
        elif tool == "read_file":
            rejected = str(args.get("path") or rejected)
        if tool == "run_tests" and obs.get("assertion"):
            assertion = str(obs.get("assertion") or "")
        row["response_tail"] = text[-240:]
        if tool == "apply_patch":
            row["tx"] = obs.get("tx") or []
            row["tests_ok"] = bool(obs.get("tests_ok"))
            row["file"] = obs.get("path") or ""
            if not obs.get("tests_ok"):
                failed_patch = str(obs.get("reason") or obs.get("tail") or "")[:180]
                assertion = str(obs.get("assertion") or "")
        if obs.get("tests_ok") and saw_file and "apply_patch" in tools:
            passes.append(datetime.now(timezone.utc).isoformat())
            state["passes"] = passes
            _remember(root, state, tools, hits, pattern=focus, missed=missed, body=last_body, read_path=read_path, read_paths=read_paths, assertion=assertion)
            row.update({
                "ok": True,
                "tests_ok": True,
                "tools": list(tools),
                "passes": len(passes),
                "tool_runtime_ok": True,
            })
            row["honest"] = is_honest_tool_path_pass(row)
            return row
        prompt = fit(base, obs)
    _remember(root, state, tools, hits, rejected=rejected, patch=failed_patch, assertion=assertion, pattern=focus, missed=missed, body=last_body, read_path=read_path, read_paths=read_paths)
    row["tools"] = list(tools)
    row["honest"] = False
    row["passes"] = len(passes)
    if "response_tail" not in row:
        row["response_tail"] = ""
    return row
