"""Containment tests for the scratch patch loop.

`core/patch_loop.py` is the one path where model-authored output is written
into the real working tree with `git apply` and then executed on the host. It
runs regardless of ETHER_SANDBOX_BACKEND, so the container is no defence here.

Its only guard used to be a substring test for "memory/scratch" anywhere on a
diff header line. An audit bypassed it two ways: a trailing tab comment, and a
git rename header pointing outside scratch. Both are pinned below.
"""

from __future__ import annotations

import pytest

from core.patch_loop import _diff_paths, _safe_paths, maybe_patch_cycle

ESCAPES = {
    "tab_comment_suffix": (
        "--- a/core/pipeline.py\t(memory/scratch)\n"
        "+++ b/core/pipeline.py\t(memory/scratch)\n"
    ),
    "git_rename_out_of_scratch": (
        "diff --git a/memory/scratch/x.py b/tools/persistent/backdoor.py\n"
        "similarity index 100%\n"
        "rename from memory/scratch/x.py\n"
        "rename to tools/persistent/backdoor.py\n"
    ),
    "parent_traversal": (
        "--- a/memory/scratch/../../core/pipeline.py\n"
        "+++ b/memory/scratch/../../core/pipeline.py\n"
    ),
    "absolute_path": "--- a/etc/passwd\n+++ b/etc/passwd\n",
    "conftest_injection": (
        "diff --git a/memory/scratch/a.py b/conftest.py\n"
        "rename from memory/scratch/a.py\n"
        "rename to conftest.py\n"
    ),
    "plain_repo_file": "--- a/core/confidence.py\n+++ b/core/confidence.py\n",
}


@pytest.mark.parametrize("name,diff", sorted(ESCAPES.items()))
def test_escapes_are_rejected(name, diff):
    assert _safe_paths(diff) is False, f"{name} escaped scratch containment"


def test_empty_or_unparseable_diff_is_refused():
    """If no paths can be extracted, containment cannot be verified."""
    assert _safe_paths("") is False
    assert _safe_paths("not a diff at all\n") is False


LEGITIMATE = {
    "simple_scratch_edit": (
        "--- a/memory/scratch/foo.py\n+++ b/memory/scratch/foo.py\n"
    ),
    "new_scratch_file": "--- /dev/null\n+++ b/memory/scratch/new.py\n",
    "git_header_in_scratch": (
        "diff --git a/memory/scratch/x.py b/memory/scratch/x.py\n"
        "--- a/memory/scratch/x.py\n+++ b/memory/scratch/x.py\n"
    ),
}


@pytest.mark.parametrize("name,diff", sorted(LEGITIMATE.items()))
def test_legitimate_scratch_diffs_are_allowed(name, diff):
    assert _safe_paths(diff) is True, f"{name} should be permitted"


def test_rename_targets_are_extracted():
    """The old check never looked at rename/copy headers at all."""
    diff = (
        "diff --git a/memory/scratch/x.py b/tools/persistent/evil.py\n"
        "rename to tools/persistent/evil.py\n"
    )
    assert "tools/persistent/evil.py" in _diff_paths(diff)


def test_patch_loop_is_opt_in(monkeypatch):
    """Host writes must not activate merely because output looks like a diff."""
    monkeypatch.delenv("ETHER_PATCH_LOOP", raising=False)
    diff = "--- a/memory/scratch/foo.py\n+++ b/memory/scratch/foo.py\n"
    report, code = maybe_patch_cycle(diff)
    assert report is None, "patch loop ran without ETHER_PATCH_LOOP=1"
    assert code == diff


def test_no_scratch_tests_is_not_a_pass(monkeypatch, tmp_path):
    """'nothing was verified' must not report ok=True."""
    import core.patch_loop as pl

    monkeypatch.setattr(pl, "SCRATCH", tmp_path)
    result = pl.run_scratch_tests()
    assert result["ok"] is False
    assert result["ran"] is False
