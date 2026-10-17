"""When the ladder is done, one existing failing project. The model picks the file."""
from __future__ import annotations

import json
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
        "A test in this project fails. You have not been told which file.\n"
        "Reply with one JSON object and nothing else.\n"
        '{"tool":"grep","args":{"pattern":"<regex>"}}\n'
        '{"tool":"read_file","args":{"path":"<relative path>"}}\n'
        '{"tool":"apply_patch","args":{"path":"<relative path>","old":"<exact text>","new":"<exact text>"}}\n'
        '{"tool":"run_tests","args":{}}\n'
        "Search or read before you patch.\n"
    )


def _today(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def trace_text(state: Dict[str, Any], now: datetime | None = None) -> str:
    """Today's tool trace only. A slogan is not memory, and yesterday is dropped."""
    trace = state.get("trace") if isinstance(state.get("trace"), dict) else {}
    if not trace or trace.get("day") != _today(now):
        return ""
    lines: List[str] = []
    tools = [str(item) for item in (trace.get("tools") or [])]
    if tools:
        lines.append("tools: " + ", ".join(tools))
    hits = [str(item) for item in (trace.get("hits") or [])][:6]
    if trace.get("pattern"):
        lines.append("pattern: " + str(trace["pattern"])[:120])
        if not hits:
            lines.append("pattern matched nothing")
    if trace.get("rejected"):
        lines.append("rejected: " + str(trace["rejected"]))
    if hits:
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


def fit(prompt: str, obs: Dict[str, Any], budget: int | None = None) -> str:
    """The instruction stays. A tool result is cut to the budget, not the whole file."""
    cap = budget if budget is not None else min(context_char_budget(), 1800)
    block = json.dumps(obs, default=str)
    if len(block) > 700:
        block = block[:700]
    head = prompt[:500]
    merged = head + "\n" + block + "\nReply with one JSON tool.\n"
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
        return {"ok": result["ok"], "tests_ok": result["ok"], "tail": result["tail"]}
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


def _remember(root: Path, state: Dict[str, Any], tools: List[str], hits: List[str], *, rejected: str = "", patch: str = "", assertion: str = "", pattern: str = "") -> None:
    state["trace"] = {
        "day": _today(),
        "tools": list(tools),
        "hits": hits[:6],
        "rejected": rejected,
        "patch": patch[:180],
        "assertion": assertion[:180],
        "pattern": pattern[:120],
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
    focus = ""
    rejected = ""
    failed_patch = ""
    assertion = ""
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
        if tool not in ALLOWED:
            prompt = fit(base, {"ok": False, "reason": "use grep, read_file, apply_patch, or run_tests"})
            continue
        if tool == "apply_patch" and not saw_file:
            prompt = fit(base, {"ok": False, "reason": "search or read before a patch", "hits": hits[:6]})
            tools.append(tool)
            continue
        if tool == "read_file" and hits:
            wanted = str(args.get("path") or "").replace("\\", "/")
            known = [item.split(":", 1)[0] for item in hits]
            if wanted not in known:
                rejected = wanted
                obs = {"ok": False, "reason": "that path is not a search hit", "hits": hits[:6]}
                tools.append(tool)
                prompt = fit(base, obs)
                continue
        if tool == "read_file" and focus:
            args = dict(args)
            args["focus"] = focus
        obs = act(workspace, tool, args)
        tools.append(tool)
        if tool == "grep":
            focus = str(args.get("pattern") or focus)
            if obs.get("hits"):
                hits = [str(item) for item in obs["hits"]]
                saw_file = True
        if tool == "read_file" and obs.get("ok") and obs.get("body"):
            saw_file = True
            obs["next"] = "apply_patch"
        elif tool == "read_file":
            rejected = str(args.get("path") or rejected)
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
            _remember(root, state, tools, hits, pattern=focus)
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
    _remember(root, state, tools, hits, rejected=rejected, patch=failed_patch, assertion=assertion, pattern=focus)
    row["tools"] = list(tools)
    row["honest"] = False
    row["passes"] = len(passes)
    return row
