"""LoRA pack for Grok. 1650 does not train. Dual chat is the trainer chair."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
PACK = ROOT / "artifacts" / "lora" / "pack.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_pack(rows: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Write a JSONL pack Grok can train from. Does not mutate 4B weights."""
    if rows is None:
        try:
            from core.loop.flywheel import last_lessons

            rows = last_lessons(24)
        except Exception:
            rows = []
    PACK.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with PACK.open("w", encoding="utf-8") as fh:
        for row in rows:
            rec = {
                "ts": _now(),
                "trainer": "grok_bus",
                "lesson": row,
            }
            fh.write(json.dumps(rec) + "\n")
            n += 1
        if n == 0:
            fh.write(
                json.dumps(
                    {
                        "ts": _now(),
                        "trainer": "grok_bus",
                        "lesson": {
                            "kind": "seed",
                            "text": "pytest is the judge. replace_once from bug_comments. policy=model.",
                        },
                    }
                )
                + "\n"
            )
            n = 1
    return {
        "ok": True,
        "n": n,
        "path": str(PACK.relative_to(ROOT)).replace("\\", "/"),
        "trainer": "grok_bus",
        "local_train": False,
        "adapter": None,
        "note": "Pack only. Grok trains. 1650 serves 4B. No adapter until Grok writes one.",
    }


def train_via_grok() -> Dict[str, Any]:
    """Named entry: Grok is the LoRA trainer. Local GPU does not train."""
    pack = build_pack()
    pack.update(
        {
            "job": "lora_via_grok",
            "backend": "grok_bus",
            "requires_api_key": False,
        }
    )
    return pack


def lora_status() -> Dict[str, Any]:
    adapter = ROOT / "artifacts" / "lora" / "adapter.safetensors"
    return {
        "ok": adapter.is_file(),
        "reason": "adapter_present" if adapter.is_file() else "pack_only",
        "trainer": "grok_bus",
        "local_train": False,
        "local_1650": True,
        "vram_min_gb": 12,
        "requires_api_key": False,
        "pack_exists": PACK.is_file(),
        "adapter": str(adapter.relative_to(ROOT)).replace("\\", "/") if adapter.is_file() else None,
        "note": "Grok trains from Dual chat pack. 4B serves. No fake weights.",
    }
