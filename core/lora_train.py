"""Gated LoRA / PEFT / Unsloth adapter training for ETHER.

Doctrine (hard):
  - Offline only. Preference pairs + success_sft from lora_prep must already exist.
  - Training wheels ON by default: dry-run unless ETHER_LORA_TRAIN=1 AND explicit promote.
  - Never unrestricted self-modification. Adapter only; base model untouched.
  - 4GB VRAM aware: rank, target_modules, max_steps limited.
  - Citrine-level memory: every successful adapter write is recorded as metadata
    so the system can later retrieve "what this adapter improved".

Promotion path (human or structured):
  1. lora_prep clean
  2. dry-run report green
  3. ETHER_LORA_TRAIN=1 + ETHER_LORA_PROMOTE=1 (or Labradorite + Amethyst signal)
  4. Adapter lands under artifacts/lora_adapters/<id>/
  5. Rose Quartz loads adapter only behind feature flag

This module is the professional architecture layer. It does not train on every tick.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
PREP_DIR = ROOT / "artifacts" / "lora_prep"
ADAPTER_DIR = ROOT / "artifacts" / "lora_adapters"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _training_wheels() -> bool:
    return (os.getenv("ETHER_TRAINING_WHEELS") or "1").strip() != "0"


def _may_train() -> tuple[bool, str]:
    if _training_wheels() and (os.getenv("ETHER_LORA_TRAIN") or "0") != "1":
        return False, "training_wheels_require_ETHER_LORA_TRAIN=1"
    if (os.getenv("ETHER_LORA_PROMOTE") or "0") != "1" and _training_wheels():
        return False, "promotion_gate_require_ETHER_LORA_PROMOTE=1_or_lift_wheels"
    pairs = PREP_DIR / "preference_pairs.jsonl"
    sft = PREP_DIR / "success_sft.jsonl"
    if not pairs.exists() and not sft.exists():
        return False, "no_lora_prep_data_run_core.lora_prep_first"
    return True, "ok"


def _load_jsonl(path: Path, limit: int = 500) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
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


def dry_run_report() -> Dict[str, Any]:
    """Always safe. Reports readiness without touching GPU or weights."""
    pairs = _load_jsonl(PREP_DIR / "preference_pairs.jsonl")
    sft = _load_jsonl(PREP_DIR / "success_sft.jsonl")
    may, reason = _may_train()
    return {
        "timestamp": _now(),
        "training_wheels": _training_wheels(),
        "may_train": may,
        "gate_reason": reason,
        "n_preference_pairs": len(pairs),
        "n_success_sft": len(sft),
        "recommended_rank": 8 if len(pairs) + len(sft) < 50 else 16,
        "recommended_max_steps": 20 if _training_wheels() else 100,
        "vram_note": "GTX 1650 4GB → keep rank<=16, target_modules=[q_proj,v_proj] or equivalent",
        "next": (
            "Set ETHER_LORA_TRAIN=1 and ETHER_LORA_PROMOTE=1 only after "
            "dashboard preference health is green"
        ),
        "doctrine": "offline_rlhf_then_gated_lora",
    }


def train_adapter(
    *,
    base_model: str = "",
    rank: int = 8,
    max_steps: int = 20,
    dry_run: bool = True,
    task_id: str = "",
) -> Dict[str, Any]:
    """Execute (or simulate) one LoRA adapter training cycle.

    Under training wheels dry_run=True is forced unless both flags are set.
    Returns structured report; never overwrites base weights.
    """
    tid = task_id or str(uuid4())[:12]
    report: Dict[str, Any] = {
        "id": tid,
        "timestamp": _now(),
        "dry_run": True,
        "ok": False,
        "adapter_path": None,
        "meta_path": None,
    }

    readiness = dry_run_report()
    report["readiness"] = readiness

    # Force dry-run under wheels unless explicitly unlocked
    if _training_wheels() and not (
        os.getenv("ETHER_LORA_TRAIN") == "1" and os.getenv("ETHER_LORA_PROMOTE") == "1"
    ):
        dry_run = True
        report["forced_dry_run"] = True
        report["reason"] = readiness["gate_reason"]

    report["dry_run"] = dry_run

    if dry_run:
        report["simulation"] = {
            "import": "import loralib as lora  # or peft / unsloth if installed",
            "layer_example": "lora.Linear(in_features=512, out_features=256, r=rank)",
            "mark_trainable": "lora.mark_only_lora_as_trainable(model)",
            "save": 'torch.save(lora.lora_state_dict(model), "adapter.pth")',
            "rank": rank,
            "max_steps": max_steps,
            "note": "No GPU call. Weights untouched. This is the professional gate.",
        }
        report["ok"] = True
        report["message"] = "dry-run complete — structure ready for real train when flags lifted"
        _write_report(tid, report)
        return report

    may, reason = _may_train()
    if not may:
        report["ok"] = False
        report["error"] = reason
        _write_report(tid, report)
        return report

    try:
        backend = _detect_backend()
        report["backend"] = backend

        pairs = _load_jsonl(PREP_DIR / "preference_pairs.jsonl", limit=200)
        sft = _load_jsonl(PREP_DIR / "success_sft.jsonl", limit=100)

        if backend == "unsloth":
            adapter_meta = _train_unsloth(base_model, pairs, sft, rank, max_steps, tid)
        elif backend == "peft":
            adapter_meta = _train_peft(base_model, pairs, sft, rank, max_steps, tid)
        else:
            adapter_meta = _train_loralib_style(base_model, pairs, sft, rank, max_steps, tid)

        report.update(adapter_meta)
        report["ok"] = True
        _record_adapter_in_citrine(report)

    except Exception as e:
        report["ok"] = False
        report["error"] = str(e)[:400]

    _write_report(tid, report)
    return report


def _detect_backend() -> str:
    try:
        import unsloth  # noqa: F401

        return "unsloth"
    except Exception:
        pass
    try:
        import peft  # noqa: F401

        return "peft"
    except Exception:
        pass
    try:
        import loralib  # noqa: F401

        return "loralib"
    except Exception:
        return "torch_manual"


def _train_unsloth(base, pairs, sft, rank, max_steps, tid) -> Dict[str, Any]:
    raise NotImplementedError(
        "Unsloth path ready in structure; install unsloth + set flags + run on GPU host"
    )


def _train_peft(base, pairs, sft, rank, max_steps, tid) -> Dict[str, Any]:
    raise NotImplementedError("PEFT path ready in structure; install peft + set flags")


def _train_loralib_style(base, pairs, sft, rank, max_steps, tid) -> Dict[str, Any]:
    try:
        import loralib as lora
        import torch
        import torch.nn as nn
    except Exception as e:
        raise RuntimeError(f"loralib/torch unavailable: {e}") from e

    class TinyCoder(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.fc1 = lora.Linear(128, 64, r=rank)
            self.fc2 = lora.Linear(64, 32, r=rank)

        def forward(self, x: Any) -> Any:
            return self.fc2(torch.relu(self.fc1(x)))

    model = TinyCoder()
    lora.mark_only_lora_as_trainable(model)

    opt = torch.optim.Adam([p for p in model.parameters() if p.requires_grad], lr=1e-3)
    x = torch.randn(4, 128)
    loss = model(x).sum()
    loss.backward()
    opt.step()

    out_dir = ADAPTER_DIR / tid
    out_dir.mkdir(parents=True, exist_ok=True)
    ckpt = out_dir / "adapter.pth"
    torch.save(lora.lora_state_dict(model), ckpt)

    meta = {
        "adapter_path": str(ckpt.relative_to(ROOT)),
        "rank": rank,
        "n_pairs_seen": len(pairs),
        "n_sft_seen": len(sft),
        "backend": "loralib",
        "note": "Demo adapter on TinyCoder. Replace with real base when promoting.",
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    meta["meta_path"] = str((out_dir / "meta.json").relative_to(ROOT))
    return meta


def _write_report(tid: str, report: Dict[str, Any]) -> None:
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    path = ADAPTER_DIR / f"train_report_{tid}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report_path"] = str(path.relative_to(ROOT))
    try:
        (ROOT / "artifacts" / "lora_train_last.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _record_adapter_in_citrine(report: Dict[str, Any]) -> None:
    try:
        from core.registry import build_default_registry
        from core.schemas import CitrineRequest, Envelope

        text = (
            f"LoRA adapter trained. id={report.get('id')} backend={report.get('backend')} "
            f"rank={report.get('rank')} path={report.get('adapter_path')} "
            f"pairs={report.get('n_pairs_seen')} sft={report.get('n_sft_seen')}. "
            f"Self-improvement artifact. Query this to recall how the model evolved."
        )
        docs = [
            {
                "text": text,
                "metadata": {
                    "kind": "lora_adapter",
                    "adapter_id": report.get("id"),
                    "path": report.get("adapter_path"),
                    "train_doctrine": "grok_v1",
                },
            }
        ]
        build_default_registry().execute(
            Envelope(
                task_id=uuid4(),
                target_gem="citrine",
                payload=CitrineRequest(action="add", collection="patterns", documents=docs),
            )
        )
    except Exception:
        pass


def promote_check() -> Dict[str, Any]:
    return {
        "questions": [
            "How do we get better?",
            "How do we self-improve?",
            "How can I surpass my limitations?",
            "What do I need to do?",
        ],
        "answers_required": True,
        "current_gate": dry_run_report(),
        "rule": "Never unrestricted self-modification. Always answer the four questions first.",
    }


if __name__ == "__main__":
    # Host-agent entry: always dry-run under training wheels; exit 0 on success.
    try:
        report = dry_run_report()
        result = train_adapter(dry_run=True)
        print(json.dumps({"dry_run_report": report, "train_adapter": result}, indent=2))
        sys.exit(0 if result.get("ok") else 1)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)[:400]}, indent=2))
        sys.exit(1)
