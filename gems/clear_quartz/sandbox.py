"""Clear Quartz sandbox implementation."""

from __future__ import annotations

import ast
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple

from core.schemas import (
    ClearQuartzRequest,
    ClearQuartzResponse,
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
)


class ClearQuartz:
    """Docker-based sandbox.

    Uses `docker run -i ... python -` and feeds code on stdin so Windows
    does not need fragile bind-mount path translation.
    """

    def __init__(self, work_dir: Optional[Path] = None):
        # kept for compatibility; not required for stdin mode
        self.work_dir = work_dir or Path(tempfile.gettempdir()) / "ether-sandbox"
        self.work_dir.mkdir(parents=True, exist_ok=True)

    def execute(self, request: Envelope) -> ResponseEnvelope:
        if not isinstance(request.payload, ClearQuartzRequest):
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                error=GemError(
                    type=GemErrorType.UNKNOWN,
                    message="Invalid payload type for Clear Quartz",
                    recoverable=False,
                ),
            )

        payload = request.payload
        start = time.perf_counter()

        try:
            security_flags = self._static_analysis(payload.code)
            result = self._run_docker(payload.code, request.timeout_seconds)
            execution_time = time.perf_counter() - start
            tests_passed, total_tests = self._count_tests(result.stdout, result.stderr)

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                payload=ClearQuartzResponse(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                    total_tests=total_tests,
                    tests_passed=tests_passed,
                    security_flags=security_flags,
                    execution_time=round(execution_time, 3),
                    static_analysis_score=0.0 if security_flags else 1.0,
                ),
            )

        except subprocess.TimeoutExpired:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                error=GemError(
                    type=GemErrorType.TIMEOUT,
                    message=f"Sandbox timed out after {request.timeout_seconds}s",
                    recoverable=True,
                    suggested_action="Increase ETHER_SANDBOX_TIMEOUT or simplify the code",
                ),
            )
        except FileNotFoundError:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                error=GemError(
                    type=GemErrorType.DEPENDENCY,
                    message="Docker is not installed or not in PATH",
                    recoverable=True,
                    suggested_action="Install Docker and ensure `docker ps` works",
                ),
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                error=GemError(type=GemErrorType.RUNTIME, message=str(e), recoverable=True),
            )

    def _static_analysis(self, code: str) -> List[str]:
        flags: List[str] = []
        dangerous = {"eval", "exec", "compile", "__import__"}
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id in dangerous:
                    flags.append(f"dangerous_name:{node.id}")
                if isinstance(node, ast.Attribute) and node.attr in {"system", "popen", "eval", "exec"}:
                    flags.append(f"dangerous_attr:{node.attr}")
        except SyntaxError as e:
            flags.append(f"syntax_error: line {getattr(e, 'lineno', '?')}: {e.msg}")
        return flags

    def _run_docker(self, code: str, timeout: int) -> subprocess.CompletedProcess:
        """Run code in Docker by feeding stdin (Windows-safe)."""
        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--network",
            "none",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "python:3.12-slim",
            "python",
            "-",
        ]
        return subprocess.run(
            cmd,
            input=code,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _count_tests(self, stdout: str, stderr: str) -> Tuple[int, int]:
        combined = stdout + "\n" + stderr
        m = re.search(r"(\d+)\s+passed", combined)
        passed = int(m.group(1)) if m else 0
        m = re.search(r"(\d+)\s+failed", combined)
        failed = int(m.group(1)) if m else 0
        if passed or failed:
            return passed, passed + failed
        m = re.search(r"Ran\s+(\d+)\s+tests?", combined)
        if m:
            total = int(m.group(1))
            if "OK" in combined:
                return total, total
            return 0, total
        if "passed" in combined.lower():
            return 1, 1
        if "failed" in combined.lower() or "error" in combined.lower():
            return 0, 1
        return 0, 0
