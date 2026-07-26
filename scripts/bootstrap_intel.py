#!/usr/bin/env python3
"""One-shot: sync curriculum from vault, ensure health, scoreboard, optional fast bench."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.curriculum import sync_from_vault
from core.health_metric import compute_health
from core.scoreboard import write_scoreboard


def main() -> int:
    state = sync_from_vault()
    health = compute_health()
    board = write_scoreboard()
    print(
        json.dumps(
            {
                "curriculum": {
                    "tier": state.get("tier"),
                    "wins": state.get("wins"),
                    "losses": state.get("losses"),
                    "last_event": state.get("last_event"),
                    "vault_pass": state.get("vault_pass"),
                    "vault_fail": state.get("vault_fail"),
                },
                "health": health,
                "scoreboard": board,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
