"""Eligible-set rates — easy allowlist only, sentinels excluded.

2026-08-28: stop all-time padding. Eligible LIVE KPI is greeter+wallet
rows with a real result. Merge/hard stays out until a critique lands.
Does not lift wheels. Does not enqueue LIVE.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
OUT = ROOT / "artifacts" / "eligible_rates.json"
TIMEOUT_FLOOR_S = float(os.getenv("ETHER_TIMEOUT_FLOOR_S", "120"))
WINDOW_N = int(os.getenv("ETHER_ELIGIBLE_WINDOW_N", "80"))
ALLOW = ("greeter", "wallet")


def _deny() -> Set[str]:
    try:
        from core.live_fixture_policy import deny_set

        return {d.lower() for d in deny_set() if d}
    except Exception:
        return {"ledger", "lru", "topo", "intervals", "pipeline_ledger", "merge"}


def _fixture_name(row: Dict[str, Any]) -> str:
    for k in ("fixture", "name"):
        v = str(row.get(k) or "").strip().lower()
        if v:
            return v
    hay = " ".join(str(row.get(k) or "") for k in ("id", "strategy", "note")).lower()
    for name in ALLOW + ("merge", "ledger", "lru", "topo", "intervals"):
        if name in hay:
            return name
    return ""


def _is_sentinel(row: Dict[str, Any]) -> bool:
    note = str(row.get("note") or "").lower()
    if "sentinel" in note:
        return True
    if row.get("partial") is True and not row.get("ok") and not row.get("tools"):
        return True
    if row.get("ok") is None and not row.get("tools") and not row.get("failure_type"):
        return True
    return False


def _is_denied(row: Dict[str, Any], denied: Set[str]) -> bool:
    fx = _fixture_name(row)
    if fx in denied:
        return True
    hay = " ".join(
        str(row.get(k) or "") for k in ("fixture", "name", "id", "strategy", "note")
    ).lower()
    return any(d and d in hay for d in denied)


def _is_timeout(row: Dict[str, Any], classified: Dict[str, Any]) -> bool:
    if classified.get("timeout"):
        return True
    ftype = str(row.get("failure_type") or "").lower()
    if "timeout" in ftype or "budget_exhaust" in ftype:
        return True
    try:
        dur = float(row.get("duration_s") or row.get("elapsed_s") or 0)
        if dur >= TIMEOUT_FLOOR_S and not classified.get("ok"):
            return True
    except Exception:
        pass
    return False


def _is_allowlisted(row: Dict[str, Any]) -> bool:
    return _fixture_name(row) in ALLOW


def compute() -> Dict[str, Any]:
    from core.honest_live import classify_row, collect_scoreboard_rows

    denied = _deny()
    rows = collect_scoreboard_rows()
    live_raw = 0
    live_eligible = 0
    timeout_raw = 0
    timeout_eligible = 0
    honest_eligible = 0
    ok_eligible = 0
    denied_live_n = 0
    sentinel_n = 0
    eligible_seq: List[Tuple[float, bool, bool, bool]] = []

    for r in rows:
        c = classify_row(r)
        if not c.get("live"):
            continue
        live_raw += 1
        if _is_sentinel(r):
            sentinel_n += 1
            continue
        is_to = _is_timeout(r, c)
        if is_to:
            timeout_raw += 1
        if _is_denied(r, denied) or not _is_allowlisted(r):
            denied_live_n += 1
            continue
        live_eligible += 1
        if is_to:
            timeout_eligible += 1
        if c.get("ok"):
            ok_eligible += 1
        if c.get("honest"):
            honest_eligible += 1
        mtime = float(r.get("_mtime") or 0.0)
        eligible_seq.append((mtime, bool(c.get("honest")), bool(c.get("ok")), is_to))

    def rate(n: int, d: int) -> Optional[float]:
        if d <= 0:
            return None
        return round(n / d, 4)

    eligible_seq.sort(key=lambda t: t[0], reverse=True)
    window = eligible_seq[:WINDOW_N]
    win_n = len(window)
    win_honest = sum(1 for t in window if t[1])
    win_to = sum(1 for t in window if t[3])

    raw_to = rate(timeout_raw, live_raw)
    elig_to = rate(timeout_eligible, live_eligible)
    elig_honest = rate(honest_eligible, live_eligible)
    win_honest_rate = rate(win_honest, win_n)
    win_to_rate = rate(win_to, win_n)

    if win_n >= 50 and win_honest_rate is not None:
        gate_honest = win_honest_rate
        gate_to = win_to_rate
        gate_n = win_n
        gate_src = f"window_{WINDOW_N}"
    else:
        gate_honest = elig_honest
        gate_to = elig_to
        gate_n = live_eligible
        gate_src = "allowlist_all"

    timeout_eligible_ok = gate_to is not None and gate_to < 0.25
    honest_eligible_ok = gate_honest is not None and gate_honest >= 0.99

    payload: Dict[str, Any] = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "denied": sorted(denied),
        "allowlist": list(ALLOW),
        "live_raw_n": live_raw,
        "live_eligible_n": gate_n,
        "live_eligible_all_n": live_eligible,
        "denied_live_n": denied_live_n,
        "sentinel_skipped_n": sentinel_n,
        "timeout_raw_n": timeout_raw,
        "timeout_eligible_n": timeout_eligible,
        "timeout_rate_raw": raw_to,
        "timeout_rate_eligible": gate_to,
        "honest_eligible_n": win_honest if gate_src.startswith("window") else honest_eligible,
        "ok_eligible_n": ok_eligible,
        "honest_rate_eligible": gate_honest,
        "honest_rate_allowlist_all": elig_honest,
        "window_n": win_n,
        "window_honest_rate": win_honest_rate,
        "gate_source": gate_src,
        "target_timeout": 0.25,
        "target_honest": 0.99,
        "timeout_eligible_ok": timeout_eligible_ok,
        "honest_eligible_ok": honest_eligible_ok,
        "metrics_ok": bool(timeout_eligible_ok and honest_eligible_ok and gate_n > 0),
        "wheels_must_stay_on": True,
        "soft_launch_blocked": True,
        "publish_ok": True,
        "ok": True,
        "note": (
            "Eligible LIVE = greeter+wallet with a real row. Sentinels skipped. "
            "Merge/hard denied until critique. Gate uses last-"
            f"{WINDOW_N} window when n>=50 else allowlist all. Never lifts wheels."
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    return payload


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
