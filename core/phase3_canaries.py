"""Phase 3 pure canaries — controlled evolution measurement.

Never trains. Never lifts wheels. Never soft-launches.
FAST units must not call Ollama. Set ETHER_LLM_CANARY=1 for that case.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "phase3_canaries.json"


def run_matrix(*, include_llm: bool | None = None) -> Dict[str, Any]:
    if include_llm is None:
        include_llm = (os.getenv("ETHER_LLM_CANARY") or "0").strip() == "1"
    cases: List[Dict[str, Any]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        cases.append({"name": name, "pass": bool(ok), "detail": detail[:140]})

    try:
        from core.agent_state import AgentState

        s = AgentState(thread_id="p3_canary")
        s.objective = "phase3 canary"
        s.hypothesis = "agent_state persists"
        s.training_wheels = True
        path = s.save()
        loaded = AgentState.load("p3_canary")
        add(
            "agent_state_roundtrip",
            loaded is not None
            and loaded.objective == "phase3 canary"
            and loaded.training_wheels is True
            and path.exists(),
            str(path.name),
        )
    except Exception as e:
        add("agent_state_roundtrip", False, str(e))

    try:
        from core.lora_dry_tick import dry_tick

        d = dry_tick(force=True)
        add(
            "lora_dry_only",
            bool(d.get("ok"))
            and d.get("trained") is False
            and d.get("dry_run") is True
            and d.get("adapter_written") is False,
            str(d.get("message") or d.get("doctrine") or "")[:80],
        )
    except Exception as e:
        add("lora_dry_only", False, str(e))

    try:
        from core.critique_plan_wire import wire_latest

        w = wire_latest(limit=8)
        add(
            "critique_plan_wire",
            "n_critiques" in w and w.get("training_wheels") is True,
            f"n={w.get('n_critiques')} replan={w.get('n_replanned')}",
        )
    except Exception as e:
        add("critique_plan_wire", False, str(e))

    try:
        from core.gem_energy import GEMS, publish

        g = publish()
        add(
            "gems_eight",
            len(GEMS) == 8 and len(g.get("gems") or []) == 8,
            ",".join(GEMS),
        )
    except Exception as e:
        add("gems_eight", False, str(e))

    try:
        from core.loop import decide_tool_first_terminal

        ok = decide_tool_first_terminal(enabled=True, done_ok=True, score=1.0)
        fail = decide_tool_first_terminal(enabled=True, done_ok=False, error="max_steps")
        add(
            "tool_first_gate",
            bool(getattr(ok, "ok", False) or getattr(ok, "terminal", False))
            and (
                not getattr(fail, "ok", True)
                or getattr(fail, "terminal", False)
            ),
            f"pass={ok} fail={fail}",
        )
    except Exception as e:
        add("tool_first_gate", False, str(e))

    try:
        from core.phase3_snapshot import build_snapshot

        snap = build_snapshot()
        add(
            "phase3_snapshot",
            bool(snap.get("ok"))
            and snap.get("soft_launch_blocked") is True
            and snap.get("training_wheels") is True,
            f"lora_trained={snap.get('lora_dry_tick', {}).get('trained')}",
        )
    except Exception as e:
        add("phase3_snapshot", False, str(e))

    try:
        from core.loop import loop_runner_enabled
        from core.symbol_index import symbol_index_enabled

        add(
            "flags_default_safe",
            loop_runner_enabled() is False and symbol_index_enabled() is False,
            f"loop={loop_runner_enabled()} symbol={symbol_index_enabled()}",
        )
    except Exception as e:
        add("flags_default_safe", False, str(e))

    if include_llm:
        try:
            from core.multi_llm import warm, chat, latency_stats

            w = warm()
            r = chat(
                [{"role": "user", "content": "Reply with exactly: pong"}],
                lane="fast",
                max_tokens=8,
                temperature=0.0,
            )
            stats = latency_stats()
            ok_llm = (
                bool(w.get("ok"))
                and bool(r.get("ok"))
                and r.get("latency_ms") is not None
                and float(r.get("latency_ms") or 99999) < 120000
            )
            add(
                "multi_llm_latency",
                ok_llm,
                f"warm_ms={w.get('warm_ms')} chat_ms={r.get('latency_ms')} p50={stats.get('p50_ms')}",
            )
        except Exception as e:
            add("multi_llm_latency", False, str(e))
    else:
        add("multi_llm_latency", True, "skipped FAST unit (ETHER_LLM_CANARY!=1)")

    wheels = (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"
    add("wheels_on", wheels, f"wheels={wheels}")

    passed = sum(1 for c in cases if c["pass"])
    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "phase": "3",
        "n": len(cases),
        "passed": passed,
        "ok": passed == len(cases),
        "include_llm": include_llm,
        "cases": cases,
        "soft_launch_blocked": True,
        "note": "FAST default skips Ollama. Set ETHER_LLM_CANARY=1 for multi_llm_latency.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(run_matrix(), indent=2))
