"""Phase C — tool-first agent runtime (Observe → Act → Observe).

NOT the best-of-N generate loop in core/agent_loop.py. That was measured net
negative (FINDINGS §11). This runtime:

- exposes a small tool surface (read / list / write / test / done)
- asks the model for ONE structured tool call per step
- executes it against a staging copy of a fixture
- stops when project tests pass or budget is exhausted

Gated by ETHER_TOOL_RUNTIME=1 (default off). Fully testable without a model
via injectible decide_fn / call_fn.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]

TOOL_SPECS: Sequence[Dict[str, str]] = (
    {
        "name": "list_files",
        "doc": "List files under the workspace root (relative paths).",
    },
    {
        "name": "read_file",
        "doc": "Read a text file. args: path (relative).",
    },
    {
        "name": "write_file",
        "doc": "Write/overwrite a text file. args: path, content.",
    },
    {
        "name": "run_tests",
        "doc": "Run project pytest in the workspace. No args. Returns ok/score.",
    },
    {
        "name": "done",
        "doc": "End the loop. args: reason (str). Call only when tests pass or giving up.",
    },
)


def tool_runtime_enabled() -> bool:
    return (os.getenv("ETHER_TOOL_RUNTIME") or "").strip() == "1"


@dataclass
class StepRecord:
    step: int
    tool: str
    args: Dict[str, Any]
    observation: Dict[str, Any]
    ok: bool


@dataclass
class RuntimeResult:
    ok: bool
    score: float
    steps: List[StepRecord] = field(default_factory=list)
    final_code: Dict[str, str] = field(default_factory=dict)
    error: str = ""
    reason: str = ""
    n_steps: int = 0
    elapsed_s: float = 0.0


DecideFn = Callable[[List[Dict[str, str]]], Dict[str, Any]]
CallFn = Callable[[List[Dict[str, str]]], str]


def _extract_json_objects(raw: str) -> List[str]:
    """Pull candidate JSON objects, including nested braces (write_file content)."""
    out: List[str] = []
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        out.append(fence.group(1))
    i = 0
    while i < len(raw):
        if raw[i] != "{":
            i += 1
            continue
        depth = 0
        in_str = False
        esc = False
        j = i
        while j < len(raw):
            ch = raw[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        out.append(raw[i : j + 1])
                        break
            j += 1
        i = j + 1 if depth == 0 else i + 1
    return out


def parse_action(text: str) -> Dict[str, Any]:
    """Extract a single tool call. Nested {} in write content supported.

    Unparseable returns tool=_retry so the loop continues (not done).
    """
    raw = (text or "").strip()
    if not raw:
        return {"tool": "_retry", "args": {"reason": "empty model output"}}
    for c in _extract_json_objects(raw):
        if '"tool"' not in c and "'tool'" not in c:
            continue
        try:
            obj = json.loads(c)
        except json.JSONDecodeError:
            try:
                obj, _ = json.JSONDecoder().raw_decode(c)
            except json.JSONDecodeError:
                continue
        if isinstance(obj, dict) and obj.get("tool"):
            tool = str(obj["tool"]).strip()
            if tool.startswith("_"):
                continue
            args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
            return {"tool": tool, "args": args}
    return {"tool": "_retry", "args": {"reason": "unparseable action"}}


def _blocked(rel: str) -> Optional[str]:
    rel = rel.replace("\\", "/").strip()
    if not rel or rel.startswith("/") or re.match(r"^[A-Za-z]:/", rel):
        return "absolute path refused"
    if ".." in Path(rel).parts:
        return "parent traversal refused"
    blocked = {".git", ".venv", "venv", "memory", "node_modules", "__pycache__"}
    if any(p.lower() in blocked for p in Path(rel).parts):
        return "blocked segment"
    return None


class ToolRuntime:
    """Observe → Act loop over a staging copy of a fixture."""

    def __init__(
        self,
        *,
        fixture_root: Path,
        decide_fn: DecideFn,
        test_args: Optional[Sequence[str]] = None,
        max_steps: int = 8,
        timeout_s: float = 120.0,
        pytest_timeout: int = 30,
    ) -> None:
        self.fixture_root = Path(fixture_root)
        self.decide_fn = decide_fn
        self.test_args = list(test_args or ["tests"])
        self.max_steps = max(1, int(max_steps))
        self.timeout_s = float(timeout_s)
        self.pytest_timeout = int(pytest_timeout)
        self.workspace: Optional[Path] = None
        self.steps: List[StepRecord] = []

    def _seed(self) -> Path:
        from core.repo_oracle import seed_staging

        return seed_staging(self.fixture_root)

    def _obs_list(self) -> Dict[str, Any]:
        assert self.workspace is not None
        files = []
        for p in sorted(self.workspace.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                files.append(str(p.relative_to(self.workspace)).replace("\\", "/"))
        return {"ok": True, "files": files[:80], "n": len(files)}

    def _obs_read(self, path: str) -> Dict[str, Any]:
        assert self.workspace is not None
        reason = _blocked(path)
        if reason:
            return {"ok": False, "error": reason}
        target = (self.workspace / path).resolve()
        try:
            target.relative_to(self.workspace.resolve())
        except ValueError:
            return {"ok": False, "error": "path escape refused"}
        if not target.is_file():
            return {"ok": False, "error": f"not found: {path}"}
        text = target.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "path": path, "content": text[:12000], "n_chars": len(text)}

    def _obs_write(self, path: str, content: str) -> Dict[str, Any]:
        assert self.workspace is not None
        reason = _blocked(path)
        if reason:
            return {"ok": False, "error": reason}
        target = (self.workspace / path).resolve()
        try:
            target.relative_to(self.workspace.resolve())
        except ValueError:
            return {"ok": False, "error": "path escape refused"}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if content is not None else "", encoding="utf-8")
        return {"ok": True, "path": path, "n_chars": len(content or "")}

    def _obs_tests(self) -> Dict[str, Any]:
        assert self.workspace is not None
        from core.repo_oracle import run_project_pytest

        result = run_project_pytest(
            self.workspace, test_args=self.test_args, timeout=self.pytest_timeout
        )
        stdout = result.get("stdout") or ""
        fails = []
        for line in stdout.splitlines():
            s = line.strip()
            if s.startswith("FAILED ") or s.startswith("E ") or "ValueError" in s or "AssertionError" in s:
                fails.append(s[:160])
        return {
            "ok": bool(result.get("ok")),
            "score": float(result.get("score") or 0.0),
            "returncode": result.get("returncode"),
            "failed": fails[:12],
            "stdout": stdout[-1800:],
            "stderr": (result.get("stderr") or "")[-800:],
        }

    def _execute(self, tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if tool == "list_files":
            return self._obs_list()
        if tool == "read_file":
            return self._obs_read(str(args.get("path") or ""))
        if tool == "write_file":
            return self._obs_write(str(args.get("path") or ""), str(args.get("content") or ""))
        if tool == "run_tests":
            return self._obs_tests()
        if tool == "done":
            return {"ok": True, "reason": str(args.get("reason") or "done")}
        if tool == "_retry":
            return {
                "ok": False,
                "error": "unparseable",
                "hint": "Reply with ONE JSON object only",
            }
        return {"ok": False, "error": f"unknown tool: {tool}"}

    def _system_prompt(self, objective: str) -> str:
        tools = "\n".join(f"- {t['name']}: {t['doc']}" for t in TOOL_SPECS)
        return (
            "You are a coding agent with tools. Each turn, output ONE JSON object only:\n"
            '  {"tool": "<name>", "args": {...}}\n'
            "No markdown, no prose. Tools:\n"
            f"{tools}\n\n"
            f"Objective:\n{objective}\n"
            "Strategy: list/read to understand, write_file to fix, run_tests to verify, "
            "done when tests pass."
        )

    def _snapshot_code(self) -> Dict[str, str]:
        assert self.workspace is not None
        out: Dict[str, str] = {}
        for p in sorted(self.workspace.rglob("*.py")):
            if "__pycache__" in p.parts or "tests" in p.parts:
                continue
            rel = str(p.relative_to(self.workspace)).replace("\\", "/")
            try:
                out[rel] = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
        return out

    def run(self, objective: str) -> RuntimeResult:
        t0 = time.perf_counter()
        self.steps = []
        self.workspace = self._seed()
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._system_prompt(objective)},
            {"role": "user", "content": "Begin. Call a tool."},
        ]
        best_score = 0.0
        last_ok = False
        try:
            for i in range(self.max_steps):
                if time.perf_counter() - t0 > self.timeout_s:
                    return RuntimeResult(
                        ok=False,
                        score=best_score,
                        steps=list(self.steps),
                        final_code=self._snapshot_code(),
                        error="timeout",
                        n_steps=len(self.steps),
                        elapsed_s=time.perf_counter() - t0,
                    )
                try:
                    decision = self.decide_fn(messages)
                except Exception as e:
                    return RuntimeResult(
                        ok=False,
                        score=best_score,
                        steps=list(self.steps),
                        final_code=self._snapshot_code(),
                        error=f"decide_fn: {type(e).__name__}: {e}"[:200],
                        n_steps=len(self.steps),
                        elapsed_s=time.perf_counter() - t0,
                    )
                if not isinstance(decision, dict):
                    decision = parse_action(str(decision))
                tool = str(decision.get("tool") or "done").strip()
                args = decision.get("args") if isinstance(decision.get("args"), dict) else {}
                obs = self._execute(tool, args)
                rec = StepRecord(
                    step=i + 1,
                    tool=tool,
                    args={k: (str(v)[:200] if k == "content" else v) for k, v in args.items()},
                    observation={
                        k: (str(v)[:500] if k in ("stdout", "stderr", "content") else v)
                        for k, v in obs.items()
                    },
                    ok=bool(obs.get("ok")),
                )
                self.steps.append(rec)
                if tool == "run_tests":
                    sc = float(obs.get("score") or 0.0)
                    best_score = max(best_score, sc)
                    if obs.get("ok"):
                        last_ok = True
                        return RuntimeResult(
                            ok=True,
                            score=sc,
                            steps=list(self.steps),
                            final_code=self._snapshot_code(),
                            reason="tests passed",
                            n_steps=len(self.steps),
                            elapsed_s=time.perf_counter() - t0,
                        )
                if tool == "done":
                    return RuntimeResult(
                        ok=last_ok,
                        score=best_score,
                        steps=list(self.steps),
                        final_code=self._snapshot_code(),
                        reason=str(args.get("reason") or obs.get("reason") or "done"),
                        n_steps=len(self.steps),
                        elapsed_s=time.perf_counter() - t0,
                    )
                messages.append(
                    {
                        "role": "assistant",
                        "content": json.dumps({"tool": tool, "args": args}, default=str)[:1500],
                    }
                )
                messages.append(
                    {
                        "role": "user",
                        "content": "Observation:\n"
                        + json.dumps(rec.observation, default=str)[:2000]
                        + "\nNext tool call (JSON only).",
                    }
                )
            return RuntimeResult(
                ok=False,
                score=best_score,
                steps=list(self.steps),
                final_code=self._snapshot_code(),
                error="max_steps",
                n_steps=len(self.steps),
                elapsed_s=time.perf_counter() - t0,
            )
        finally:
            if self.workspace is not None:
                shutil.rmtree(self.workspace, ignore_errors=True)
                self.workspace = None


def _default_rose_call(
    messages: List[Dict[str, str]],
    *,
    temperature: float = 0.1,
    max_tokens: int = 512,
) -> str:
    """Call Rose Quartz via the gem registry. Soft import — core stays thin."""
    from uuid import uuid4

    from core.registry import build_default_registry
    from core.schemas import ChatMessage, Envelope, RoseQuartzRequest, RoseQuartzResponse

    reg = build_default_registry()
    chat = [
        ChatMessage(role=m.get("role", "user"), content=m.get("content") or "")  # type: ignore[arg-type]
        for m in messages
    ]
    env = Envelope(
        task_id=uuid4(),
        target_gem="rose-quartz",
        payload=RoseQuartzRequest(
            messages=chat,
            prefer_local=True,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
        ),
    )
    res = reg.execute(env)
    if res.error:
        raise RuntimeError(f"rose-quartz: {res.error.message}")
    if not isinstance(res.payload, RoseQuartzResponse):
        raise RuntimeError("rose-quartz: unexpected payload")
    return str(res.payload.content or "")


def make_llm_decide_fn(
    call_fn: Optional[CallFn] = None,
    *,
    temperature: float = 0.1,
    max_tokens: int = 512,
) -> DecideFn:
    """Build a decide_fn that asks a model for one JSON tool call.

    - `call_fn(messages) -> str` is injectible (tests / offline).
    - Default call_fn routes through Rose Quartz (Ollama local primary).
    - Output is always parsed via `parse_action` (fail closed).
    """

    def _call(messages: List[Dict[str, str]]) -> str:
        if call_fn is not None:
            return call_fn(messages)
        return _default_rose_call(
            messages, temperature=temperature, max_tokens=max_tokens
        )

    def decide(messages: List[Dict[str, str]]) -> Dict[str, Any]:
        raw = _call(messages)
        return parse_action(raw)

    return decide


def run_if_enabled(
    objective: str,
    *,
    decide_fn=None,
    fixture_root=None,
    max_steps=None,
    timeout_s=None,
):
    """Phase C slice 3 entry — run tool runtime when gated on, else None."""
    import os
    from pathlib import Path as _P

    if not tool_runtime_enabled():
        return None
    root = fixture_root
    if root is None:
        raw = (
            (os.getenv("ETHER_TOOL_RUNTIME_FIXTURE") or "").strip()
            or (os.getenv("ETHER_REPO_ORACLE_FIXTURE") or "").strip()
        )
        if not raw:
            return None
        root = _P(raw)
    root = _P(root)
    if not root.is_dir():
        return RuntimeResult(ok=False, score=0.0, error=f"fixture not found: {root}")
    steps = max_steps
    if steps is None:
        try:
            steps = int(os.getenv("ETHER_TOOL_RUNTIME_STEPS") or "8")
        except ValueError:
            steps = 8
    wall = timeout_s
    if wall is None:
        try:
            wall = float(os.getenv("ETHER_TOOL_RUNTIME_SECONDS") or "180")
        except ValueError:
            wall = 180.0
    decide = decide_fn if decide_fn is not None else make_llm_decide_fn()
    rt = ToolRuntime(
        fixture_root=root,
        decide_fn=decide,
        max_steps=steps,
        timeout_s=wall,
    )
    return rt.run(objective)


def code_from_result(result):
    """Flatten final_code into a single artifact (markers if multi-file)."""
    files = result.final_code or {}
    if not files:
        return ""
    if len(files) == 1:
        return next(iter(files.values()))
    parts = []
    for rel, body in sorted(files.items()):
        parts.append("# file: " + rel + chr(10) + body)
    return (chr(10) + chr(10)).join(parts)

