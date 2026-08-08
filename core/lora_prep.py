"""LoRA / QLoRA data preparation — gated, offline, no training.

Produces clean preference / success datasets from:
  - memory/experience/preferences.jsonl
  - artifacts/scoreboard*.json
  - train_gates filtered experience

Output is ready for Unsloth / PEFT later. This module never touches weights.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
PREF_PATH = ROOT / "memory" / "experience" / "preferences.jsonl"
PASS_PATH = ROOT / "memory" / "experience" / "pass.jsonl"
OUT_DIR = ROOT / "artifacts" / "lora_prep"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_jsonl(path: Path, limit: int = 5000) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return rows


def export_preference_pairs(
    min_gap: float = 0.15,
    min_confidence: float = 0.0,
    max_rows: int = 2000,
) -> Dict[str, Any]:
    """Export gated preference pairs in a simple instruction format.

    Format (one jsonl line):
      {"prompt": "...", "chosen": "...", "rejected": "...", "gap": 0.2, "source": "..."}
    """
    rows = _load_jsonl(PREF_PATH)
    out: List[Dict[str, Any]] = []
    skipped = 0
    for r in rows:
        try:
            gap = float(r.get("gap") or 0)
            if gap < min_gap:
                skipped += 1
                continue
            pref = r.get("preferred") or {}
            rej = r.get("rejected") or {}
            # Reject infra-tainted pairs
            reason = str(rej.get("reason") or "").lower()
            if any(x in reason for x in ("docker", "ollama", "timeout_infra", "connection refused")):
                skipped += 1
                continue
            prompt = (
                f"Task / mutation: {pref.get('mutation') or rej.get('mutation') or 'unknown'}\n"
                f"Prefer the higher-scoring strategy and outcome."
            )
            chosen = json.dumps(pref, ensure_ascii=False)[:2000]
            rejected = json.dumps(rej, ensure_ascii=False)[:2000]
            out.append(
                {
                    "prompt": prompt,
                    "chosen": chosen,
                    "rejected": rejected,
                    "gap": round(gap, 4),
                    "source": r.get("source") or "preferences",
                    "rlhf": r.get("rlhf") or "offline_pair",
                    "train_doctrine": r.get("train_doctrine") or "grok_v1",
                }
            )
            if len(out) >= max_rows:
                break
        except Exception:
            skipped += 1
            continue

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "preference_pairs.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    meta = {
        "timestamp": _now(),
        "n_exported": len(out),
        "n_skipped": skipped,
        "min_gap": min_gap,
        "path": str(out_path.relative_to(ROOT)),
        "note": "Ready for Unsloth/QLoRA preference tuning. No weights updated.",
    }
    (OUT_DIR / "preference_pairs_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def export_success_sft(
    min_verification: float = 0.99,
    max_rows: int = 1000,
) -> Dict[str, Any]:
    """Export high-quality successful runs for supervised fine-tune later."""
    rows = _load_jsonl(PASS_PATH)
    out: List[Dict[str, Any]] = []
    skipped = 0
    for r in rows:
        try:
            ver = float(r.get("verification_score") or r.get("confidence") or 0)
            if ver < min_verification:
                skipped += 1
                continue
            if r.get("holdout_ok") is False:
                skipped += 1
                continue
            objective = str(r.get("objective") or "")[:500]
            code = str(r.get("code") or "")[:8000]
            if not objective or not code.strip():
                skipped += 1
                continue
            out.append(
                {
                    "instruction": objective,
                    "output": code,
                    "verification_score": ver,
                    "strategy": r.get("strategy") or "",
                    "train_doctrine": r.get("train_doctrine") or "grok_v1",
                }
            )
            if len(out) >= max_rows:
                break
        except Exception:
            skipped += 1
            continue

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "success_sft.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    meta = {
        "timestamp": _now(),
        "n_exported": len(out),
        "n_skipped": skipped,
        "min_verification": min_verification,
        "path": str(out_path.relative_to(ROOT)),
        "note": "SFT-ready successes only. Holdout failures excluded.",
    }
    (OUT_DIR / "success_sft_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def prepare_all() -> Dict[str, Any]:
    """One-shot: export both datasets + summary. Safe under training wheels."""
    pref = export_preference_pairs()
    sft = export_success_sft()
    summary = {
        "timestamp": _now(),
        "preference_pairs": pref,
        "success_sft": sft,
        "ready_for_unsloth": True,
        "training_executed": False,
        "doctrine": "offline_rlhf_then_optional_lora",
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "prep_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    # Mirror for host observability
    try:
        (ROOT / "artifacts" / "lora_prep_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
    return summary


if __name__ == "__main__":
    import pprint
    pprint.pprint(prepare_all())
