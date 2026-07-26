"""Shared intelligence hooks used by Pipeline (keeps pipeline thinner)."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from core.assert_harness import ensure_harness, has_self_check
from core.experience import retrieve as experience_retrieve
from core.rag_bm25 import format_block as rag_block


def build_knowledge(objective: str, strategy: str) -> Dict[str, Any]:
    exp = experience_retrieve(objective, k=3)
    rag = ""
    if strategy in ("rag_on", "repo_map_on", "default", "few_shot_on"):
        try:
            rag = rag_block(objective, k=3)
        except Exception:
            rag = ""
    return {
        "experience_block": exp.get("block") or "",
        "experience_chars": len(exp.get("block") or ""),
        "rag_block": rag,
        "rag_chars": len(rag),
        "n_pass": exp.get("n_pass", 0),
        "n_fail": exp.get("n_fail", 0),
    }


def prepare_code_for_sandbox(code: str) -> Tuple[str, bool, bool]:
    """Returns code, harness_modified, had_self_check_before."""
    before = has_self_check(code)
    new_code, modified = ensure_harness(code)
    return new_code, modified, before


def note_failure(stderr: str) -> None:
    try:
        from core.failure_graph import observe

        observe(stderr, repaired_ok=False)
    except Exception:
        pass


def note_repair_success(stderr: str) -> None:
    try:
        from core.failure_graph import observe

        observe(stderr, repaired_ok=True)
    except Exception:
        pass
