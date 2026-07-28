"""The health gate and the bench guardian must fail CLOSED.

Every test here pins a way the system used to declare itself healthy — or keep
promote/fabricate unfrozen — on evidence that did not exist:

  * the regression baseline ratcheted DOWN one tolerated step at a time
    (0.95 -> 0.86 -> 0.77 -> ... -> 0.41 never froze),
  * the baseline was pinned to the first bench ever seen and never raised, so a
    system that grew 0.42 -> 0.95 could fall back to 0.43 undetected,
  * a missing bench, an unstamped bench, and a 400-day-old bench all read as
    "ok",
  * timestamps in the FUTURE produced stale_hours: -8760 and healthy: True,
  * a bench with no pass_rate key, and a quiz scoring 0.0, were both healthy,
  * health read a CACHED guardian.json, so the verdict depended on whether
    something else had called is_frozen() first,
  * recovery had no attempt counter, no backoff and no reachability probe, so
    an Ollama outage cost two 30-minute LLM timeouts per cycle, forever.

No test in this file may invoke the model: recovery is exercised with `_run`
replaced by a recorder.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

import core.autonomy as autonomy
import core.bench_guardian as bg
import core.curriculum as cur
import core.health_metric as hm


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _bench(rate, hours_ago: float = 1.0, n: int = 10) -> dict:
    row = {"n": n, "duration_s": 1.0, "timestamp": _iso(hours_ago)}
    if rate is not None:
        row["pass_rate"] = rate
    return row


@pytest.fixture()
def guard(tmp_path, monkeypatch):
    """Redirect every guardian/health file into a temp dir."""
    bench_dir = tmp_path / "bench"
    quiz_dir = tmp_path / "quiz"
    bench_dir.mkdir()
    quiz_dir.mkdir()

    monkeypatch.setattr(bg, "BENCH_LATEST", bench_dir / "latest.json")
    monkeypatch.setattr(bg, "BASELINE_PATH", bench_dir / "baseline.json")
    monkeypatch.setattr(bg, "GUARD_PATH", bench_dir / "guardian.json")
    monkeypatch.setattr(hm, "BENCH_DIR", bench_dir)
    monkeypatch.setattr(hm, "QUIZ_DIR", quiz_dir)
    monkeypatch.setattr(hm, "HEALTH_PATH", bench_dir / "health.json")
    for var in (
        "ETHER_BENCH_GUARDIAN",
        "ETHER_BENCH_MIN_PASS",
        "ETHER_BENCH_DROP_TOL",
        "ETHER_BENCH_MAX_AGE_H",
        "ETHER_QUIZ_MIN_PASS",
        "ETHER_GUARDIAN_AUTO_BASELINE",
    ):
        monkeypatch.delenv(var, raising=False)

    class _Dirs:
        bench = bench_dir
        quiz = quiz_dir

        @staticmethod
        def write_bench(rate, hours_ago: float = 1.0, **extra) -> dict:
            payload = {**_bench(rate, hours_ago), **extra}
            (bench_dir / "latest.json").write_text(json.dumps(payload), encoding="utf-8")
            return payload

        @staticmethod
        def write_quiz(rate, hours_ago: float = 1.0, **extra) -> dict:
            payload = {"n": 5, "timestamp": _iso(hours_ago), **extra}
            if rate is not None:
                payload["pass_rate"] = rate
            (quiz_dir / "latest.json").write_text(json.dumps(payload), encoding="utf-8")
            return payload

        @staticmethod
        def baseline(mode: str = "full") -> dict:
            # Baselines are keyed per bench mode now, because `--fast` runs only
            # the five easiest tasks and must not pin the full bench's bar.
            path = bench_dir / "baseline.json"
            if not path.exists():
                return {}
            doc = json.loads(path.read_text(encoding="utf-8"))
            return (doc.get("modes") or {}).get(mode, {})

    return _Dirs


# --------------------------------------------------------------------------
# 1. the baseline ratchet
# --------------------------------------------------------------------------


def test_baseline_is_raised_when_the_system_improves(guard):
    """A system that grows 0.42 -> 0.95 must be held to 0.95."""
    bg.ensure_baseline(_bench(0.42))
    assert guard.baseline()["pass_rate"] == pytest.approx(0.42)

    bg.ensure_baseline(_bench(0.95))
    assert guard.baseline()["pass_rate"] == pytest.approx(0.95)

    # Falling back near the original level is now a detected regression.
    guard.write_bench(0.43)
    decision = bg.evaluate()
    assert decision["frozen"] is True
    assert "regression" in decision["reason"]
    assert guard.baseline()["pass_rate"] == pytest.approx(0.95)


def test_evaluate_does_not_lower_the_baseline_it_reads(guard):
    guard.write_bench(0.90)
    bg.evaluate()
    guard.write_bench(0.85)
    bg.evaluate()
    assert guard.baseline()["pass_rate"] == pytest.approx(0.90)


def test_recovery_baseline_cannot_ratchet_the_guardian_down_to_nothing(guard):
    """The 0.95 -> 0.86 -> 0.77 -> ... -> 0.41 walk must freeze, not drift.

    Each step is individually inside the 0.10 drop tolerance, which is exactly
    why rewriting the baseline to the current rate defeated the guardian.
    """
    guard.write_bench(0.95)
    bg.evaluate()
    assert guard.baseline()["pass_rate"] == pytest.approx(0.95)

    froze_at = None
    verdicts = {}
    for rate in (0.86, 0.77, 0.68, 0.59, 0.50, 0.41):
        guard.write_bench(rate)
        autonomy.maybe_reset_baseline_on_recovery()
        decision = bg.evaluate()
        verdicts[rate] = decision["frozen"]
        if decision["frozen"] and froze_at is None:
            froze_at = rate

    assert guard.baseline()["pass_rate"] == pytest.approx(0.95), "baseline drifted down"
    # 0.95 -> 0.86 is a real 0.09 drop, inside the 0.10 tolerance. Everything
    # below it is measured against 0.95, not against the previous step.
    assert froze_at == 0.77, f"guardian froze late (first freeze at {froze_at})"
    assert all(verdicts[r] for r in (0.77, 0.68, 0.59, 0.50, 0.41)), verdicts


def test_recovery_still_ratchets_the_baseline_up(guard):
    guard.write_bench(0.60)
    bg.evaluate()
    guard.write_bench(0.80)
    out = autonomy.maybe_reset_baseline_on_recovery()
    assert out.get("raised") is True
    assert guard.baseline()["pass_rate"] == pytest.approx(0.80)


def test_lowering_the_baseline_needs_an_explicit_operator_action(guard):
    guard.write_bench(0.90)
    bg.evaluate()

    refused = bg.set_baseline(0.50, reason="oops")
    assert refused["ok"] is False
    assert guard.baseline()["pass_rate"] == pytest.approx(0.90)

    allowed = bg.set_baseline(0.50, reason="hardware change", allow_lower=True)
    assert allowed["ok"] is True
    assert guard.baseline()["pass_rate"] == pytest.approx(0.50)


# --------------------------------------------------------------------------
# 2. the guardian fails closed
# --------------------------------------------------------------------------


def test_no_bench_at_all_freezes(guard):
    """The repo's actual state today: no bench, and is_frozen() said False."""
    decision = bg.evaluate()
    assert decision["frozen"] is True
    assert decision["ok"] is False
    assert bg.is_frozen() is True


def test_a_400_day_old_bench_freezes_however_good_it_looked(guard):
    guard.write_bench(0.99, hours_ago=400 * 24)
    decision = bg.evaluate()
    assert decision["frozen"] is True
    assert "stale" in decision["reason"]


def test_a_bench_with_no_timestamp_freezes(guard):
    (guard.bench / "latest.json").write_text(json.dumps({"pass_rate": 0.99, "n": 10}), encoding="utf-8")
    decision = bg.evaluate()
    assert decision["frozen"] is True
    assert "timestamp" in decision["reason"]


def test_a_future_dated_bench_freezes(guard):
    guard.write_bench(0.99, hours_ago=-24 * 365)
    decision = bg.evaluate()
    assert decision["frozen"] is True
    assert "future" in decision["reason"]


def test_a_bench_without_a_pass_rate_freezes(guard):
    guard.write_bench(None)
    decision = bg.evaluate()
    assert decision["frozen"] is True
    assert "pass_rate" in decision["reason"]


def test_a_fresh_passing_bench_is_not_frozen(guard):
    guard.write_bench(0.85)
    decision = bg.evaluate()
    assert decision["frozen"] is False
    assert decision["reason"] == "healthy"


def test_guardian_disabled_is_still_an_explicit_opt_out(guard, monkeypatch):
    monkeypatch.setenv("ETHER_BENCH_GUARDIAN", "0")
    assert bg.evaluate()["reason"] == "guardian_disabled"


# --------------------------------------------------------------------------
# 3. health fails closed on absurd input
# --------------------------------------------------------------------------


def test_healthy_only_when_bench_and_quiz_are_fresh_and_scored(guard):
    guard.write_bench(0.85)
    guard.write_quiz(0.8)
    health = hm.compute_health()
    assert health["healthy"] is True
    assert health["unhealthy_reasons"] == []


def test_a_bench_timestamp_in_the_future_is_not_health(guard):
    guard.write_bench(0.85, hours_ago=-24 * 365)
    guard.write_quiz(0.8)
    health = hm.compute_health()
    assert health["healthy"] is False
    assert health["bench_stale"] is True
    assert any("future" in r for r in health["unhealthy_reasons"])


def test_a_quiz_timestamp_in_the_future_is_not_health(guard):
    guard.write_bench(0.85)
    guard.write_quiz(0.8, hours_ago=-24 * 365)
    health = hm.compute_health()
    assert health["healthy"] is False
    assert any("future" in r for r in health["unhealthy_reasons"])


def test_a_bench_missing_pass_rate_cannot_inherit_yesterdays_score(guard):
    (guard.bench / "bench_0001.json").write_text(
        json.dumps({"pass_rate": 0.9, "duration_s": 1.0}), encoding="utf-8"
    )
    guard.write_bench(None)
    guard.write_quiz(0.8)
    health = hm.compute_health()
    assert health["healthy"] is False
    assert "bench_pass_rate_missing_or_invalid" in health["unhealthy_reasons"]


def test_a_quiz_that_scored_zero_is_not_health(guard):
    guard.write_bench(0.85)
    guard.write_quiz(0.0)
    health = hm.compute_health()
    assert health["healthy"] is False
    assert any("quiz_pass_rate_low" in r for r in health["unhealthy_reasons"])


def test_a_quiz_with_no_pass_rate_is_not_health(guard):
    guard.write_bench(0.85)
    guard.write_quiz(None)
    health = hm.compute_health()
    assert health["healthy"] is False
    assert "quiz_pass_rate_missing_or_invalid" in health["unhealthy_reasons"]


def test_an_out_of_range_pass_rate_is_not_health(guard):
    guard.write_bench(7.5)
    guard.write_quiz(0.8)
    health = hm.compute_health()
    assert health["healthy"] is False


def test_health_asks_the_guardian_instead_of_reading_a_cached_verdict(guard):
    """Health used to depend on who called is_frozen() first."""
    # Establish a 0.95 baseline, then regress hard.
    guard.write_bench(0.95)
    bg.evaluate()
    guard.write_bench(0.55)
    guard.write_quiz(0.8)

    # A cached file claiming everything is fine must not be believed.
    (guard.bench / "guardian.json").write_text(
        json.dumps({"ok": True, "frozen": False, "reason": "stale cache"}), encoding="utf-8"
    )
    health = hm.compute_health()
    assert health["guardian_frozen"] is True
    assert health["healthy"] is False

    # And the answer does not change based on evaluation order.
    (guard.bench / "guardian.json").write_text(
        json.dumps({"ok": True, "frozen": False, "reason": "stale cache"}), encoding="utf-8"
    )
    bg.is_frozen()
    assert hm.compute_health()["guardian_frozen"] is True


def test_declare_healthy_reports_the_same_verdict_as_compute_health(guard):
    guard.write_bench(0.85)
    guard.write_quiz(0.8)
    assert hm.declare_healthy()["healthy"] is hm.compute_health()["healthy"]
    guard.write_bench(0.1)
    assert hm.declare_healthy()["healthy"] is False


# --------------------------------------------------------------------------
# 4. recovery is bounded and precondition-gated
# --------------------------------------------------------------------------


@pytest.fixture()
def recovery(tmp_path, monkeypatch, guard):
    """recovery_cycle with every subprocess replaced by a recorder."""
    monkeypatch.setattr(autonomy, "LOG_DIR", tmp_path / "daemon")
    monkeypatch.setattr(autonomy, "AUTONOMY_LOG", tmp_path / "daemon" / "autonomy.jsonl")
    monkeypatch.setattr(autonomy, "RECOVERY_STATE", tmp_path / "daemon" / "recovery_state.json")
    monkeypatch.setattr(autonomy, "seed_queue_if_empty", lambda: {"seeded": 0})
    monkeypatch.setattr(autonomy, "maybe_reset_baseline_on_recovery", lambda: {"skipped": True})
    monkeypatch.setattr(autonomy, "reevaluate_guardian", lambda: {"frozen": True})
    for var in (
        "ETHER_RECOVERY_MAX_ATTEMPTS",
        "ETHER_RECOVERY_BACKOFF_S",
        "ETHER_RECOVERY_MAX_BACKOFF_S",
        "ETHER_RECOVERY_BUDGET_S",
        "ETHER_RECOVERY_STEP_TIMEOUT_S",
    ):
        monkeypatch.delenv(var, raising=False)

    calls: list = []

    def _fake_run(args, timeout: int = 1800):
        calls.append({"args": args, "timeout": timeout})
        return {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(autonomy, "_run", _fake_run)
    return calls


def test_recovery_refuses_to_spend_two_llm_budgets_when_ollama_is_down(recovery, monkeypatch):
    monkeypatch.setattr(autonomy, "ollama_reachable", lambda timeout=1.0: False)
    report = autonomy.recovery_cycle()
    assert report["skipped"] is True
    assert report["reason"].startswith("ollama_unreachable")
    assert recovery == [], "spawned model work with the model server down"


def test_recovery_backs_off_instead_of_running_back_to_back(recovery, monkeypatch, guard):
    monkeypatch.setattr(autonomy, "ollama_reachable", lambda timeout=1.0: True)
    first = autonomy.recovery_cycle()
    assert not first.get("skipped")
    assert first["healthy"]["healthy"] is False  # nothing healed it
    assert first["attempts"] == 1
    assert first["retry_in_s"] >= autonomy.DEFAULT_BACKOFF_S

    second = autonomy.recovery_cycle()
    assert second["skipped"] is True
    assert second["gate"]["reason"] == "backoff"
    assert second["gate"]["retry_in_s"] > 0


def test_recovery_backoff_grows_and_then_stops_retrying(recovery, monkeypatch):
    monkeypatch.setattr(autonomy, "ollama_reachable", lambda timeout=1.0: True)
    assert autonomy.recovery_backoff_s(1) < autonomy.recovery_backoff_s(3)
    assert autonomy.recovery_backoff_s(50) <= autonomy.DEFAULT_MAX_BACKOFF_S

    monkeypatch.setenv("ETHER_RECOVERY_BACKOFF_S", "0")
    monkeypatch.setenv("ETHER_RECOVERY_MAX_ATTEMPTS", "3")
    for _ in range(3):
        assert not autonomy.recovery_cycle().get("skipped")
    exhausted = autonomy.recovery_cycle()
    assert exhausted["skipped"] is True
    assert exhausted["gate"]["reason"] == "max_attempts_exhausted"

    autonomy.reset_recovery_backoff()
    assert autonomy.recovery_ready()["ready"] is True


def test_a_healed_recovery_clears_the_attempt_counter(recovery, monkeypatch, guard):
    monkeypatch.setattr(autonomy, "ollama_reachable", lambda timeout=1.0: True)
    guard.write_bench(0.85)
    guard.write_quiz(0.8)
    report = autonomy.recovery_cycle()
    assert report["healthy"]["healthy"] is True
    assert report["attempts"] == 0
    assert autonomy.recovery_ready()["ready"] is True


def test_one_recovery_cannot_outlast_the_callers_cooldown(recovery, monkeypatch):
    """Its own step timeouts used to sum to 3720s against an 1800s cooldown.

    The daemon stamps that cooldown BEFORE the run, so a recovery slower than
    the cooldown makes the next one immediately eligible: ~100% duty cycle on a
    shared GPU.
    """
    daemon_cooldown = 1800
    assert autonomy.DEFAULT_BUDGET_S < daemon_cooldown

    monkeypatch.setattr(autonomy, "ollama_reachable", lambda timeout=1.0: True)
    autonomy.recovery_cycle()
    assert sum(c["timeout"] for c in recovery) <= autonomy.DEFAULT_BUDGET_S
    for call in recovery:
        assert call["timeout"] <= autonomy.DEFAULT_STEP_TIMEOUT_S


def test_ollama_reachability_probe_reads_the_configured_endpoint(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://10.0.0.5:11500")
    assert autonomy.ollama_endpoint() == ("10.0.0.5", 11500)
    monkeypatch.delenv("OLLAMA_BASE_URL")
    host, port = autonomy.ollama_endpoint()
    assert port == 11434


# --------------------------------------------------------------------------
# 5. the empty-objective fallback must not hand over the answer
# --------------------------------------------------------------------------


def test_empty_objective_fallback_does_not_leak_its_own_answer():
    objective = autonomy.ensure_assert_objective("")
    problems = cur.check_task_leakage(
        {"id": "fallback", "objective": objective, "holdout_test": "assert is_even(4) is True\n"}
    )
    assert problems == [], problems
    assert "return n % 2" not in objective
    assert not any(line.strip().startswith("assert ") for line in objective.splitlines())


# --------------------------------------------------------------------------
# 6. curriculum sync must use gated evidence and leave record_outcome alone
# --------------------------------------------------------------------------


@pytest.fixture()
def vault(tmp_path, monkeypatch):
    cur_dir = tmp_path / "curriculum"
    exp_dir = tmp_path / "experience"
    cur_dir.mkdir()
    exp_dir.mkdir()
    monkeypatch.setattr(cur, "CUR_DIR", cur_dir)
    monkeypatch.setattr(cur, "STATE_PATH", cur_dir / "state.json")
    monkeypatch.setattr(cur, "MINED_PATH", cur_dir / "mined_tasks.json")
    monkeypatch.setattr(cur, "SCRATCH_PATH", cur_dir / "scratch_tier.json")
    monkeypatch.setattr(cur, "PASS_PATH", exp_dir / "pass.jsonl")
    monkeypatch.setattr(cur, "FAIL_PATH", exp_dir / "fail.jsonl")
    monkeypatch.setattr(cur, "load_tiers", lambda: [{"name": f"t{i}"} for i in range(4)])
    for var in ("ETHER_CURRICULUM_PROMOTE_AFTER", "ETHER_CURRICULUM_DEMOTE_AFTER"):
        monkeypatch.delenv(var, raising=False)

    class _Vault:
        @staticmethod
        def passes(n: int, **fields) -> None:
            row = {"success": True, "confidence": 0.95, **fields}
            with (exp_dir / "pass.jsonl").open("a", encoding="utf-8") as f:
                for i in range(n):
                    f.write(json.dumps({**row, "timestamp": _iso(10 - i)}) + "\n")

        @staticmethod
        def state() -> dict:
            path = cur_dir / "state.json"
            return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    return _Vault


def test_sync_will_not_promote_on_ungated_evidence(vault):
    """Three exit-zero rows with no tests are not three verified wins."""
    vault.passes(3, total_tests=0, verification_score=0.0)
    state = cur.sync_from_vault()
    assert state["tier"] == 0
    assert state.get("synced_wins") == 0


def test_sync_will_not_promote_on_a_low_verification_score(vault):
    vault.passes(3, total_tests=2, verification_score=0.3)
    assert cur.sync_from_vault()["tier"] == 0


def test_sync_will_not_promote_when_the_holdout_failed(vault):
    vault.passes(3, total_tests=2, verification_score=1.0, holdout_ok=False)
    assert cur.sync_from_vault()["tier"] == 0


def test_sync_promotes_on_verified_evidence(vault):
    vault.passes(3, total_tests=2, verification_score=1.0, holdout_ok=True)
    state = cur.sync_from_vault()
    assert state["tier"] == 1
    assert state["last_event"] == "synced_promoted_to_1"


def test_sync_does_not_clobber_the_streak_record_outcome_is_building(vault):
    """The verified 3-win streak could never accumulate.

    sample_objective() calls sync_from_vault() on every task, and sync used to
    overwrite state["wins"]/["losses"] from its own ungated count — so the
    guarded promotion path in record_outcome() was effectively dead code.
    """
    cur.record_outcome(True, task_id="a", verification_score=1.0, total_tests=2)
    cur.record_outcome(True, task_id="b", verification_score=1.0, total_tests=2)
    assert vault.state()["wins"] == 2

    # Ungated vault noise arrives (exit-zero, no tests).
    vault.passes(2, total_tests=0, verification_score=0.0)
    cur.sync_from_vault()
    assert vault.state()["wins"] == 2, "sync erased record_outcome's verified streak"

    state = cur.record_outcome(True, task_id="c", verification_score=1.0, total_tests=2)
    assert state["tier"] == 1, "the third verified win did not promote"


# --------------------------------------------------------------------------
# 7. ledger
# --------------------------------------------------------------------------


def test_p50_is_the_median_not_the_upper_middle_sample(tmp_path, monkeypatch):
    import core.ledger as ledger

    runs = tmp_path / "runs"
    runs.mkdir()
    for i, ms in enumerate((100.0, 200.0, 300.0, 400.0)):
        (runs / f"r{i}.json").write_text(
            json.dumps({"stages": [{"stage": "s", "duration_ms": ms}]}), encoding="utf-8"
        )
    monkeypatch.setattr(ledger, "RUNS", runs)
    monkeypatch.setattr(ledger, "OUT", tmp_path / "ledger" / "latest.json")
    monkeypatch.setattr(ledger, "BURST_LEDGER", tmp_path / "burst" / "ledger.jsonl")

    out = ledger.compute_ledger()
    assert out["avg_run_ms"] == pytest.approx(250.0)
    assert out["p50_run_ms"] == pytest.approx(250.0)


# --------------------------------------------------------------------------
# Per-mode baselines
# --------------------------------------------------------------------------


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _guard(monkeypatch, tmp_path):
    """Point the guardian at a temp bench dir."""
    import core.bench_guardian as g

    monkeypatch.setattr(g, "BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(g, "BENCH_LATEST", tmp_path / "latest.json")
    monkeypatch.setattr(g, "GUARD_PATH", tmp_path / "guardian.json")
    return g


def test_fast_bench_cannot_repin_the_full_baseline(monkeypatch, tmp_path):
    """`--fast` is only the five easiest tasks.

    It used to write the shared baseline, pinning an optimistic rate the full
    bench structurally cannot meet — observed as baseline 1.0 (n=5) versus a
    full result of 0.933 (n=15), leaving 0.033 before a spurious freeze.
    """
    g = _guard(monkeypatch, tmp_path)
    g.ensure_baseline({"pass_rate": 0.933, "n": 15, "mode": "full"})
    g.ensure_baseline({"pass_rate": 1.0, "n": 5, "mode": "fast"})

    assert g.load_baseline("full")["pass_rate"] == 0.933
    assert g.load_baseline("fast")["pass_rate"] == 1.0


def test_full_bench_is_compared_against_its_own_baseline(monkeypatch, tmp_path):
    """A full result at its own baseline must not read as a regression."""
    import json

    g = _guard(monkeypatch, tmp_path)
    g.ensure_baseline({"pass_rate": 1.0, "n": 5, "mode": "fast"})
    g.ensure_baseline({"pass_rate": 0.933, "n": 15, "mode": "full"})

    g.BENCH_LATEST.write_text(
        json.dumps(
            {"pass_rate": 0.933, "n": 15, "mode": "full", "timestamp": _now_iso()}
        ),
        encoding="utf-8",
    )
    verdict = g.evaluate()
    assert verdict["baseline"] == 0.933, verdict
    assert verdict["frozen"] is False, verdict


def test_a_genuine_two_task_regression_still_freezes(monkeypatch, tmp_path):
    """The brake must still work: 15 tasks, 2 failures beyond baseline."""
    import json

    g = _guard(monkeypatch, tmp_path)
    g.ensure_baseline({"pass_rate": 0.933, "n": 15, "mode": "full"})
    g.BENCH_LATEST.write_text(
        json.dumps(
            {"pass_rate": 0.800, "n": 15, "mode": "full", "timestamp": _now_iso()}
        ),
        encoding="utf-8",
    )
    verdict = g.evaluate()
    assert verdict["frozen"] is True, verdict


def test_legacy_flat_baseline_is_migrated(monkeypatch, tmp_path):
    import json

    g = _guard(monkeypatch, tmp_path)
    g.BASELINE_PATH.write_text(json.dumps({"pass_rate": 0.5, "n": 9}), encoding="utf-8")
    assert g.load_baseline("full")["pass_rate"] == 0.5
