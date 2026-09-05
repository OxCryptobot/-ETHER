"""LoRA pack + Grok prompt-adapter. 1650 does not train. No fake PEFT weights."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(os.environ.get("ETHER_ROOT") or Path(__file__).resolve().parents[1]).resolve()
PACK = ROOT / "artifacts" / "lora" / "pack.jsonl"
ADAPTER = ROOT / "artifacts" / "lora" / "adapter.json"
PREFIX = (
    "pytest is the judge. replace_once from bug_comments. policy=model. "
    "Wheels ON. One agent. Dual chat is Grok. FAST stays local 4B. "
    "Teacher playbook does not count. Seed fixtures start red."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_pack(rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
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
            fh.write(json.dumps({"ts": _now(), "trainer": "grok_bus", "lesson": row}) + "\n")
            n += 1
        if n == 0:
            fh.write(
                json.dumps(
                    {
                        "ts": _now(),
                        "trainer": "grok_bus",
                        "lesson": {"kind": "seed", "text": PREFIX},
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
        "peft": False,
        "note": "Pack written. Grok distills adapter.json (prompt adapter, not PEFT).",
    }


def distill() -> Dict[str, Any]:
    """Grok trains: pack → prompt adapter. Not safetensors. Not 1650."""
    lessons: List[Any] = []
    if PACK.is_file():
        for line in PACK.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                lessons.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if not lessons:
        build_pack()
        return distill()
    texts: List[str] = []
    for rec in lessons:
        lesson = rec.get("lesson") if isinstance(rec, dict) else None
        if isinstance(lesson, dict):
            text = str(lesson.get("text") or "")
        else:
            text = str(lesson or "")
        if text and text not in texts:
            texts.append(text)
        if len(texts) >= 8:
            break
    adapter = {
        "schema": "ether_grok_lora_v1",
        "trainer": "grok_bus",
        "kind": "prompt_adapter",
        "peft": False,
        "local_train": False,
        "requires_api_key": False,
        "prefix": PREFIX,
        "lessons": texts,
        "n_pack": len(lessons),
        "updated": _now(),
        "note": "Grok prompt-adapter from pack. 4B serves. No fake PEFT weights.",
    }
    ADAPTER.parent.mkdir(parents=True, exist_ok=True)
    ADAPTER.write_text(json.dumps(adapter, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "trainer": "grok_bus",
        "local_train": False,
        "peft": False,
        "adapter": str(ADAPTER.relative_to(ROOT)).replace("\\", "/"),
        "n_lessons": len(texts),
        "requires_api_key": False,
    }


def train_via_grok() -> Dict[str, Any]:
    pack = build_pack()
    trained = distill()
    pack.update(trained)
    pack["job"] = "lora_via_grok"
    pack["backend"] = "grok_bus"
    return pack


def apply_adapter(prompt: str) -> str:
    if not ADAPTER.is_file():
        return prompt
    try:
        data = json.loads(ADAPTER.read_text(encoding="utf-8"))
        prefix = str(data.get("prefix") or "").strip()
    except Exception:
        return prompt
    if not prefix:
        return prompt
    if prompt.startswith(prefix):
        return prompt
    return prefix + "\n\n" + prompt


def lora_status() -> Dict[str, Any]:
    peft = ROOT / "artifacts" / "lora" / "adapter.safetensors"
    json_ok = False
    prefix = ""
    if ADAPTER.is_file():
        try:
            data = json.loads(ADAPTER.read_text(encoding="utf-8"))
            prefix = str(data.get("prefix") or "")
            json_ok = bool(prefix) and data.get("trainer") == "grok_bus"
        except Exception:
            json_ok = False
    return {
        "ok": json_ok,
        "reason": "grok_prompt_adapter" if json_ok else "pack_only",
        "trainer": "grok_bus",
        "local_train": False,
        "peft": False,
        "peft_file": peft.is_file(),
        "local_1650": True,
        "requires_api_key": False,
        "pack_exists": PACK.is_file(),
        "adapter": str(ADAPTER.relative_to(ROOT)).replace("\\", "/") if json_ok else None,
        "prefix_chars": len(prefix),
        "note": "Grok prompt-adapter. No fake PEFT. 4B serves.",
    }
