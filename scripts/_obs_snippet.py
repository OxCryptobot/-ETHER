    def _obs_tests(self) -> Dict[str, Any]:
        assert self.workspace is not None
        from core.repo_oracle import run_project_pytest

        result = run_project_pytest(
            self.workspace, test_args=self.test_args, timeout=self.pytest_timeout
        )
        stdout = result.get("stdout") or ""
        fails = []
        for line in stdout.splitlines():
            s = line.strip()
            if s.startswith("FAILED ") or s.startswith("E ") or "ValueError" in s or "AssertionError" in s:
                fails.append(s[:160])
        return {
            "ok": bool(result.get("ok")),
            "score": float(result.get("score") or 0.0),
            "returncode": result.get("returncode"),
            "failed": fails[:12],
            "stdout": stdout[-1800:],
            "stderr": (result.get("stderr") or "")[-800:],
        }
