"""Clear Quartz — Docker or local subprocess; auto-fallback when Docker missing."""

from __future__ import annotations

import ast
import os
import re
import shutil
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
    """docker | local | auto (prefer docker if present, else local)."""
    raw = (os.getenv("ETHER_SANDBOX_BACKEND") or "auto").strip().lower()
    if raw in ("local", "subprocess", "native"):
        return "local"
    if raw == "docker":
        return "docker"
    # auto
    if shutil.which("docker"):
        return "docker"
    return "local"


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
            # An explicit ETHER_SANDBOX_BACKEND=docker is a security decision,
            # not a preference: silently re-running model-authored code on the
            # host defeats the only real isolation boundary this system has.
            # Only "auto" may degrade, and only with a visible flag.
            if backend == "auto":
                try:
                    result = self._run_local(code, request.timeout_seconds)
                    execution_time = time.perf_counter() - start
                    tests_passed, total_tests = self._count_tests(
                        result.stdout, result.stderr, result.returncode, code
                    )
                    flags = self._static_analysis(code)
                    return ResponseEnvelope(
                        task_id=request.task_id,
                        source_gem="clear-quartz",
                        payload=ClearQuartzResponse(
                            stdout=result.stdout,
                            stderr=result.stderr,
                            exit_code=result.returncode,
                            total_tests=total_tests,
                            tests_passed=tests_passed,
                            security_flags=flags + ["sandbox_fallback:local"],
                            execution_time=round(execution_time, 3),
                            static_analysis_score=0.0 if flags else 1.0,
                        ),
                    )
                except Exception:
                    pass
            msg = (
                "Docker is not installed or not in PATH"
                if backend == "docker"
                else f"Local Python runner missing: {e}"
            )
            hint = (
                "Install Docker, or set ETHER_SANDBOX_BACKEND=local"
                if backend == "docker"
                else "Ensure python3 is on PATH or set ETHER_SANDBOX_PYTHON"
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
        if backend == "local":
            return self._run_local(code, timeout)
        try:
            from gems.clear_quartz.warm import warm_enabled, run_in_warm

            if warm_enabled():
                warm = run_in_warm(code, timeout)
                if warm is not None:
                    return warm
        except Exception:
            pass
        # Deliberately NOT catching FileNotFoundError here. Doing so silently
        # re-ran model-authored code on the host — with the host filesystem,
        # network and PATH — while the operator had explicitly asked for
        # container isolation, and left `security_flags` empty so nothing
        # downstream could tell. Letting it propagate reaches execute()'s
        # handler, which is the only place `sandbox_fallback:local` is ever
        # attached, and which refuses the downgrade when backend == "docker".
        return self._run_docker(code, timeout)

    def _run_local(self, code: str, timeout: int) -> subprocess.CompletedProcess:
        """No Docker: host Python with -I. Weaker isolation — trusted local use only."""
        env = {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": "",
            "HOME": tempfile.gettempdir(),
            "TMPDIR": tempfile.gettempdir(),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        }
        py = os.getenv("ETHER_SANDBOX_PYTHON") or (
            "python3" if sys.platform != "win32" else sys.executable
        )
        return subprocess.run(
            [py, "-I", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=tempfile.gettempdir(),
        )

    def _run_docker(self, code: str, timeout: int) -> subprocess.CompletedProcess:
        # Hardening beyond --network/--memory/--cpus. The container previously
        # ran as uid 0 with the full default capability set and a writable
        # root filesystem; SECURITY.md already claimed --read-only was in use.
        # --pids-limit matters because a fork bomb in the container otherwise
        # exhausts host PIDs.
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
            "--pids-limit",
            "128",
            "--user",
            "65534:65534",  # nobody
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            # Writable scratch so legitimate code can still use temp files,
            # but capped and wiped with the container.
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--env",
            "HOME=/tmp",
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
        from core.assert_audit import count_real_asserts, uses_test_runner

        combined = stdout + "\n" + stderr

        # Counts printed on stdout are only trustworthy when a real runner
        # produced them. The sandboxed code is model-authored, so otherwise a
        # bare `print("42 passed")` manufactures a perfect verification score.
        if uses_test_runner(code):
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

        # Count only assertions that could actually have failed: parsed from
        # the AST (so comments and strings don't count), excluding tautologies,
        # dead branches, and failures swallowed by an enclosing try/except.
        assert_count = count_real_asserts(code)
        if assert_count:
            if exit_code == 0 and "AssertionError" not in combined:
                return assert_count, assert_count
            return 0, assert_count
        return 0, 0
