"""Batch 9 item 8: one flags table covers every batch 9 flag; operational docs no longer send people to :8787."""
from __future__ import annotations

import re
from pathlib import Path

BATCH9_MODULES = ("core/agent/gate_sandbox.py", "core/agent/planted.py", "core/agent/pillars.py", "core/agent/goal_source.py",
                  "scripts/host_signals.py", "scripts/origin_publish.py", "dashboard/app.py", "core/agent/tree_guard.py")
OPERATIONAL_DOCS = ("DAEMON.md", "OPS.md", "RECOVERY.md", "ONBOARDING.md", "docs/HOST_AGENT.md", "docs/PHASE_G.md")


def test_flags_table_lists_every_batch9_flag():
    table = Path("docs/FLAGS.md").read_text(encoding="utf-8")
    flags = set()
    for rel in BATCH9_MODULES:
        flags |= set(re.findall(r"\"(ETHER_[A-Z0-9_]+)\"", Path(rel).read_text(encoding="utf-8")))
    flags -= {"ETHER_ROOT", "ETHER_TEST_STATE_ROOT", "ETHER_SUPERVISOR", "ETHER_SBFL_OUT", "ETHER_SBFL_ROOT",
              "ETHER_GATE_SANDBOXED"}
    missing = sorted(f for f in flags if f not in table)
    assert not missing, missing


def test_operational_docs_do_not_point_at_the_retired_dashboard():
    for rel in OPERATIONAL_DOCS:
        assert "127.0.0.1:8787" not in Path(rel).read_text(encoding="utf-8"), rel


def test_status_names_the_open_owner_decisions_and_product_md_is_untouched():
    status = Path("STATUS.md").read_text(encoding="utf-8")
    assert "Swarm vs `PRODUCT.md`" in status and "2026-11-22" in status
    assert "a swarm" in Path("PRODUCT.md").read_text(encoding="utf-8")  # owner decision: unchanged
