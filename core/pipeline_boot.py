"""Patch Pipeline.run once at import — contextual bandit + prepare_code_for_sandbox."""

from __future__ import annotations

_patched = False


def apply() -> None:
    global _patched
    if _patched:
        return
    from core.pipeline import Pipeline
    from core.pipeline_patch import select_strategy, prep_code
    from core.schemas import ClearQuartzRequest, Envelope

    original = Pipeline.run

    def run(self, objective: str, prefer_local: bool = True, critique: bool = False):
        # temporarily wrap policy.select if learning path uses it inside original
        policy = self.policy
        _orig_select = policy.select

        def _select(*args, **kwargs):
            return select_strategy(policy, objective)

        policy.select = _select  # type: ignore
        try:
            # We cannot easily inject prep without replacing sandbox section;
            # monkeypatch registry.execute for clear-quartz only during this run.
            reg = self.registry
            _orig_exec = reg.execute

            def _exec(request):
                try:
                    if getattr(request, "target_gem", None) == "clear-quartz":
                        payload = request.payload
                        if isinstance(payload, ClearQuartzRequest):
                            code2, meta = prep_code(payload.code, objective)
                            payload = ClearQuartzRequest(
                                code=code2,
                                language=getattr(payload, "language", "python") or "python",
                                test_command=getattr(payload, "test_command", None),
                            )
                            request = Envelope(
                                task_id=request.task_id,
                                target_gem=request.target_gem,
                                payload=payload,
                                timeout_seconds=request.timeout_seconds,
                                context=getattr(request, "context", None),
                            )
                except Exception:
                    pass
                return _orig_exec(request)

            reg.execute = _exec  # type: ignore
            try:
                return original(self, objective, prefer_local=prefer_local, critique=critique)
            finally:
                reg.execute = _orig_exec  # type: ignore
        finally:
            policy.select = _orig_select  # type: ignore

    Pipeline.run = run  # type: ignore
    _patched = True
