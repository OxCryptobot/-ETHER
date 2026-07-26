"""Clear Quartz — Docker or local subprocess sandbox (ETHER_SANDBOX_BACKEND)."""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
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


def sandbox_backend() -> str:
    """docker (default) | local (no Docker; still timeout + static analysis)."""
    return (os.getenv("ETHER_SANDBOX_BACKEND") or "docker").strip().lower()


class ClearQuartz:
    def __init__(self, work_dir: Optional[Path] = None):
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
        code = payload.code
        try:
            from core.pipeline_hooks import prepare_code_for_sandbox

            code, _meta = prepare_code_for_sandbox(code, objective="")
        except Exception:
            try:
                from core.test_synth import synthesize_asserts

                code, _ = synthesize_asserts(code, objective="")
            except Exception:
                pass
            try:
                from core.assert_harness import ensure_harness

                code, _ = ensure_harness(code)
            except Exception:
                pass

        try:
            security_flags = self._static_analysis(code)
            result = self._run(code, request.timeout_seconds)
            execution_time = time.perf_counter() - start
            tests_passed, total_tests = self._count_tests(
                result.stdout, result.stderr, result.returncode, code
            )

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
        except FileNotFoundError as e:
            backend = sandbox_backend()
            msg = (
                "Docker is not installed or not in PATH"
                if backend == "docker"
                else f"Local Python runner missing: {e}"
            )
            hint = (
                "Install Docker, or set ETHER_SANDBOX_BACKEND=local for subprocess execution"
                if backend == "docker"
                else "Ensure python3 is on PATH"
            )
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                error=GemError(
                    type=GemErrorType.DEPENDENCY,
                    message=msg,
                    recoverable=True,
                    suggested_action=hint,
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

    def _run(self, code: str, timeout: int) -> subprocess.CompletedProcess:
        backend = sandbox_backend()
        if backend in ("local", "subprocess", "native"):
            return self._run_local(code, timeout)
        try:
            from gems.clear_quartz.warm import warm_enabled, run_in_warm

            if warm_enabled():
                warm = run_in_warm(code, timeout)
                if warm is not None:
                    return warm
        except Exception:
            pass
        return self._run_docker(code, timeout)

    def _run_local(self, code: str, timeout: int) -> subprocess.CompletedProcess:
        """No Docker: run with host Python. Weaker isolation — trusted local use only."""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": "",
            "HOME": tempfile.gettempdir(),
            "TMPDIR": tempfile.gettempdir(),
            "LANG": "C.UTF-8",
        }
        # Prefer python3 on Linux
        py = os.getenv("ETHER_SANDBOX_PYTHON") or ("python3" if sys.platform != "win32" else sys.executable)
        return subprocess.run(
            [py, "-I", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=tempfile.gettempdir(),
        )

    def _run_docker(self, code: str, timeout: int) -> subprocess.CompletedProcess:
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

    def _count_tests(
        self, stdout: str, stderr: str, exit_code: int, code: str
    ) -> Tuple[int, int]:
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
            if "OK" in combined and exit_code == 0:
                return total, total
            return 0, total
        assert_count = len(re.findall(r"\bassert\b", code))
        if assert_count:
            if exit_code == 0 and "AssertionError" not in combined:
                return assert_count, assert_count
            return 0, assert_count
        return 0, 0
