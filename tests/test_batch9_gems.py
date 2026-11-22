"""Batch 9 item 7: the two real gem bugs from the batch 6 contract tests, fixed, plus contracts."""
from __future__ import annotations

import ast
import json

import httpx

from tests.test_gem_contracts import grand, gx, rose, rq_env, rx  # noqa: F401  (fixtures)


def test_grandidierite_scaffold_compiles_and_stub_returns_a_dict(grand, tmp_path):  # noqa: F811
    res = gx(grand, {"name": "sum it", "args": "a, b", "docstring": "Adds a and b"})
    assert res.error is None, res.error
    code = res.payload.generated_code
    ast.parse(code)
    ns: dict = {}
    body = code.split("def main()", 1)[0].split("from _lib import", 1)[1].split("\n", 1)[1]
    exec(compile(body, "<scaffold>", "exec"), ns)  # the stub alone, no tool I/O
    assert ns["sum_it"](1, 2) == {"ok": False, "error": "stub", "tool": "sum_it"}


def test_grandidierite_every_template_formats(grand):  # noqa: F811
    for tid, tpl in grand.TEMPLATES.items():
        out = tpl.format(name="n", args="x", docstring="d")
        ast.parse(out)


def test_rose_quartz_stream_joins_chunks_and_rejects_whitespace_only(rq_env):  # noqa: F811
    good = "\n".join(json.dumps(c) for c in ({"message": {"content": "he"}}, {"message": {"content": "llo"}, "done": True,
                                                                               "eval_count": 3}))
    res = rx(rose(lambda r: httpx.Response(200, text=good), stream=True))
    assert res.error is None and res.payload.content == "hello" and res.payload.tokens == 3
    blank = json.dumps({"message": {"content": "  \n"}, "done": True})
    res = rx(rose(lambda r: httpx.Response(200, text=blank), stream=True))
    assert res.payload is None and "empty content" in res.error.message
