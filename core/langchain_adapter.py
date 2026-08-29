"""LangChain adapter — optional Window-B / retrieval chain on ETHER tools.

Does not replace GEMS. Does not lift wheels. Import-safe if langchain is absent.
Install: pip install 'ether[langchain]'
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "langchain_adapter.json"


def available() -> bool:
    try:
        import langchain  # noqa: F401

        return True
    except Exception:
        return False


def tool_specs() -> List[Dict[str, str]]:
    return [
        {"name": "rag_search", "doc": "BM25/Qdrant lesson+code search. args: query, k."},
        {"name": "graph_hint", "doc": "Failure-graph repair template. args: stderr."},
        {"name": "fail_learn", "doc": "Classify a failed job name. args: name."},
        {"name": "propose", "doc": "Open ether_improve_v1 proposal. args: gap, hypothesis, why."},
        {"name": "escalate_grok", "doc": "Dual-window escalate to tutor. args: text."},
    ]


def invoke_tool(name: str, args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    args = args or {}
    if name == "rag_search":
        from core.memory_stack import rag_query

        return rag_query(str(args.get("query") or "anchor_edit"), k=int(args.get("k") or 4))
    if name == "graph_hint":
        from core.failure_graph import repair_hint

        return {"ok": True, "hint": repair_hint(str(args.get("stderr") or "Timeout"))}
    if name == "fail_learn":
        from core.fail_learn import classify_name

        return {"ok": True, "kind": classify_name(str(args.get("name") or ""))}
    if name == "propose":
        from core.improvement_proposal import make_proposal, persist
        from core.self_mod_gate import validate_proposal

        p = make_proposal(
            gap=str(args.get("gap") or "langchain_adapter"),
            hypothesis=str(args.get("hypothesis") or "compose LC with GEMS"),
            metric="hard_live_canary_pass",
            why=str(args.get("why") or "deadline integration"),
        )
        gate = validate_proposal(p)
        path = persist(p, ROOT) if gate.get("ok") else None
        return {"ok": bool(gate.get("ok")), "proposal_id": p.get("id"), "gate": gate, "path": str(path) if path else None}
    if name == "escalate_grok":
        from core.dual_window import submit_proposal

        return submit_proposal(
            {
                "id": "lc_escalate",
                "gap": "langchain",
                "hypothesis": str(args.get("text") or "")[:300],
                "metric": "dual_window",
                "why": "adapter escalate",
            }
        )
    return {"ok": False, "error": f"unknown tool: {name}"}


def run_chain(query: str) -> Dict[str, Any]:
    """Retrieve → graph hint → proposal. LCEL-shaped even without langchain installed."""
    rag = invoke_tool("rag_search", {"query": query, "k": 3})
    graph = invoke_tool("graph_hint", {"stderr": query})
    prop = invoke_tool(
        "propose",
        {
            "gap": query[:80],
            "hypothesis": str((graph.get("hint") or ""))[:200],
            "why": f"langchain_adapter chain hits={rag.get('n')}",
        },
    )
    return {
        "ok": bool(prop.get("ok")),
        "langchain_installed": available(),
        "query": query[:160],
        "rag_n": rag.get("n"),
        "hint": graph.get("hint"),
        "proposal_id": prop.get("proposal_id"),
        "note": (
            "Chain ran on ETHER tools. Install ether[langchain] for LCEL Runnable export."
            if not available()
            else "langchain present; ETHER tools remain source of truth."
        ),
    }


def as_langchain_tools() -> List[Any]:
    """Export StructuredTools when langchain_core is installed."""
    if not available():
        return []
    try:
        from langchain_core.tools import StructuredTool
    except Exception:
        return []

    def _rag(query: str, k: int = 4) -> str:
        return json.dumps(invoke_tool("rag_search", {"query": query, "k": k}), default=str)[:2000]

    def _hint(stderr: str) -> str:
        return json.dumps(invoke_tool("graph_hint", {"stderr": stderr}), default=str)[:1000]

    return [
        StructuredTool.from_function(_rag, name="rag_search", description="ETHER BM25/Qdrant search"),
        StructuredTool.from_function(_hint, name="graph_hint", description="ETHER failure-graph hint"),
    ]


def snapshot() -> Dict[str, Any]:
    chain = run_chain("observe loop merge ledger anchor_edit")
    payload = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "langchain_installed": available(),
        "tools": [t["name"] for t in tool_specs()],
        "exported_lc_tools": len(as_langchain_tools()),
        "last_chain_ok": chain.get("ok"),
        "training_wheels": True,
        "soft_launch": False,
        "replaces_gems": False,
        "path_note": "Optional extra. Default path stays GEMS + ToolRuntime.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    payload["path"] = str(OUT.relative_to(ROOT)).replace("\\", "/")
    payload["chain"] = chain
    return payload


if __name__ == "__main__":
    print(json.dumps(snapshot(), indent=2, default=str))
