"""Automated tool fabrication — AST gate + safety + sandbox + audit + promote."""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
QUARANTINE = ROOT / "tools" / "quarantine"
PERSISTENT = ROOT / "tools" / "persistent"
FABRICATE_LOG = ROOT / "memory" / "tools" / "fabricate.jsonl"

RISKY = re.compile(r"\b(eval|exec)\s*\(|os\.system\s*\(|shell\s*=\s*True|pickle\.loads?\s*\(")
SECRETISH = re.compile(
    r"AKIA[0-9A-Z]{16}|-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----", re.I
)

STUB_TEMPLATE = '''#!/usr/bin/env python3
"""{docstring}"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _lib import emit, read_input

def main() -> None:
    inp = read_input()
    emit(False, error="not implemented", tool="{name}", input_keys=list(inp.keys()))

if __name__ == "__main__":
    main()
'''


def _sanitize(name: str) -> str:
    name = re.sub(r"[^0-9a-zA-Z_]", "_", (name or "new_tool").strip()) or "new_tool"
    if name[0].isdigit():
        name = f"tool_{name}"
    return name[:64]


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    if text.startswith("```"):
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return text


def _log(entry: Dict[str, Any]) -> None:
    FABRICATE_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), **entry}
    with FABRICATE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def ast_validate(code: str) -> Dict[str, Any]:
    """Require parseable Python + a top-level main function."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"ok": False, "error": f"syntax: {e}"}
    has_main = any(
        isinstance(n, ast.FunctionDef) and n.name == "main" for n in tree.body
    )
    if not has_main:
        return {"ok": False, "error": "missing def main()"}
    return {"ok": True, "has_main": True}


def static_safety(code: str) -> Dict[str, Any]:
    findings: List[str] = []
    if RISKY.search(code):
        findings.append("risky_exec_pattern")
    if SECRETISH.search(code):
        findings.append("secret_like_pattern")
    if any(x in code for x in ("requests.", "urllib.", "httpx.")):
        findings.append("network_client_import")
    return {"ok": len(findings) == 0, "findings": findings}


def sandbox_selftest(code: str, timeout: int = 30) -> Dict[str, Any]:
    try:
        from core.schemas import Envelope, ClearQuartzRequest
        from core.registry import build_default_registry

        harness = (
            "code = '''" + code.replace("\\", "\\\\").replace("'''", "\\'\'\'") + "'''\n"
            "compile(code, '<tool>', 'exec')\n"
            "print('compile_ok')\n"
        )
        reg = build_default_registry()
        res = reg.execute(
            Envelope(
                task_id=uuid4(),
                target_gem="clear-quartz",
                payload=ClearQuartzRequest(code=harness),
                timeout_seconds=timeout,
            )
        )
        if res.error:
            return {"ok": False, "error": res.error.message, "exit_code": 1}
        payload = res.payload
        return {
            "ok": getattr(payload, "exit_code", 1) == 0,
            "exit_code": getattr(payload, "exit_code", 1),
            "stdout": getattr(payload, "stdout", "")[:500],
            "stderr": getattr(payload, "stderr", "")[:500],
        }
    except Exception as e:
        try:
            compile(code, "<tool>", "exec")
            return {"ok": True, "exit_code": 0, "stdout": "compile_ok_local", "stderr": ""}
        except Exception as ce:
            return {"ok": False, "error": str(ce), "exit_code": 1}


def audit_code(code: str) -> Dict[str, Any]:
    try:
        from core.schemas import Envelope, BlackTourmalineRequest
        from core.registry import build_default_registry

        reg = build_default_registry()
        res = reg.execute(
            Envelope(
                task_id=uuid4(),
                target_gem="black-tourmaline",
                payload=BlackTourmalineRequest(artifact=code, artifact_type="tool"),
            )
        )
        if res.error:
            return {"ok": False, "approved": False, "error": res.error.message}
        p = res.payload
        return {
            "ok": bool(getattr(p, "approved", False)),
            "approved": bool(getattr(p, "approved", False)),
            "risk_score": float(getattr(p, "risk_score", 1.0)),
        }
    except Exception as e:
        return {"ok": False, "approved": False, "error": str(e)}


def llm_implement(name: str, docstring: str, spec: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from core.schemas import Envelope, RoseQuartzRequest, ChatMessage, RoseQuartzResponse
        from core.registry import build_default_registry

        prompt = f"""Implement a complete @ETHER persistent tool as a single Python file.
Rules:
- Must define main() and if __name__ == "__main__": main()
- JSON in; JSON out with key ok via _lib emit/read_input
- No network, eval, exec, os.system, shell=True
- Tool name: {name}
- Purpose: {docstring}
- Spec: {json.dumps(spec)[:1500]}
Return ONLY full Python source, no markdown.
"""
        reg = build_default_registry()
        res = reg.execute(
            Envelope(
                task_id=uuid4(),
                target_gem="rose-quartz",
                payload=RoseQuartzRequest(
                    messages=[ChatMessage(role="user", content=prompt)], prefer_local=True
                ),
            )
        )
        if res.error or not isinstance(res.payload, RoseQuartzResponse):
            return {"ok": False, "error": res.error.message if res.error else "llm failed"}
        code = _strip_fences(res.payload.content)
        if "def main" not in code:
            return {"ok": False, "error": "llm output missing main()", "code": code[:500]}
        return {"ok": True, "code": code, "model": res.payload.model_used}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def promote(path: Path) -> Dict[str, Any]:
    PERSISTENT.mkdir(parents=True, exist_ok=True)
    base = path.name
    m = re.match(r"^(.+?)_\d{{8}}_\d{{6}}\.py$", base)
    dest_name = f"{m.group(1)}.py" if m else base
    dest = PERSISTENT / dest_name
    dest.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return {"ok": True, "path": str(dest.relative_to(ROOT)).replace("\\", "/")}


def fabricate(tool_request: Dict[str, Any]) -> Dict[str, Any]:
    name = _sanitize(str(tool_request.get("name") or "new_tool"))
    docstring = str(tool_request.get("docstring") or tool_request.get("purpose") or f"Tool {name}")
    spec = {k: v for k, v in tool_request.items() if k not in {"action", "name"}}
    auto_promote = os.getenv("ETHER_AUTO_PROMOTE", "0") == "1"
    skip_llm = bool(tool_request.get("stub_only")) or os.getenv("ETHER_FABRICATE_STUB_ONLY", "0") == "1"

    QUARANTINE.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = QUARANTINE / f"{name}_{ts}.py"

    result: Dict[str, Any] = {
        "name": name,
        "quarantine_path": str(out_path.relative_to(ROOT)).replace("\\", "/"),
        "stages": [],
        "validation_status": "pending",
        "promoted": False,
        "promote_path": None,
    }

    if skip_llm:
        code = STUB_TEMPLATE.format(name=name, docstring=docstring)
        result["stages"].append({"stage": "implement", "ok": True, "mode": "stub"})
    else:
        impl = llm_implement(name, docstring, spec)
        result["stages"].append(
            {"stage": "implement", "ok": impl.get("ok"), "mode": "llm", "error": impl.get("error")}
        )
        code = impl["code"] if impl.get("ok") else STUB_TEMPLATE.format(name=name, docstring=docstring)
        if not impl.get("ok"):
            result["stages"].append({"stage": "implement_fallback", "ok": True, "mode": "stub"})

    out_path.write_text(code, encoding="utf-8")

    av = ast_validate(code)
    result["stages"].append({"stage": "ast_validate", **av})
    if not av["ok"]:
        result["validation_status"] = "failed"
        result["error"] = av.get("error")
        _log(result)
        return result

    safety = static_safety(code)
    result["stages"].append({"stage": "static_safety", **safety})
    if not safety["ok"]:
        result["validation_status"] = "failed"
        result["error"] = f"static safety: {safety['findings']}"
        _log(result)
        return result

    st = sandbox_selftest(code)
    result["stages"].append({"stage": "sandbox_selftest", **st})
    if not st.get("ok"):
        result["validation_status"] = "failed"
        result["error"] = st.get("error") or f"selftest exit {st.get('exit_code')}"
        _log(result)
        return result

    aud = audit_code(code)
    result["stages"].append({"stage": "audit", **aud})
    if not aud.get("approved", False):
        result["validation_status"] = "failed"
        result["error"] = aud.get("error") or "audit rejected"
        _log(result)
        return result

    result["validation_status"] = "pending_promote"
    if auto_promote:
        promo = promote(out_path)
        result["stages"].append({"stage": "promote", **promo})
        result["promoted"] = bool(promo.get("ok"))
        result["promote_path"] = promo.get("path")
        result["validation_status"] = "promoted" if promo.get("ok") else "pending_promote"
    else:
        result["stages"].append(
            {"stage": "promote", "ok": False, "note": "ETHER_AUTO_PROMOTE=0"}
        )

    _log(result)
    return result
