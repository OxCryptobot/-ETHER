"""One loop. The model writes. The tests keep. No stub is injected."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

STATE = "artifacts/sota.json"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def load(root: Path) -> Dict[str, Any]:
    path = Path(root) / STATE
    if not path.is_file():
        return {"day": _today(), "goals": [], "lessons": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"day": _today(), "goals": [], "lessons": []}
    return data if isinstance(data, dict) else {"day": _today(), "goals": [], "lessons": []}


def save(root: Path, state: Dict[str, Any]) -> None:
    path = Path(root) / STATE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def goals() -> List[Dict[str, str]]:
    """Real work. The test names the result. The file does not contain the answer."""
    return [
        {
            "id": "packed_count",
            "file": "core/kernel/context_budget.py",
            "symbol": "packed_count",
            "test": (
                "from core.kernel.context_budget import packed_count\n"
                "def test_count():\n"
                "    assert packed_count('### a\\n### b\\n') == 2\n"
                "    assert packed_count('') == 0\n"
            ),
        },
        {
            "id": "fits_empty",
            "file": "core/kernel/context_budget.py",
            "symbol": "fits",
            "test": (
                "from core.kernel.context_budget import fits\n"
                "def test_empty():\n"
                "    assert fits('') is True\n"
            ),
        },
        {
            "id": "file_count",
            "file": "core/kernel/context_budget.py",
            "symbol": "file_count",
            "test": (
                "from core.kernel.context_budget import file_count\n"
                "def test_files():\n"
                "    assert file_count('### a.py\\n### b.py\\n') == 2\n"
                "    assert file_count('') == 0\n"
            ),
        },
        {
            "id": "is_over",
            "file": "core/kernel/context_budget.py",
            "symbol": "is_over",
            "test": (
                "from core.kernel.context_budget import is_over\n"
                "def test_over():\n"
                "    assert is_over('x' * 10000) is True\n"
                "    assert is_over('') is False\n"
            ),
        },
        {
            "id": "budget_of",
            "file": "core/kernel/context_budget.py",
            "symbol": "budget_of",
            "test": (
                "from core.kernel.context_budget import budget_of\n"
                "def test_budget():\n"
                "    assert budget_of(8192) == 7200\n"
                "    assert budget_of(100) >= 800\n"
            ),
        },
    ]


def recall(root: Path) -> str:
    """The last thing that worked, or the last tool trace."""
    state = load(root)
    lessons = [str(item) for item in (state.get("lessons") or [])]
    for item in reversed(lessons):
        if "trace" in item or "passed" in item:
            return item
    return lessons[-1] if lessons else ""


# Ladder generator: after the fixed list and the learn.py ladder, seed goals from
# repo state. Each package gets its own id prefix so equal stems never collide.
# core/agent (the writer's own brain) and scripts/ are never seeded.
SEED_DIRS = (("core/kernel", "describe_"), ("core/loop", "describe_loop_"), ("core/spine", "describe_spine_"))


def describe_goal(rel_dir: str, prefix: str, name: str) -> Dict[str, str]:
    mod = rel_dir.replace("/", ".") + "." + name
    return {
        "id": f"{prefix}{name}",
        "file": f"{rel_dir}/{name}.py",
        "symbol": "describe",
        "test": (
            f"from {mod} import describe\n"
            "def test_describe():\n"
            f"    assert describe() == '{name}'\n"
        ),
    }


def generate(root: Path, done: set, failed: set) -> Dict[str, str] | None:
    """When the fixed list and the ladder are done, pick the next module with no describe."""
    for rel_dir, prefix in SEED_DIRS:
        pkg = Path(root) / rel_dir
        if not pkg.is_dir():
            continue
        for path in sorted(pkg.glob("*.py")):
            name = path.stem
            goal_id = f"{prefix}{name}"
            if goal_id in done or goal_id in failed or name.startswith("_"):
                continue
            body = path.read_text(encoding="utf-8", errors="ignore")
            if "def describe" in body:
                continue
            return describe_goal(rel_dir, prefix, name)
    return None


def seed_depth(root: Path) -> int:
    """How many repo-state goals generate() can still hand out (for host_main.json)."""
    if not legacy_allowed():
        return 0
    state = load(root)
    done = {str(item) for item in (state.get("goals") or [])}
    failed = {str(item) for item in (state.get("skipped") or [])}
    n = 0
    for rel_dir, prefix in SEED_DIRS:
        pkg = Path(root) / rel_dir
        for path in sorted(pkg.glob("*.py")) if pkg.is_dir() else []:
            gid = f"{prefix}{path.stem}"
            if path.stem.startswith("_") or gid in done or gid in failed:
                continue
            if "def describe" not in path.read_text(encoding="utf-8", errors="ignore"):
                n += 1
    return n


def _defines(root: Path, rel: str, symbol: str) -> bool:
    path = Path(root) / rel
    if not path.is_file():
        return False
    body = path.read_text(encoding="utf-8", errors="ignore")
    return f"def {symbol}(" in body


def goal_site(goal_id: str) -> tuple | None:
    """(file, symbol) for a known goal id, else None."""
    for item in goals():
        if item["id"] == goal_id:
            return item["file"], item["symbol"]
    from core.agent.learn import LADDER

    if goal_id in LADDER:
        return LADDER[goal_id]
    site = _describe_site(goal_id)
    return (site[0] + f"/{site[2]}.py", "describe") if site else None


def _describe_site(goal_id: str) -> tuple | None:
    """(rel_dir, prefix, name) for a describe goal id; longest prefix wins."""
    for rel_dir, prefix in sorted(SEED_DIRS, key=lambda x: -len(x[1])):
        if goal_id.startswith(prefix) and len(goal_id) > len(prefix):
            return rel_dir, prefix, goal_id[len(prefix):]
    return None


def lost_kept(root: Path, state: Dict[str, Any] | None = None) -> List[str]:
    """Goals sota.json calls kept whose function is not in the file on disk.

    The honest gate kept them once, but the edit never reached this tree (lost to
    a reset or a failed publish). They go back in the queue; the gate decides again.
    """
    state = state if state is not None else load(root)
    lost: List[str] = []
    from core.agent.goal_quality import filler_id

    for goal_id in [str(item) for item in (state.get("goals") or [])]:
        if filler_id(goal_id) and not legacy_allowed():
            continue  # retired filler is never requeued (it would re-add junk)
        site = goal_site(goal_id)
        if site is None:
            continue
        rel, symbol = site
        if not (Path(root) / rel).is_file():
            continue
        if not _defines(root, rel, symbol):
            lost.append(goal_id)
    return lost


def _requeue(root: Path, goal_id: str) -> Dict[str, str] | None:
    for item in goals():
        if item["id"] == goal_id:
            return item
    site = _describe_site(goal_id)
    if site is not None:
        return {**describe_goal(*site), "requeued": "lost_kept"}
    return None


def legacy_allowed() -> bool:
    """The fixed list, the learn.py ladder and describe() seeding. Every one of their
    prompts holds the answer (spoiler) or their test checks a constant, so with the
    goal-quality guard on (default) they are retired. ETHER_SOTA_LEGACY=1 brings them back."""
    from core.agent.goal_quality import guard_enabled

    return os.getenv("ETHER_SOTA_LEGACY") == "1" or not guard_enabled()


def next_goal(root: Path, skip: Any = ()) -> Dict[str, Any] | None:
    """Real goals (failing tests, lint) first, then refactors (flag), then legacy (flag)."""
    from core.agent import goal_source

    if goal_source.enabled():
        real = goal_source.next_real(root, skip=skip)
        if real is not None:
            return real
    try:
        from core.agent import refactor

        if refactor.enabled():
            item = refactor.next_refactor(root, skip=skip)
            if item is not None:
                return item
    except Exception:
        pass
    if not legacy_allowed():
        return None
    return legacy_next_goal(root)


def legacy_next_goal(root: Path) -> Dict[str, str] | None:
    state = load(root)
    lost = set(lost_kept(root, state))
    done = {str(item) for item in (state.get("goals") or [])} - lost
    lessons = [str(item) for item in (state.get("lessons") or [])]
    failed = set(str(item) for item in (state.get("skipped") or []))
    failed.discard("find_fits")
    failed.update(
        name
        for name in {item.split(" ", 1)[-1].split(":", 1)[0] for item in lessons}
        if sum(item.endswith(f"{name}: no edit") or item.endswith(f"{name}: tests failed") for item in lessons) >= 1
    )
    for item in goals():
        if item["id"] not in done and item["id"] not in failed:
            return item
    from core.agent.learn import next_from

    # A skipped rung must not block the rungs after it. Passing only `done`
    # made next_from return the first skipped rung (find_clamp), which was then
    # dropped, so the ladder never reached find_add and the tick said
    # "queue empty" while host_main showed next_goal: find_add.
    learned = next_from(root, done | failed)
    if learned is not None and learned["id"] not in failed:
        return learned
    for goal_id in sorted(lost - failed):
        item = _requeue(root, goal_id)
        if item is not None:
            return item
    return generate(root, done, failed)


def edit(root: Path, rel: str, old: str, new: str) -> Dict[str, Any]:
    path = (Path(root) / rel).resolve()
    try:
        path.relative_to(Path(root).resolve())
    except ValueError:
        return {"ok": False, "reason": "outside the repo"}
    if not path.is_file() or not old or old == new:
        return {"ok": False, "reason": "patch needs one file and a change"}
    body = path.read_text(encoding="utf-8")
    if body.count(old) != 1:
        return {"ok": False, "reason": "old text must match once"}
    path.write_text(body.replace(old, new, 1), encoding="utf-8")
    return {"ok": True}


def revert(root: Path, rel: str, body: str) -> None:
    (Path(root) / rel).write_text(body, encoding="utf-8")


def test(root: Path, code: str) -> Dict[str, Any]:
    ws = Path(root) / "sota_ws"
    if ws.exists():
        import shutil
        shutil.rmtree(ws)
    ws.mkdir()
    (ws / "tests").mkdir()
    (ws / "tests" / "test_goal.py").write_text(code, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "-q", "--tb=line"],
        cwd=str(ws),
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(root)},
    )
    return {"ok": proc.returncode == 0, "tail": ((proc.stdout or "") + (proc.stderr or ""))[-300:]}


def remember(root: Path, goal: str, lesson: str, *, kept: bool, file: str = "") -> None:
    state = load(root)
    if kept and goal not in (state.get("goals") or []):
        state.setdefault("goals", []).append(goal)
    if kept and file:
        files = [str(item) for item in (state.get("files") or [])]
        if file not in files:
            files.append(file)
        state["files"] = files[-20:]
    lessons = [str(item) for item in (state.get("lessons") or [])]
    line = f"{_today()} {goal}: {lesson}"[:240]
    if line not in lessons:
        lessons.append(line)
    state["lessons"] = lessons[-8:]
    if not kept and ("failed" in lesson or "no edit" in lesson):
        skipped = [str(item) for item in (state.get("skipped") or [])]
        if goal not in skipped:
            skipped.append(goal)
        state["skipped"] = skipped[-40:]
    state["day"] = _today()
    state["last"] = {"goal": goal, "kept": kept, "file": file, "ts": datetime.now(timezone.utc).isoformat()}
    save(root, state)


_INFRA_ERRORS = (ConnectionError, TimeoutError, OSError)


def _guard(ask: Callable[..., str], seen: Dict[str, str]) -> Callable[..., str]:
    """Record an infra outage. An outage is not a lesson and must not skip a goal."""

    def wrapped(prompt: str, n: int = 240, **kw: Any) -> str:
        try:
            return ask(prompt, n=n, **kw)
        except _INFRA_ERRORS as exc:
            seen.setdefault("error", type(exc).__name__)
            raise

    try:
        from core.agent.sampling import accepts_temperature

        wrapped.accepts_temperature = accepts_temperature(ask)  # type: ignore[attr-defined]
    except Exception:
        wrapped.accepts_temperature = False  # type: ignore[attr-defined]
    return wrapped


def _infra(goal: Dict[str, str], seen: Dict[str, str]) -> Dict[str, Any]:
    return {
        "ok": False,
        "honest": True,
        "infra": True,
        "goal": goal["id"],
        "note": f"infra: {seen.get('error')}",
    }


def _one(root: Path, ask: Callable[..., str], skip: Any = ()) -> Dict[str, Any]:
    """One attempt. The honest gate's outcome trains the existing bandit."""
    try:
        goal = next_goal(root, skip=skip)
    except Exception:
        goal = None
    try:
        from core.agent.outcome import choose, record

        pick = choose(root, goal=goal)
    except Exception:
        pick = None
    t0 = time.monotonic()
    result = _attempt(root, ask, pick, skip, goal=goal)
    if pick is not None:
        pick.trace["secs"] = round(time.monotonic() - t0, 2)  # wall time: guard runs + model calls
    if pick is not None and result.get("note") != "queue empty":
        try:
            row = record(root, pick, result)
            result["learn"] = {"arm": pick.arm, "bucket": pick.bucket, "kind": row.get("kind"),
                               "reward": row.get("reward"), "promote": row.get("promote")}
        except Exception as exc:
            result["learn_error"] = type(exc).__name__
    return result


def _attempt_real(root: Path, ask: Callable[..., str], goal: Dict[str, Any], pick: Any,
                  seen: Dict[str, str]) -> Dict[str, Any]:
    """Failing test / lint goal. Unspoiled prompt, tool edit, target + regression gate."""
    from core.agent import goal_source as gs
    from core.agent.goal_quality import check

    trace: Dict[str, Any] = pick.trace if pick is not None else {}
    root = Path(root)
    base = {"goal": goal["id"], "kind": goal["kind"], "file": goal["file"]}
    if goal["kind"] == "fix_test" and (goal.get("targets") or goal.get("alt_targets")):
        from core.agent import multi_edit

        if multi_edit.enabled():
            tries_so_far = int((gs.load_index(root).get("tries") or {}).get(goal["id"], 0))
            places = multi_edit.trim_to_fit(root, goal, multi_edit.targets_of(goal, tries_so_far))
            if places:
                return _attempt_multi(root, ask, goal, pick, seen, places)
            if goal.get("targets"):
                gs.mark(root, goal["id"], kept=False)
                return {**base, "ok": False, "honest": True, "note": "rejected: places exceed the reply cap"}
        elif goal.get("targets"):
            return {**base, "ok": False, "honest": True, "note": "multi goal: ETHER_MULTI_EDIT off"}
    suite = gs.guard_suite(root, goal)
    before = gs.run_pytest(root, suite)
    baseline = before["status"]
    if goal["kind"] == "fix_test" and baseline.get(goal["nodeid"]) == "pass":
        gs.mark(root, goal["id"], kept=True)
        return {**base, "ok": True, "honest": True, "note": "already present", "resolved": "already_passing"}
    if goal["kind"] == "lint" and gs.lint_clear(root, goal):
        gs.mark(root, goal["id"], kept=True)
        return {**base, "ok": True, "honest": True, "note": "already present", "resolved": "lint_clear"}
    try:
        from core.agent.bandit import factored_behaviour
        from core.learning import arm_behaviour

        behaviour = (factored_behaviour(pick.arm) or arm_behaviour(pick.arm)) if pick is not None else None
        if pick is not None and pick.arm == "exemplar":
            from core.agent import exemplars

            behaviour = exemplars.behaviour()
    except Exception:
        behaviour = None
    shown: List[Dict[str, Any]] = []
    if getattr(behaviour, "use_exemplars", False):
        try:
            from core.agent import exemplars

            shown = exemplars.retrieve(root, goal, k=1)
        except Exception:
            shown = []
    try:
        from core.agent.bandit import tries_for

        tries = tries_for(pick.arm) if pick is not None else 1
    except Exception:
        tries = 2 if (pick is not None and pick.arm == "repair_heavy") else 1
    feedback = ""
    last: Dict[str, Any] = {}
    trace["spoiler"] = False
    from core.agent import sampling

    tries_before = int((gs.load_index(root).get("tries") or {}).get(goal["id"], 0))
    from core.agent.tree_guard import TreeGuard

    tree = TreeGuard(root).begin()  # batch 9: every path the attempt touches is checked and restored
    for i in range(tries):
        prompt = gs.build_prompt(root, goal, behaviour, feedback=feedback, exemplar=shown)
        if shown and gs.EXEMPLAR_HEAD in prompt:
            trace["exemplar"] = shown[0].get("id")
        try:
            current = (root / goal["file"]).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            current = ""
        q = check(goal, prompt, current)
        trace["spoiler"] = trace["spoiler"] or "spoiler" in q["reasons"]
        trace["prompt_chars"] = len(prompt)
        if not q["ok"]:
            gs.mark(root, goal["id"], kept=False)
            return {**base, "ok": False, "honest": True, "note": "rejected: " + ",".join(q["reasons"])}
        try:
            from core.agent.react import react

            n_reply = gs.reply_tokens(root, goal)
            trace["reply_cap"] = n_reply
            temp = sampling.temp_for(tries_before + i)  # 0.0 unless ETHER_SAMPLE_TEMP is set
            ask_i = sampling.with_temp(ask, temp)
            trace["temp"] = temp if ask_i is not ask else 0.0
            row = react(ask_i, root, prompt, turns=2, n=n_reply)
            text = row.get("text") or ""
            trace["tools"] = ["search"] if row.get("used") else []
        except Exception as exc:
            if seen:
                return _infra(goal, seen)
            return {**base, "ok": False, "honest": False, "error": str(exc)[:200]}
        if seen and not text.strip():
            return _infra(goal, seen)
        trace["reply"] = text[-200:]
        edit = gs.extract_edit(text, goal)
        if not edit["function"] and not edit["assigns"] and not edit.get("span"):
            want = ("`%s = ...`" if goal.get("symbol_kind") == "assign" else "complete function `def %s`")
            feedback = "no " + want % goal["symbol"].split(".")[-1] + " in the reply"
            if goal.get("span"):
                feedback = "no replacement lines for the marked window in the reply"
            last = {**base, "ok": False, "honest": False, "note": "no function"}
            continue
        trace["reply_hash"] = sampling.edit_hash(edit)
        trace["file_hash"] = sampling.file_hash(current, baseline)
        if sampling.dedup_on() and sampling.reverted_before(root, goal["id"], trace["reply_hash"], trace["file_hash"]):
            # the gate already reverted this exact edit on this exact file: reuse its verdict, skip the run
            trace["dedup_skipped"] = True
            feedback = "your reply repeated an edit that already failed the tests; write a different fix"
            last = {**base, "ok": False, "honest": False, "note": "duplicate reply"}
            continue
        applied = gs.apply_edit(root, goal, edit)
        trace["edit_assigns"] = len(applied.get("assigns") or [])
        if not applied.get("ok"):
            feedback = str(applied.get("reason"))
            last = {**base, "ok": False, "honest": False, "note": "no edit: " + feedback}
            continue
        verdict = gs.gate(root, goal, baseline, suite)
        touched = tree.violations([goal["file"]])
        if touched:
            # batch 9 (W1): a diff outside the goal file (tests/ always) is never kept, whatever the tests say
            verdict = {**verdict, "ok": False, "outside": touched}
        if verdict["ok"]:
            try:
                from core.agent import exemplars

                if exemplars.recording():
                    after = (root / goal["file"]).read_text(encoding="utf-8", errors="ignore")
                    exemplars.record_kept(root, goal, applied["original"], after, verdict)
                    if trace.get("exemplar"):
                        exemplars.note_use(root, str(trace["exemplar"]))
            except Exception as exc:
                trace["exemplar_error"] = type(exc).__name__
            gs.mark(root, goal["id"], kept=True)
            for sib in [g for g in gs.load_index(root)["goals"].values()
                        if g.get("nodeid") in set(gs.siblings(root, goal))]:
                gs.mark(root, sib["id"], kept=True)  # resolved by the same edit
            remember(root, goal["id"], "tests passed, 0 regressions" + (" via tool" if trace.get("tools") else ""),
                     kept=True, file=goal["file"])
            return {**base, "ok": True, "honest": True, "tests_ok": True, "regressions": 0,
                    "tx": ["read", "edit", "test", "guard", "promote"], "attempt": i + 1,
                    "suite_n": verdict["suite_n"], "checked": True}
        revert(root, goal["file"], applied["original"])
        restored = tree.restore()  # batch 9: ALL touched paths, not only goal['file']
        feedback = ("regressed: " + ", ".join(verdict["regressions"][:3])) if verdict["n_regressions"] else verdict["tail"]
        note = "regression" if verdict["n_regressions"] else (
            "siblings failed" if verdict.get("target_pass") and verdict.get("siblings_failing") else "tests failed")
        if verdict.get("outside"):
            note = "rejected: touched " + ", ".join(verdict["outside"][:3])
            feedback = "edit only the target function in " + goal["file"]
        last = {**base, "ok": False, "honest": False, "note": note,
                "regressions": verdict["n_regressions"], "siblings_failing": len(verdict.get("siblings_failing") or [])}
        if restored:
            last["restored"] = restored
        if verdict.get("outside"):
            last["outside"] = verdict["outside"][:10]
    gs.mark(root, goal["id"], kept=False)
    remember(root, goal["id"], str(last.get("note") or "tests failed"), kept=False)
    return last


def _attempt_multi(root: Path, ask: Callable[..., str], goal: Dict[str, Any], pick: Any,
                   seen: Dict[str, str], places: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Batch 5 (ETHER_MULTI_EDIT=1): 2-3 places in one FileTx; target + siblings + regression gate."""
    from core.agent import goal_source as gs
    from core.agent import multi_edit
    from core.agent.goal_quality import check

    trace: Dict[str, Any] = pick.trace if pick is not None else {}
    base = {"goal": goal["id"], "kind": goal["kind"], "file": goal["file"], "multi": len(places)}
    suite = multi_edit.guard_suite(root, goal, places)
    before = gs.run_pytest(root, suite)
    baseline = before["status"]
    if baseline.get(goal["nodeid"]) == "pass":
        gs.mark(root, goal["id"], kept=True)
        return {**base, "ok": True, "honest": True, "note": "already present", "resolved": "already_passing"}
    try:
        from core.agent.bandit import factored_behaviour, tries_for
        from core.learning import arm_behaviour

        behaviour = (factored_behaviour(pick.arm) or arm_behaviour(pick.arm)) if pick is not None else None
        tries = tries_for(pick.arm) if pick is not None else 1
    except Exception:
        behaviour, tries = None, 1
    feedback = ""
    last: Dict[str, Any] = {**base, "ok": False, "honest": False, "note": "no edit"}
    trace["spoiler"] = False
    trace["multi"] = len(places)
    from core.agent.tree_guard import TreeGuard

    tree = TreeGuard(root).begin()  # batch 9
    for i in range(tries):
        prompt, kept_places = multi_edit.build_prompt(root, goal, places, behaviour, feedback=feedback)
        if not prompt:
            gs.mark(root, goal["id"], kept=False)
            return {**base, "ok": False, "honest": True, "note": "rejected: places do not fit the context"}
        current = "\n".join((root / t["file"]).read_text(encoding="utf-8", errors="ignore")
                            for t in kept_places if (root / t["file"]).is_file())
        q = check(goal, prompt, current)
        trace["spoiler"] = trace["spoiler"] or "spoiler" in q["reasons"]
        trace["prompt_chars"] = len(prompt)
        if not q["ok"]:
            gs.mark(root, goal["id"], kept=False)
            return {**base, "ok": False, "honest": True, "note": "rejected: " + ",".join(q["reasons"])}
        try:
            from core.agent.react import react

            n_reply = min(gs.reply_max(), max(gs.REPLY_MIN, multi_edit.reply_tokens(root, kept_places)))
            trace["reply_cap"] = n_reply
            row = react(ask, root, prompt, turns=2, n=n_reply)
            text = row.get("text") or ""
            trace["tools"] = ["search"] if row.get("used") else []
        except Exception as exc:
            if seen:
                return _infra(goal, seen)
            return {**base, "ok": False, "honest": False, "error": str(exc)[:200]}
        if seen and not text.strip():
            return _infra(goal, seen)
        trace["reply"] = text[-200:]
        edits, why = multi_edit.extract(text, kept_places)
        if not edits:
            feedback = why
            last = {**base, "ok": False, "honest": False, "note": "no edit: " + why}
            continue
        applied = multi_edit.apply(root, edits)
        if not applied.get("ok"):
            feedback = str(applied.get("reason"))
            last = {**base, "ok": False, "honest": False, "note": "no edit: " + feedback}
            continue
        tx = applied["tx"]
        verdict = gs.gate(root, goal, baseline, suite)
        touched = tree.violations(applied["files"])
        if touched:
            verdict = {**verdict, "ok": False, "outside": touched}
        if verdict["ok"]:
            tx.commit()
            gs.mark(root, goal["id"], kept=True)
            for sib in [g for g in gs.load_index(root)["goals"].values()
                        if g.get("nodeid") in set(gs.siblings(root, goal))]:
                gs.mark(root, sib["id"], kept=True)
            for rel in applied["files"]:
                remember(root, goal["id"], f"tests passed, 0 regressions, {len(applied['files'])} files",
                         kept=True, file=rel)
            return {**base, "ok": True, "honest": True, "tests_ok": True, "regressions": 0,
                    "tx": ["read", "edit", "test", "guard", "promote"], "attempt": i + 1,
                    "files": applied["files"], "suite_n": verdict["suite_n"], "checked": True}
        tx.revert()
        restored = tree.restore()
        feedback = ("regressed: " + ", ".join(verdict["regressions"][:3])) if verdict["n_regressions"] else verdict["tail"]
        note = "regression" if verdict["n_regressions"] else (
            "siblings failed" if verdict.get("target_pass") and verdict.get("siblings_failing") else "tests failed")
        if verdict.get("outside"):
            note = "rejected: touched " + ", ".join(verdict["outside"][:3])
        last = {**base, "ok": False, "honest": False, "note": note, "regressions": verdict["n_regressions"],
                "reverted": sorted(set(applied["files"]) | set(restored))}
    gs.mark(root, goal["id"], kept=False)
    remember(root, goal["id"], str(last.get("note") or "tests failed"), kept=False)
    return last


def _attempt(root: Path, ask: Callable[..., str], pick: Any = None, skip: Any = (),
             goal: Any = None) -> Dict[str, Any]:
    trace: Dict[str, Any] = pick.trace if pick is not None else {}
    seen: Dict[str, str] = {}
    ask = _guard(ask, seen)
    if goal is None:
        goal = next_goal(root, skip=skip)
    if goal is None:
        return {"ok": False, "honest": True, "note": "queue empty"}
    if goal.get("kind") in ("fix_test", "lint"):
        return _attempt_real(root, ask, goal, pick, seen)
    if goal.get("kind") == "refactor":
        from core.agent import refactor

        return refactor.attempt(root, goal, pick)
    path = Path(root) / goal["file"]
    original = path.read_text(encoding="utf-8") if path.is_file() else ""
    from core.agent.skills import route

    found = route(root, "search", query=goal["symbol"])
    hits = found.get("hits") or []
    if goal["file"] in hits:
        remember(root, goal["id"], "already present", kept=True, file=goal["file"])
        return {"ok": True, "honest": True, "goal": goal["id"], "file": goal["file"], "note": "found by search"}
    if f"def {goal['symbol']}" in original and goal["id"] != "packed_count":
        remember(root, goal["id"], "already present", kept=True, file=goal["file"])
        return {"ok": True, "honest": True, "goal": goal["id"], "file": goal["file"], "note": "already present"}
    skeletons = {
        "packed_count": "def packed_count(text: str) -> int:\n    return text.count('### ')",
        "file_count": "def file_count(text: str) -> int:\n    return text.count('### ')",
        "is_over": "def is_over(text: str) -> bool:\n    from core.kernel.context_budget import context_char_budget\n    return len(text or '') > context_char_budget()",
        "budget_of": "def budget_of(model_ctx: int) -> int:\n    tokens = min(int(model_ctx * 0.35), 1800)\n    return max(800, tokens * 4)",
    }
    from core.agent.learn import skeleton as learned_skeleton

    body = skeletons.get(goal["id"]) or learned_skeleton(goal)
    if goal["symbol"] == "describe" and not body:
        name = Path(goal["file"]).stem
        body = f"def describe() -> str:\n    return '{name}'"
    lesson = recall(root)
    find = goal.get("find")
    if find:
        from core.agent.learn import skeleton as learned_skeleton

        body = learned_skeleton(goal) or body
        prompt = (
            f"Last: {lesson}\n"
            f"Find the file that defines {find}. "
            f"Reply with {{\"tool\":\"search\",\"args\":{{\"query\":\"{find}\"}}}}\n"
            f"Then write only:\n{body}\n"
        )
    elif body:
        prompt = f"Last: {lesson}\nWrite only this function. Do not explain.\n{body}\n"
    else:
        prompt = (
            f"Last: {lesson}\n"
            f"Add def {goal['symbol']}. The test is:\n{goal['test']}\n"
            "Reply with the whole function only.\n"
        )
    if pick is not None and getattr(pick, "addon", ""):
        prompt = prompt + pick.addon.strip() + "\n"
    trace["spoiler"] = bool(body)
    try:
        from core.agent.react import react

        row = react(ask, root, prompt, turns=3)
        text = row.get("text") or ""
        used_tool = bool(row.get("used"))
    except Exception as exc:
        if seen:
            return _infra(goal, seen)
        return {"ok": False, "honest": False, "goal": goal["id"], "error": str(exc)[:200]}
    if seen and not text.strip():
        return _infra(goal, seen)
    from core.agent.skills import call

    tool = call(root, text)
    if tool is not None and tool.get("skill") == "search" and tool.get("hits"):
        used_tool = True
        hits = [str(item).replace("\\", "/") for item in tool["hits"]]
        # The goal's test imports from goal["file"]; editing another file can
        # never pass. Keep the target and record what the search found.
        hit = goal["file"] if goal["file"] in hits else hits[0]
        try:
            text = ask(
                f"Found {hit}. Write only this:\n{body or ('def ' + goal['symbol'])}\n", n=240)
        except Exception:
            if seen:
                return _infra(goal, seen)
            raise
    if text.strip().startswith("READ") or text.strip().startswith("{"):
        try:
            text = ask("Copy this and nothing else:\n" + prompt, n=240)
        except Exception:
            pass
    start = text.find("def ")
    fn = text[start:].strip() if start >= 0 else ""
    trace["tools"] = ["search"] if used_tool else []
    trace["reply"] = text[-200:]
    if not fn.startswith(f"def {goal['symbol']}"):
        if body:
            try:
                text = ask("Copy this and nothing else:\n" + body, n=240)
            except Exception:
                pass
            start = text.find("def ")
            fn = text[start:].strip() if start >= 0 else ""
    if not fn.startswith(f"def {goal['symbol']}"):
        if seen:
            return _infra(goal, seen)
        remember(root, goal["id"], "no edit", kept=False)
        return {"ok": False, "honest": False, "goal": goal["id"], "note": "no function", "reply": text[-200:]}
    new = original.rstrip() + "\n\n" + fn + "\n"
    result = edit(root, goal["file"], original, new)
    if not result.get("ok"):
        remember(root, goal["id"], "no edit", kept=False)
        return {"ok": False, "honest": False, "goal": goal["id"], "note": result.get("reason")}
    checked = test(root, goal["test"])
    if not checked["ok"]:
        revert(root, goal["file"], original)
        remember(root, goal["id"], "tests failed", kept=False)
        return {"ok": False, "honest": False, "goal": goal["id"], "note": "tests failed"}
    remember(root, goal["id"], "tests passed" + (" via tool" if used_tool else ""), kept=True, file=goal["file"])
    from core.agent.checker import check

    verified = check(root, goal["id"])
    return {
        "ok": True,
        "honest": True,
        "goal": goal["id"],
        "file": goal["file"],
        "tx": ["search", "edit", "test", "check", "promote"],
        "tests_ok": True,
        "checked": verified.get("ok"),
    }


def run(root: Path, ask: Callable[..., str]) -> Dict[str, Any]:
    """Adaptive batch. Real goals: at most ETHER_REAL_PER_TICK attempts, a miss moves on.
    Legacy goals keep the old rule (stop on the first miss)."""
    from core.agent.learn import batch_size

    root = Path(root)
    scanned = _maybe_scan(root)
    size = batch_size(root)
    real_cap = int(os.getenv("ETHER_REAL_PER_TICK", "2"))
    kept: List[str] = []
    tried: List[str] = []
    real = 0
    last: Dict[str, Any] = {"ok": False, "honest": True, "note": "none"}
    for _ in range(size):
        row = _one(root, ask, skip=tried)
        if row.get("note") == "queue empty" and tried:
            break  # keep the last real attempt as the tick's result
        last = row
        gid = str(last.get("goal") or "")
        if gid:
            tried.append(gid)
        if last.get("kind") in ("fix_test", "lint", "refactor") and last.get("note") != "already present":
            real += 1
        if last.get("ok"):
            if last.get("note") != "already present":
                kept.append(gid)
            if real >= real_cap:
                break
            continue
        if last.get("infra") or last.get("note") == "queue empty" or not last.get("kind") or real >= real_cap:
            break
    last["batch"] = kept
    last["tried"] = tried
    last["kept_n"] = len(kept)
    last["batch_size"] = size
    if scanned:
        last["scan"] = scanned
    state = load(root)
    state["kept_n"] = len(kept)
    save(root, state)
    return last


SCAN_EVERY_S = int(os.getenv("ETHER_GOAL_SCAN_S", "900"))


def _maybe_scan(root: Path) -> Dict[str, Any] | None:
    """Refresh one shard of the failing-test index when it is stale or the queue is dry."""
    from core.agent import goal_source as gs

    if not gs.enabled() or os.getenv("ETHER_GOAL_SCAN", "1") == "0":
        return None
    data = gs.load_index(root)
    stale = True
    try:
        ts = datetime.fromisoformat(str(data.get("scan_ts")))
        stale = (datetime.now(timezone.utc) - ts).total_seconds() > SCAN_EVERY_S
    except Exception:
        pass
    if not stale and gs.next_real(root) is not None:
        return None
    try:
        row = gs.scan(root, n_files=int(os.getenv("ETHER_GOAL_SCAN_FILES", "8")))
        data = gs.load_index(root)
        data["scan_ts"] = datetime.now(timezone.utc).isoformat()
        gs.save_index(root, data)
        return row
    except Exception as exc:
        return {"ok": False, "error": type(exc).__name__}
