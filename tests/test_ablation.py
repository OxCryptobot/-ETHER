"""The ablation harness must be trustworthy before its number is.

`scripts/ablation.py` is meant to produce the first honest `ETHER - bare model`
figure this project has ever had. Every failure mode that has already burned
this repo is re-testable here:

  * a private grader that scored `exit_code == 0` (hidden_quiz.py) — so a
    deliberately WRONG implementation is run through the harness end to end
    with the real `core.holdout` grader and must come out a fail;
  * the holdout leaking into the prompt (four separate channels, one of which
    produced a published 0.933) — so a leaking task must be excluded, never
    passed, and the model must not even be called;
  * unseeded decode, which made regressions indistinguishable from sampling
    noise — so the env vars `decode_options` actually reads are asserted;
  * work lost late in a long run — so resume must skip completed triples.

The model is never called: the router and the Pipeline are fakes. The sandbox
IS used, because grading is the one thing that must not be faked.
"""

from __future__ import annotations

import json
import os

import pytest

from scripts import ablation
from scripts.ablation import (
    ARMS,
    Ablation,
    Arm,
    bootstrap_ci,
    build_messages,
    decode_env,
    extract_code,
    load_completed,
    load_dataset,
    markdown_summary,
    mcnemar_exact,
    min_detectable_effect,
    paired_delta_ci,
    paired_table,
    sample_key,
    summarize,
)

GOOD = "def is_even(n):\n    return n % 2 == 0\n"
BAD = "def is_even(n):\n    return True\n"
HOLDOUT = "assert is_even(4) is True\nassert is_even(5) is False\nprint('ok')"

TASK = {
    "id": "t01",
    "title": "is_even",
    "objective": "Implement: def is_even(n: int) -> bool — True when n is even.",
    "holdout_test": HOLDOUT,
    "difficulty": "easy",
}


# --------------------------------------------------------------------------
# Fakes. The 35B model shares this GPU; nothing here may reach it.
# --------------------------------------------------------------------------


class FakeRouter:
    """Stands in for the rose-quartz router. Records the environment it saw."""

    def __init__(self, content=GOOD):
        self._content = content
        self.calls = []

    def complete(self, messages, max_tokens=4096):
        self.calls.append(
            {
                "messages": [dict(m) for m in messages],
                "max_tokens": max_tokens,
                "seed": os.environ.get("ETHER_SEED"),
                "temperature": os.environ.get("ETHER_TEMPERATURE"),
                "top_p": os.environ.get("ETHER_TOP_P"),
            }
        )
        content = self._content(messages) if callable(self._content) else self._content
        return {"content": content, "model_used": "fake-model", "error": ""}


class ExplodingRouter:
    def complete(self, messages, max_tokens=4096):  # pragma: no cover - must not run
        raise AssertionError("the model was called when it should not have been")


class FakeStage:
    def __init__(self, stage, success=True, detail=""):
        self.stage = stage
        self.success = success
        self.detail = detail


class FakeResult:
    def __init__(self, code=GOOD, holdout_ok=None, stages=(), status="complete"):
        self.generated_code = code
        self.holdout_ok = holdout_ok
        self.stages = list(stages)
        self.status = status
        self.error = ""
        self.retries = 0
        self.used_burst = False
        self.strategy = "default"
        self.confidence = 0.9


class FakePipeline:
    def __init__(self, result=None):
        self._result = result or FakeResult()
        self.calls = []

    def run(self, objective, holdout_test="", **kwargs):
        self.calls.append({"objective": objective, "holdout_test": holdout_test, **kwargs})
        return self._result


def fake_grade(code, holdout, timeout=60):
    """Cheap stand-in for core.holdout: 'solves it' iff it does the modulo."""
    return {
        "ok": "n % 2" in (code or ""),
        "reason": "" if "n % 2" in (code or "") else "holdout assertions failed",
        "asserts": 2,
        "leaked": False,
        "exit_code": 0 if "n % 2" in (code or "") else 1,
    }


def make_ablation(tmp_path, tasks=None, arms=("bare",), seeds=(1,), **kw):
    kw.setdefault("grade", fake_grade)
    kw.setdefault("log", lambda *_a, **_k: None)
    kw.setdefault("model_info", {"model": "fake-model", "digest": "deadbeef"})
    kw.setdefault("dataset_meta", {"id": "unit", "source": "unit", "sha256": "abc"})
    return Ablation(
        tasks or [TASK],
        [ARMS[a] if isinstance(a, str) else a for a in arms],
        list(seeds),
        jsonl_path=tmp_path / "samples.jsonl",
        out_dir=tmp_path,
        **kw,
    )


# --------------------------------------------------------------------------
# Statistics — checked against hand computation, not against themselves
# --------------------------------------------------------------------------


def test_mcnemar_matches_hand_computation():
    """b=10, c=2: n=12, sum C(12,0..2)=79, p = 2*79/4096 = 0.03857421875."""
    r = mcnemar_exact(10, 2)
    assert r["n_discordant"] == 12
    assert r["p_value"] == pytest.approx(158 / 4096, abs=1e-12)
    assert r["favours"] == "A"


def test_mcnemar_is_symmetric_in_p_and_reports_direction():
    assert mcnemar_exact(2, 10)["p_value"] == pytest.approx(mcnemar_exact(10, 2)["p_value"])
    assert mcnemar_exact(2, 10)["favours"] == "B"


def test_mcnemar_six_one_sided_pairs_is_the_significance_threshold():
    """2*0.5^6 = 0.03125 <= 0.05; 2*0.5^5 = 0.0625 > 0.05."""
    assert mcnemar_exact(6, 0)["p_value"] == pytest.approx(0.03125)
    assert mcnemar_exact(5, 0)["p_value"] == pytest.approx(0.0625)
    assert mcnemar_exact(5, 0)["p_value"] > 0.05


def test_mcnemar_no_discordant_pairs_is_p_one():
    r = mcnemar_exact(0, 0)
    assert r["p_value"] == 1.0
    assert r["favours"] == "neither"
    assert mcnemar_exact(7, 7)["p_value"] == 1.0


def test_bootstrap_ci_on_a_known_distribution():
    """20 passes / 20 fails: the normal approx gives 0.5 +- 1.96*0.5/sqrt(40)."""
    values = [1.0] * 20 + [0.0] * 20
    lo, hi = bootstrap_ci(values, resamples=10_000)
    assert lo < 0.5 < hi
    assert lo == pytest.approx(0.345, abs=0.06)
    assert hi == pytest.approx(0.655, abs=0.06)


def test_bootstrap_ci_is_deterministic():
    values = [1.0] * 7 + [0.0] * 13
    assert bootstrap_ci(values, resamples=10_000) == bootstrap_ci(values, resamples=10_000)


def test_bootstrap_ci_degenerate_cases():
    assert bootstrap_ci([]) == (0.0, 0.0)
    assert bootstrap_ci([1.0] * 30) == (1.0, 1.0)
    assert bootstrap_ci([0.0] * 30) == (0.0, 0.0)


def test_bootstrap_ci_narrows_with_more_tasks():
    wide = bootstrap_ci([1.0] * 5 + [0.0] * 5, resamples=10_000)
    narrow = bootstrap_ci([1.0] * 100 + [0.0] * 100, resamples=10_000)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_minimum_detectable_effect_is_stated_honestly():
    m = min_detectable_effect(40)
    assert m["min_one_sided_discordant_pairs"] == 6
    assert m["best_case_mde_pp"] == pytest.approx(15.0)
    assert "not enough tasks to tell" in m["note"]
    tiny = min_detectable_effect(4)
    assert "UNDERPOWERED BY CONSTRUCTION" in tiny["note"]


def test_paired_delta_ci_uses_every_sample_and_stays_paired():
    """Uniform +1/3 on every task: the delta is 1/3 and the CI cannot span 0."""
    a = {f"t{i}": 1.0 for i in range(20)}
    b = {f"t{i}": 2 / 3 for i in range(20)}
    r = paired_delta_ci(a, b, resamples=10_000)
    assert r["delta"] == pytest.approx(1 / 3, abs=1e-3)
    assert r["excludes_zero"] is True
    assert r["n_tasks"] == 20


def test_paired_delta_ci_spans_zero_when_the_arms_trade_wins():
    a = {f"t{i}": (1.0 if i % 2 else 0.0) for i in range(20)}
    b = {f"t{i}": (0.0 if i % 2 else 1.0) for i in range(20)}
    r = paired_delta_ci(a, b, resamples=10_000)
    assert r["delta"] == pytest.approx(0.0, abs=1e-9)
    assert r["excludes_zero"] is False
    assert r["ci95"][0] < 0 < r["ci95"][1]


def test_paired_delta_ci_ignores_unshared_tasks():
    r = paired_delta_ci({"t1": 1.0, "t2": 1.0}, {"t1": 0.0})
    assert r["n_tasks"] == 1 and r["delta"] == 1.0


def test_paired_table_counts_only_shared_tasks():
    a = {"t1": True, "t2": True, "t3": False, "t4": False, "t9": True}
    b = {"t1": True, "t2": False, "t3": True, "t4": False}
    t = paired_table(a, b)
    assert t == {"n_tasks": 4, "both_pass": 1, "only_a": 1, "only_b": 1, "neither": 1}


# --------------------------------------------------------------------------
# Grading — one grader, and a wrong answer is a fail
# --------------------------------------------------------------------------


def test_wrong_implementation_is_scored_a_fail(tmp_path):
    """End to end with the REAL grader. `return True` passes its own tests."""
    ab = make_ablation(tmp_path, router=FakeRouter(BAD), grade=ablation.grade_against_holdout)
    row = ab.run_sample(TASK, ARMS["bare"], 1)
    assert row["passed"] is False
    assert row["leaked"] is False
    assert row["reason"] == "holdout assertions failed"


def test_correct_implementation_is_scored_a_pass(tmp_path):
    ab = make_ablation(tmp_path, router=FakeRouter(GOOD), grade=ablation.grade_against_holdout)
    row = ab.run_sample(TASK, ARMS["bare"], 1)
    assert row["passed"] is True
    assert row["holdout_asserts"] == 2


def test_self_authored_asserts_cannot_buy_a_pass(tmp_path):
    """The model grading itself is exactly what the holdout exists to defeat."""
    ab = make_ablation(
        tmp_path,
        router=FakeRouter(BAD + "\nassert is_even(2) is True\nprint('all tests passed')\n"),
        grade=ablation.grade_against_holdout,
    )
    assert ab.run_sample(TASK, ARMS["bare"], 1)["passed"] is False


def test_ether_arm_is_regraded_and_does_not_trust_the_pipeline_verdict(tmp_path):
    """A pipeline claiming holdout_ok=True on wrong code must not score a pass."""
    pipe = FakePipeline(FakeResult(code=BAD, holdout_ok=True))
    ab = make_ablation(
        tmp_path,
        arms=("ether",),
        pipeline_factory=lambda: pipe,
        grade=ablation.grade_against_holdout,
    )
    row = ab.run_sample(TASK, ARMS["ether"], 1)
    assert row["passed"] is False
    assert row["pipeline_holdout_ok"] is True
    assert row["grade_agrees_with_pipeline"] is False


def test_generation_error_is_a_fail_not_a_crash(tmp_path):
    class Broken:
        def complete(self, messages, max_tokens=4096):
            return {"content": "", "model_used": "", "error": "Ollama unreachable"}

    row = make_ablation(tmp_path, router=Broken()).run_sample(TASK, ARMS["bare"], 1)
    assert row["passed"] is False
    assert "Ollama unreachable" in row["error"]


def test_exception_during_generation_is_captured_as_a_row(tmp_path):
    class Boom:
        def complete(self, messages, max_tokens=4096):
            raise RuntimeError("gpu fell over")

    row = make_ablation(tmp_path, router=Boom()).run_sample(TASK, ARMS["bare"], 1)
    assert row["passed"] is False
    assert "gpu fell over" in row["error"]


# --------------------------------------------------------------------------
# Leak exclusion
# --------------------------------------------------------------------------


LEAKY_TASK = {
    "id": "t02",
    "title": "leaky",
    "objective": "Implement is_even.\nassert is_even(4) is True\nassert is_even(5) is False",
    "holdout_test": HOLDOUT,
    "difficulty": "easy",
}


def test_leaked_prompt_is_excluded_and_the_model_is_never_called(tmp_path):
    ab = make_ablation(tmp_path, tasks=[LEAKY_TASK], router=ExplodingRouter())
    row = ab.run_sample(LEAKY_TASK, ARMS["bare"], 1)
    assert row["leaked"] is True
    assert row["passed"] is False
    assert "preflight" in row["leak_detail"]


def test_leaked_sample_is_never_scored_as_a_pass_even_with_correct_code(tmp_path):
    ab = make_ablation(tmp_path, tasks=[LEAKY_TASK], router=FakeRouter(GOOD))
    row = ab.run_sample(LEAKY_TASK, ARMS["bare"], 1)
    assert (row["leaked"], row["passed"]) == (True, False)


def test_pipeline_prompt_guard_leak_excludes_the_sample(tmp_path):
    """The ether arm's real prompt only exists after the run; use its own guard."""
    pipe = FakePipeline(
        FakeResult(
            code=GOOD,
            holdout_ok=None,
            stages=[FakeStage("prompt_guard", success=False, detail="LEAK: 3 assertions")],
        )
    )
    ab = make_ablation(tmp_path, arms=("ether",), pipeline_factory=lambda: pipe)
    row = ab.run_sample(TASK, ARMS["ether"], 1)
    assert row["leaked"] is True
    assert row["passed"] is False


def test_holdout_inside_generated_code_is_excluded(tmp_path):
    """Code that contains the holdout grades nothing, so it is a leak not a pass."""
    ab = make_ablation(
        tmp_path,
        router=FakeRouter(GOOD + "\n" + HOLDOUT),
        grade=ablation.grade_against_holdout,
    )
    row = ab.run_sample(TASK, ARMS["bare"], 1)
    assert (row["leaked"], row["passed"]) == (True, False)


def test_leaked_samples_are_out_of_every_denominator():
    rows = [
        {"task_id": "t1", "arm": "bare", "seed": 1, "passed": True, "leaked": False},
        {"task_id": "t2", "arm": "bare", "seed": 1, "passed": False, "leaked": True},
    ]
    s = summarize(rows, arms=["bare"], seeds=[1], resamples=10_000)
    assert s["arms"]["bare"]["n_samples_scored"] == 1
    assert s["arms"]["bare"]["pass_rate"] == 1.0
    assert s["arms"]["bare"]["n_leaked_excluded"] == 1
    assert any("excluded for holdout leakage" in n for n in s["notes"])


# --------------------------------------------------------------------------
# Arms, prompts and decode
# --------------------------------------------------------------------------


def test_bare_arm_sends_the_objective_and_nothing_else():
    msgs = build_messages(ARMS["bare"], "do the thing")
    assert msgs == [{"role": "user", "content": "do the thing"}]


def test_bare_sys_arm_adds_the_short_system_prompt():
    msgs = build_messages(ARMS["bare+sys"], "do the thing")
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == "Write only Python. No markdown, no explanation."
    assert len(msgs[0]["content"]) < 120  # three lines, not an engineered prompt


def test_direct_arms_never_touch_the_pipeline(tmp_path):
    def no_pipeline():  # pragma: no cover - must not run
        raise AssertionError("a direct arm built a Pipeline")

    router = FakeRouter(GOOD)
    ab = make_ablation(
        tmp_path, arms=("bare", "bare+sys"), router=router, pipeline_factory=no_pipeline
    )
    ab.run()
    assert len(router.calls) == 2


def test_ether_arm_passes_the_holdout_to_the_pipeline_but_not_the_prompt(tmp_path):
    pipe = FakePipeline(FakeResult(code=GOOD))
    ab = make_ablation(tmp_path, arms=("ether",), pipeline_factory=lambda: pipe)
    ab.run_sample(TASK, ARMS["ether"], 2)
    assert pipe.calls[0]["holdout_test"] == HOLDOUT
    assert pipe.calls[0]["objective"] == TASK["objective"]
    assert "assert is_even" not in pipe.calls[0]["objective"]


def test_decode_env_sets_exactly_what_the_router_reads():
    """If these names drift, the ablation silently runs on Modelfile defaults."""
    from gems.rose_quartz.router import decode_options

    decode = {
        "temperature": 0.2,
        "top_p": 0.9,
        "top_k": 40,
        "num_ctx": 32768,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "repeat_penalty": 1.0,
    }
    with decode_env(decode, seed=7):
        opts = decode_options(512)
    assert opts["temperature"] == 0.2
    assert opts["top_p"] == 0.9
    assert opts["top_k"] == 40
    assert opts["num_ctx"] == 32768
    assert opts["presence_penalty"] == 0.0
    assert opts["repeat_penalty"] == 1.0
    assert opts["seed"] == 7


def test_decode_env_restores_the_environment():
    before = dict(os.environ)
    with decode_env({"temperature": 1.7}, seed=99, extra={"ETHER_SANDBOX_RETRY": "0"}):
        assert os.environ["ETHER_TEMPERATURE"] == "1.7"
        assert os.environ["ETHER_SANDBOX_RETRY"] == "0"
    assert os.environ.get("ETHER_TEMPERATURE") == before.get("ETHER_TEMPERATURE")
    assert os.environ.get("ETHER_SANDBOX_RETRY") == before.get("ETHER_SANDBOX_RETRY")


def test_every_sample_is_generated_under_its_own_seed(tmp_path):
    router = FakeRouter(GOOD)
    ab = make_ablation(tmp_path, arms=("bare",), seeds=(1, 2, 3), router=router)
    ab.run()
    assert [c["seed"] for c in router.calls] == ["1", "2", "3"]
    assert {c["temperature"] for c in router.calls} == {"0.2"}


def test_arm_env_is_applied_only_during_generation(tmp_path):
    seen = {}

    class Pipe:
        def run(self, objective, holdout_test=""):
            seen["retry"] = os.environ.get("ETHER_SANDBOX_RETRY")
            return FakeResult(code=GOOD)

    ab = make_ablation(tmp_path, arms=("ether-no-repair",), pipeline_factory=Pipe)
    ab.run_sample(TASK, ARMS["ether-no-repair"], 1)
    assert seen["retry"] == "0"


def test_arm_table_is_extensible():
    """Adding an ablation is one dict entry, not a new branch."""
    arm = Arm(name="ether-no-plan", kind="ether", description="x", env={"ETHER_LLM_PLAN": "0"})
    assert arm.kind == "ether"
    assert {"ether-no-retrieval", "ether-no-repair"} <= set(ARMS)
    assert ARMS["ether-no-retrieval"].env["ETHER_RAG_BM25"] == "0"


def test_code_extraction_is_generous_to_the_baseline():
    """A bare model answers with prose around a fence; that is not a failure."""
    reply = "Sure! Here you go:\n\n```python\n" + GOOD + "```\n\nHope that helps."
    assert extract_code(reply).strip() == GOOD.strip()
    assert extract_code(GOOD) == GOOD.strip()
    assert extract_code("") == ""


# --------------------------------------------------------------------------
# Resume
# --------------------------------------------------------------------------


def test_resume_skips_completed_triples(tmp_path):
    router = FakeRouter(GOOD)
    first = make_ablation(tmp_path, arms=("bare",), seeds=(1, 2), router=router)
    first.run()
    assert len(router.calls) == 2

    # A crash and a restart: the model must not be asked the same thing twice.
    second = make_ablation(
        tmp_path, arms=("bare",), seeds=(1, 2), router=ExplodingRouter(), resume=True
    )
    summary = second.run()
    assert summary["arms"]["bare"]["n_samples_scored"] == 2
    lines = (tmp_path / "samples.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # nothing re-appended


def test_resume_runs_only_the_missing_samples(tmp_path):
    make_ablation(tmp_path, arms=("bare",), seeds=(1,), router=FakeRouter(GOOD)).run()
    router = FakeRouter(GOOD)
    ab = make_ablation(tmp_path, arms=("bare",), seeds=(1, 2, 3), router=router, resume=True)
    ab.run()
    assert [c["seed"] for c in router.calls] == ["2", "3"]


def test_resume_ignores_rows_from_a_different_config(tmp_path):
    """Resuming across a model or decode change would merge two experiments."""
    make_ablation(tmp_path, arms=("bare",), seeds=(1,), router=FakeRouter(GOOD)).run()
    other = make_ablation(
        tmp_path,
        arms=("bare",),
        seeds=(1,),
        router=FakeRouter(GOOD),
        resume=True,
        model_info={"model": "a-different-model", "digest": "cafe"},
    )
    assert load_completed(tmp_path / "samples.jsonl", other.config_key) == {}
    other.run()
    lines = (tmp_path / "samples.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2


def test_each_sample_is_durable_before_the_next_one_starts(tmp_path):
    """A crash at hour 3 must lose at most the sample in flight."""
    path = tmp_path / "samples.jsonl"

    class HalfwayCrash:
        def __init__(self):
            self.n = 0

        def complete(self, messages, max_tokens=4096):
            self.n += 1
            if self.n == 2:
                raise KeyboardInterrupt
            return {"content": GOOD, "model_used": "fake", "error": ""}

    ab = make_ablation(tmp_path, arms=("bare",), seeds=(1, 2, 3), router=HalfwayCrash())
    with pytest.raises(KeyboardInterrupt):
        ab.run()
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").strip().splitlines()]
    assert len(rows) == 1 and rows[0]["seed"] == 1 and rows[0]["passed"] is True


def test_load_completed_survives_a_torn_final_line(tmp_path):
    path = tmp_path / "samples.jsonl"
    path.write_text(
        json.dumps({"task_id": "t1", "arm": "bare", "seed": 1, "passed": True})
        + "\n{\"task_id\": \"t2\", \"arm\": \"ba",
        encoding="utf-8",
    )
    done = load_completed(path)
    assert list(done) == [sample_key("t1", "bare", 1)]


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def _row(task, arm, seed, passed):
    return {"task_id": task, "arm": arm, "seed": seed, "passed": passed, "leaked": False}


def test_pass_at_1_and_oracle_pass_at_n():
    rows = [
        _row("t1", "bare", 1, False),
        _row("t1", "bare", 2, True),  # oracle yes, pass@1 no
        _row("t2", "bare", 1, True),
        _row("t2", "bare", 2, True),
    ]
    s = summarize(rows, arms=["bare"], seeds=[1, 2], resamples=10_000)["arms"]["bare"]
    assert s["pass_rate"] == 0.75
    assert s["pass_at_1"] == 0.5
    assert s["oracle_pass_at_n"] == 1.0


def test_summary_carries_the_paired_comparison_and_provenance():
    rows = []
    for i in range(1, 11):
        t = f"t{i:02d}"
        ether_ok = i <= 8
        sys_ok = i <= 3
        rows += [_row(t, "ether", 1, ether_ok), _row(t, "bare+sys", 1, sys_ok)]
    s = summarize(
        rows,
        arms=["ether", "bare+sys"],
        seeds=[1],
        decode={"temperature": 0.2},
        dataset_meta={"id": "headroom_v1", "source": "headroom", "sha256": "abc"},
        model_info={"model": "m", "digest": "d"},
        resamples=10_000,
    )
    primary = s["comparisons"][0]
    assert (primary["a"], primary["b"]) == ("ether", "bare+sys")
    assert primary["table"]["only_a"] == 5 and primary["table"]["only_b"] == 0
    assert primary["mcnemar"]["p_value"] == pytest.approx(2 * 0.5**5)
    assert primary["delta_pass_rate"] == pytest.approx(0.5)
    assert primary["paired_delta_ci"]["delta"] == pytest.approx(0.5)
    assert primary["paired_delta_ci"]["excludes_zero"] is True
    assert s["dataset"]["id"] == "headroom_v1"
    assert s["decode"] == {"temperature": 0.2}
    assert s["graded_on"] == "core.holdout.grade_against_holdout"
    assert s["power"]["n_tasks"] == 10


def test_ceiling_effect_is_called_out():
    rows = [_row(f"t{i}", "bare", 1, True) for i in range(10)]
    s = summarize(rows, arms=["bare"], seeds=[1], resamples=10_000)
    assert any("Ceiling effect" in n for n in s["notes"])


def test_burst_usage_is_called_out():
    rows = [{**_row("t1", "ether", 1, True), "used_burst": True}]
    s = summarize(rows, arms=["ether"], seeds=[1], resamples=10_000)
    assert any("CLOUD BURST" in n for n in s["notes"])


def test_markdown_summary_reports_the_caveats_with_the_number():
    rows = [_row("t1", "bare", 1, True), _row("t2", "bare", 1, False)]
    md = markdown_summary(
        summarize(
            rows,
            arms=["bare"],
            seeds=[1],
            model_info={"model": "m", "digest": ""},
            dataset_meta={"id": "unit", "source": "bench", "warning": "x"},
            resamples=10_000,
        )
    )
    assert "| `bare` | 0.500 |" in md
    assert "UNKNOWN" in md  # a missing digest is visible, not hidden
    assert "DATASET FALLBACK" in md
    assert "Power" in md


# --------------------------------------------------------------------------
# Dataset loading
# --------------------------------------------------------------------------


def test_headroom_dataset_shape_is_read_when_present(tmp_path):
    path = tmp_path / "headroom_v1.json"
    path.write_text(
        json.dumps(
            {
                "id": "headroom_v1",
                "tasks": [
                    {
                        "id": "hr01",
                        "title": "merge",
                        "objective": "Implement def merge(a, b)",
                        "holdout_test": "assert merge([], []) == []\n",
                        "difficulty": "medium",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    tasks, meta = load_dataset(path)
    assert meta["source"] == "headroom"
    assert meta["id"] == "headroom_v1"
    assert meta["sha256"]
    assert tasks[0]["difficulty"] == "medium"
    assert tasks[0]["holdout_test"].startswith("assert")


def test_missing_headroom_falls_back_to_bench_and_says_so(tmp_path):
    tasks, meta = load_dataset(tmp_path / "not_here.json")
    assert meta["source"] == "bench"
    assert "fell back to bench" in meta["note"]
    assert meta["warning"]
    assert tasks and all(t["holdout_test"] for t in tasks)


def test_a_bare_list_dataset_also_loads(tmp_path):
    path = tmp_path / "headroom_v1.json"
    path.write_text(
        json.dumps([{"id": "x", "objective": "o", "holdout_test": "assert 1 == 1"}]), "utf-8"
    )
    tasks, meta = load_dataset(path)
    assert meta["source"] == "headroom" and len(tasks) == 1


def test_dataset_audit_rejects_a_task_that_leaks_its_answer():
    from scripts.ablation import audit_dataset

    assert audit_dataset([TASK]) == []
    assert audit_dataset([LEAKY_TASK])
    assert audit_dataset([{**TASK, "holdout_test": ""}])


def test_instruction_preamble_is_detected_so_bare_is_not_misread():
    from scripts.ablation import has_instruction_preamble, strip_instruction_preamble

    bench_style = "Write only Python, no markdown.\n\nImplement:\n\ndef f(x)\n\nDo the thing."
    assert has_instruction_preamble(bench_style)
    assert strip_instruction_preamble(bench_style).startswith("def f(x)")
    assert not has_instruction_preamble(TASK["objective"])


def test_bare_strip_preamble_applies_to_bare_only(tmp_path):
    task = {**TASK, "objective": "Write only Python, no markdown.\n\nImplement:\n\ndef f(x)"}
    ab = make_ablation(tmp_path, tasks=[task], strip_bare_preamble=True)
    assert ab.objective_for(ARMS["bare"], task) == "def f(x)"
    assert ab.objective_for(ARMS["bare+sys"], task) == task["objective"]
    assert ab.objective_for(ARMS["ether"], task) == task["objective"]


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_dry_run_calls_no_model_and_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ablation.RouterClient, "complete", ExplodingRouter.complete)
    monkeypatch.setattr(
        ablation.Ablation,
        "_default_pipeline_factory",
        staticmethod(lambda: (_ for _ in ()).throw(AssertionError("built a Pipeline"))),
    )
    rc = ablation.main(
        [
            "--dry-run",
            "--no-probe",
            "--limit",
            "3",
            "--samples",
            "2",
            "--jsonl",
            str(tmp_path / "s.jsonl"),
            "--out-dir",
            str(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY RUN" in out
    assert '"generations_total": 18' in out
    assert list(tmp_path.iterdir()) == []


def test_unknown_arm_is_rejected(tmp_path, capsys):
    assert ablation.main(["--arms", "wishful", "--dry-run", "--no-probe"]) == 2


@pytest.mark.parametrize(
    "argv,expected",
    [
        ([], [1, 2, 3]),
        (["--samples", "1"], [1]),
        (["--samples", "5"], [1, 2, 3, 4, 5]),
        (["--seeds", "11,12"], [11, 12]),
    ],
)
def test_seeds_are_fixed_and_explicit(argv, expected, tmp_path, monkeypatch, capsys):
    """Default [1,2,3]; never time- or random-derived, or reruns are not comparable."""
    monkeypatch.setattr(ablation.RouterClient, "complete", ExplodingRouter.complete)
    rc = ablation.main(
        ["--dry-run", "--no-probe", "--limit", "1", "--out-dir", str(tmp_path)] + argv
    )
    assert rc == 0
    assert f"seeds={expected}" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_full_run_writes_the_summary_and_the_markdown(tmp_path, monkeypatch):
    """The whole loop, fakes for the model, real files on disk."""
    meta = {"id": "unit", "source": "headroom", "sha256": "z"}
    monkeypatch.setattr(ablation, "load_dataset", lambda p=None: ([TASK], meta))
    monkeypatch.setattr(
        ablation.RouterClient,
        "complete",
        lambda self, m, max_tokens=4096: {"content": GOOD, "model_used": "fake", "error": ""},
    )
    monkeypatch.setattr(
        ablation.Ablation,
        "_default_pipeline_factory",
        staticmethod(lambda: FakePipeline(FakeResult(code=GOOD))),
    )
    # The grader is resolved through the module attribute, so this reaches the
    # Ablation `main` builds without reaching into its constructor.
    monkeypatch.setattr(ablation, "grade_against_holdout", fake_grade)

    rc = ablation.main(
        [
            "--no-probe",
            "--samples",
            "1",
            "--jsonl",
            str(tmp_path / "s.jsonl"),
            "--out-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    summary = json.loads((tmp_path / "ablation_latest.json").read_text(encoding="utf-8"))
    assert set(summary["arms"]) == {"bare", "bare+sys", "ether"}
    assert summary["arms"]["bare"]["pass_rate"] == 1.0
    assert (tmp_path / "ablation_latest.md").exists()
    assert len((tmp_path / "s.jsonl").read_text(encoding="utf-8").strip().splitlines()) == 3


def test_the_default_grader_is_the_shared_one(tmp_path):
    """No private grader. hidden_quiz.py's divergent copy is why this is a test."""
    from core.holdout import grade_against_holdout

    assert make_ablation(tmp_path, grade=None).grade is grade_against_holdout
    assert ablation.guard_check.__module__ == "core.prompt_guard"
