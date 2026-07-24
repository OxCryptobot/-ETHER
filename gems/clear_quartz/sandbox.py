"""Clear Quartz sandbox implementation."""

from __future__ import annotations

import ast
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional

from core.schemas import (
    ClearQuartzRequest,
    ClearQuartzResponse,
    Envelope,
    ResponseEnvelope,
    GemError,
    GemErrorType,
)


class ClearQuartz:
    """Dual-tier sandbox gem (fast = Docker)."""

    def __init__(self, work_dir: Optional[Path] = None):
        self.work_dir = work_dir or Path("/tmp/ether-sandbox")
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

        payload: ClearQuartzRequest = request.payload
        start = time.perf_counter()

        try:
            security_flags = self._static_analysis(payload.code)

            with tempfile.TemporaryDirectory(dir=self.work_dir) as tmp:
                code_path = Path(tmp) / "code.py"
                code_path.write_text(payload.code, encoding="utf-8")

                result = self._run_docker(
                    code_path=code_path,
                    timeout=request.timeout_seconds,
                )

            execution_time = time.perf_counter() - start
            tests_passed, total_tests = self._count_tests(result.stdout, result.stderr)

            response_payload = ClearQuartzResponse(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                total_tests=total_tests,
                tests_passed=tests_passed,
                security_flags=security_flags,
                execution_time=round(execution_time, 3),
                static_analysis_score=0.0 if security_flags else 1.0,
            )

            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                payload=response_payload,
            )

        except subprocess.TimeoutExpired:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                error=GemError(
                    type=GemErrorType.TIMEOUT,
                    message=f"Sandbox timed out after {request.timeout_seconds}s",
                    recoverable=True,
                    suggested_action="Increase timeout or simplify the code",
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
                    suggested_action="Install Docker and ensure it is running",
                ),
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                error=GemError(
                    type=GemErrorType.RUNTIME,
                    message=str(e),
                    recoverable=True,
                ),
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
        except SyntaxError:
            flags.append("syntax_error")

        return flags

    def _run_docker(self, code_path: Path, timeout: int) -> subprocess.CompletedProcess:
        cmd = [
            "docker",
            "run",
            "--rm",
            "--network", "none",
            "--read-only",
            "--memory", "512m",
            "--cpus", "1",
            "-v", f"{code_path}:/code.py:ro",
            "python:3.12-slim",
            "python", "/code.py",
        ]

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _count_tests(self, stdout: str, stderr: str) -> tuple[int, int]:
        combined = (stdout + stderr).lower()
        if "passed" in combined:
            return 1, 1
        if "failed" in combined or "error" in combined:
            return 0, 1
        return 0, 0
