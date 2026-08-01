    def _execute_multifile(
        self,
        request: Envelope,
        payload: ClearQuartzRequest,
        files: dict,
        start: float,
    ) -> ResponseEnvelope:
        """Seed staging workspace and run project pytest (shared with repo_oracle).

        Clear Quartz remains the truth container: observe only, no code mutation.
        """
        from pathlib import Path as _P

        joined = "\n\n".join(f"# file: {k}\n{v}" for k, v in sorted(files.items()))
        security_flags = self._static_analysis(joined)

        fixture_raw = (
            getattr(payload, "fixture_root", None)
            or (os.getenv("ETHER_TOOL_RUNTIME_FIXTURE") or "").strip()
            or (os.getenv("ETHER_REPO_ORACLE_FIXTURE") or "").strip()
            or ""
        )
        fixture_root = _P(fixture_raw) if fixture_raw else None
        if fixture_root is not None and not fixture_root.is_dir():
            fixture_root = None

        test_args = list(getattr(payload, "test_args", None) or []) or ["tests"]
        timeout = int(getattr(request, "timeout_seconds", None) or 60)

        try:
            from core.repo_oracle import score_repo_edit

            result = score_repo_edit(
                files,
                fixture_root=fixture_root,
                test_args=test_args,
                timeout=timeout,
                cleanup=True,
            )
        except Exception as e:
            return ResponseEnvelope(
                task_id=request.task_id,
                source_gem="clear-quartz",
                error=GemError(
                    type=GemErrorType.RUNTIME,
                    message=f"multifile sandbox: {type(e).__name__}: {e}"[:300],
                    recoverable=True,
                ),
            )

        execution_time = time.perf_counter() - start
        ok = bool(result.get("ok"))
        stdout = str(result.get("stdout") or "")
        stderr = str(result.get("stderr") or "")
        m_pass = re.search(r"(\d+)\s+passed", stdout + "\n" + stderr)
        m_fail = re.search(r"(\d+)\s+failed", stdout + "\n" + stderr)
        passed = int(m_pass.group(1)) if m_pass else 0
        failed = int(m_fail.group(1)) if m_fail else 0
        if passed or failed:
            total_tests = passed + failed
            tests_passed = passed
        elif ok:
            total_tests, tests_passed = 1, 1
        else:
            total_tests, tests_passed = 1, 0

        backend = sandbox_backend()
        flags = list(security_flags)
        flags.append("multifile:project_pytest")
        if backend == "local":
            flags.append("sandbox_fallback:local")

        return ResponseEnvelope(
            task_id=request.task_id,
            source_gem="clear-quartz",
            payload=ClearQuartzResponse(
                stdout=stdout[-4000:],
                stderr=(stderr or str(result.get("error") or ""))[-2000:],
                exit_code=0 if ok else int(result.get("returncode") or 1),
                total_tests=total_tests,
                tests_passed=tests_passed,
                security_flags=flags,
                execution_time=round(execution_time, 3),
                static_analysis_score=0.0 if security_flags else 1.0,
            ),
        )

