"""Gem handler contracts — the handlers behind GemRegistry.execute.

WRITTEN BY THE BATCH-6 REVIEWER (OxCryptobot session), NOT BY THE HOST. FOR HUMAN REVIEW.

Why: batch 5 planted 32 bugs in these handlers and the suite caught 3. These tests pin the
observable behaviour of each handler's `execute` (real outputs computed from real inputs, no
network: Ollama/Qdrant are replaced by httpx.MockTransport / tiny fakes). They assert what a
caller can see — payload fields, error type/message, files written — not constants copied
from the code under test.

Two tests in this file FAIL ON PURPOSE. They expose real bugs and are left failing (no xfail)
as honest goals for the host (docs/AUDIT_SOTA_2026-11-21_B6.md, "real bugs"):
  - test_grandidierite_generate_scaffolds_into_quarantine
      (TEMPLATES uses literal `{"ok": ...}` braces with str.format -> KeyError, so the default
      `generate` action always returns a runtime error)
  - test_rose_quartz_stream_empty_content_is_an_error
      (the streaming path returns a success envelope for empty content; the non-stream path
      already treats that as a failed generation)
Handler code was not modified.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from core.schemas import (
    AmethystRequest,
    BlackTourmalineRequest,
    ChatMessage,
    CitrineRequest,
    ClearQuartzRequest,
    Envelope,
    GemErrorType,
    GrandidieriteRequest,
    LabradoriteRequest,
    RoseQuartzRequest,
    SeleniteRequest,
)


def env(gem: str, payload, timeout: int = 60) -> Envelope:
    return Envelope(task_id=uuid4(), target_gem=gem, payload=payload, timeout_seconds=timeout)


def code_of(n_lines: int, body: str = "    assert True") -> str:
    return "\n".join(["def f():"] + [body] * (n_lines - 1))


# ------------------------------------------------------------------ registry routing
def test_registry_unknown_gem_is_a_non_recoverable_error():
    from core.registry import GemRegistry

    reg = GemRegistry()
    req = env("labradorite", LabradoriteRequest(code="x"))
    res = reg.execute(req)
    assert res.payload is None and res.task_id == req.task_id
    assert res.error.type == GemErrorType.UNKNOWN
    assert res.error.message == "Unknown gem: labradorite"
    assert res.error.recoverable is False


def test_registry_routes_to_the_registered_handler_by_target_gem():
    from core.registry import GemRegistry
    from gems.labradorite.profiler import Labradorite

    seen = []

    class Spy:
        def execute(self, request):
            seen.append(request.target_gem)
            return Labradorite().execute(request)

    reg = GemRegistry()
    reg.register("labradorite", Spy())
    res = reg.execute(env("labradorite", LabradoriteRequest(code="def f():\n    assert 1\n")))
    assert seen == ["labradorite"]
    assert res.source_gem == "labradorite" and res.payload.critique.startswith("[clean]")


# ------------------------------------------------------------------ labradorite
def lab(code, payload_cls=LabradoriteRequest):
    from gems.labradorite.profiler import Labradorite

    return Labradorite().execute(env("labradorite", payload_cls(code=code)))


def test_labradorite_clean_function():
    res = lab("def f(x):\n    assert x\n    return x\n")
    p = res.payload
    assert res.error is None and res.source_gem == "labradorite"
    assert p.critique == "[clean] ~4 lines, complexity=0.02. No structural issues flagged."
    assert p.suggested_improvements == []
    assert p.complexity_score == 0.02
    assert p.confidence_score == 0.7


def test_labradorite_empty_artifact_blocks():
    p = lab("").payload
    assert p.critique.startswith("[block] ~0 lines, complexity=0.00. No code to review")
    assert p.suggested_improvements[0].startswith("No code to review")
    assert any("named function entrypoint" in s for s in p.suggested_improvements)
    assert p.confidence_score == 0.55 and p.complexity_score == 0.0


def test_labradorite_dynamic_exec_blocks_and_missing_asserts_improve():
    p = lab("def f(s):\n    return eval(s)\n").payload
    assert p.critique.startswith("[block]")
    assert any("eval/exec" in s for s in p.suggested_improvements)
    assert any("Add asserts" in s for s in p.suggested_improvements)
    q = lab("def f(s):\n    return s\n").payload
    assert q.critique.startswith("[improve]") and q.confidence_score == 0.55
    assert q.suggested_improvements == ["Add asserts that prove correctness before user-facing delivery"]


def test_labradorite_conditional_density_threshold_is_more_than_eight():
    eight = "def f(x):\n    assert x\n" + "    if x: x\n" * 8
    nine = "def f(x):\n    assert x\n" + "    if x: x\n" * 9
    assert lab(eight).payload.critique.startswith("[clean]")
    p = lab(nine).payload
    assert p.critique.startswith("[improve]")
    assert any("conditional density" in s for s in p.suggested_improvements)


def test_labradorite_large_artifact_threshold_and_complexity_scale():
    at = lab(code_of(120)).payload
    over = lab(code_of(121)).payload
    assert not any("Large artifact" in s for s in at.suggested_improvements)
    assert any("Large artifact" in s for s in over.suggested_improvements)
    assert at.complexity_score == 0.6 and over.complexity_score == 0.6  # 121/200 = 0.605 -> 0.6
    assert lab(code_of(100)).payload.complexity_score == 0.5
    assert lab(code_of(300)).payload.complexity_score == 1.0
    assert "~121 lines" in over.critique


def test_labradorite_loop_append_hint_does_not_change_severity():
    p = lab("def f():\n    out = []\n    for i in range(3):\n        out.append(i)\n    assert out\n    return out\n").payload
    assert p.critique.startswith("[clean]")  # a hint, not a flag
    assert p.suggested_improvements == ["Consider list comprehensions or generator expressions for clarity"]


def test_labradorite_critique_lists_at_most_three_suggestions():
    code = "x = eval('1')\n" + "if x: x\n" * 9 + "\n" * 125
    p = lab(code).payload
    assert len(p.suggested_improvements) == 5
    assert p.critique.count("; ") == 2  # three joined
    assert len(p.critique) <= 500


def test_labradorite_reads_code_from_a_foreign_payload_shape():
    from gems.labradorite.profiler import Labradorite

    res = Labradorite().execute(env("labradorite", BlackTourmalineRequest(artifact="x")))
    assert res.payload.critique.startswith("[block] ~0 lines")  # no `code` field -> empty


# ------------------------------------------------------------------ black tourmaline
def bt(artifact):
    from gems.black_tourmaline.security import BlackTourmaline

    return BlackTourmaline().execute(env("black-tourmaline", BlackTourmalineRequest(artifact=artifact)))


def test_black_tourmaline_clean_code_is_approved_with_zero_risk():
    p = bt("def add(a, b):\n    return a + b\n").payload
    assert p.approved is True and p.violations == [] and p.risk_score == 0.0


@pytest.mark.parametrize("src", ["import os\nos.system('ls')\n", "import subprocess\nsubprocess.run(['ls'])\n",
                                 "import os\nos.popen('ls')\n", "import socket\nsocket.socket()\n"])
def test_black_tourmaline_single_violation_is_rejected(src):
    p = bt(src).payload
    assert p.approved is False
    assert len(p.violations) >= 1
    assert p.risk_score == round(min(1.0, len(p.violations) * 0.35), 2)
    assert all(v.severity == "high" and v.message.startswith("Matched forbidden pattern") for v in p.violations)


def test_black_tourmaline_eval_hits_regex_and_ast_and_caps_risk():
    p = bt("x = eval('1+1')\n").payload
    rules = [v.rule for v in p.violations]
    assert "ast_eval" in rules and any(r.startswith("eval") for r in rules)
    crit = [v for v in p.violations if v.rule == "ast_eval"][0]
    assert crit.severity == "critical" and crit.message == "AST detected call to eval"
    many = bt("eval('1')\nexec('2')\nimport os\nos.system('x')\n").payload
    assert len(many.violations) >= 3 and many.risk_score == 1.0


def test_black_tourmaline_compile_is_ast_only_and_syntax_errors_are_medium():
    p = bt("c = compile('1', 'f', 'eval')\n").payload
    assert [v.rule for v in p.violations if v.rule.startswith("ast_")] == ["ast_compile"]
    s = bt("def broken(:\n").payload
    assert s.approved is False
    assert [(v.rule, v.severity) for v in s.violations] == [("syntax_error", "medium")]
    assert s.risk_score == 0.35


def test_black_tourmaline_rule_names_are_truncated_to_forty_chars():
    from gems.black_tourmaline.security import BlackTourmaline

    g = BlackTourmaline()
    g.patterns = ["forbidden_" + "x" * 50]
    out = g._scan("forbidden_" + "x" * 50)
    assert len(out) == 1 and len(out[0].rule) == 40


# ------------------------------------------------------------------ amethyst
class FakePolicy:
    def select(self):
        return "arm_b"

    def snapshot(self):
        return {"arms": {"arm_b": {"n": 3}}}


def ame(tmp_path, payload):
    from gems.amethyst.evolution import Amethyst

    g = Amethyst(log_dir=tmp_path / "logs")
    g.policy = FakePolicy()
    return g, g.execute(env("amethyst", payload))


def test_amethyst_log_appends_one_jsonl_row(tmp_path, monkeypatch):
    monkeypatch.setenv("ETHER_LEARNING", "0")
    g, res = ame(tmp_path, AmethystRequest(action="log", interaction={"objective": "o1", "status": "complete"}))
    assert res.payload.status == "logged"
    files = list((tmp_path / "logs").glob("*.jsonl"))
    assert len(files) == 1 and len(files[0].stem) == 10  # YYYY-MM-DD
    rows = [json.loads(x) for x in files[0].read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["objective"] == "o1" and rows[0]["status"] == "complete"
    assert rows[0]["timestamp"][:10] == files[0].stem


def test_amethyst_learn_records_reward_only_when_learning_on_and_asked(tmp_path, monkeypatch):
    import gems.amethyst.evolution as ev

    got = []
    monkeypatch.setattr(ev, "append_experience", lambda row: got.append(row))
    monkeypatch.setenv("ETHER_LEARNING", "1")
    ame(tmp_path, AmethystRequest(action="log", interaction={"strategy": "s1", "reward": 0.25}))
    assert got == []  # learn not requested
    ame(tmp_path, AmethystRequest(action="log", interaction={"learn": True, "strategy": "s1", "reward": 0.25}))
    assert got[-1]["strategy"] == "s1" and got[-1]["reward"] == 0.25
    inter = {"learn": True, "exit_code": 0, "confidence": 0.9, "audit_approved": True, "retries": 2}
    ame(tmp_path, AmethystRequest(action="log", interaction=inter))
    want = ev.compute_reward(exit_code=0, confidence=0.9, audit_approved=True, retries=2)
    assert got[-1]["strategy"] == "default" and got[-1]["reward"] == want
    monkeypatch.setenv("ETHER_LEARNING", "0")
    ame(tmp_path, AmethystRequest(action="log", interaction={"learn": True, "reward": 1.0}))
    assert len(got) == 2


def test_amethyst_recommend_uses_policy_only_when_learning_on(tmp_path, monkeypatch):
    monkeypatch.setenv("ETHER_LEARNING", "1")
    assert ame(tmp_path, AmethystRequest(action="recommend"))[1].payload.status == "strategy:arm_b"
    monkeypatch.setenv("ETHER_LEARNING", "0")
    assert ame(tmp_path, AmethystRequest(action="recommend"))[1].payload.status == "strategy:default"


def test_amethyst_stats_and_unknown_actions(tmp_path):
    _, res = ame(tmp_path, AmethystRequest.model_construct(action="stats", interaction={}))
    assert json.loads(res.payload.status) == {"arms": {"arm_b": {"n": 3}}}
    _, res = ame(tmp_path, AmethystRequest(action="analyze"))
    assert res.payload.status == "unknown_action"


def test_amethyst_failure_is_a_recoverable_runtime_error(tmp_path):
    from gems.amethyst.evolution import Amethyst

    g = Amethyst(log_dir=tmp_path / "logs")

    class Boom:
        def select(self):
            raise RuntimeError("policy broke")

    g.policy = Boom()
    res = g.execute(env("amethyst", AmethystRequest(action="recommend")))
    assert res.error.type == GemErrorType.RUNTIME and res.error.message == "policy broke" and res.error.recoverable


# ------------------------------------------------------------------ selenite
@pytest.fixture
def no_lessons(monkeypatch):
    import core.memory_bus as mb

    monkeypatch.setattr(mb, "recent_lessons", lambda q, k=5: "")
    monkeypatch.setenv("ETHER_LANGGRAPH", "0")
    monkeypatch.setenv("ETHER_LLM_PLAN", "0")


def sel(query, depth=5, tools=(), context=()):
    from gems.selenite.planner import Selenite

    return Selenite().execute(env("selenite", SeleniteRequest(user_query=query, max_plan_depth=depth,
                                                              available_tools=list(tools), context=list(context))))


def test_selenite_rule_plans_follow_intent(no_lessons):
    p = sel("implement a csv parser").payload
    assert [s.action for s in p.plan.steps] == ["analyze", "generate", "test", "validate"]
    assert p.plan.reasoning == "Rule plan intent=implement: implement a csv parser"
    assert p.needs_tool is False and p.tool_request is None and p.confidence_score == 0.7
    r = sel("refactor the cache layer", depth=3).payload
    assert [s.action for s in r.plan.steps] == ["analyze", "design", "migrate"]
    e = sel("explain the scheduler").payload
    assert [s.action for s in e.plan.steps] == ["retrieve", "synthesize"]


def test_selenite_fix_words_use_the_fix_dag(no_lessons):
    from core.loop.fix_dag import fix_plan

    q = "fix the failing ledger test " + "x" * 200
    p = sel(q).payload
    assert p.plan == fix_plan(q[:120])


def test_selenite_lessons_add_a_review_step_within_depth(no_lessons):
    ctx = [{"kind": "critique_loop", "text": "add asserts"}, {"kind": "other", "text": "ignored"}, {"kind": "lesson"}]
    p = sel("explain the scheduler", depth=5, context=ctx).payload
    assert [s.action for s in p.plan.steps] == ["retrieve", "synthesize", "review"]
    assert p.plan.steps[-1].deps == [2] and p.plan.steps[-1].target == "labradorite"
    assert p.plan.reasoning.endswith("| self-improvement lessons applied")
    full = sel("explain the scheduler", depth=2, context=ctx).payload
    assert [s.action for s in full.plan.steps] == ["retrieve", "synthesize"]


@pytest.mark.parametrize("query,want", [
    ("please fabricate a tool named parse_csv", {"action": "fabricate", "name": "parse_csv"}),
    ("create tool called Sum2", {"action": "fabricate", "name": "sum2"}),
    ("we need a new tool for this", {"action": "fabricate", "name": "auto_tool"}),
    ("run tool lint_all now", {"action": "run", "name": "lint_all", "payload": {}}),
    ("generate tool for zip files", {"action": "generate", "name": "scaffolded_tool"}),
])
def test_selenite_tool_intents(no_lessons, query, want):
    p = sel(query).payload
    assert p.needs_tool is True and p.confidence_score == 0.75
    assert {k: p.tool_request[k] for k in want} == want


def test_selenite_available_tool_needs_a_use_verb(no_lessons):
    assert sel("use formatter on this file", tools=["formatter.py"]).payload.tool_request == {
        "action": "run", "name": "formatter", "payload": {}}
    assert sel("formatter is nice", tools=["formatter.py"]).payload.needs_tool is False


def test_selenite_depth_truncates_and_query_is_capped_in_reasoning(no_lessons):
    p = sel("hello there " + "y" * 300, depth=1).payload
    assert len(p.plan.steps) == 1
    assert len(p.plan.reasoning) == len("Rule plan intent=general: ") + 100


# ------------------------------------------------------------------ grandidierite
@pytest.fixture
def grand(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from gems.grandidierite.extension import Grandidierite

    return Grandidierite(quarantine_dir=tmp_path / "q")


def gx(g, tool_request, template_id="basic_python_tool"):
    return g.execute(env("grandidierite", GrandidieriteRequest(tool_request=tool_request, template_id=template_id)))


def test_grandidierite_list_returns_the_catalog_json(grand, monkeypatch):
    import gems.grandidierite.extension as ext

    monkeypatch.setattr(ext, "list_tools", lambda full=True: [{"name": "a"}, {"name": "b"}])
    p = gx(grand, {"action": "list"}).payload
    assert json.loads(p.generated_code) == [{"name": "a"}, {"name": "b"}]
    assert p.template_used == "list" and p.validation_status == "passed"


def test_grandidierite_run_maps_ok_and_truncates(grand, monkeypatch):
    import gems.grandidierite.extension as ext

    calls = []
    monkeypatch.setattr(ext, "run_tool", lambda name, payload: calls.append((name, payload)) or {"ok": True, "out": "z" * 5000})
    p = gx(grand, {"action": "run", "name": "t1", "payload": {"x": 1}}).payload
    assert calls == [("t1", {"x": 1})]
    assert p.validation_status == "passed" and p.template_used == "run" and len(p.generated_code) == 4000
    monkeypatch.setattr(ext, "run_tool", lambda name, payload: {"ok": False, "error": "nope"})
    p = gx(grand, {"action": "run", "name": "t1"}).payload
    assert p.validation_status == "failed" and json.loads(p.generated_code) == {"ok": False, "error": "nope"}


@pytest.mark.parametrize("status,want", [("promoted", "passed"), ("failed", "failed"), ("quarantined", "pending"), (None, "pending")])
def test_grandidierite_fabricate_status_mapping(grand, monkeypatch, status, want):
    import gems.grandidierite.extension as ext

    monkeypatch.setattr(ext, "fabricate", lambda req: {"validation_status": status, "name": req.get("name"), "pad": "p" * 9000})
    for action in ("fabricate", "auto", "build"):
        p = gx(grand, {"action": action, "name": "n1"}).payload
        assert p.validation_status == want and p.template_used == "fabricate" and len(p.generated_code) == 8000


def test_grandidierite_sanitize_name():
    from gems.grandidierite.extension import _sanitize_name

    assert _sanitize_name(" my tool! ") == "my_tool_"
    assert _sanitize_name("9lives") == "tool_9lives"
    assert _sanitize_name("") == "new_tool"
    assert len(_sanitize_name("a" * 100)) == 64


def test_grandidierite_generate_scaffolds_into_quarantine(grand, tmp_path):
    """REAL BUG (left failing on purpose): str.format over a template with literal `{"ok": ...}`."""
    res = gx(grand, {"name": "my tool", "args": "x", "docstring": "Adds things"})
    assert res.error is None, res.error
    p = res.payload
    assert "def my_tool(x):" in p.generated_code and '"""Adds things"""' in p.generated_code
    assert p.template_used == "basic_python_tool" and p.validation_status == "pending"
    files = list((tmp_path / "q").glob("my_tool_*.py"))
    assert len(files) == 1 and files[0].read_text() == p.generated_code


# ------------------------------------------------------------------ citrine
class _Hit:
    def __init__(self, id, score, payload):
        self.id, self.score, self.payload = id, score, payload


class FakeQdrant:
    def __init__(self, hits=()):
        self.hits = list(hits)
        self.searched = []
        self.upserts = []

    def get_collections(self):
        return types.SimpleNamespace(collections=[types.SimpleNamespace(name=n) for n in ("ether_code", "patterns", "failures", "runs")])

    def search(self, collection_name, query_vector, limit):
        self.searched.append((collection_name, list(query_vector), limit))
        return self.hits[:limit]

    def upsert(self, collection_name, points):
        self.upserts.append((collection_name, points))

    def get_collection(self, name):
        return types.SimpleNamespace(points_count=7)


@pytest.fixture
def fake_qmodels(monkeypatch):
    models = types.SimpleNamespace(
        PointStruct=lambda id, vector, payload: types.SimpleNamespace(id=id, vector=vector, payload=payload),
        VectorParams=lambda size, distance: (size, distance),
        Distance=types.SimpleNamespace(COSINE="cosine"),
    )
    pkg, http = types.ModuleType("qdrant_client"), types.ModuleType("qdrant_client.http")
    http.models = models
    pkg.http = http
    monkeypatch.setitem(sys.modules, "qdrant_client", pkg)
    monkeypatch.setitem(sys.modules, "qdrant_client.http", http)
    monkeypatch.setitem(sys.modules, "qdrant_client.http.models", models)


def citrine(embedding=(0.5, 0.25), client=None, status=200):
    from gems.citrine.memory import Citrine

    g = Citrine(qdrant_url="http://q:6333/", ollama_url="http://o:11434", embed_model="emb", connect=False)
    g.prompts = []

    def handler(request):
        g.prompts.append(json.loads(request.content)["prompt"])
        return httpx.Response(status, json={"embedding": list(embedding)})

    g.http = httpx.Client(transport=httpx.MockTransport(handler))
    g._connect = lambda: False
    g._client = client
    return g


def cx(g, **kw):
    return g.execute(env("citrine", CitrineRequest(**kw)))


def test_citrine_health_offline_without_client():
    g = citrine()
    res = cx(g, action="health", collection="runs")
    r = res.payload.results[0]
    assert res.payload.action == "health" and res.payload.collection == "runs"
    assert r.id == "health" and r.text == "offline" and r.score == 0.0
    assert r.metadata["reachable"] is False and r.metadata["error"] == "offline"
    assert r.metadata["qdrant_url"] == "http://q:6333"


def test_citrine_search_without_qdrant_is_a_dependency_error():
    res = cx(citrine(), action="search", query="x")
    assert res.error.type == GemErrorType.DEPENDENCY and res.error.recoverable
    assert res.error.message == "Qdrant unreachable at http://q:6333: offline"
    assert res.error.suggested_action == "Start Qdrant or set QDRANT_URL"


def test_citrine_search_maps_hits_and_limits_top_k(fake_qmodels):
    q = FakeQdrant([_Hit(1, 0.9, {"text": "def a(): pass", "path": "a.py"}), _Hit("b", 0.5, None)])
    g = citrine(client=q)
    res = cx(g, action="search", query="find a", top_k=1, collection="patterns")
    assert q.searched == [("patterns", [0.5, 0.25], 1)]
    assert [(r.id, r.text, r.score, r.metadata) for r in res.payload.results] == [("1", "def a(): pass", 0.9, {"path": "a.py"})]
    assert g.prompts == ["find a"]
    both = cx(g, action="search", query="find a", top_k=5)
    assert [r.id for r in both.payload.results] == ["1", "b"] and both.payload.results[1].text == ""
    assert cx(g, action="search", query="", top_k=5).payload.results == []
    cx(g, action="search", query="z", top_k=0)  # 0 means "default", not "none"
    assert q.searched[-1][2] == 5


def test_citrine_add_embeds_each_document(fake_qmodels):
    q = FakeQdrant()
    g = citrine(client=q)
    res = cx(g, action="add", collection="runs", documents=[{"text": "first note", "metadata": {"k": 1}},
                                                             {"text": "   "}, {"text": "second note"}])
    assert res.payload.action == "add" and res.payload.results == []
    (col, points), = q.upserts
    assert col == "runs" and [p.payload["text"] for p in points] == ["first note", "second note"]
    assert points[0].payload["k"] == 1 and points[0].vector == [0.5, 0.25]


def test_citrine_zero_embedding_is_a_dependency_error_not_a_zero_vector(fake_qmodels):
    g = citrine(embedding=(0.0, 0.0), client=FakeQdrant([_Hit(1, 1.0, {"text": "t"})]))
    res = cx(g, action="search", query="q")
    assert res.error.type == GemErrorType.DEPENDENCY
    assert res.error.message == "all-zero embedding from emb" and res.error.suggested_action == "ollama pull emb"
    bad = citrine(status=500, client=FakeQdrant())
    assert cx(bad, action="search", query="q").error.message.startswith("embed failed (emb)")


def test_citrine_unsupported_action():
    g = citrine(client=FakeQdrant())
    res = g.execute(env("citrine", CitrineRequest.model_construct(action="drop", query=None, collection="ether_code",
                                                                  top_k=5, documents=None, filters={})))
    assert res.error.type == GemErrorType.UNKNOWN and res.error.message == "Unsupported action drop"


def test_citrine_health_reports_points_and_embedding(fake_qmodels):
    g = citrine(client=FakeQdrant())
    r = cx(g, action="health").payload.results[0]
    assert r.score == 1.0 and r.metadata["reachable"] is True and r.metadata["embed_ok"] is True
    assert r.metadata["vector_size"] == 2
    assert r.metadata["collections"]["runs"] == {"exists": True, "points": 7}


# ------------------------------------------------------------------ clear quartz
@pytest.fixture
def cq(tmp_path, monkeypatch):
    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "local")
    monkeypatch.setenv("ETHER_SANDBOX_PYTHON", sys.executable)
    from gems.clear_quartz.sandbox import ClearQuartz

    return ClearQuartz(work_dir=tmp_path / "sb")


def run_cq(g, code, timeout=30, **kw):
    return g.execute(env("clear-quartz", ClearQuartzRequest(code=code, prepare_code=False, **kw), timeout=timeout))


def test_clear_quartz_rejects_foreign_payloads(cq):
    res = cq.execute(env("clear-quartz", LabradoriteRequest(code="x")))
    assert res.error.type == GemErrorType.UNKNOWN and res.error.recoverable is False
    assert res.error.message == "Invalid payload type for Clear Quartz"


def test_clear_quartz_counts_real_asserts_on_success(cq):
    code = "def add(a, b):\n    return a + b\nassert add(2, 3) == 5\nassert add(1, 1) == 2\nprint('hi')\n"
    p = run_cq(cq, code).payload
    assert p.exit_code == 0 and p.stdout == "hi\n"
    assert (p.tests_passed, p.total_tests) == (2, 2)
    assert p.security_flags == ["sandbox_fallback:local"] and p.static_analysis_score == 1.0


def test_clear_quartz_failed_assert_scores_zero(cq):
    p = run_cq(cq, "def add(a, b):\n    return a - b\nassert add(2, 3) == 5\n").payload
    assert p.exit_code == 1 and "AssertionError" in p.stderr
    assert (p.tests_passed, p.total_tests) == (0, 1)


def test_clear_quartz_printed_counts_need_a_real_runner(cq):
    p = run_cq(cq, "print('42 passed')\n").payload
    assert (p.tests_passed, p.total_tests) == (0, 0)


def test_clear_quartz_unittest_runner_counts(cq):
    code = ("import unittest\nclass T(unittest.TestCase):\n    def test_a(self):\n        self.assertEqual(1 + 1, 2)\n"
            "    def test_b(self):\n        self.assertTrue(True)\nunittest.main(exit=True)\n")
    p = run_cq(cq, code).payload
    assert p.exit_code == 0 and (p.tests_passed, p.total_tests) == (2, 2)
    bad = code.replace("1 + 1, 2", "1 + 1, 3")
    q = run_cq(cq, bad).payload
    assert q.exit_code != 0 and (q.tests_passed, q.total_tests) == (0, 2)


def test_clear_quartz_static_flags_zero_the_score(cq):
    p = run_cq(cq, "import os\nx = eval('1')\nassert x == 1\n").payload
    assert "dangerous_name:eval" in p.security_flags and p.static_analysis_score == 0.0
    s = run_cq(cq, "def f(:\n").payload
    assert any(f.startswith("syntax_error: line 1") for f in s.security_flags) and s.exit_code != 0


def test_clear_quartz_timeout_is_an_error(cq):
    res = run_cq(cq, "while True:\n    pass\n", timeout=1)
    assert res.error.type == GemErrorType.TIMEOUT and res.error.message == "Sandbox timed out after 1s"


def test_clear_quartz_explicit_docker_never_falls_back_to_the_host(cq, monkeypatch):
    import gems.clear_quartz.sandbox as sb

    monkeypatch.setenv("ETHER_SANDBOX_BACKEND", "docker")
    monkeypatch.setattr(sb.shutil, "which", lambda name: None)
    res = run_cq(cq, "assert 1 == 1\n")
    assert res.error.type == GemErrorType.DEPENDENCY
    assert res.error.message == "Docker is not installed or not in PATH"


def test_clear_quartz_docker_unavailable_is_infrastructure(cq, monkeypatch):
    import gems.clear_quartz.sandbox as sb

    def boom(code, timeout):
        raise sb.DockerUnavailable("daemon down")

    monkeypatch.setattr(cq, "_run", boom)
    res = run_cq(cq, "assert 1 == 1\n")
    assert res.error.type == GemErrorType.DEPENDENCY and res.error.message == "Docker sandbox unavailable: daemon down"


@pytest.mark.parametrize("result,want", [
    ({"ok": False, "stdout": "3 passed, 1 failed", "returncode": 1}, (1, 3, 4)),
    ({"ok": True, "stdout": "all good"}, (0, 1, 1)),
    ({"ok": False, "stdout": "", "error": "boom", "returncode": 2}, (2, 0, 1)),
])
def test_clear_quartz_multifile_scores_project_pytest(cq, monkeypatch, result, want):
    import core.repo_oracle as ro

    seen = {}
    monkeypatch.setattr(ro, "score_repo_edit", lambda files, **kw: seen.update(files=files, **kw) or result)
    res = cq.execute(env("clear-quartz", ClearQuartzRequest(files={"pkg/a.py": "X = 1\n"}, test_args=["tests/t.py"]), timeout=9))
    p = res.payload
    assert (p.exit_code, p.tests_passed, p.total_tests) == want
    assert seen["files"] == {"pkg/a.py": "X = 1\n"} and seen["test_args"] == ["tests/t.py"] and seen["timeout"] == 9
    assert p.security_flags == ["multifile:project_pytest", "sandbox_fallback:local"]
    if result.get("error"):
        assert p.stderr == "boom"


def test_clear_quartz_multifile_oracle_crash_is_an_error(cq, monkeypatch):
    import core.repo_oracle as ro

    def crash(files, **kw):
        raise OSError("disk")

    monkeypatch.setattr(ro, "score_repo_edit", crash)
    res = cq.execute(env("clear-quartz", ClearQuartzRequest(files={"a.py": "x"})))
    assert res.error.type == GemErrorType.RUNTIME and res.error.message == "multifile sandbox: OSError: disk"


# ------------------------------------------------------------------ rose quartz
@pytest.fixture
def rq_env(monkeypatch):
    import gems.rose_quartz.burst as burst

    monkeypatch.setattr(burst, "burst_enabled", lambda: False)
    monkeypatch.delenv("ETHER_FORCE_BURST", raising=False)
    import core.model_router as mr

    monkeypatch.setattr(mr, "select_backend", lambda d: {"backend": "local"})


def rose(handler, stream=False, monkeypatch=None):
    from gems.rose_quartz.router import RoseQuartz

    g = RoseQuartz(ollama_base_url="http://o:11434/", primary_model="m-primary", fallback_model="m-fallback")
    g.stream = stream
    g.client = httpx.Client(transport=httpx.MockTransport(handler))
    return g


def rx(g, prefer_local=True, max_tokens=64):
    return g.execute(env("rose-quartz", RoseQuartzRequest(messages=[ChatMessage(role="user", content="hi")],
                                                          prefer_local=prefer_local, max_tokens=max_tokens)))


def test_rose_quartz_rejects_foreign_payloads(rq_env):
    from gems.rose_quartz.router import RoseQuartz

    res = RoseQuartz().execute(env("rose-quartz", LabradoriteRequest(code="x")))
    assert res.error.type == GemErrorType.UNKNOWN and res.error.message == "Invalid payload"


def test_rose_quartz_returns_content_tokens_and_model(rq_env):
    bodies = []

    def h(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"message": {"content": "def f(): pass"}, "eval_count": 5, "prompt_eval_count": 7})

    p = rx(rose(h)).payload
    assert p.content == "def f(): pass" and p.tokens == 12 and p.model_used == "m-primary" and p.confidence_score == 0.8
    assert bodies[0]["model"] == "m-primary" and bodies[0]["messages"] == [{"role": "user", "content": "hi"}]
    assert bodies[0]["options"]["num_predict"] == 64 and bodies[0]["stream"] is False
    assert rx(rose(h), prefer_local=False).payload.model_used == "m-fallback"


def test_rose_quartz_empty_content_is_a_failed_generation(rq_env):
    res = rx(rose(lambda r: httpx.Response(200, json={"message": {"content": "  "}})))
    assert res.error.type == GemErrorType.RUNTIME and res.error.message == "Model m-primary returned empty content"


def test_rose_quartz_missing_model_retries_the_fallback(rq_env):
    seen = []

    def h(req):
        m = json.loads(req.content)["model"]
        seen.append(m)
        if m == "m-primary":
            return httpx.Response(404, text="model not found")
        return httpx.Response(200, json={"message": {"content": "ok"}})

    p = rx(rose(h)).payload
    assert seen == ["m-primary", "m-fallback"] and p.model_used == "m-fallback"


def test_rose_quartz_http_errors_are_dependency_errors(rq_env):
    res = rx(rose(lambda r: httpx.Response(404, text="model not found")))
    assert res.error.type == GemErrorType.DEPENDENCY
    assert res.error.message == "Model 'm-primary' not found in Ollama. Pull it or set ETHER_PRIMARY_MODEL."
    assert res.error.suggested_action == "ollama pull m-primary"
    res = rx(rose(lambda r: httpx.Response(503, text="busy")))
    assert res.error.message == "Ollama HTTP 503: busy"


def test_rose_quartz_connect_error_names_the_url(rq_env):
    def h(req):
        raise httpx.ConnectError("refused", request=req)

    res = rx(rose(h))
    assert res.error.type == GemErrorType.DEPENDENCY and res.error.message == "Cannot connect to Ollama at http://o:11434"


def test_rose_quartz_stream_joins_chunks(rq_env):
    lines = "\n".join(json.dumps(c) for c in [{"message": {"content": "de"}, "eval_count": 1},
                                             {"message": {"content": "f"}, "eval_count": 2, "done": True},
                                             {"message": {"content": "IGNORED"}}])
    p = rx(rose(lambda r: httpx.Response(200, text=lines), stream=True)).payload
    assert p.content == "def" and p.tokens == 3


def test_rose_quartz_stream_empty_content_is_an_error(rq_env):
    """REAL BUG (left failing on purpose): the stream path returns success for empty content."""
    lines = json.dumps({"message": {"content": ""}, "done": True})
    res = rx(rose(lambda r: httpx.Response(200, text=lines), stream=True))
    assert res.payload is None and res.error is not None
    assert res.error.type == GemErrorType.RUNTIME
