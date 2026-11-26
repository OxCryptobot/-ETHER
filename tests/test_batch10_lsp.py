"""Batch 10 item 4: LSP client (Content-Length framing), read-only lsp skill, optional pre-gate."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from core.agent import lsp_client as L

FAKE = textwrap.dedent(r'''
    import json, sys
    inp, out = sys.stdin.buffer, sys.stdout.buffer
    docs = {}
    def send(msg):
        b = json.dumps(msg).encode()
        out.write(b"Content-Length: %d\r\n\r\n" % len(b) + b); out.flush()
    def diags(uri):
        text = docs.get(uri, "")
        d = []
        for i, line in enumerate(text.splitlines()):
            if "undefined_thing" in line:
                d.append({"range": {"start": {"line": i, "character": 0}, "end": {"line": i, "character": 5}},
                          "severity": 1, "source": "fake", "message": "undefined name 'undefined_thing'"})
            if "warnme" in line:
                d.append({"range": {"start": {"line": i, "character": 0}, "end": {"line": i, "character": 5}},
                          "severity": 2, "source": "fake", "message": "warning"})
        send({"jsonrpc": "2.0", "method": "textDocument/publishDiagnostics", "params": {"uri": uri, "diagnostics": d}})
    while True:
        n = None
        while True:
            line = inp.readline()
            if not line: sys.exit(0)
            line = line.strip()
            if not line: break
            k, _, v = line.decode().partition(":")
            if k.lower() == "content-length": n = int(v)
        msg = json.loads(inp.read(n))
        m, rid = msg.get("method"), msg.get("id")
        if m == "initialize":
            send({"jsonrpc": "2.0", "id": 900, "method": "workspace/configuration", "params": {"items": [{}]}})
            send({"jsonrpc": "2.0", "id": rid, "result": {"capabilities": {}}})
        elif m == "textDocument/didOpen":
            docs[msg["params"]["textDocument"]["uri"]] = msg["params"]["textDocument"]["text"]; diags(msg["params"]["textDocument"]["uri"])
        elif m == "textDocument/didChange":
            docs[msg["params"]["textDocument"]["uri"]] = msg["params"]["contentChanges"][-1]["text"]; diags(msg["params"]["textDocument"]["uri"])
        elif m == "textDocument/definition":
            u = msg["params"]["textDocument"]["uri"]
            send({"jsonrpc": "2.0", "id": rid, "result": {"uri": u, "range": {"start": {"line": 0, "character": 4}, "end": {"line": 0, "character": 7}}}})
        elif m == "textDocument/references":
            u = msg["params"]["textDocument"]["uri"]
            send({"jsonrpc": "2.0", "id": rid, "result": [{"uri": u, "range": {"start": {"line": 3, "character": 0}, "end": {"line": 3, "character": 1}}},
                                                         {"uri": "file:///etc/passwd", "range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}}]})
        elif m == "shutdown":
            send({"jsonrpc": "2.0", "id": rid, "result": None})
        elif m == "exit":
            sys.exit(0)
        elif rid is not None and "method" in msg:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "nope"}})
''')


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "fake_lsp.py").write_text(FAKE, encoding="utf-8")
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "m.py").write_text("def add(a, b):\n    return a + b\n\n\nx = add(1, 2)\n", encoding="utf-8")
    monkeypatch.setenv("ETHER_LSP_CMD", f'"{sys.executable}" "{tmp_path / "fake_lsp.py"}"')
    monkeypatch.setenv("ETHER_LSP", "1")
    monkeypatch.setenv("ETHER_LSP_TIMEOUT_S", "10")
    return tmp_path


def test_framing_diagnostics_definition_references(repo):
    with L.LspClient(L.find_server(), repo) as cli:
        cli.initialize()
        d = cli.diagnostics("core/m.py", "y = undefined_thing\n")
        assert d and d[0]["severity"] == 1
        cli.open("core/m.py", (repo / "core/m.py").read_text())
        assert cli.locations("textDocument/definition", "core/m.py", 4, 4) == [{"file": "core/m.py", "line": 1}]
        refs = cli.locations("textDocument/references", "core/m.py", 0, 4)
        assert refs[0] == {"file": "core/m.py", "line": 4} and refs[1]["file"] == "<outside repo>"


def test_lsp_skill_ops_and_confinement(repo):
    assert L.tool(repo, op="diagnostics", file="core/m.py")["ok"]
    r = L.tool(repo, op="references", file="core/m.py", symbol="add")
    assert r["ok"] and "core/m.py:4" in r["hits"][0]
    assert not L.tool(repo, op="rename", file="core/m.py")["ok"]
    assert not L.tool(repo, op="diagnostics", file="../etc/passwd")["ok"]
    assert not L.tool(repo, op="diagnostics", file=".env")["ok"]


def test_absent_server_is_a_graceful_noop(repo, monkeypatch):
    monkeypatch.delenv("ETHER_LSP_CMD")
    monkeypatch.setattr(L, "CANDIDATES", (("definitely-not-an-lsp-binary", []),))
    assert L.find_server() is None
    assert L.tool(repo, op="diagnostics", file="core/m.py")["reason"] == "no language server"
    assert L.pregate(repo, "core/m.py", "a", "b") == {"ok": True, "skipped": "no language server"}


def test_off_by_default(repo, monkeypatch):
    monkeypatch.delenv("ETHER_LSP")
    assert L.tool(repo, op="diagnostics", file="core/m.py")["reason"] == "ETHER_LSP off"
    from core.agent.skills import model_skills, tool_hint

    assert "lsp" not in model_skills()
    assert tool_hint(repo, {"file": "core/m.py", "symbol": "add"}) == ""


def test_pregate_rejects_only_new_errors(repo):
    before = "def f():\n    return 1\n"
    assert L.pregate(repo, "core/m.py", before, "def f():\n    return 2\n")["ok"]
    bad = L.pregate(repo, "core/m.py", before, "def f():\n    return undefined_thing\n")
    assert not bad["ok"] and bad["added"]
    # an error already present before the edit is not the edit's fault; warnings never block
    assert L.pregate(repo, "core/m.py", "z = undefined_thing\n", "z = undefined_thing\n\n\nw = 1  # warnme\n")["ok"]


def test_new_errors_ignores_line_shifts():
    a = [{"severity": 1, "message": "undefined name 'q' at line 3", "source": "s"}]
    b = [{"severity": 1, "message": "undefined name 'q' at line 9", "source": "s"}]
    assert L.new_errors(a, b) == []
    assert L.new_errors([], b)


def test_pregate_timeout_is_skipped_not_rejected(tmp_path, monkeypatch):
    mute = tmp_path / "mute.py"
    mute.write_text("import sys, time\nsys.stdin.read()\n", encoding="utf-8")
    monkeypatch.setenv("ETHER_LSP_CMD", f'"{sys.executable}" "{mute}"')
    monkeypatch.setenv("ETHER_LSP_TIMEOUT_S", "1")
    r = L.pregate(tmp_path, "m.py", "a = 1\n", "a = 2\n")
    assert r["ok"] and "skipped" in r


def test_hint_names_the_lsp_tool_when_on(repo):
    from core.agent.skills import model_skills, tool_hint

    assert "lsp" in model_skills()
    assert '"tool":"lsp"' in tool_hint(repo, {"file": "core/m.py", "symbol": "add"})


def test_real_pylsp_if_installed(tmp_path, monkeypatch):
    import shutil

    exe = shutil.which("pylsp")
    if not exe:
        pytest.skip("pylsp not installed")
    monkeypatch.setenv("ETHER_LSP_CMD", exe)
    monkeypatch.setenv("ETHER_LSP_TIMEOUT_S", "30")
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    r = L.pregate(tmp_path, "m.py", "def f():\n    return 1\n", "def f():\n    return nope_name\n")
    assert r.get("skipped") or not r["ok"]


def test_sota_lsp_pregate_wiring(tmp_path, monkeypatch):
    """ETHER_LSP_PREGATE=1: added error diagnostics block the edit before the gate; off / skipped = no-op."""
    from core.agent import sota

    (tmp_path / "m.py").write_text("def f():\n    return nope\n", encoding="utf-8")
    goal = {"file": "m.py"}
    applied = {"original": "def f():\n    return 1\n"}
    monkeypatch.delenv("ETHER_LSP_PREGATE", raising=False)
    assert sota._lsp_pregate(tmp_path, goal, applied, {}) == []
    monkeypatch.setenv("ETHER_LSP_PREGATE", "1")
    monkeypatch.setattr(L, "pregate", lambda root, rel, b, a: {"ok": False, "added": ["undefined name 'nope'"],
                                                                   "n_before": 0, "n_after": 1})
    trace = {}
    assert sota._lsp_pregate(tmp_path, goal, applied, trace) == ["undefined name 'nope'"]
    assert trace["lsp_pregate"]["ok"] is False
    monkeypatch.setattr(L, "pregate", lambda *a: {"ok": True, "skipped": "no language server"})
    assert sota._lsp_pregate(tmp_path, goal, applied, {}) == []

    def boom(*a):
        raise RuntimeError("x")
    monkeypatch.setattr(L, "pregate", boom)
    assert sota._lsp_pregate(tmp_path, goal, applied, {}) == []
