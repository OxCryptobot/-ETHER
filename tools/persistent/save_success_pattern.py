#!/usr/bin/env python3
"""Append a successful code pattern for later recall."""
from __future__ import annotations

import json
import pathlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input, repo_root


def main() -> None:
    inp = read_input()
    objective = inp.get("objective") or ""
    code = inp.get("code") or ""
    if not code:
        emit(False, error="code required")

    # Refuse to store an artifact carrying a holdout assertion.
    #
    # few_shot_pack replays this store into later prompts, so a leaked-era
    # artifact becomes a permanent contamination source: the model was shown
    # the holdout, wrote those assertions into its code, the run "passed", the
    # code was saved as a worked example, and it has been re-injected into
    # every prompt since. Measured: 17 of 120 ether samples in a clean ablation
    # were still excluded for leakage traceable to this file, and only the
    # ether arm was affected because only it uses few-shot retrieval.
    #
    # Checking on the WRITE path is what stops the loop closing. Fixing the
    # readers only removes today's copy.
    holdout = inp.get("holdout_test") or ""
    if holdout:
        try:
            import sys

            sys.path.insert(0, str(repo_root()))
            from core.prompt_guard import find_leaks

            leaks = find_leaks(f"{objective}\n{code}", holdout)
            if leaks:
                emit(
                    False,
                    error=f"refused: artifact carries {len(leaks)} holdout assertion(s)",
                    leaked=True,
                )
                return
        except Exception:
            # A guard that cannot run must not silently permit the write.
            emit(False, error="refused: leak guard unavailable", leaked=True)
            return
    path = pathlib.Path(
        os.environ.get("ETHER_SUCCESS_PATTERNS_PATH")
        # Overridable so the test suite does not write mock runs into the
        # store that few_shot_pack replays into real prompts: 84 of 101
        # rows were "write hello" test artifacts served to the model as
        # worked examples.
        or repo_root() / "memory" / "learning" / "success_patterns.jsonl"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "objective": objective[:300],
        "code": code[:8000],
        "tags": inp.get("tags") or [],
        "confidence": inp.get("confidence"),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    emit(True, saved=True, path=str(path))


if __name__ == "__main__":
    main()
