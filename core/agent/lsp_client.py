"""Batch 10: a real LSP client (stdio, Content-Length framing) for read-only code intelligence.

Servers, first found wins: ETHER_LSP_CMD (shell-split), pyright-langserver --stdio, pylsp,
jedi-language-server (looked up on PATH and next to the writer's interpreter). No server ->
every call returns {"ok": False, "reason": "no language server"}: a graceful no-op.

Uses:
  ETHER_LSP=1           the model may call {"tool": "lsp", "args": {"op": "diagnostics"|"definition"|
                        "references", "file": rel, "symbol": name | "line": n, "col": c}} (read-only).
  ETHER_LSP_PREGATE=1   after the edit is applied and before the gate runs, diagnostics of the goal
                        file before vs after the edit; an edit that ADDS error-severity diagnostics
                        (undefined name, syntax, ...) is rejected and restored without spending a
                        gate run. Can only reject; reward for a rejected edit is 0 like any miss.
Both default off. The client never writes files (didOpen/didChange carry text in memory).
"""
from __future__ import annotations

import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class LspError(RuntimeError):
    pass


def enabled() -> bool:
    return os.getenv("ETHER_LSP", "0") == "1"


def pregate_on() -> bool:
    return os.getenv("ETHER_LSP_PREGATE", "0") == "1"


def timeout_s() -> float:
    return float(os.getenv("ETHER_LSP_TIMEOUT_S", "20"))


CANDIDATES = (("pyright-langserver", ["--stdio"]), ("pylsp", []), ("jedi-language-server", []))


def find_server() -> Optional[List[str]]:
    env = os.getenv("ETHER_LSP_CMD", "").strip()
    if env:
        return shlex.split(env, posix=os.name != "nt")
    bindir = Path(sys.executable).parent
    for name, args in CANDIDATES:
        hit = shutil.which(name) or shutil.which(name, path=str(bindir))
        if hit:
            return [hit, *args]
    return None


def uri(path: Path) -> str:
    return Path(path).resolve().as_uri()


class LspClient:
    def __init__(self, command: List[str], root: Path, timeout: Optional[float] = None) -> None:
        from core.agent.gate_sandbox import scrub_env

        self.root = Path(root).resolve()
        self.timeout = timeout_s() if timeout is None else float(timeout)
        self.proc = subprocess.Popen(list(command), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, cwd=str(self.root), env=scrub_env())
        self._msgs: "queue.Queue[Optional[Dict[str, Any]]]" = queue.Queue()
        self.diags: Dict[str, List[Dict[str, Any]]] = {}
        self._diag_seq: Dict[str, int] = {}
        self._cv = threading.Condition()
        self._next = 0
        self._versions: Dict[str, int] = {}
        threading.Thread(target=self._read, daemon=True).start()

    # framing ---------------------------------------------------------------
    def _read(self) -> None:
        out = self.proc.stdout
        assert out is not None
        try:
            while True:
                length = None
                while True:
                    line = out.readline()
                    if not line:
                        return
                    line = line.strip()
                    if not line:
                        break
                    k, _, v = line.decode("ascii", "ignore").partition(":")
                    if k.strip().lower() == "content-length":
                        length = int(v.strip())
                if length is None:
                    continue
                body = out.read(length)
                try:
                    msg = json.loads(body.decode("utf-8"))
                except ValueError:
                    continue
                if msg.get("method") == "textDocument/publishDiagnostics":
                    p = msg.get("params") or {}
                    with self._cv:
                        self.diags[str(p.get("uri"))] = list(p.get("diagnostics") or [])
                        self._diag_seq[str(p.get("uri"))] = self._diag_seq.get(str(p.get("uri")), 0) + 1
                        self._cv.notify_all()
                    continue
                if "method" in msg and "id" in msg:  # server -> client request: answer minimally
                    method = msg["method"]
                    result: Any = None
                    if method == "workspace/configuration":
                        result = [None for _ in (msg.get("params") or {}).get("items") or []]
                    self._write({"jsonrpc": "2.0", "id": msg["id"], "result": result})
                    continue
                self._msgs.put(msg)
        finally:
            self._msgs.put(None)
            with self._cv:
                self._cv.notify_all()

    def _write(self, msg: Dict[str, Any]) -> None:
        body = json.dumps(msg).encode("utf-8")
        if self.proc.stdin is None or self.proc.poll() is not None:
            raise LspError("server exited")
        try:
            self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise LspError(f"write failed: {exc}") from exc

    def notify(self, method: str, params: Any) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: Any, timeout: Optional[float] = None) -> Any:
        self._next += 1
        rid = self._next
        self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise LspError(f"timeout: {method}")
            try:
                msg = self._msgs.get(timeout=left)
            except queue.Empty:
                raise LspError(f"timeout: {method}") from None
            if msg is None:
                raise LspError(f"server closed during {method}")
            if msg.get("id") != rid:
                continue
            if "error" in msg:
                raise LspError(f"{method}: {str((msg['error'] or {}).get('message'))[:200]}")
            return msg.get("result")

    # protocol --------------------------------------------------------------
    def initialize(self) -> Dict[str, Any]:
        res = self.request("initialize", {
            "processId": os.getpid(), "rootUri": self.root.as_uri(),
            "workspaceFolders": [{"uri": self.root.as_uri(), "name": self.root.name}],
            "capabilities": {"textDocument": {"publishDiagnostics": {}, "definition": {}, "references": {}},
                             "workspace": {"configuration": True}},
        }, timeout=self.timeout * 1.5)
        self.notify("initialized", {})
        return res or {}

    def open(self, rel: str, text: str) -> str:
        u = uri(self.root / rel)
        ver = self._versions.get(u)
        if ver is None:
            self._versions[u] = 1
            self.notify("textDocument/didOpen", {"textDocument": {"uri": u, "languageId": "python", "version": 1,
                                                                  "text": text}})
        else:
            self._versions[u] = ver + 1
            self.notify("textDocument/didChange", {"textDocument": {"uri": u, "version": ver + 1},
                                                   "contentChanges": [{"text": text}]})
        return u

    def diagnostics(self, rel: str, text: str, wait: Optional[float] = None) -> List[Dict[str, Any]]:
        u = uri(self.root / rel)
        with self._cv:
            seq = self._diag_seq.get(u, 0)
        self.open(rel, text)
        deadline = time.monotonic() + (self.timeout if wait is None else wait)
        with self._cv:
            while self._diag_seq.get(u, 0) <= seq:
                left = deadline - time.monotonic()
                if left <= 0 or self.proc.poll() is not None:
                    raise LspError("no diagnostics before timeout")
                self._cv.wait(timeout=min(left, 0.5))
            return list(self.diags.get(u) or [])

    def locations(self, method: str, rel: str, line: int, col: int) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"textDocument": {"uri": uri(self.root / rel)}, "position": {"line": line, "character": col}}
        if method == "textDocument/references":
            params["context"] = {"includeDeclaration": False}
        res = self.request(method, params)
        if isinstance(res, dict):
            res = [res]
        out = []
        for loc in res or []:
            target = loc.get("uri") or loc.get("targetUri") or ""
            rng = loc.get("range") or loc.get("targetSelectionRange") or {}
            try:
                path = Path(target.replace("file://", "", 1)) if not target.startswith("file:") else _from_uri(target)
                rel_out = path.resolve().relative_to(self.root).as_posix()
            except (ValueError, OSError):
                rel_out = "<outside repo>"
            out.append({"file": rel_out, "line": int((rng.get("start") or {}).get("line", 0)) + 1})
        return out

    def close(self) -> None:
        try:
            self.request("shutdown", None, timeout=min(3.0, self.timeout))
            self.notify("exit", None)
        except LspError:
            pass
        try:
            self.proc.wait(timeout=min(3.0, self.timeout))
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)

    def __enter__(self) -> "LspClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def _from_uri(u: str) -> Path:
    from urllib.parse import unquote, urlparse

    p = unquote(urlparse(u).path)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:", p):
        p = p[1:]
    return Path(p)


def errors(diags: List[Dict[str, Any]]) -> List[str]:
    """Error-severity diagnostics as line-free keys (an edit shifts lines; the message is the identity)."""
    out = []
    for d in diags:
        if int(d.get("severity") or 1) != 1:
            continue
        msg = re.sub(r"\d+", "#", str(d.get("message") or ""))[:160]
        out.append(f"{d.get('source', '')}:{d.get('code', '')}:{msg}")
    return sorted(out)


def new_errors(before: List[Dict[str, Any]], after: List[Dict[str, Any]]) -> List[str]:
    from collections import Counter

    b, a = Counter(errors(before)), Counter(errors(after))
    return sorted((a - b).elements())


def _locate(text: str, symbol: str) -> Optional[Tuple[int, int]]:
    m = re.search(rf"\b{re.escape(symbol)}\b", text or "")
    if not m:
        return None
    line = text.count("\n", 0, m.start())
    col = m.start() - (text.rfind("\n", 0, m.start()) + 1)
    return line, col


def tool(root: Path, op: str = "", file: str = "", symbol: str = "", line: int = 0, col: int = 0) -> Dict[str, Any]:
    """The `lsp` skill (read-only). Repo-confined, secret paths refused (same rule as `read`)."""
    from core.agent.skills import _inside

    base = {"skill": "lsp", "op": op, "file": file}
    if not enabled():
        return {**base, "ok": False, "reason": "ETHER_LSP off"}
    if op not in ("diagnostics", "definition", "references"):
        return {**base, "ok": False, "reason": "op must be diagnostics, definition or references"}
    path = _inside(Path(root), file)
    if path is None or not path.is_file() or path.suffix != ".py":
        return {**base, "ok": False, "reason": "not a python file in the repo"}
    cmd = find_server()
    if not cmd:
        return {**base, "ok": False, "reason": "no language server"}
    text = path.read_text(encoding="utf-8", errors="ignore")
    try:
        with LspClient(cmd, Path(root)) as cli:
            cli.initialize()
            if op == "diagnostics":
                diags = cli.diagnostics(file, text)
                hits = [f"L{int(d['range']['start']['line']) + 1}: {str(d.get('message'))[:120]}" for d in diags[:5]]
                return {**base, "ok": True, "hits": ["; ".join(hits) or "no diagnostics"], "n": len(diags)}
            pos = _locate(text, symbol) if symbol else (max(0, int(line) - 1), int(col))
            if pos is None:
                return {**base, "ok": False, "reason": "symbol not in file"}
            cli.open(file, text)
            method = "textDocument/definition" if op == "definition" else "textDocument/references"
            locs = cli.locations(method, file, pos[0], pos[1])
            return {**base, "ok": bool(locs), "hits": [", ".join(f"{l['file']}:{l['line']}" for l in locs[:8]) or "none"],
                    "locations": locs[:20]}
    except (LspError, OSError) as exc:
        return {**base, "ok": False, "reason": f"{type(exc).__name__}: {str(exc)[:160]}"}


def pregate(root: Path, rel: str, before: str, after: str) -> Dict[str, Any]:
    """Diagnostics before vs after an edit. ok=False only when the edit adds error diagnostics.
    Any infrastructure problem (no server, timeout) is ok=True + skipped: the gate decides."""
    cmd = find_server()
    if not cmd:
        return {"ok": True, "skipped": "no language server"}
    try:
        with LspClient(cmd, Path(root)) as cli:
            cli.initialize()
            d0 = cli.diagnostics(rel, before)
            d1 = cli.diagnostics(rel, after)
    except (LspError, OSError) as exc:
        return {"ok": True, "skipped": f"{type(exc).__name__}: {str(exc)[:120]}"}
    added = new_errors(d0, d1)
    return {"ok": not added, "added": added[:5], "n_before": len(errors(d0)), "n_after": len(errors(d1))}
