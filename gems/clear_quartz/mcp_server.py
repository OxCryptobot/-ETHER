"""Clear Quartz MCP server — thin standardized tool surface over the real sandbox.

Exposes 3 tools via the 2026-07-28 MCP spec (stateless):
  - execute_code
  - run_project_tests
  - sandbox_health

All paths still go through ClearQuartz.execute so isolation, static analysis,
DockerUnavailable handling, and multifile/project-pytest stay identical.
Training wheels / honest gate remain upstream in ToolRuntimeGateHandler.

Usage (stdio):
  python -m gems.clear_quartz.mcp_server

Or import create_server() and run under the official Client for in-process tests.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Prefer official MCPServer (v2 / 2026-07-28). Fall back gracefully if not installed
# so the rest of ETHER never breaks on import.
try:
    from mcp.server import MCPServer

    _MCP_AVAILABLE = True
except Exception:  # pragma: no cover
    MCPServer = None  # type: ignore[misc, assignment]
    _MCP_AVAILABLE = False


def _cq() -> Any:
    from gems.clear_quartz.sandbox import ClearQuartz

    return ClearQuartz()


def _envelope(code: str = "", files: Optional[Dict[str, str]] = None, timeout: int = 30, **extra: Any):
    from core.schemas import ClearQuartzRequest, Envelope

    payload = ClearQuartzRequest(
        code=code or "",
        files=files or {},
        prepare_code=False,  # MCP surface is verbatim / explicit
        **{k: v for k, v in extra.items() if k in ("objective", "fixture_root", "test_args")},
    )
    return Envelope(
        task_id=uuid4(),
        target_gem="clear-quartz",
        payload=payload,
        timeout_seconds=int(timeout),
    )


def create_server(name: str = "ether-clear-quartz") -> Any:
    """Build an MCPServer that wraps Clear Quartz. Raises if mcp SDK missing."""
    if not _MCP_AVAILABLE or MCPServer is None:
        raise RuntimeError(
            "mcp package not installed. Install with: pip install 'mcp[cli]>=1.0' "
            "or uv add 'mcp[cli]'"
        )

    mcp = MCPServer(name)

    @mcp.tool()
    def execute_code(code: str, timeout: int = 30) -> Dict[str, Any]:
        """Execute Python code in the Clear Quartz sandbox (Docker or local fallback).

        Returns stdout/stderr/exit_code/tests_passed/security_flags.
        Isolation and static analysis are identical to the native gem path.
        """
        cq = _cq()
        env = _envelope(code=code, timeout=timeout)
        res = cq.execute(env)
        if res.error:
            return {
                "ok": False,
                "error": res.error.message,
                "error_type": str(getattr(res.error, "type", "runtime")),
                "recoverable": bool(getattr(res.error, "recoverable", True)),
            }
        p = res.payload
        return {
            "ok": True,
            "stdout": getattr(p, "stdout", "") or "",
            "stderr": getattr(p, "stderr", "") or "",
            "exit_code": int(getattr(p, "exit_code", 1) or 1),
            "tests_passed": int(getattr(p, "tests_passed", 0) or 0),
            "total_tests": int(getattr(p, "total_tests", 0) or 0),
            "security_flags": list(getattr(p, "security_flags", []) or []),
            "execution_time": float(getattr(p, "execution_time", 0.0) or 0.0),
            "static_analysis_score": float(getattr(p, "static_analysis_score", 1.0) or 1.0),
        }

    @mcp.tool()
    def run_project_tests(
        files: Dict[str, str],
        test_args: Optional[List[str]] = None,
        timeout: int = 60,
        fixture_root: str = "",
    ) -> Dict[str, Any]:
        """Run project pytest against a multifile workspace seeded from `files`.

        `files` maps relative path -> content. Uses the same repo_oracle path
        as native Clear Quartz multifile execution.
        """
        cq = _cq()
        extra: Dict[str, Any] = {}
        if test_args:
            extra["test_args"] = list(test_args)
        if fixture_root:
            extra["fixture_root"] = fixture_root
        env = _envelope(files=files, timeout=timeout, **extra)
        res = cq.execute(env)
        if res.error:
            return {
                "ok": False,
                "error": res.error.message,
                "error_type": str(getattr(res.error, "type", "runtime")),
            }
        p = res.payload
        return {
            "ok": int(getattr(p, "exit_code", 1) or 1) == 0,
            "exit_code": int(getattr(p, "exit_code", 1) or 1),
            "tests_passed": int(getattr(p, "tests_passed", 0) or 0),
            "total_tests": int(getattr(p, "total_tests", 0) or 0),
            "stdout": (getattr(p, "stdout", "") or "")[-4000:],
            "stderr": (getattr(p, "stderr", "") or "")[-2000:],
            "security_flags": list(getattr(p, "security_flags", []) or []),
            "execution_time": float(getattr(p, "execution_time", 0.0) or 0.0),
        }

    @mcp.tool()
    def sandbox_health() -> Dict[str, Any]:
        """Report sandbox backend and basic readiness (no code execution)."""
        from gems.clear_quartz.sandbox import sandbox_backend

        backend = sandbox_backend()
        return {
            "ok": True,
            "backend": backend,
            "mcp_available": True,
            "docker_in_path": bool(__import__("shutil").which("docker")),
            "python": sys.executable,
            "note": "Clear Quartz MCP surface is live; honest gate remains upstream",
        }

    return mcp


def main() -> None:
    if not _MCP_AVAILABLE:
        print("mcp SDK not installed", file=sys.stderr)
        sys.exit(2)
    server = create_server()
    # stdio is the local-first default
    server.run()


if __name__ == "__main__":
    main()
