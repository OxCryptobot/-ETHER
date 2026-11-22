"""Batch 10: a real MCP client (stdio, JSON-RPC 2.0) with an operator allowlist (audit pillar 3).

The old core/mcp_client.py needs the `mcp` SDK (not installed on the 1650) and only calls gem
servers in-process. This client has no dependency: it launches a server from config, speaks
newline-delimited JSON-RPC 2.0 over stdio (MCP stdio transport) and supports exactly what the
writer needs: initialize -> notifications/initialized -> tools/list (paged) -> tools/call.

Config (first file that exists wins; memory/ is local-only and never published):
    memory/mcp.json, config/mcp.json
    {"servers": {"docs": {"command": ["python", "-m", "some_server"], "env": {"X": "1"},
                          "read_only": ["search_docs"], "timeout_s": 15}}}

Model exposure (ETHER_MCP=1, default off): a reply may call {"tool": "mcp", "args": {"server": s,
"call": t, "arguments": {...}}}. A tool is model-callable only when it is in that server's
`read_only` list (operator allowlist) AND the server does not annotate it destructive. Server
annotations alone never grant access (a server can lie about readOnlyHint). Results are text,
capped (ETHER_MCP_MAX_CHARS). Write tools are never callable from model text and the honest gate
is unchanged: the only edit path is still the goal-file edit checked by tests.

The server process gets the scrubbed gate environment (no tokens) plus the config's `env`.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROTOCOL = "2025-06-18"
CONFIG_FILES = ("memory/mcp.json", "config/mcp.json")


class McpError(RuntimeError):
    pass


def enabled() -> bool:
    return os.getenv("ETHER_MCP", "0") == "1"


def max_chars() -> int:
    return int(os.getenv("ETHER_MCP_MAX_CHARS", "1200"))


def default_timeout() -> float:
    return float(os.getenv("ETHER_MCP_TIMEOUT_S", "15"))


def load_config(root: Path) -> Dict[str, Any]:
    for rel in CONFIG_FILES:
        path = Path(root) / rel
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return {"servers": {}, "error": f"{rel}: unreadable"}
            servers = data.get("servers") if isinstance(data, dict) else None
            return {"servers": servers if isinstance(servers, dict) else {}, "file": rel}
    return {"servers": {}}


class McpClient:
    """One stdio MCP server process. Use as a context manager."""

    def __init__(self, command: List[str], env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None,
                 timeout: Optional[float] = None) -> None:
        if not command:
            raise McpError("empty command")
        self.command = list(command)
        if self.command[0] in ("python", "python3", "py"):
            import sys

            self.command[0] = sys.executable  # the writer's own interpreter, not whatever PATH finds
        self.timeout = default_timeout() if timeout is None else float(timeout)
        from core.agent.gate_sandbox import scrub_env

        full = scrub_env()
        full.update({str(k): str(v) for k, v in (env or {}).items()})
        self.proc = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, cwd=cwd, env=full, text=True, encoding="utf-8",
                                     bufsize=1)
        self._next = 0
        self._lines: "queue.Queue[Optional[str]]" = queue.Queue()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()
        self.server_info: Dict[str, Any] = {}
        self.notifications: List[Dict[str, Any]] = []

    def _read(self) -> None:
        assert self.proc.stdout is not None
        try:
            for line in self.proc.stdout:
                self._lines.put(line)
        finally:
            self._lines.put(None)

    def _send(self, msg: Dict[str, Any]) -> None:
        if self.proc.poll() is not None or self.proc.stdin is None:
            raise McpError(f"server exited rc={self.proc.returncode}")
        try:
            self.proc.stdin.write(json.dumps(msg, separators=(",", ":")) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise McpError(f"write failed: {exc}") from exc

    def notify(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: Optional[float] = None) -> Any:
        self._next += 1
        rid = self._next
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise McpError(f"timeout waiting for {method}")
            try:
                line = self._lines.get(timeout=left)
            except queue.Empty:
                raise McpError(f"timeout waiting for {method}") from None
            if line is None:
                raise McpError(f"server closed during {method}")
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue  # a server that logs to stdout: skip non-JSON lines
            if not isinstance(data, dict):
                continue
            if "method" in data and "id" in data:  # server -> client request (sampling, roots...): refuse
                self._send({"jsonrpc": "2.0", "id": data["id"],
                            "error": {"code": -32601, "message": "not supported by ETHER"}})
                continue
            if "method" in data:
                self.notifications.append(data)
                continue
            if data.get("id") != rid:
                continue
            if "error" in data:
                err = data["error"] or {}
                raise McpError(f"{method}: {err.get('code')} {str(err.get('message'))[:200]}")
            return data.get("result")

    def initialize(self) -> Dict[str, Any]:
        res = self.request("initialize", {"protocolVersion": PROTOCOL, "capabilities": {},
                                          "clientInfo": {"name": "ether", "version": "batch10"}})
        self.server_info = res if isinstance(res, dict) else {}
        self.notify("notifications/initialized")
        return self.server_info

    def list_tools(self, max_pages: int = 10) -> List[Dict[str, Any]]:
        tools: List[Dict[str, Any]] = []
        cursor = None
        for _ in range(max_pages):
            res = self.request("tools/list", {"cursor": cursor} if cursor else {}) or {}
            tools += [t for t in (res.get("tools") or []) if isinstance(t, dict) and t.get("name")]
            cursor = res.get("nextCursor")
            if not cursor:
                break
        return tools

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        res = self.request("tools/call", {"name": name, "arguments": arguments or {}}) or {}
        texts = [str(c.get("text") or "") for c in (res.get("content") or []) if isinstance(c, dict)
                 and c.get("type") == "text"]
        return {"is_error": bool(res.get("isError")), "text": "\n".join(texts), "raw": res}

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=2)

    def __enter__(self) -> "McpClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _server(root: Path, name: str) -> Dict[str, Any]:
    cfg = load_config(root)
    spec = cfg["servers"].get(name)
    if not isinstance(spec, dict) or not isinstance(spec.get("command"), list):
        raise McpError(f"unknown MCP server {name!r}")
    return spec


def model_callable(spec: Dict[str, Any], tool: Dict[str, Any]) -> bool:
    """Operator allowlist (`read_only`) is required; a destructive annotation always refuses."""
    allow = {str(t) for t in (spec.get("read_only") or [])}
    ann = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    if ann.get("destructiveHint") is True or ann.get("readOnlyHint") is False:
        return False
    return str(tool.get("name")) in allow


def read_only_tools(root: Path, name: str) -> List[Dict[str, Any]]:
    spec = _server(root, name)
    with McpClient(spec["command"], spec.get("env"), cwd=str(root), timeout=spec.get("timeout_s")) as cli:
        cli.initialize()
        return [t for t in cli.list_tools() if model_callable(spec, t)]


def call_read_only(root: Path, server: str = "", name: str = "", arguments: Any = None) -> Dict[str, Any]:
    """The `mcp` skill. Fails closed: off, unknown server, tool not allowlisted, error, timeout."""
    base = {"skill": "mcp", "server": server, "name": name}
    if not enabled():
        return {**base, "ok": False, "reason": "ETHER_MCP off"}
    try:
        spec = _server(root, server)
        if name not in {str(t) for t in (spec.get("read_only") or [])}:
            return {**base, "ok": False, "reason": "denied: not an allowlisted read-only tool"}
        with McpClient(spec["command"], spec.get("env"), cwd=str(root), timeout=spec.get("timeout_s")) as cli:
            cli.initialize()
            tools = {t["name"]: t for t in cli.list_tools()}
            tool = tools.get(name)
            if tool is None or not model_callable(spec, tool):
                return {**base, "ok": False, "reason": "denied: tool missing or not read-only"}
            res = cli.call_tool(name, arguments if isinstance(arguments, dict) else {})
    except McpError as exc:
        return {**base, "ok": False, "reason": str(exc)[:200]}
    except OSError as exc:
        return {**base, "ok": False, "reason": f"spawn failed: {type(exc).__name__}"}
    text = res["text"][: max_chars()]
    return {**base, "ok": not res["is_error"], "hits": [text.replace("\n", " ")[:300]], "text": text}


def catalog(root: Path, limit: int = 6) -> List[str]:
    """`server.tool` names the model may call (for the prompt hint). Empty when off or unreachable."""
    if not enabled():
        return []
    out: List[str] = []
    for server in sorted(load_config(root)["servers"]):
        try:
            out += [f"{server}.{t['name']}" for t in read_only_tools(root, server)]
        except (McpError, OSError):
            continue
        if len(out) >= limit:
            break
    return out[:limit]
