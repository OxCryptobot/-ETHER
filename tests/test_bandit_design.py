"""Design-level regression tests for the contextual bandit.

The audit found the bandit structurally unable to converge:

* the strategy was drawn once, before any code existed, so `fail_kind` was
  always empty and the repair branch of the policy could never fire;
* rewards earned in a hard context were credited to a single global arm table,
  so the arms that were deliberately steered at hard contexts accumulated the
  worst means and were then avoided;
* eight of the ten arms were prompt-only, three of them literal no-ops, so the
  bandit was choosing between near-identical things;
* plus: an asymmetric COLD_DECAY that walked negative arms upward, exploration
  that neither annealed nor matched the configured epsilon, a double update
  from two stale in-memory copies of the arm table, and used_burst inferred by
  substring-matching "llama".

Each test below pins one of those.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

import pytest

from core import learning
from core.learning import (
    RETIRED_STRATEGIES,
    STRATEGIES,
    STRATEGY_BEHAVIOUR,
    BanditPolicy,
    arm_behaviour,
    context_key,
)
from core.pipeline import Pipeline, _is_burst_model
from core.registry import GemRegistry
from core.schemas import (
    AmethystResponse,
    BlackTourmalineResponse,
    ClearQuartzResponse,
    Envelope,
    ExecutionPlan,
    LabradoriteResponse,
    PlanStep,
    ResponseEnvelope,
    RoseQuartzResponse,
    SeleniteResponse,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


class _Gem:
    def __init__(self, name: str, responder):
        self.name = name
        self.responder = responder

    def execute(self, request: Envelope) -> ResponseEnvelope:
        return self.responder(request)


class Recorder:
    """Registry whose sandbox verdicts are scripted and whose prompts are kept."""

    def __init__(self, sandbox_exits: List[int], model_used: str = "local-model"):
        self.sandbox_exits = list(sandbox_exits)
        self.model_used = model_used
        self.prompts: List[str] = []
        self.sandbox_calls = 0

    def registry(self) -> GemRegistry:
        reg = GemRegistry()
        reg.register(
            "selenite",
            _Gem(
                "selenite",
                lambda r: ResponseEnvelope(
                    task_id=r.task_id,
                    source_gem="selenite",
                    payload=SeleniteResponse(
                        plan=ExecutionPlan(
                            steps=[PlanStep(id=1, action="generate", target="code", description="g")]
                        )
                    ),
                ),
            ),
        )

        def _code(r: Envelope) -> ResponseEnvelope:
            self.prompts.append(r.payload.messages[0].content or "")
            return ResponseEnvelope(
                task_id=r.task_id,
                source_gem="rose-quartz",
                payload=RoseQuartzResponse(
                    content="def hello():\n    return 'hi'\n", model_used=self.model_used
                ),
            )

        reg.register("rose-quartz", _Gem("rose-quartz", _code))

        def _sandbox(r: Envelope) -> ResponseEnvelope:
            idx = min(self.sandbox_calls, len(self.sandbox_exits) - 1)
            exit_code = self.sandbox_exits[idx]
            self.sandbox_calls += 1
            return ResponseEnvelope(
                task_id=r.task_id,
                source_gem="clear-quartz",
                payload=ClearQuartzResponse(
                    exit_code=exit_code,
                    total_tests=0,
                    tests_passed=0,
                    stderr="" if exit_code == 0 else 'File "x.py", line 1\nSyntaxError: bad token',
                ),
            )

        reg.register("clear-quartz", _Gem("clear-quartz", _sandbox))
        reg.register(
            "black-tourmaline",
            _Gem(
                "black-tourmaline",
                lambda r: ResponseEnvelope(
                    task_id=r.task_id,
                    source_gem="black-tourmaline",
                    payload=BlackTourmalineResponse(approved=True, risk_score=0.0),
                ),
            ),
        )
        reg.register(
            "labradorite",
            _Gem(
                "labradorite",
                lambda r: ResponseEnvelope(
                    task_id=r.task_id,
                    source_gem="labradorite",
                    payload=LabradoriteResponse(critique="fine"),
                ),
            ),
        )
        reg.register(
            "amethyst",
            _Gem(
                "amethyst",
                lambda r: ResponseEnvelope(
                    task_id=r.task_id,
                    source_gem="amethyst",
                    payload=AmethystResponse(status="logged"),
                ),
            ),
        )
        reg.register(
            "grandidierite",
            _Gem(
                "grandidierite",
                lambda r: ResponseEnvelope(
                    task_id=r.task_id,
                    source_gem="grandidierite",
                    payload=AmethystResponse(status="ok"),
                ),
            ),
        )
        return reg


class StubPolicy:
    """Policy that returns a scripted arm order and records every credit."""

    def __init__(self, arms: List[str]):
        self.arms_to_return = list(arms)
        self.selections: List[Dict[str, Any]] = []
        self.updates: List[Dict[str, Any]] = []

    def select(self, context: Optional[Dict] = None) -> str:
        self.selections.append(dict(context or {}))
        idx = min(len(self.selections) - 1, len(self.arms_to_return) - 1)
        return self.arms_to_return[idx]

    def update(self, strategy, reward, context=None, extra=None):
        self.updates.append(
            {"strategy": strategy, "reward": reward, "context": dict(context or {})}
        )


class LegacyPolicy:
    """Pre-change policy signature — the pipeline must still drive it."""

    def __init__(self):
        self.updates: List[Any] = []

    def select(self, context=None):
        return "default"

    def update(self, strategy, reward):
        self.updates.append((strategy, reward))


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setenv("ETHER_LEARNING", "1")
    monkeypatch.setenv("ETHER_LEARN_EPSILON", "0.15")
    monkeypatch.setenv("ETHER_TOOL_ASSIST", "0")
    monkeypatch.setenv("ETHER_CONTEXT", "0")
    monkeypatch.setenv("ETHER_SANDBOX_RETRY", "0")
    monkeypatch.setenv("ETHER_AUTO_FABRICATE_ON_FAIL", "0")
    monkeypatch.delenv("ETHER_BURST", raising=False)
    monkeypatch.delenv("ETHER_BURST_MODEL", raising=False)
    # Nothing in these tests may reach an embedding server or a model.
    import core.pipeline as pipeline_mod

    monkeypatch.setattr(pipeline_mod, "index_pass_pattern", lambda **kw: {"ok": True})


def _policy(tmp_path, epsilon: float = 0.15) -> BanditPolicy:
    return BanditPolicy(epsilon=epsilon, path=tmp_path / "bandit.json")


GEN = {"tier": 0, "fail_kind": "", "multifile": False}
SYNTAX = {"tier": 0, "fail_kind": "SyntaxError", "multifile": False}
LOGIC = {"tier": 0, "fail_kind": "AssertionError", "multifile": False}


def _cover(policy: BanditPolicy, context: Dict[str, Any], reward: float = 0.0) -> None:
    """Give every arm one pull in this bucket so coverage is finished."""
    for arm in STRATEGIES:
        policy.update(arm, reward, context=context)


# --------------------------------------------------------------------------
# Defect 3 — the arm set
# --------------------------------------------------------------------------


def test_no_op_arms_are_gone():
    """rag_on / few_shot_on / burst_on_fail changed nothing at all.

    BM25 runs for every strategy inside gather_workspace_context, few_shot_pack
    runs unconditionally, and burst needs ETHER_BURST=1 (default 0) — and when
    it is on, any retry bursts regardless of the arm.
    """
    for dead in ("rag_on", "few_shot_on", "burst_on_fail", "step_by_step"):
        assert dead not in STRATEGIES
        assert dead in RETIRED_STRATEGIES


def test_arm_set_is_small_and_every_arm_has_a_behaviour():
    assert 3 <= len(STRATEGIES) <= 6, "ten near-identical arms cannot be told apart"
    assert set(STRATEGIES) == set(STRATEGY_BEHAVIOUR)
    addons = {a: arm_behaviour(a).prompt_addon for a in STRATEGIES}
    assert len(set(addons.values())) == len(STRATEGIES), "two arms with the same directive"


def test_retired_arms_are_never_selected_even_if_present_in_the_state_file(tmp_path):
    path = tmp_path / "bandit.json"
    path.write_text(
        '{"epsilon": 0.15, "arms": {"rag_on": {"pulls": 20, "total_reward": 6.0},'
        ' "default": {"pulls": 6, "total_reward": 1.4}}}',
        encoding="utf-8",
    )
    pol = BanditPolicy(path=path)
    assert "rag_on" not in pol.arms
    # The history is preserved rather than deleted, just not selectable.
    assert pol.snapshot()["retired_arms"]["rag_on"]["pulls"] == 20
    for _ in range(200):
        assert pol.select(GEN) in STRATEGIES


def test_no_context_is_a_real_ablation_and_repo_map_on_is_a_real_addition(monkeypatch):
    """`no_context` still received the experience block, the few-shot block,
    the tool output and the repo map. `repo_map_on` was one sentence."""
    monkeypatch.setenv("ETHER_TOOL_ASSIST", "1")
    monkeypatch.setenv("ETHER_CONTEXT", "1")
    import core.pipeline as pipeline_mod

    monkeypatch.setattr(
        pipeline_mod, "gather_workspace_context", lambda root, query="": "WORKSPACE-MARKER"
    )
    monkeypatch.setattr(
        pipeline_mod, "experience_retrieve", lambda *a, **k: {"block": "EXPERIENCE-MARKER"}
    )

    def _run_tool(name, payload=None):
        if name == "few_shot_pack":
            return {"ok": True, "result": {"block": "FEWSHOT-MARKER"}}
        if name == "repo_map":
            return {"ok": True, "files": [{"path": "REPOMAP-MARKER.py", "symbols": ["f"]}]}
        return {"ok": True, "result": {"clean": True}}

    import gems.grandidierite.registry as gregistry

    monkeypatch.setattr(gregistry, "run_tool", _run_tool)

    prompts = {}
    for arm in ("default", "no_context", "repo_map_on"):
        rec = Recorder([0])
        pipe = Pipeline(registry=rec.registry())
        pipe.policy = StubPolicy([arm])  # type: ignore[assignment]
        pipe.run("add two numbers")
        prompts[arm] = rec.prompts[0]

    for marker in ("WORKSPACE-MARKER", "EXPERIENCE-MARKER", "FEWSHOT-MARKER"):
        assert marker in prompts["default"]
        assert marker not in prompts["no_context"], f"no_context still saw {marker}"

    # The objective is not multifile, so only the arm pulls the map in.
    assert "REPOMAP-MARKER" not in prompts["default"]
    assert "REPOMAP-MARKER" in prompts["repo_map_on"]
    assert "REPOMAP-MARKER" not in prompts["no_context"]


def test_every_arm_produces_a_distinguishable_prompt(monkeypatch):
    monkeypatch.setenv("ETHER_TOOL_ASSIST", "1")
    monkeypatch.setenv("ETHER_CONTEXT", "1")
    import core.pipeline as pipeline_mod
    import gems.grandidierite.registry as gregistry

    monkeypatch.setattr(pipeline_mod, "gather_workspace_context", lambda root, query="": "CTX")
    monkeypatch.setattr(pipeline_mod, "experience_retrieve", lambda *a, **k: {"block": "EXP"})
    monkeypatch.setattr(
        gregistry,
        "run_tool",
        lambda name, payload=None: (
            {"ok": True, "result": {"block": "FS"}}
            if name == "few_shot_pack"
            else {"ok": True, "files": [{"path": "m.py", "symbols": ["f"]}], "result": {"clean": True}}
        ),
    )

    seen = {}
    for arm in STRATEGIES:
        rec = Recorder([0])
        pipe = Pipeline(registry=rec.registry())
        pipe.policy = StubPolicy([arm])  # type: ignore[assignment]
        pipe.run("add two numbers")
        seen[arm] = rec.prompts[0]
    assert len(set(seen.values())) == len(STRATEGIES), "some arms are indistinguishable no-ops"


# --------------------------------------------------------------------------
# Defect 1 — fail_kind must be able to influence selection
# --------------------------------------------------------------------------


def test_context_key_separates_generation_from_the_two_repair_phases():
    assert context_key(GEN) != context_key(SYNTAX)
    assert context_key(SYNTAX) != context_key(LOGIC)
    # Coarse on purpose: these three share a repair phase.
    assert context_key(SYNTAX) == context_key({"fail_kind": "NameError"})
    assert context_key(SYNTAX) == context_key({"fail_kind": "ImportError"})


def test_fail_kind_changes_the_arm_that_is_selected(tmp_path):
    pol = _policy(tmp_path, epsilon=0.0)
    _cover(pol, GEN)
    _cover(pol, SYNTAX)
    for _ in range(6):
        pol.update("minimal", 0.9, context=GEN)
        pol.update("repair_heavy", -0.9, context=GEN)
        pol.update("repair_heavy", 0.9, context=SYNTAX)
        pol.update("minimal", -0.9, context=SYNTAX)

    assert pol.select(GEN) == "minimal"
    assert pol.select(SYNTAX) == "repair_heavy"


def test_pipeline_reselects_the_arm_on_retry_with_the_observed_fail_kind(monkeypatch):
    """The strategy was chosen once, before the code stage, so the whole
    SyntaxError/NameError/ImportError branch of select() was unreachable."""
    monkeypatch.setenv("ETHER_SANDBOX_RETRY", "1")
    rec = Recorder([1, 0])  # fail, then pass
    pipe = Pipeline(registry=rec.registry())
    policy = StubPolicy(["minimal", "repair_heavy"])
    pipe.policy = policy  # type: ignore[assignment]
    result = pipe.run("add two numbers")

    assert len(policy.selections) == 2, "the arm was not re-drawn for the retry"
    assert policy.selections[0]["fail_kind"] == ""
    assert policy.selections[1]["fail_kind"] == "SyntaxError"
    assert result.strategies == ["minimal", "repair_heavy"]
    assert result.strategy == "repair_heavy", "result.strategy must name the arm that ran last"


def test_retry_reward_is_credited_to_the_arm_that_produced_it(monkeypatch):
    """Attempt 1 used arm A and failed; attempt 2 used arm B and succeeded.
    Crediting A with the run reward is the bug."""
    monkeypatch.setenv("ETHER_SANDBOX_RETRY", "1")
    rec = Recorder([1, 0])
    pipe = Pipeline(registry=rec.registry())
    policy = StubPolicy(["minimal", "repair_heavy"])
    pipe.policy = policy  # type: ignore[assignment]
    result = pipe.run("add two numbers")

    assert [u["strategy"] for u in policy.updates] == ["minimal", "repair_heavy"]
    failed, succeeded = policy.updates
    assert succeeded["reward"] == result.reward
    assert failed["reward"] < 0, "the arm whose code did not run must not share the win"
    assert failed["reward"] != result.reward
    # ...and each is booked in the situation it was drawn from.
    assert failed["context"]["fail_kind"] == ""
    assert succeeded["context"]["fail_kind"] == "SyntaxError"


def test_single_attempt_run_credits_exactly_one_arm_once():
    rec = Recorder([0])
    pipe = Pipeline(registry=rec.registry())
    policy = StubPolicy(["default"])
    pipe.policy = policy  # type: ignore[assignment]
    result = pipe.run("add two numbers")
    assert len(policy.updates) == 1
    assert policy.updates[0] == {
        "strategy": "default",
        "reward": result.reward,
        "context": policy.selections[0],
    }


def test_a_policy_without_contextual_update_still_works():
    """Back-compat: update(self, strategy, reward) must not raise."""
    rec = Recorder([0])
    pipe = Pipeline(registry=rec.registry())
    policy = LegacyPolicy()
    pipe.policy = policy  # type: ignore[assignment]
    result = pipe.run("add two numbers")
    assert policy.updates == [("default", result.reward)]


# --------------------------------------------------------------------------
# Defect 2 — rewards must be compared within a context
# --------------------------------------------------------------------------


def test_credit_in_one_context_does_not_move_the_score_in_another(tmp_path):
    """`repair_heavy` was steered at broken code, banked the resulting bad
    rewards in the one global table, and was then avoided everywhere."""
    pol = _policy(tmp_path, epsilon=0.0)
    _cover(pol, GEN)
    _cover(pol, SYNTAX)
    before = pol.score(context_key(GEN), "repair_heavy")
    for _ in range(10):
        pol.update("repair_heavy", -0.9, context=SYNTAX)
    assert pol.score(context_key(GEN), "repair_heavy") == pytest.approx(before)
    assert pol.score(context_key(SYNTAX), "repair_heavy") < before


def test_an_arm_that_only_ever_sees_hard_contexts_still_wins_its_own_context(tmp_path):
    """The live table had repair_heavy at -0.221 and rag_on at +0.034 purely
    because of which problems each was handed. Within a context, the arm that
    does best there must be picked there."""
    pol = _policy(tmp_path, epsilon=0.0)
    _cover(pol, GEN)
    _cover(pol, SYNTAX)
    # Everything is bad in the repair context, but repair_heavy is least bad;
    # meanwhile every other arm looks great in the easy context.
    for _ in range(8):
        pol.update("repair_heavy", -0.3, context=SYNTAX)
        for arm in STRATEGIES:
            if arm != "repair_heavy":
                pol.update(arm, -0.8, context=SYNTAX)
                pol.update(arm, 0.8, context=GEN)

    assert pol.arms["repair_heavy"].mean_reward < pol.arms["default"].mean_reward
    assert pol.select(SYNTAX) == "repair_heavy", "still comparing against the global mean"


def test_domain_hints_are_a_prior_not_a_forced_choice(tmp_path):
    """The dead branch hard-assigned repair arms to syntax failures 40% of the
    time. The knowledge is kept as a prior that evidence can overrule."""
    pol = _policy(tmp_path, epsilon=0.0)
    bucket = context_key(SYNTAX)
    assert pol.score(bucket, "repair_heavy") > pol.score(bucket, "default")
    for _ in range(12):
        pol.update("repair_heavy", -0.9, context=SYNTAX)
        pol.update("default", 0.6, context=SYNTAX)
    assert pol.score(bucket, "default") > pol.score(bucket, "repair_heavy")


# --------------------------------------------------------------------------
# COLD_DECAY
# --------------------------------------------------------------------------


def test_updating_one_arm_never_rewrites_another_arms_history(tmp_path):
    """COLD_DECAY multiplied total_reward (but not pulls) of every arm with
    pulls<8 on every update. For a negative arm that moves its mean *up*
    toward 0, so an arm that failed once drifted past a well-sampled arm that
    failed consistently."""
    pol = _policy(tmp_path, epsilon=0.0)
    pol.update("minimal", -0.9, context=GEN)
    once_failed = pol.arms["minimal"].total_reward
    ctx_failed = pol.context_stats(context_key(GEN)).arm("minimal").total_reward

    for _ in range(40):
        pol.update("default", -0.5, context=GEN)

    assert pol.arms["minimal"].total_reward == pytest.approx(once_failed)
    assert pol.context_stats(context_key(GEN)).arm("minimal").total_reward == pytest.approx(
        ctx_failed
    )
    # The consistently-failing arm is still rated better than the once-failing
    # one, which is the ordering the decay used to invert.
    bucket = context_key(GEN)
    assert pol.score(bucket, "default") > pol.score(bucket, "minimal")


def test_reloading_the_state_file_preserves_means(tmp_path):
    path = tmp_path / "bandit.json"
    pol = BanditPolicy(epsilon=0.15, path=path)
    for _ in range(5):
        pol.update("minimal", -0.4, context=GEN)
    again = BanditPolicy(path=path)
    assert again.arms["minimal"].pulls == 5
    assert again.arms["minimal"].mean_reward == pytest.approx(-0.4)
    assert again.context_stats(context_key(GEN)).arm("minimal").pulls == 5


# --------------------------------------------------------------------------
# Exploration rate + annealing
# --------------------------------------------------------------------------


def test_exploration_rate_matches_the_configured_epsilon(tmp_path):
    """Measured 14%/48%/42% against ETHER_LEARN_EPSILON=0.15, because three
    stacked branches (0.35 cold, 0.40 preferred, then epsilon) each fired
    before the epsilon test."""
    random.seed(20260727)
    pol = _policy(tmp_path, epsilon=0.15)
    _cover(pol, GEN)
    for _ in range(4):
        pol.update("default", 0.9, context=GEN)  # a clear, unique winner

    bucket = context_key(GEN)
    eps = pol.effective_epsilon(bucket)
    trials = 4000
    explored = 0
    for _ in range(trials):
        pol.select(GEN)
        if pol.last_decision["reason"] == "explore":
            explored += 1
    rate = explored / trials
    assert abs(rate - eps) < 0.03, f"exploration {rate:.3f} vs epsilon {eps:.3f}"
    assert rate < 0.25, "still exploring ~45% of the time"


def test_exploration_anneals_with_experience(tmp_path):
    pol = _policy(tmp_path, epsilon=0.15)
    bucket = context_key(GEN)
    _cover(pol, GEN)
    first = pol.effective_epsilon(bucket)
    for _ in range(60):
        pol.update("default", 0.5, context=GEN)
    later = pol.effective_epsilon(bucket)
    assert later < first
    assert first <= 0.15 + 1e-9, "exploration above the configured epsilon"
    assert later >= learning.EPSILON_FLOOR


def test_cold_start_covers_every_arm_before_exploiting(tmp_path):
    pol = _policy(tmp_path, epsilon=0.0)
    picked = set()
    for _ in range(len(STRATEGIES)):
        arm = pol.select(GEN)
        assert pol.last_decision["reason"] == "cover"
        picked.add(arm)
        pol.update(arm, 0.1, context=GEN)
    assert picked == set(STRATEGIES)
    pol.select(GEN)
    assert pol.last_decision["reason"] in ("exploit", "explore")


# --------------------------------------------------------------------------
# Double update / experience.jsonl row count
# --------------------------------------------------------------------------


def test_one_experience_row_per_attempt(monkeypatch, tmp_path):
    """The bandit was updated twice per run from two stale in-memory copies
    (Pipeline.policy and Amethyst.policy), each writing the whole file, and
    experience.jsonl collected three rows per run."""
    exp_path = tmp_path / "experience.jsonl"
    monkeypatch.setattr(learning, "EXP_PATH", exp_path)
    monkeypatch.setenv("ETHER_SANDBOX_RETRY", "1")

    rec = Recorder([0])
    pipe = Pipeline(registry=rec.registry())
    pipe.policy = _policy(tmp_path)
    pipe.run("add two numbers")
    assert exp_path.read_text(encoding="utf-8").strip().count("\n") + 1 == 1

    rec2 = Recorder([1, 0])
    pipe2 = Pipeline(registry=rec2.registry())
    pipe2.policy = _policy(tmp_path)
    pipe2.run("add two numbers")
    rows = [ln for ln in exp_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(rows) == 3, "one row per bandit decision: 1 + 2 attempts"


def test_pipeline_does_not_ask_amethyst_to_learn():
    """`_log(result, learn=True)` is what reached the second BanditPolicy."""
    logged: List[Dict[str, Any]] = []
    rec = Recorder([0])
    reg = rec.registry()

    def _amethyst(r: Envelope) -> ResponseEnvelope:
        logged.append(dict(r.payload.interaction or {}))
        return ResponseEnvelope(
            task_id=r.task_id, source_gem="amethyst", payload=AmethystResponse(status="logged")
        )

    reg.register("amethyst", _Gem("amethyst", _amethyst))
    pipe = Pipeline(registry=reg)
    pipe.policy = StubPolicy(["default"])  # type: ignore[assignment]
    pipe.run("add two numbers")

    assert logged, "the run was never logged"
    assert all(not entry.get("learn") for entry in logged)


def test_real_policy_writes_both_tables_once(tmp_path, monkeypatch):
    monkeypatch.setattr(learning, "EXP_PATH", tmp_path / "experience.jsonl")
    monkeypatch.setenv("ETHER_SANDBOX_RETRY", "1")
    path = tmp_path / "bandit.json"
    rec = Recorder([1, 0])
    pipe = Pipeline(registry=rec.registry())
    pipe.policy = BanditPolicy(path=path)
    result = pipe.run("add two numbers")

    reloaded = BanditPolicy(path=path)
    assert sum(a.pulls for a in reloaded.arms.values()) == 2
    # The scope half of the key depends on the live curriculum tier; what must
    # hold is that the two attempts landed in different *phases*.
    phases = {b.split("|")[0] for b, cs in reloaded.contexts.items() if cs.pulls}
    assert phases == {"gen", "repair_syntax"}
    repair_bucket = next(b for b in reloaded.contexts if b.startswith("repair_syntax"))
    assert reloaded.context_stats(repair_bucket).arm(result.strategy).pulls == 1


# --------------------------------------------------------------------------
# used_burst
# --------------------------------------------------------------------------


def test_local_llama_model_is_not_a_burst(monkeypatch):
    """`"llama" in model_used` marked every run on a local llama-family model
    as a cloud burst and charged it the -0.05 burst penalty."""
    assert _is_burst_model("llama3.1:8b-instruct") is False
    assert _is_burst_model("qwen2.5-coder:32b") is False
    assert _is_burst_model("") is False
    assert _is_burst_model("grok-3") is True
    assert _is_burst_model("burst") is True
    monkeypatch.setenv("ETHER_BURST_MODEL", "grok-4")
    assert _is_burst_model("grok-4") is True
    assert _is_burst_model("grok-3") is False


def test_run_on_a_local_llama_model_is_not_flagged_as_burst():
    rec = Recorder([0], model_used="llama3.1:8b-instruct")
    pipe = Pipeline(registry=rec.registry())
    pipe.policy = StubPolicy(["default"])  # type: ignore[assignment]
    result = pipe.run("add two numbers")
    assert result.used_burst is False

    rec2 = Recorder([0], model_used="grok-3")
    pipe2 = Pipeline(registry=rec2.registry())
    pipe2.policy = StubPolicy(["default"])  # type: ignore[assignment]
    assert pipe2.run("add two numbers").used_burst is True
