"""Batch 10 item 3: dependency-free MCP stdio client + ETHER read-only status server."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

from core.agent import mcp_stdio as M

FAKE = textwrap.dedent('''
    import json, sys, time
    MODE = sys.argv[1] if len(sys.argv) > 1 else "ok"
    print("server log line on stdout, not json", flush=True)
    for line in sys.stdin:
        msg = json.loads(line)
        rid = msg.get("id")
        if rid is None:
            continue
        m = msg["method"]
        if MODE == "hang" and m == "tools/call":
            time.sleep(30)
        if m == "initialize":
            res = {"protocolVersion": msg["params"]["protocolVersion"], "capabilities": {"tools": {}},
                   "serverInfo": {"name": "fake"}}
        elif m == "tools/list":
            cur = (msg.get("params") or {}).get("cursor")
            if not cur:
                res = {"tools": [{"name": "lookup", "annotations": {"readOnlyHint": True}}], "nextCursor": "p2"}
            else:
                res = {"tools": [{"name": "write_file", "annotations": {"destructiveHint": True}},
                                 {"name": "liar", "annotations": {"readOnlyHint": True}}]}
        elif m == "tools/call":
            name = msg["params"]["name"]
            if name == "boom":
                print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32000, "message": "kaput"}}), flush=True)
                continue
            res = {"content": [{"type": "text", "text": "result for " + json.dumps(msg["params"]["arguments"])}],
                   "isError": False}
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "nope"}}), flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": rid, "result": res}), flush=True)
''')


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "fake_mcp.py").write_text(FAKE, encoding="utf-8")
    (tmp_path / "memory").mkdir()
    cfg = {"servers": {"fake": {"command": [sys.executable, str(tmp_path / "fake_mcp.py")],
                                "read_only": ["lookup", "write_file", "boom"], "timeout_s": 10},
                       "slow": {"command": [sys.executable, str(tmp_path / "fake_mcp.py"), "hang"],
                                "read_only": ["lookup"], "timeout_s": 1.5}}}
    (tmp_path / "memory" / "mcp.json").write_text(json.dumps(cfg), encoding="utf-8")
    monkeypatch.setenv("ETHER_MCP", "1")
    return tmp_path


def test_handshake_paged_list_and_call(repo):
    spec = M.load_config(repo)["servers"]["fake"]
    with M.McpClient(spec["command"], timeout=10) as cli:
        info = cli.initialize()
        assert info["serverInfo"]["name"] == "fake"
        names = [t["name"] for t in cli.list_tools()]
        assert names == ["lookup", "write_file", "liar"]  # both pages, non-JSON stdout line skipped
        res = cli.call_tool("lookup", {"q": "x"})
        assert "result for" in res["text"] and not res["is_error"]
        with pytest.raises(M.McpError):
            cli.request("bogus/method")


def test_allowlist_and_annotations(repo):
    ro = [t["name"] for t in M.read_only_tools(repo, "fake")]
    assert ro == ["lookup"]  # write_file: destructive annotation refuses; liar: not allowlisted
    assert M.call_read_only(repo, "fake", "lookup", {"q": 1})["ok"]
    assert "denied" in M.call_read_only(repo, "fake", "write_file", {})["reason"]
    assert "denied" in M.call_read_only(repo, "fake", "liar", {})["reason"]
    assert not M.call_read_only(repo, "nope", "lookup", {})["ok"]


def test_server_error_and_timeout_fail_closed(repo):
    r = M.call_read_only(repo, "fake", "boom", {})
    assert not r["ok"]
    r = M.call_read_only(repo, "slow", "lookup", {})
    assert not r["ok"] and "timeout" in r["reason"]


def test_off_by_default(repo, monkeypatch):
    monkeypatch.delenv("ETHER_MCP")
    assert M.call_read_only(repo, "fake", "lookup", {})["reason"] == "ETHER_MCP off"
    assert M.catalog(repo) == []
    from core.agent.skills import MODEL_SKILLS, model_skills

    assert model_skills() == MODEL_SKILLS


def test_model_reply_reaches_mcp_only_when_on_and_never_edit(repo, monkeypatch):
    from core.agent.skills import call, model_skills

    assert "mcp" in model_skills() and "edit" not in model_skills() and "test" not in model_skills()
    text = json.dumps({"tool": "mcp", "args": {"server": "fake", "call": "lookup", "arguments": {"q": 2}}})
    row = call(repo, text, allowed=model_skills())
    assert row["ok"] and "result for" in row["hits"][0]
    row = call(repo, json.dumps({"tool": "edit", "args": {}}), allowed=model_skills())
    assert row["reason"].startswith("denied")


def test_server_env_is_scrubbed(repo, monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secretsecret")
    probe = tmp_path / "envdump.py"
    probe.write_text(textwrap.dedent('''
        import json, os, sys
        for line in sys.stdin:
            msg = json.loads(line)
            if msg.get("id") is None: continue
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {"env": sorted(os.environ)}}), flush=True)
    '''), encoding="utf-8")
    with M.McpClient([sys.executable, str(probe)], env={"EXTRA": "1"}, timeout=10) as cli:
        env = cli.request("initialize", {})["env"]
    assert "GITHUB_TOKEN" not in env and "EXTRA" in env


def test_ether_status_server_end_to_end(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    art = tmp_path / "artifacts"
    art.mkdir()
    (art / "host_main.json").write_text(json.dumps({"health": "degraded", "health_worst": "pull: rc 128",
                                                     "token_like": "x"}), encoding="utf-8")
    (art / "learning_summary.json").write_text(json.dumps({"totals": {"graded": 3}}), encoding="utf-8")
    with M.McpClient([sys.executable, "-m", "scripts.mcp_status_server"], cwd=str(root),
                     env={"ETHER_ROOT": str(tmp_path), "PYTHONPATH": str(root)}, timeout=15) as cli:
        cli.initialize()
        tools = cli.list_tools()
        assert {t["name"] for t in tools} == {"ether_health", "ether_learning", "ether_sota"}
        assert all(t["annotations"]["readOnlyHint"] for t in tools)
        health = json.loads(cli.call_tool("ether_health")["text"])
        assert health["health_worst"] == "pull: rc 128" and "token_like" not in health
        assert json.loads(cli.call_tool("ether_learning")["text"])["totals"]["graded"] == 3
        assert "missing" in json.loads(cli.call_tool("ether_sota")["text"])
        with pytest.raises(M.McpError):
            cli.call_tool("nope")


def test_status_server_never_writes():
    src = Path("scripts/mcp_status_server.py").read_text(encoding="utf-8")
    for bad in ("write_text", "open(", "subprocess", "os.replace", "unlink", "rmtree"):
        assert bad not in src, bad


def test_shipped_config_only_allowlists_status_tools():
    cfg = json.loads(Path("config/mcp.json").read_text(encoding="utf-8"))
    assert set(cfg["servers"]) == {"ether-status"}
    assert cfg["servers"]["ether-status"]["read_only"] == ["ether_health", "ether_learning", "ether_sota"]
