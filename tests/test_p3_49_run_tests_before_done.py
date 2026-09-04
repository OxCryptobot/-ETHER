"""p3_49: observe kill must not drop a mutate, and must run_tests after mutate."""
from core.observe_breaker import rewrite


def test_kill_does_not_override_replace_once():
    forced = rewrite("replace_once", 5, mutated=True)
    assert forced is None


def test_kill_does_not_override_run_tests():
    assert rewrite("run_tests", 9, mutated=True) is None


def test_kill_after_mutate_routes_to_run_tests():
    forced = rewrite("read_file", 5, mutated=True)
    assert forced is not None
    assert forced["tool"] == "run_tests"


def test_kill_without_mutate_still_done():
    forced = rewrite("read_file", 5, mutated=False)
    assert forced is not None
    assert forced["tool"] == "done"


def test_mid_streak_observe_still_bug_comments():
    forced = rewrite("read_file", 3, mutated=False)
    assert forced is not None
    assert forced["tool"] == "bug_comments"
