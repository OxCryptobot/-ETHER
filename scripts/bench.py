#!/usr/bin/env python3
"""Regression bench — --fast (5) or full (15)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv
from core.pipeline import Pipeline
from core.health_metric import compute_health
from core.bench_guardian import evaluate as guardian_evaluate
from core.scoreboard import write_scoreboard

load_dotenv(ROOT / ".env")

TASKS = [
    "Write only Python: def is_even(n):\n    return n % 2 == 0\nassert is_even(4) and not is_even(5)\nprint(is_even(4))",
    "Write only Python: def add(a,b):\n    return a+b\nassert add(2,3)==5\nprint(add(2,3))",
    "Write only Python: def reverse_string(s):\n    return s[::-1]\nassert reverse_string('abc')=='cba'\nprint(reverse_string('abc'))",
    "Write only Python: def factorial(n):\n    r=1\n    for i in range(2,n+1):\n        r*=i\n    return r\nassert factorial(5)==120\nprint(factorial(5))",
    "Write only Python: def is_palindrome(s):\n    s=s.lower()\n    return s==s[::-1]\nassert is_palindrome('Racecar')\nprint(is_palindrome('Racecar'))",
    "Write only Python: def max_of_three(a,b,c):\n    return max(a,b,c)\nassert max_of_three(1,9,3)==9\nprint(max_of_three(1,9,3))",
    "Write only Python: def count_vowels(s):\n    return sum(1 for ch in s.lower() if ch in 'aeiou')\nassert count_vowels('ether')==2\nprint(count_vowels('ether'))",
    "Write only Python: def flatten(xss):\n    return [x for xs in xss for x in xs]\nassert flatten([[1,2],[3]])==[1,2,3]\nprint(flatten([[1,2],[3],[4,5]]))",
    "Write only Python: def unique(xs):\n    out=[]\n    for x in xs:\n        if x not in out: out.append(x)\n    return out\nassert unique([1,2,2,3,1])==[1,2,3]\nprint(unique([1,2,2,3,1]))",
    "Write only Python: def word_count(s):\n    return len(s.split())\nassert word_count('one two three')==3\nprint(word_count('one two three'))",
    "Write only Python: def sum_list(xs):\n    return sum(xs)\nassert sum_list([1,2,3,4])==10\nprint(sum_list([1,2,3,4]))",
    "Write only Python: def clamp(x,lo,hi):\n    return max(lo, min(hi, x))\nassert clamp(15,0,10)==10\nprint(clamp(15,0,10))",
    "Write only Python: def title_case(s):\n    return ' '.join(w.capitalize() for w in s.split())\nassert title_case('hello ether')=='Hello Ether'\nprint(title_case('hello ether'))",
    "Write only Python: def gcd(a,b):\n    while b: a,b=b,a%b\n    return a\nassert gcd(48,18)==6\nprint(gcd(48,18))",
    "Write only Python: def merge_sorted(a,b):\n    i=j=0; out=[]\n    while i<len(a) and j<len(b):\n        if a[i]<=b[j]: out.append(a[i]); i+=1\n        else: out.append(b[j]); j+=1\n    out.extend(a[i:]); out.extend(b[j:]); return out\nassert merge_sorted([1,3],[2,4])==[1,2,3,4]\nprint(merge_sorted([1,3,5],[2,4,6]))",
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="5-task smoke bench")
    args = ap.parse_args()
    tasks = TASKS[:5] if args.fast else TASKS

    out_dir = ROOT / "memory" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    pipe = Pipeline()
    t0 = time.perf_counter()
    for i, obj in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {'FAST' if args.fast else 'FULL'} ...", flush=True)
        r = pipe.run(obj)
        results.append(
            {
                "i": i,
                "status": r.status,
                "confidence": r.confidence,
                "verification_score": r.verification_score,
                "exit_code": r.sandbox.exit_code if r.sandbox else None,
                "total_tests": r.sandbox.total_tests if r.sandbox else 0,
                "audit": bool(r.audit and r.audit.approved),
                "objective": obj[:80],
            }
        )
        print(
            f"  status={r.status} conf={r.confidence:.3f} ver={r.verification_score:.3f} tests={results[-1]['total_tests']} exit={results[-1]['exit_code']}",
            flush=True,
        )
    ok = sum(1 for x in results if x["status"] == "complete" and x["exit_code"] == 0)
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "fast" if args.fast else "full",
        "n": len(tasks),
        "pass": ok,
        "pass_rate": round(ok / max(1, len(tasks)), 3),
        "duration_s": round(time.perf_counter() - t0, 2),
        "results": results,
    }
    path = out_dir / f"bench_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    health = compute_health()
    guard = guardian_evaluate()
    write_scoreboard()
    print(
        json.dumps(
            {
                "mode": summary["mode"],
                "pass_rate": summary["pass_rate"],
                "pass": ok,
                "n": len(tasks),
                "healthy": health.get("healthy"),
                "guardian_frozen": guard.get("frozen"),
            },
            indent=2,
        )
    )
    return 0 if ok == len(tasks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
