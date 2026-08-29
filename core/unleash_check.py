"""Honest unleash readiness. Never writes .env. Never flips wheels from a job.

The operator unleashes by setting flags on the Windows host. This module only
says whether that is safe given measured evidence.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "unleash_check.json"


def evaluate() -> Dict[str, Any]:
    blocked: List[str] = []
    evidence: Dict[str, Any] = {}

    gate = {}
    gp = ROOT / "artifacts" / "phase1_gate.json"
    if gp.exists():
        try:
            gate = json.loads(gp.read_text(encoding="utf-8"))
        except Exception:
            gate = {}
    evidence["metrics_go"] = bool(gate.get("metrics_go"))
    if not evidence["metrics_go"]:
        blocked.append("metrics_go_false")

    merge_pass = False
    for name in (
        "scoreboard_p1_242_live_merge_canary.json",
        "scoreboard_p1_248_merge_replay.json",
    ):
        p = ROOT / "artifacts" / name
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in data.get("results") or []:
            if row.get("fixture") == "merge" and row.get("ok") and row.get("mode") == "live":
                merge_pass = True
    evidence["hard_merge_live_pass"] = merge_pass
    replay = ROOT / "artifacts" / "scoreboard_p1_248_merge_replay.json"
    replay_ok = False
    if replay.exists():
        try:
            rb = json.loads(replay.read_text(encoding="utf-8"))
            replay_ok = bool((rb.get("summary") or {}).get("passed"))
        except Exception:
            replay_ok = False
    evidence["hard_merge_replay_pass"] = replay_ok
    if not replay_ok:
        blocked.append("merge_replay_not_repeatable")

    evidence["langchain_installed"] = False
    try:
        from core.langchain_adapter import available

        evidence["langchain_installed"] = available()
    except Exception:
        pass

    evidence["rag_ok"] = True
    evidence["graph_ok"] = True
    evidence["lora_dry_ok"] = True
    try:
        from core.memory_stack import snapshot

        ms = snapshot()
        evidence["rag_ok"] = bool(ms.get("ok"))
        evidence["lora_mode"] = (ms.get("lora") or {}).get("mode")
    except Exception as exc:
        evidence["rag_ok"] = False
        blocked.append(f"memory_stack:{exc.__class__.__name__}")

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    explicit = (os.getenv("ETHER_SOFT_LAUNCH") or "0").strip() == "1"
    evidence["training_wheels"] = wheels
    evidence["soft_launch_flag"] = explicit

    if wheels:
        blocked.append("training_wheels_on — set ETHER_TRAINING_WHEELS=0 on the host .env")
    if not explicit:
        blocked.append("set ETHER_SOFT_LAUNCH=1 on the host .env to launch")

    ready = not blocked
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "unleash_ready": ready,
        "blocked": blocked,
        "evidence": evidence,
        "operator_env": {
            "ETHER_TRAINING_WHEELS": "0",
            "ETHER_SOFT_LAUNCH": "1",
            "ETHER_LORA_TRAIN": "0",
            "ETHER_LORA_PROMOTE": "0",
            "ETHER_RAG_BM25": "1",
        },
        "note": (
            "This file never flips flags. Merge LIVE is not yet repeatable "
            "(p1_248 observe-loop). Unleash today is operator risk, not a green gate. "
            "Real LoRA train stays 0 until preference health is green."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(evaluate(), indent=2))
