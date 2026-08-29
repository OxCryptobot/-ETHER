"""P3: fixture spoilers stay on that fixture. Global prompt does not name merge remainder."""
from __future__ import annotations

from core.mutate_doctrine import BASE, suffix


def test_global_suffix_has_no_fixture_spoilers():
    s = suffix("greeter")
    assert "debit" not in s.lower()
    assert "remainder" not in s.lower()
    assert "list(b)" not in s
    assert "bug_comments" in s


def test_merge_suffix_only_when_merge():
    m = suffix("repo_oracle_merge")
    g = suffix("greeter")
    assert "BOTH remainders" in m
    assert "BOTH remainders" not in g
    assert "BOTH remainders" not in BASE


def test_ledger_suffix_only_when_ledger():
    l = suffix("ledger")
    assert "debit" in l.lower()
    assert "debit" not in suffix("merge").lower() or "Ledger" not in suffix("merge")
    assert "a.debit" not in suffix("topo")
