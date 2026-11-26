"""Batch 10 item 7: every batch 10 flag is in docs/FLAGS.md; the rollout is written down."""
from __future__ import annotations

import re
from pathlib import Path

MODULES = ("core/agent/gate_jail.py", "core/agent/mcp_stdio.py", "core/agent/lsp_client.py", "core/agent/swarm.py",
           "core/agent/scouts.py", "core/agent/goal_source.py")


def test_flags_table_lists_every_batch10_flag():
    table = Path("docs/FLAGS.md").read_text(encoding="utf-8")
    flags = set()
    for rel in MODULES:
        flags |= set(re.findall(r"\"(ETHER_[A-Z0-9_]+)\"", Path(rel).read_text(encoding="utf-8")))
    flags -= {"ETHER_ROOT", "ETHER_TEST_STATE_ROOT", "ETHER_SBFL_OUT", "ETHER_SBFL_ROOT", "ETHER_GATE_SANDBOXED", "ETHER_SUPERVISOR",
              "ETHER_JAIL_OK"}
    assert not sorted(f for f in flags if f not in table)


def test_rollout_phases_are_documented():
    for rel in ("docs/FLAGS.md", "docs/BATCH10.md"):
        text = Path(rel).read_text(encoding="utf-8")
        assert "Phase A" in text and "Phase B" in text and "10 %" in text, rel
        assert "ETHER_SWARM_K=2" in text and "ETHER_DEDUP_REPLY=1" in text, rel
