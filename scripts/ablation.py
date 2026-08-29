#!/usr/bin/env python3
"""ETHER vs the bare model it runs on. The one number this project has never had.

WHAT THIS MEASURES, AND WHY IT DOES NOT EXIST YET
--------------------------------------------------
@ETHER's premise is that plan -> retrieve -> generate -> sandbox -> audit ->
repair makes a small local model write better code than that model writes
alone. Every "baseline" in this repo is ETHER's own previous score
(`memory/bench/baseline.json`, the guardian ratchet, the scoreboard). There is
not one number of the form `ETHER - bare model`. Without it, the pipeline could
be worth +30 points, 0 points, or negative, and nothing in the repo would tell
the difference.

This harness runs the SAME model, with the SAME decode settings, on the SAME
tasks, through three arms:

  bare      objective only, one message straight to the router. No pipeline.
  bare+sys  objective plus three lines of system prompt. No pipeline.
  ether     the full `Pipeline.run(objective, holdout_test=...)`.

`bare+sys` is the arm that matters most. If a system prompt saying "write only
Python" captures most of the delta, then the pipeline is mostly an expensive
markdown stripper, and that is the single most valuable thing this project
could learn about itself. The arm table is data (`ARMS`), so
`ether-no-retrieval` / `ether-no-repair` drop in as one entry each.

RULES THIS HARNESS ENFORCES ON ITSELF
--------------------------------------
1. One grader for every sample: `core.holdout.grade_against_holdout`. Never an
   exit code — `scripts/hidden_quiz.py` kept a private divergent copy that
   scored `exit_code == 0`, and `sys.exit(0)` passed it. The ether arm is
   re-graded here even though the pipeline already graded it, so all three arms
   are scored by the same call on the same string.
2. Every prompt goes through `core.prompt_guard.check` BEFORE it is sent. A
   leaked sample is excluded from the denominator and counted separately. It is
   never a pass. (BM25 retrieval leaked assertions into 12 of 15 bench prompts
   once; that is how a pass_rate of 0.933 came to be published.)
3. Fixed seeds, explicit decode. Every sampling parameter is written into the
   environment `gems/rose_quartz/router.py::decode_options` reads, and recorded
   in the output next to the model name, the model digest, the git commit and
   the dataset id. A run whose decode is unknown proves nothing.
4. Statistics that support the claim, not decorate it: bootstrap CI (clustered
   on tasks, because samples within a task are not independent), McNemar's
   exact test on the paired per-task outcomes, and an explicit statement of the
   minimum detectable effect so a null result is not read as "no difference".
5. Resumable. ~360 generations at ~29s is an overnight run; every completed
   sample is appended to JSONL and fsync'd before the next one starts.

USAGE
-----
    ./.venv/bin/python scripts/ablation.py --dry-run          # validate + plan
    ./.venv/bin/python scripts/ablation.py --limit 5 --samples 1
    ./.venv/bin/python scripts/ablation.py                     # the full run
    ./.venv/bin/python scripts/ablation.py --resume            # after a crash

Outputs `memory/bench/ablation_latest.json`, a timestamped copy,
`memory/bench/ablation_latest.md` and the append-only
`memory/bench/ablation_samples.jsonl`.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.dotenv import load_dotenv  # noqa: E402
from core.holdout import grade_against_holdout  # noqa: E402
from core.prompt_guard import check as guard_check  # noqa: E402

load_dotenv(ROOT / ".env")

try:  # numpy is already a transitive dependency here; scipy is NOT installed.
    import numpy as _np
except Exception:  # pragma: no cover - exercised only on a numpy-less box
    _np = None  # type: ignore[assignment]


# --------------------------------------------------------------------------
# Dataset
# --------------------------------------------------------------------------

HEADROOM_PATH = ROOT / "memory" / "quizzes" / "headroom_v1.json"
OUT_DIR = ROOT / "memory" / "bench"
SAMPLES_JSONL = OUT_DIR / "ablation_samples.jsonl"

# Datasets whose tasks are trivial for the bare model measure nothing: if bare
# scores 0.95 there is no headroom for a pipeline to recover. headroom_v1 is
# built for exactly that reason; bench is the fallback and is expected to be
# ceiling-bound.
FALLBACK_NOTE = (
    "scripts/bench.py::load_tasks() — 15 one-liner tasks chosen as a REGRESSION "
    "suite, not a headroom suite. A bare 35B model is expected to score near "
    "ceiling on them, which leaves the pipeline almost nothing to improve. "
    "Treat any null result on this dataset as uninformative."
)


def _normalize_task(raw: Dict[str, Any], index: int) -> Dict[str, Any]:
    """Canonical task shape, whatever the source file calls its fields."""
    tid = str(raw.get("id") or raw.get("task_id") or f"t{index:02d}")
    return {
        "id": tid,
        "title": str(raw.get("title") or tid),
        # `prompt` / `hidden_test` is the hidden_humaneval spelling; accept it
        # so this harness can be pointed at any of the existing quiz files.
        "objective": str(raw.get("objective") or raw.get("prompt") or ""),
        "holdout_test": str(raw.get("holdout_test") or raw.get("hidden_test") or ""),
        "difficulty": str(raw.get("difficulty") or ""),
    }


def load_dataset(path: Optional[Path] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Load the headroom set, or fall back to the bench tasks, and say which.

    Returns `(tasks, meta)`. `meta["source"]` is `"headroom"` or `"bench"` and
    is echoed on stdout and into the results file: a number produced on the
    fallback set means something different from one produced on the headroom
    set, and the reader must not have to guess which they are looking at.
    """
    path = Path(path) if path is not None else HEADROOM_PATH
    meta: Dict[str, Any] = {
        "source": "headroom",
        "path": str(path),
        "id": path.stem,
        "note": "",
        "sha256": "",
    }

    raw_text = ""
    data: Any = None
    if path.exists():
        try:
            raw_text = path.read_text(encoding="utf-8")
            data = json.loads(raw_text)
        except Exception as e:
            meta["note"] = f"unreadable ({e}); fell back to bench"
            data = None

    if data is not None:
        if isinstance(data, dict):
            items = data.get("tasks") or data.get("items") or []
            meta["id"] = str(data.get("id") or data.get("name") or path.stem)
            if data.get("version") is not None:
                meta["version"] = data["version"]
        else:
            items = data
        tasks = [_normalize_task(t, i) for i, t in enumerate(items, 1) if isinstance(t, dict)]
        if tasks:
            meta["sha256"] = hashlib.sha256(raw_text.encode("utf-8", "replace")).hexdigest()[:16]
            meta["n"] = len(tasks)
            return tasks, meta
        meta["note"] = "file present but contained no tasks; fell back to bench"
    elif not meta["note"]:
        meta["note"] = f"{path.name} absent; fell back to bench"

    from scripts.bench import load_tasks as bench_load_tasks

    tasks = [_normalize_task(t, i) for i, t in enumerate(bench_load_tasks(), 1)]
    meta.update(
        {
            "source": "bench",
            "path": str(ROOT / "scripts" / "bench.py"),
            "id": "bench_v2",
            "n": len(tasks),
            "warning": FALLBACK_NOTE,
        }
    )
    meta["sha256"] = hashlib.sha256(
        json.dumps(tasks, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return tasks, meta


def audit_dataset(tasks: Sequence[Dict[str, Any]]) -> List[str]:
    """Ways these tasks hand the model their own answer. Empty means gradeable.

    Delegates to the single shared auditor (`core.curriculum.check_task_leakage`
    via `scripts.bench.audit_tasks`) rather than growing a second opinion about
    what a leak is.
    """
    from scripts.bench import audit_tasks

    problems = list(audit_tasks(list(tasks)))
    for t in tasks:
        if not (t.get("holdout_test") or "").strip():
            problems.append(f"{t.get('id')}: no holdout_test — ungradeable")
        if not (t.get("objective") or "").strip():
            problems.append(f"{t.get('id')}: empty objective")
    return problems


_INSTRUCTION_RE = re.compile(
    r"^\s*write only python[^\n]*\n+(implement\s*:?\s*\n+)?", re.IGNORECASE
)


def has_instruction_preamble(objective: str) -> bool:
    """Does this objective already carry the instruction `bare+sys` supplies?

    `scripts/bench.py` prefixes every objective with "Write only Python, no
    markdown.\\n\\nImplement:\\n\\n". If the dataset does that, `bare` is not
    instruction-free and the `bare` vs `bare+sys` contrast degrades to "same
    words, user turn vs system turn" — which is a real finding, but a different
    one, and the reader has to be told.
    """
    return bool(_INSTRUCTION_RE.match(objective or ""))


def strip_instruction_preamble(objective: str) -> str:
    """Remove that preamble, for `--bare-strip-preamble`."""
    return _INSTRUCTION_RE.sub("", objective or "", count=1).lstrip()


# --------------------------------------------------------------------------
# Arms
# --------------------------------------------------------------------------

# Deliberately short. The claim under test is that three lines of system prompt
# do NOT capture what the pipeline does; a long engineered prompt would make
# that a different, weaker claim.
SYSTEM_PROMPT = "Write only Python. No markdown, no explanation."


@dataclass(frozen=True)
class Arm:
    """One experimental condition.

    `kind="direct"` goes straight to the router with `messages`; `kind="ether"`
    calls `Pipeline.run`. `env` is applied around the generation only, so
    pipeline ablations are declared here rather than coded as branches.
    """

    name: str
    kind: str  # "direct" | "ether"
    description: str
    system_prompt: str = ""
    env: Dict[str, str] = field(default_factory=dict)
    # Rough seconds per generation relative to a single bare call; used only by
    # the dry-run cost estimate.
    cost_factor: float = 1.0


ARMS: Dict[str, Arm] = {
    "bare": Arm(
        name="bare",
        kind="direct",
        description="objective only, single user message to the router; no pipeline",
    ),
    "bare+sys": Arm(
        name="bare+sys",
        kind="direct",
        description=f"system prompt {SYSTEM_PROMPT!r} + objective; no pipeline",
        system_prompt=SYSTEM_PROMPT,
    ),
    "ether": Arm(
        name="ether",
        kind="ether",
        description="full Pipeline.run(objective, holdout_test=...)",
        cost_factor=2.2,
    ),
    # Extension points. Not in DEFAULT_ARMS: adding them to the overnight run is
    # a deliberate choice about GPU hours, not a default.
    "ether-no-retrieval": Arm(
        name="ether-no-retrieval",
        kind="ether",
        description="pipeline with workspace context / experience / BM25 retrieval off",
        env={
            "ETHER_USE_CONTEXT": "0",
            "ETHER_EXPERIENCE": "0",
            "ETHER_RAG_BM25": "0",
        },
        cost_factor=2.0,
    ),
    "ether-no-repair": Arm(
        name="ether-no-repair",
        kind="ether",
        description="pipeline with the sandbox repair retry off",
        env={"ETHER_SANDBOX_RETRY": "0"},
        cost_factor=1.6,
    ),
    # The agent loop (core/agent_loop.py). Measured against the SAME clean
    # baseline the current pipeline failed to beat: bare 0.317, bare+sys 0.333,
    # ether 0.292 on qwen2.5:3b, 360 samples, zero leaks. Any claim for the loop
    # has to clear 0.333, not clear the old contaminated 0.875.
    "ether-loop": Arm(
        name="ether-loop",
        kind="ether",
        description="agent loop: generate -> verify -> repair -> select best",
        env={"ETHER_AGENT_LOOP": "1"},
        # N candidates instead of one generation, so it costs roughly N times a
        # bare call. Judge any gain against that: a 4x cost for a 2pp lift is a
        # bad trade, and the harness should make that visible rather than
        # reporting pass rate alone.
        cost_factor=4.0,
    ),
}

DEFAULT_ARMS = ["bare", "bare+sys", "ether"]
# The paired comparison the project actually needs. bare+sys, not bare, is the
# honest control: beating a model that was never told to emit code is not a
# result.
PRIMARY_PAIR = ("ether", "bare+sys")


# --------------------------------------------------------------------------
# Decode control
# --------------------------------------------------------------------------

# name -> the env var gems/rose_quartz/router.py::decode_options actually reads.
DECODE_ENV = {
    "temperature": "ETHER_TEMPERATURE",
    "top_p": "ETHER_TOP_P",
    "top_k": "ETHER_TOP_K",
    "num_ctx": "ETHER_NUM_CTX",
    "presence_penalty": "ETHER_PRESENCE_PENALTY",
    "frequency_penalty": "ETHER_FREQUENCY_PENALTY",
    "repeat_penalty": "ETHER_REPEAT_PENALTY",
}

DEFAULT_DECODE: Dict[str, Any] = {
    "temperature": 0.2,
    "top_p": 0.9,
    "top_k": 40,
    "num_ctx": 32768,
    "presence_penalty": 0.0,
    "frequency_penalty": 0.0,
    "repeat_penalty": 1.0,
}

DEFAULT_SEEDS = [1, 2, 3]
MAX_TOKENS = 4096


@contextmanager
def decode_env(
    decode: Dict[str, Any], seed: int, extra: Optional[Dict[str, str]] = None
) -> Iterator[Dict[str, str]]:
    """Pin sampling for one generation, then put the environment back.

    Set through the environment on purpose: `decode_options` reads it at call
    time, so this reaches the router, the repair retry and the burst path
    without any of them needing to know an ablation is running. The seed is
    per-sample, so sample k of every arm is drawn with the same seed and the
    arms differ only in the prompt/pipeline.
    """
    updates: Dict[str, str] = {
        env_name: str(decode[key]) for key, env_name in DECODE_ENV.items() if key in decode
    }
    updates["ETHER_SEED"] = str(seed)
    updates.update(extra or {})
    previous = {k: os.environ.get(k) for k in updates}
    os.environ.update(updates)
    try:
        yield dict(updates)
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def model_fingerprint(model: Optional[str] = None, probe: bool = True) -> Dict[str, Any]:
    """Model name plus digest, so "same model" is checkable and not asserted.

    `ollama show` reads the manifest; it does not load weights, so this is safe
    to call next to somebody else's finetune. Best effort: a missing digest is
    recorded as missing rather than raising, because the run is still worth
    having.
    """
    name = model or os.getenv("ETHER_PRIMARY_MODEL", "qwen3.5:4b")
    info: Dict[str, Any] = {
        "model": name,
        "digest": "",
        "parameter_size": "",
        "quantization": "",
        "source": "not probed",
    }
    if not probe:
        return info

    try:
        proc = subprocess.run(
            ["ollama", "show", name],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            info["source"] = "ollama show"
            info["show"] = proc.stdout.strip()[:2000]
            for line in proc.stdout.splitlines():
                low = line.strip().lower()
                if low.startswith("parameters ") and not info["parameter_size"]:
                    info["parameter_size"] = line.split(None, 1)[1].strip()
                elif low.startswith("quantization"):
                    info["quantization"] = line.split(None, 1)[1].strip()
    except Exception as e:
        info["show_error"] = str(e)[:200]

    # `ollama show` does not print the manifest digest; /api/tags does.
    try:
        import httpx

        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        resp = httpx.get(f"{base}/api/tags", timeout=10.0)
        resp.raise_for_status()
        for entry in resp.json().get("models", []):
            if entry.get("name") == name or entry.get("model") == name:
                info["digest"] = str(entry.get("digest") or "")[:24]
                details = entry.get("details") or {}
                info["parameter_size"] = info["parameter_size"] or str(
                    details.get("parameter_size") or ""
                )
                info["quantization"] = info["quantization"] or str(
                    details.get("quantization_level") or ""
                )
                info["size_bytes"] = entry.get("size")
                if info["source"] == "not probed":
                    info["source"] = "/api/tags"
                break
    except Exception as e:
        info["tags_error"] = str(e)[:200]

    if not info["digest"]:
        info["warning"] = "no digest — cannot prove which weights produced this run"
    return info


def git_commit() -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        sha = proc.stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(ROOT), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=15,
        ).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except Exception:
        return ""


# --------------------------------------------------------------------------
# Statistics (stdlib + numpy; scipy is NOT installed on this box)
# --------------------------------------------------------------------------


def bootstrap_ci(
    values: Sequence[float],
    *,
    resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 20260727,
) -> Tuple[float, float]:
    """Percentile bootstrap CI for the mean of `values`.

    `values` are the per-resampling-unit means. Pass one value per TASK, not
    one per sample: three samples of the same task are three draws of the same
    problem, and treating them as independent shrinks the interval by ~sqrt(3)
    and manufactures significance.
    """
    vals = [float(v) for v in values]
    n = len(vals)
    if n == 0:
        return (0.0, 0.0)
    if n == 1 or len(set(vals)) == 1:
        return (vals[0], vals[0])

    lo_q, hi_q = alpha / 2.0, 1.0 - alpha / 2.0
    if _np is not None:
        rng = _np.random.default_rng(seed)
        arr = _np.asarray(vals, dtype=float)
        idx = rng.integers(0, n, size=(int(resamples), n))
        means = arr[idx].mean(axis=1)
        lo, hi = _np.quantile(means, [lo_q, hi_q])
        return (float(lo), float(hi))

    import random  # pragma: no cover - numpy is installed here

    rng_py = random.Random(seed)
    means = sorted(
        sum(vals[rng_py.randrange(n)] for _ in range(n)) / n for _ in range(int(resamples))
    )
    lo = means[max(0, int(math.floor(lo_q * len(means))))]
    hi = means[min(len(means) - 1, int(math.ceil(hi_q * len(means))) - 1)]
    return (float(lo), float(hi))


def mcnemar_exact(b: int, c: int) -> Dict[str, Any]:
    """Two-sided exact McNemar (binomial sign test on the discordant pairs).

    `b` = tasks arm A passed and arm B failed; `c` = the reverse. Concordant
    pairs carry no information about the difference and are excluded, which is
    the whole point of the paired test: with ~40 tasks, an unpaired comparison
    of two arms on the same problems throws away most of the power.

        p = min(1, 2 * sum_{i=0..min(b,c)} C(n, i) * 0.5^n),  n = b + c

    Worked check used by the tests: b=10, c=2 -> n=12,
    sum = C(12,0)+C(12,1)+C(12,2) = 1+12+66 = 79, p = 2*79/4096 = 0.038574...
    """
    b, c = int(b), int(c)
    n = b + c
    if n == 0:
        return {
            "b": b,
            "c": c,
            "n_discordant": 0,
            "p_value": 1.0,
            "favours": "neither",
            "detail": "no discordant pairs — the arms agreed on every task",
        }
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    p = min(1.0, 2.0 * tail)
    return {
        "b": b,
        "c": c,
        "n_discordant": n,
        "p_value": p,
        "favours": "A" if b > c else ("B" if c > b else "neither"),
        "detail": f"{b} tasks only A passed, {c} tasks only B passed",
    }


def paired_table(a: Dict[str, bool], b: Dict[str, bool]) -> Dict[str, int]:
    """Contingency counts over the task ids both arms actually completed."""
    shared = sorted(set(a) & set(b))
    both = sum(1 for t in shared if a[t] and b[t])
    only_a = sum(1 for t in shared if a[t] and not b[t])
    only_b = sum(1 for t in shared if b[t] and not a[t])
    neither = sum(1 for t in shared if not a[t] and not b[t])
    return {
        "n_tasks": len(shared),
        "both_pass": both,
        "only_a": only_a,
        "only_b": only_b,
        "neither": neither,
    }


def paired_delta_ci(
    a_rates: Dict[str, float],
    b_rates: Dict[str, float],
    *,
    resamples: int = 10_000,
    alpha: float = 0.05,
    seed: int = 20260727,
) -> Dict[str, Any]:
    """Bootstrap CI for the per-task mean difference `a - b`.

    McNemar on pass@1 is the significance test, but it throws away samples 2..N
    of every task. This uses all of them: the resampling unit is still the task
    (the pairing is preserved, which is where the power comes from), and the
    statistic is the mean of the per-task rate differences. It is the interval
    to quote for the headline "ETHER - bare+sys = X".
    """
    shared = sorted(set(a_rates) & set(b_rates))
    diffs = [a_rates[t] - b_rates[t] for t in shared]
    if not diffs:
        return {"n_tasks": 0, "delta": 0.0, "ci95": [0.0, 0.0], "excludes_zero": False}
    lo, hi = bootstrap_ci(diffs, resamples=resamples, alpha=alpha, seed=seed)
    delta = sum(diffs) / len(diffs)
    return {
        "n_tasks": len(diffs),
        "delta": round(delta, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "excludes_zero": bool(lo > 0.0 or hi < 0.0),
        "unit": "mean per-task pass rate difference over all samples",
    }


def min_detectable_effect(n_tasks: int, alpha: float = 0.05) -> Dict[str, Any]:
    """What this experiment can and cannot see. State it before reading the p.

    Exact McNemar needs `k` discordant pairs ALL in one direction before it can
    reach `alpha`: `2 * 0.5^k <= alpha`, so k=6 at alpha=0.05 (k=5 gives
    p=0.0625). With 40 tasks that is a floor of 6/40 = 15 percentage points in
    the best case where the arms never disagree in ETHER's disfavour. Realistic
    discordance is two-sided, so the true MDE is larger.

    This is why a null result here must be reported as "underpowered", not as
    "the pipeline does not help".
    """
    n_tasks = max(0, int(n_tasks))
    k = 1
    while 2.0 * (0.5**k) > alpha and k < 64:
        k += 1
    best_case_pp = (k / n_tasks * 100.0) if n_tasks else float("inf")
    if not n_tasks:
        note = "no tasks"
    elif n_tasks < k:
        note = (
            f"UNDERPOWERED BY CONSTRUCTION: exact McNemar needs at least {k} discordant pairs "
            f"to reach p<={alpha}, and there are only {n_tasks} tasks. No outcome of this run "
            "can be statistically significant."
        )
    else:
        note = (
            f"exact McNemar cannot reach p<={alpha} with fewer than {k} discordant pairs, "
            f"and only if every one of them favours the same arm. On {n_tasks} tasks that "
            f"is a floor of {best_case_pp:.1f} percentage points of pass@1 difference; with "
            "two-sided disagreement the real minimum detectable effect is larger. A p>alpha "
            "here means 'not enough tasks to tell', not 'no effect'."
        )
    return {
        "alpha": alpha,
        "n_tasks": n_tasks,
        "min_one_sided_discordant_pairs": k,
        "best_case_mde_pp": round(min(best_case_pp, 100.0), 1) if n_tasks else None,
        "note": note,
    }


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------


def extract_code(text: str) -> str:
    """Best-effort code out of a raw completion.

    Deliberately GENEROUS to the baseline arms. A model with no system prompt
    answers with prose around a ```python block; scoring that as a syntax error
    would measure formatting compliance and flatter ETHER — the direction of
    the bias must be against the hypothesis, not for it.

    The `ether` arm is graded on whatever the pipeline actually executed
    (`Pipeline._strip`), because re-extracting there would grade a different
    string than the one ETHER ran through its own sandbox and audit.
    """
    text = (text or "").strip()
    if not text:
        return ""
    fenced = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.DOTALL)
    if fenced:
        return "\n\n".join(block.strip() for block in fenced if block.strip()).strip()
    if text.startswith("```"):  # unterminated fence
        lines = text.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def build_messages(arm: Arm, objective: str) -> List[Dict[str, str]]:
    """The exact message list a direct arm sends. Also what the guard inspects."""
    messages: List[Dict[str, str]] = []
    if arm.system_prompt:
        messages.append({"role": "system", "content": arm.system_prompt})
    messages.append({"role": "user", "content": objective})
    return messages


def messages_text(messages: Sequence[Dict[str, str]]) -> str:
    return "\n\n".join((m.get("content") or "") for m in messages)


class RouterClient:
    """One message in, one completion out. No plan, no retrieval, no repair."""

    def __init__(self, registry: Any = None) -> None:
        self._registry = registry

    @property
    def registry(self) -> Any:
        if self._registry is None:
            from core.registry import build_default_registry

            self._registry = build_default_registry()
        return self._registry

    def complete(
        self, messages: Sequence[Dict[str, str]], max_tokens: int = MAX_TOKENS
    ) -> Dict[str, Any]:
        from core.schemas import ChatMessage, Envelope, RoseQuartzRequest, RoseQuartzResponse

        env = Envelope(
            task_id=uuid4(),
            target_gem="rose-quartz",
            payload=RoseQuartzRequest(
                messages=[ChatMessage(role=m["role"], content=m["content"]) for m in messages],
                prefer_local=True,
                max_tokens=max_tokens,
            ),
        )
        response = self.registry.execute(env)
        if response.error or not isinstance(response.payload, RoseQuartzResponse):
            return {
                "content": "",
                "model_used": "",
                "error": response.error.message if response.error else "no router payload",
            }
        return {
            "content": response.payload.content or "",
            "model_used": response.payload.model_used or "",
            "tokens": int(getattr(response.payload, "tokens", 0) or 0),
            "error": "",
        }


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


def sample_key(task_id: str, arm: str, seed: int) -> str:
    return f"{task_id}|{arm}|{seed}"


def load_completed(jsonl_path: Path, config_key: str = "") -> Dict[str, Dict[str, Any]]:
    """Completed (task, arm, seed) rows from a previous run of the SAME config.

    Rows written under a different model/decode/dataset are ignored rather than
    reused: resuming across a config change would silently mix two experiments
    into one table, which is the failure mode this whole file exists to avoid.
    """
    done: Dict[str, Dict[str, Any]] = {}
    if not Path(jsonl_path).exists():
        return done
    for line in Path(jsonl_path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue  # a torn last line after a crash is expected; skip it
        if not all(k in row for k in ("task_id", "arm", "seed")):
            continue
        if config_key and row.get("config_key") and row["config_key"] != config_key:
            continue
        done[sample_key(str(row["task_id"]), str(row["arm"]), int(row["seed"]))] = row
    return done


class Ablation:
    """Runs the arms, grades every sample the same way, and never loses work."""

    def __init__(
        self,
        tasks: Sequence[Dict[str, Any]],
        arms: Sequence[Arm],
        seeds: Sequence[int],
        *,
        decode: Optional[Dict[str, Any]] = None,
        jsonl_path: Path = SAMPLES_JSONL,
        out_dir: Path = OUT_DIR,
        resume: bool = False,
        dataset_meta: Optional[Dict[str, Any]] = None,
        model_info: Optional[Dict[str, Any]] = None,
        router: Any = None,
        pipeline_factory: Optional[Callable[[], Any]] = None,
        # Resolved at call time, not bound at def time, so a test can swap the
        # module attribute and so there is exactly one place either can come
        # from. `grade` defaults to the ONLY grader this project is allowed to
        # use: core.holdout.grade_against_holdout.
        grade: Optional[Callable[..., Dict[str, Any]]] = None,
        guard: Optional[Callable[[str, str], Dict[str, Any]]] = None,
        log: Callable[[str], None] = print,
        strip_bare_preamble: bool = False,
        max_tokens: int = MAX_TOKENS,
        run_id: str = "",
        resamples: int = 10_000,
    ) -> None:
        self.tasks = [dict(t) for t in tasks]
        self.arms = list(arms)
        self.seeds = [int(s) for s in seeds]
        self.decode = dict(decode or DEFAULT_DECODE)
        self.jsonl_path = Path(jsonl_path)
        self.out_dir = Path(out_dir)
        self.resume = resume
        self.dataset_meta = dict(dataset_meta or {})
        self.model_info = dict(model_info or {})
        self.grade = grade or grade_against_holdout
        self.guard = guard or guard_check
        self.log = log
        self.strip_bare_preamble = strip_bare_preamble
        self.max_tokens = max_tokens
        self.resamples = int(resamples)
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._router = router if router is not None else RouterClient()
        self._pipeline_factory = pipeline_factory or self._default_pipeline_factory
        self._pipelines: Dict[str, Any] = {}
        self.rows: List[Dict[str, Any]] = []

    # -- config identity ---------------------------------------------------

    @property
    def config_key(self) -> str:
        """Everything that must be identical for two rows to belong together."""
        payload = json.dumps(
            {
                "model": self.model_info.get("model", ""),
                "digest": self.model_info.get("digest", ""),
                "decode": self.decode,
                "dataset": self.dataset_meta.get("sha256") or self.dataset_meta.get("id", ""),
                "max_tokens": self.max_tokens,
                "strip_bare_preamble": self.strip_bare_preamble,
            },
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _default_pipeline_factory() -> Any:
        from core.pipeline import Pipeline

        return Pipeline()

    def _pipeline_for(self, arm: Arm) -> Any:
        # One Pipeline per arm: `env` differs per arm, and a Pipeline built
        # under one env must not be reused under another.
        if arm.name not in self._pipelines:
            self._pipelines[arm.name] = self._pipeline_factory()
        return self._pipelines[arm.name]

    # -- planning ----------------------------------------------------------

    def objective_for(self, arm: Arm, task: Dict[str, Any]) -> str:
        objective = task.get("objective") or ""
        if self.strip_bare_preamble and arm.kind == "direct" and not arm.system_prompt:
            return strip_instruction_preamble(objective)
        return objective

    def plan(self) -> Dict[str, Any]:
        """Everything checkable without calling the model."""
        total = len(self.tasks) * len(self.arms) * len(self.seeds)
        done = load_completed(self.jsonl_path, self.config_key) if self.resume else {}
        remaining = [k for k in self._all_keys() if k not in done]

        preflight: List[Dict[str, Any]] = []
        leaks = 0
        for task in self.tasks:
            for arm in self.arms:
                prompt = self.preflight_prompt(arm, task)
                verdict = self.guard(prompt, task.get("holdout_test") or "")
                if not verdict.get("clean"):
                    leaks += 1
                    preflight.append(
                        {
                            "task_id": task["id"],
                            "arm": arm.name,
                            "leaks": verdict.get("leaks", [])[:3],
                        }
                    )
        est = self.estimate_seconds(len(remaining))
        return {
            "run_id": self.run_id,
            "config_key": self.config_key,
            "tasks": len(self.tasks),
            "arms": [a.name for a in self.arms],
            "seeds": self.seeds,
            "generations_total": total,
            "generations_done": len(done),
            "generations_remaining": len(remaining),
            "preflight_leaks": leaks,
            "preflight_detail": preflight,
            "estimated_seconds": est,
            "estimated_hms": _hms(est),
            "instruction_preamble_tasks": sum(
                1 for t in self.tasks if has_instruction_preamble(t.get("objective") or "")
            ),
        }

    def _all_keys(self) -> List[str]:
        return [
            sample_key(t["id"], a.name, s)
            for t in self.tasks
            for a in self.arms
            for s in self.seeds
        ]

    def estimate_seconds(
        self, remaining: Optional[int] = None, secs_per_gen: float = 29.0
    ) -> float:
        """Wall clock, weighted by arm: the pipeline is not one generation."""
        per_arm = {a.name: secs_per_gen * a.cost_factor for a in self.arms}
        if remaining is None:
            return sum(per_arm[a.name] for a in self.arms) * len(self.tasks) * len(self.seeds)
        # Remaining work is not necessarily evenly spread across arms; use the
        # mean arm cost, which is the honest approximation for a plan number.
        mean_cost = sum(per_arm.values()) / max(1, len(per_arm))
        return mean_cost * remaining

    def preflight_prompt(self, arm: Arm, task: Dict[str, Any]) -> str:
        """The text checked for leaks BEFORE anything is sent.

        For a direct arm this is exactly what goes over the wire. For the ether
        arm it is only the objective: the pipeline composes retrieval blocks
        internally, so its full prompt cannot exist before it runs. That is why
        the ether path is ALSO checked afterwards, via the pipeline's own
        `prompt_guard` stage, which sees every prompt that was actually sent.
        """
        objective = self.objective_for(arm, task)
        if arm.kind == "direct":
            return messages_text(build_messages(arm, objective))
        return objective

    # -- execution ---------------------------------------------------------

    def run(self) -> Dict[str, Any]:
        done = load_completed(self.jsonl_path, self.config_key) if self.resume else {}
        self.rows = list(done.values())
        todo = [
            (t, a, s)
            for t in self.tasks
            for a in self.arms
            for s in self.seeds
            if sample_key(t["id"], a.name, s) not in done
        ]
        total = len(self.tasks) * len(self.arms) * len(self.seeds)
        if done:
            self.log(f"resume: {len(done)} samples already completed, {len(todo)} to go")

        started = time.perf_counter()
        for i, (task, arm, seed) in enumerate(todo, 1):
            t0 = time.perf_counter()
            row = self.run_sample(task, arm, seed)
            self._append(row)
            self.rows.append(row)
            elapsed = time.perf_counter() - t0
            verdict = "LEAK" if row["leaked"] else ("PASS" if row["passed"] else "fail")
            self.log(
                f"[{len(done) + i}/{total}] {task['id']:<8} {arm.name:<18} seed={seed} "
                f"-> {verdict} ({elapsed:.1f}s)"
                + (f" — {row['reason'][:70]}" if row["reason"] and not row["passed"] else "")
            )
            self._abort_if_broken(len(done) + i, total)
        if todo:
            self.log(f"generation done in {_hms(time.perf_counter() - started)}")
        return self.summarize()

    # A run is only worth its wall clock if the samples are real. An earlier
    # 360-sample run completed after four hours with 214 samples (59%) errored
    # — 147 timeouts and 64 empty completions from a reasoning model whose
    # thinking tokens exhausted num_predict. Errors count as fails, so the
    # experiment measured infrastructure failure, and it measured it unevenly:
    # bare 83, bare+sys 72, ether 59. The apparent ETHER advantage tracked its
    # lower error count almost exactly.
    ABORT_MIN_SAMPLES = 15
    ABORT_ERROR_RATE = 0.25

    def _abort_if_broken(self, done_count: int, total: int) -> None:
        """Stop early rather than spend hours producing an uninterpretable result."""
        if done_count < self.ABORT_MIN_SAMPLES:
            return
        errored = [r for r in self.rows if r.get("error")]
        rate = len(errored) / max(1, len(self.rows))
        if rate < self.ABORT_ERROR_RATE:
            return
        top: Dict[str, int] = {}
        for r in errored:
            key = str(r.get("error") or "")[:60]
            top[key] = top.get(key, 0) + 1
        worst = sorted(top.items(), key=lambda kv: -kv[1])[:3]
        detail = "; ".join(f"{n}x {msg}" for msg, n in worst)
        raise SystemExit(
            f"\nABORTING after {len(self.rows)} samples: {len(errored)} errored "
            f"({rate:.0%}, threshold {self.ABORT_ERROR_RATE:.0%}).\n"
            f"Most common: {detail}\n"
            f"Errors count as failures, so continuing would produce a number that "
            f"measures infrastructure, not code quality.\n"
            f"Fix the cause, then rerun with --resume (completed samples are kept).\n"
            f"If the model is a reasoner returning empty content, thinking tokens are "
            f"consuming num_predict: set ETHER_THINKING=0 or raise --max-tokens.\n"
        )

    def run_sample(self, task: Dict[str, Any], arm: Arm, seed: int) -> Dict[str, Any]:
        """One (task, arm, seed). Always returns a row; never raises."""
        objective = self.objective_for(arm, task)
        holdout = task.get("holdout_test") or ""
        row: Dict[str, Any] = {
            "run_id": self.run_id,
            "config_key": self.config_key,
            "ts": datetime.now(timezone.utc).isoformat(),
            "task_id": task["id"],
            "title": task.get("title", ""),
            "difficulty": task.get("difficulty", ""),
            "arm": arm.name,
            "seed": seed,
            "passed": False,
            "leaked": False,
            "leak_detail": "",
            "error": "",
            "reason": "",
            "code_chars": 0,
            "model_used": "",
            "duration_s": 0.0,
            "exit_code": None,
            "holdout_asserts": 0,
            "pipeline_holdout_ok": None,
        }

        # 1. Leak check BEFORE the model sees anything.
        pre = self.guard(self.preflight_prompt(arm, task), holdout)
        if not pre.get("clean"):
            row["leaked"] = True
            row["leak_detail"] = f"preflight: {pre.get('detail', '')}"[:300]
            row["reason"] = "excluded — holdout reached the prompt"
            return row

        t0 = time.perf_counter()
        try:
            with decode_env(self.decode, seed, arm.env):
                gen = self._generate(arm, task, objective, holdout)
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"[:300]
            row["reason"] = row["error"]
            row["duration_s"] = round(time.perf_counter() - t0, 2)
            return row
        row["duration_s"] = round(time.perf_counter() - t0, 2)
        row["model_used"] = gen.get("model_used", "")
        row["code_chars"] = len(gen.get("code") or "")
        row["pipeline_holdout_ok"] = gen.get("pipeline_holdout_ok")
        for extra in ("status", "retries", "used_burst", "strategy", "confidence"):
            if extra in gen:
                row[extra] = gen[extra]

        # 2. A leak the pipeline detected in its own composed prompt.
        if gen.get("leaked"):
            row["leaked"] = True
            row["leak_detail"] = str(gen.get("leak_detail") or "pipeline prompt_guard")[:300]
            row["reason"] = "excluded — holdout reached the prompt"
            return row

        if gen.get("error"):
            row["error"] = str(gen["error"])[:300]
            row["reason"] = row["error"]
            return row

        # 3. One grader for every arm. Exit codes grade nothing.
        graded = self.grade(gen.get("code") or "", holdout)
        row["exit_code"] = graded.get("exit_code")
        row["holdout_asserts"] = int(graded.get("asserts") or 0)
        row["reason"] = str(graded.get("reason") or "")[:300]
        if graded.get("leaked"):
            # The holdout turned up inside the generated code: whatever this is,
            # it is not evidence the model solved the task.
            row["leaked"] = True
            row["leak_detail"] = "holdout text present in generated code"
            row["passed"] = False
            return row
        row["passed"] = bool(graded.get("ok"))
        if row["pipeline_holdout_ok"] is not None:
            row["grade_agrees_with_pipeline"] = bool(row["pipeline_holdout_ok"]) == row["passed"]
        return row

    def _generate(
        self, arm: Arm, task: Dict[str, Any], objective: str, holdout: str
    ) -> Dict[str, Any]:
        if arm.kind == "direct":
            messages = build_messages(arm, objective)
            out = self._router.complete(messages, max_tokens=self.max_tokens)
            return {
                "code": extract_code(out.get("content") or ""),
                "model_used": out.get("model_used", ""),
                "error": out.get("error", ""),
            }

        if arm.kind == "ether":
            pipe = self._pipeline_for(arm)
            # Detected, not assumed — scripts/bench.py does the same. An older
            # Pipeline without the parameter still runs; it just does not grade
            # internally, and this harness re-grades every sample anyway.
            if _accepts_holdout(pipe.run):
                result = pipe.run(objective, holdout_test=holdout)
            else:
                result = pipe.run(objective)
            stages = list(getattr(result, "stages", None) or [])
            leak_stage = next(
                (
                    s
                    for s in stages
                    if getattr(s, "stage", "") == "prompt_guard" and not getattr(s, "success", True)
                ),
                None,
            )
            return {
                "code": getattr(result, "generated_code", "") or "",
                "model_used": _model_from_stages(stages),
                "error": getattr(result, "error", "") or "",
                "leaked": leak_stage is not None,
                "leak_detail": getattr(leak_stage, "detail", "") if leak_stage else "",
                "pipeline_holdout_ok": getattr(result, "holdout_ok", None),
                "status": getattr(result, "status", ""),
                "retries": int(getattr(result, "retries", 0) or 0),
                "used_burst": bool(getattr(result, "used_burst", False)),
                "strategy": getattr(result, "strategy", ""),
                "confidence": float(getattr(result, "confidence", 0.0) or 0.0),
            }

        raise ValueError(f"unknown arm kind: {arm.kind}")

    def _append(self, row: Dict[str, Any]) -> None:
        """Durably append one sample. A crash at hour 3 loses at most this one."""
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    # -- reporting ---------------------------------------------------------

    def summarize(self, rows: Optional[Sequence[Dict[str, Any]]] = None) -> Dict[str, Any]:
        return summarize(
            rows if rows is not None else self.rows,
            arms=[a.name for a in self.arms],
            seeds=self.seeds,
            decode=self.decode,
            dataset_meta=self.dataset_meta,
            model_info=self.model_info,
            run_id=self.run_id,
            config_key=self.config_key,
            resamples=self.resamples,
        )


def _accepts_holdout(run: Callable[..., Any]) -> bool:
    try:
        import inspect

        return "holdout_test" in inspect.signature(run).parameters
    except (TypeError, ValueError):
        return True


def _model_from_stages(stages: Sequence[Any]) -> str:
    for stage in stages:
        if getattr(stage, "stage", "") in ("code", "code_retry"):
            m = re.search(r"model=(\S+)", str(getattr(stage, "detail", "")))
            if m:
                return m.group(1)
    return ""


def _hms(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m{seconds % 60:02d}s"


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------


def summarize(
    rows: Sequence[Dict[str, Any]],
    *,
    arms: Sequence[str],
    seeds: Sequence[int],
    decode: Optional[Dict[str, Any]] = None,
    dataset_meta: Optional[Dict[str, Any]] = None,
    model_info: Optional[Dict[str, Any]] = None,
    run_id: str = "",
    config_key: str = "",
    resamples: int = 10_000,
) -> Dict[str, Any]:
    """Per-arm rates with CIs, the paired test, and the honesty notes.

    Leaked samples are removed from every denominator here and reported on
    their own line. Scoring a leaked sample either way is wrong: as a pass it
    is unearned, as a fail it punishes the model for the harness's mistake.
    """
    seeds = list(seeds)
    by_arm: Dict[str, List[Dict[str, Any]]] = {a: [] for a in arms}
    for row in rows:
        by_arm.setdefault(row.get("arm", "?"), []).append(row)

    task_ids = sorted({str(r.get("task_id")) for r in rows if r.get("task_id")})
    arm_stats: Dict[str, Any] = {}
    pass_at_1: Dict[str, Dict[str, bool]] = {}
    oracle: Dict[str, Dict[str, bool]] = {}
    task_rates: Dict[str, Dict[str, float]] = {}

    for arm in by_arm:
        arm_rows = by_arm[arm]
        leaked = [r for r in arm_rows if r.get("leaked")]
        errored = [r for r in arm_rows if r.get("error") and not r.get("leaked")]
        scored = [r for r in arm_rows if not r.get("leaked")]
        n = len(scored)
        n_pass = sum(1 for r in scored if r.get("passed"))

        per_task_rate: List[float] = []
        rate_map: Dict[str, float] = {}
        p1: Dict[str, bool] = {}
        orc: Dict[str, bool] = {}
        for tid in task_ids:
            trows = [r for r in scored if str(r.get("task_id")) == tid]
            if not trows:
                continue
            rate_map[tid] = sum(1 for r in trows if r.get("passed")) / len(trows)
            per_task_rate.append(rate_map[tid])
            first_seed = min(int(r.get("seed", 0)) for r in trows)
            first = [r for r in trows if int(r.get("seed", 0)) == first_seed]
            p1[tid] = bool(first and first[0].get("passed"))
            orc[tid] = any(bool(r.get("passed")) for r in trows)
        pass_at_1[arm] = p1
        oracle[arm] = orc
        task_rates[arm] = rate_map

        lo, hi = bootstrap_ci(per_task_rate, resamples=resamples)
        arm_stats[arm] = {
            "arm": arm,
            "description": ARMS[arm].description if arm in ARMS else "",
            "n_samples_scored": n,
            "n_pass": n_pass,
            "n_leaked_excluded": len(leaked),
            "n_errors": len(errored),
            "n_tasks": len(per_task_rate),
            "pass_rate": round(n_pass / n, 4) if n else 0.0,
            "ci95": [round(lo, 4), round(hi, 4)],
            "ci_method": "percentile bootstrap, clustered on task",
            "resamples": resamples,
            "pass_at_1": round(sum(p1.values()) / len(p1), 4) if p1 else 0.0,
            "oracle_pass_at_n": round(sum(orc.values()) / len(orc), 4) if orc else 0.0,
            "n_for_pass_at_n": len(seeds),
            "mean_duration_s": (
                round(sum(float(r.get("duration_s") or 0) for r in scored) / n, 1) if n else 0.0
            ),
        }

    comparisons = []
    for a_name, b_name in _comparison_pairs(list(by_arm)):
        if a_name not in pass_at_1 or b_name not in pass_at_1:
            continue
        comparisons.append(
            _compare(a_name, b_name, pass_at_1, oracle, arm_stats, task_rates, resamples)
        )

    return {
        "run_id": run_id,
        "config_key": config_key,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "model": model_info or {},
        "decode": decode or {},
        "seeds": seeds,
        "dataset": dataset_meta or {},
        "arms": arm_stats,
        "comparisons": comparisons,
        "power": min_detectable_effect(len(task_ids)),
        "n_tasks": len(task_ids),
        "n_samples": len(rows),
        "n_leaked": sum(1 for r in rows if r.get("leaked")),
        "graded_on": "core.holdout.grade_against_holdout",
        "notes": _honesty_notes(rows, arm_stats, dataset_meta or {}),
    }


def _comparison_pairs(arm_names: Sequence[str]) -> List[Tuple[str, str]]:
    """Primary pair first, then every ether-* arm against `ether` itself."""
    pairs: List[Tuple[str, str]] = []
    a, b = PRIMARY_PAIR
    if a in arm_names and b in arm_names:
        pairs.append((a, b))
    if "ether" in arm_names and "bare" in arm_names:
        pairs.append(("ether", "bare"))
    if "bare+sys" in arm_names and "bare" in arm_names:
        pairs.append(("bare+sys", "bare"))
    for name in arm_names:
        if name.startswith("ether-") and "ether" in arm_names:
            pairs.append(("ether", name))
    return pairs


def _compare(
    a: str,
    b: str,
    pass_at_1: Dict[str, Dict[str, bool]],
    oracle: Dict[str, Dict[str, bool]],
    arm_stats: Dict[str, Any],
    task_rates: Optional[Dict[str, Dict[str, float]]] = None,
    resamples: int = 10_000,
) -> Dict[str, Any]:
    table = paired_table(pass_at_1[a], pass_at_1[b])
    mc = mcnemar_exact(table["only_a"], table["only_b"])
    orc_table = paired_table(oracle[a], oracle[b])
    orc_mc = mcnemar_exact(orc_table["only_a"], orc_table["only_b"])
    delta = round(arm_stats[a]["pass_rate"] - arm_stats[b]["pass_rate"], 4)
    rates = task_rates or {}
    paired_ci = (
        paired_delta_ci(rates.get(a, {}), rates.get(b, {}), resamples=resamples)
        if rates
        else {"n_tasks": 0, "delta": delta, "ci95": [0.0, 0.0], "excludes_zero": False}
    )
    return {
        "a": a,
        "b": b,
        "headline": f"{a} - {b}",
        "delta_pass_rate": delta,
        # The interval to quote. McNemar below is the significance test on
        # pass@1; this uses every sample, still paired on the task.
        "paired_delta_ci": paired_ci,
        "delta_pass_at_1": round(arm_stats[a]["pass_at_1"] - arm_stats[b]["pass_at_1"], 4),
        "delta_oracle_pass_at_n": round(
            arm_stats[a]["oracle_pass_at_n"] - arm_stats[b]["oracle_pass_at_n"], 4
        ),
        "paired_on": "pass@1 (first seed) per task",
        "table": table,
        "mcnemar": mc,
        "mcnemar_oracle": {"table": orc_table, **orc_mc},
        "significant_at_0.05": bool(mc["p_value"] <= 0.05),
    }


def _honesty_notes(
    rows: Sequence[Dict[str, Any]], arm_stats: Dict[str, Any], dataset_meta: Dict[str, Any]
) -> List[str]:
    notes: List[str] = []
    if dataset_meta.get("source") == "bench":
        notes.append("DATASET FALLBACK: " + FALLBACK_NOTE)
    leaked = sum(1 for r in rows if r.get("leaked"))
    if leaked:
        notes.append(
            f"{leaked} sample(s) excluded for holdout leakage — they are in the JSONL "
            "with leaked=true and are in no denominator."
        )
    errored = sum(1 for r in rows if r.get("error"))
    if errored:
        notes.append(
            f"{errored} sample(s) errored (router/pipeline failure). They count as FAILS, "
            "which is the conservative reading for whichever arm they hit."
        )
    ceiling = [a for a, s in arm_stats.items() if s["n_samples_scored"] and s["pass_rate"] >= 0.95]
    if ceiling:
        notes.append(
            "Ceiling effect: " + ", ".join(ceiling) + " scored >=0.95. A dataset the bare "
            "model already solves cannot show what the pipeline adds; re-run on harder tasks."
        )
    disagree = [
        r
        for r in rows
        if r.get("grade_agrees_with_pipeline") is False
    ]
    if disagree:
        notes.append(
            f"{len(disagree)} ether sample(s) where this harness's grade disagreed with the "
            "pipeline's own holdout verdict — investigate before quoting the number."
        )
    if any(r.get("used_burst") for r in rows):
        notes.append(
            "At least one ether sample used the CLOUD BURST model. That breaks 'same model, "
            "all arms'; set ETHER_BURST=0 and re-run those samples."
        )
    return notes


def markdown_summary(summary: Dict[str, Any]) -> str:
    """The table a human reads. Every caveat stays attached to the number."""
    m = summary.get("model", {}) or {}
    d = summary.get("dataset", {}) or {}
    lines: List[str] = []
    lines.append("# @ETHER ablation — pipeline vs the bare model")
    lines.append("")
    lines.append(f"- run: `{summary.get('run_id', '')}`  config: `{summary.get('config_key', '')}`")
    lines.append(f"- timestamp: {summary.get('timestamp', '')}")
    lines.append(f"- git commit: `{summary.get('git_commit', '') or 'unknown'}`")
    lines.append(
        f"- model: `{m.get('model', '?')}` digest `{m.get('digest') or 'UNKNOWN'}` "
        f"({m.get('parameter_size') or '?'} {m.get('quantization') or ''})"
    )
    lines.append(f"- decode: `{json.dumps(summary.get('decode', {}), sort_keys=True)}`")
    lines.append(f"- seeds: {summary.get('seeds')}")
    lines.append(
        f"- dataset: `{d.get('id', '?')}` ({d.get('source', '?')}, sha `{d.get('sha256', '')}`, "
        f"{summary.get('n_tasks', 0)} tasks)"
    )
    lines.append(f"- graded on: `{summary.get('graded_on', '')}` (never exit code)")
    lines.append("")
    lines.append(
        "| arm | pass rate | 95% CI | pass@1 | oracle pass@N | n | leaked | errors | mean s |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for name, s in summary.get("arms", {}).items():
        ci = s.get("ci95", [0, 0])
        lines.append(
            f"| `{name}` | {s['pass_rate']:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] | "
            f"{s['pass_at_1']:.3f} | {s['oracle_pass_at_n']:.3f} | {s['n_samples_scored']} | "
            f"{s['n_leaked_excluded']} | {s['n_errors']} | {s['mean_duration_s']} |"
        )
    lines.append("")
    lines.append("## Paired comparisons")
    lines.append("")
    lines.append(
        "`delta 95% CI` is the bootstrap interval on the per-task pass-rate difference "
        "(all samples, paired on task). `p` is McNemar's exact test on per-task pass@1."
    )
    lines.append("")
    lines.append(
        "| comparison | delta | delta 95% CI | only A | only B | discordant | p | significant |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for c in summary.get("comparisons", []):
        t, mc = c["table"], c["mcnemar"]
        pci = c.get("paired_delta_ci") or {"ci95": [0.0, 0.0]}
        lines.append(
            f"| {c['headline']} | {c['delta_pass_rate']:+.3f} | "
            f"[{pci['ci95'][0]:+.3f}, {pci['ci95'][1]:+.3f}] | {t['only_a']} | {t['only_b']} | "
            f"{mc['n_discordant']} | {mc['p_value']:.4f} | "
            f"{'yes' if c['significant_at_0.05'] else 'no'} |"
        )
    lines.append("")
    power = summary.get("power", {})
    lines.append("## Power")
    lines.append("")
    lines.append(power.get("note", ""))
    notes = summary.get("notes") or []
    if notes:
        lines.append("")
        lines.append("## Read this before quoting any number above")
        lines.append("")
        for n in notes:
            lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(summary: Dict[str, Any], out_dir: Path = OUT_DIR) -> Dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = summary.get("run_id") or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    blob = json.dumps(summary, indent=2, default=str)
    paths = {
        "json": str(out_dir / "ablation_latest.json"),
        "json_stamped": str(out_dir / f"ablation_{stamp}.json"),
        "markdown": str(out_dir / "ablation_latest.md"),
    }
    (out_dir / "ablation_latest.json").write_text(blob, encoding="utf-8")
    (out_dir / f"ablation_{stamp}.json").write_text(blob, encoding="utf-8")
    (out_dir / "ablation_latest.md").write_text(markdown_summary(summary), encoding="utf-8")
    return paths


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Measure ETHER minus the bare model it runs on.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Arms: " + ", ".join(f"{k} ({v.description})" for k, v in ARMS.items()) + "\n\n"
            "This is an overnight run. Always --dry-run first."
        ),
    )
    ap.add_argument("--limit", type=int, default=0, help="use only the first N tasks")
    ap.add_argument(
        "--arms",
        default=",".join(DEFAULT_ARMS),
        help="comma-separated arm names (default: %(default)s)",
    )
    ap.add_argument("--samples", type=int, default=3, help="samples per task per arm")
    ap.add_argument("--seeds", default="", help="explicit comma-separated seeds, e.g. 1,2,3")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="validate everything and print the plan WITHOUT calling the model",
    )
    ap.add_argument("--resume", action="store_true", help="skip (task, arm, seed) already in JSONL")
    ap.add_argument("--dataset", default="", help="path to a dataset json (default: headroom_v1)")
    ap.add_argument("--jsonl", default=str(SAMPLES_JSONL), help="append-only sample log")
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    ap.add_argument("--temperature", type=float, default=DEFAULT_DECODE["temperature"])
    ap.add_argument("--top-p", type=float, default=DEFAULT_DECODE["top_p"])
    ap.add_argument("--top-k", type=int, default=DEFAULT_DECODE["top_k"])
    ap.add_argument("--num-ctx", type=int, default=DEFAULT_DECODE["num_ctx"])
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--model", default="", help="override ETHER_PRIMARY_MODEL for this run")
    ap.add_argument("--no-probe", action="store_true", help="skip the ollama model/digest probe")
    ap.add_argument("--resamples", type=int, default=10_000, help="bootstrap resamples (>=10k)")
    ap.add_argument("--secs-per-gen", type=float, default=29.0, help="cost model for --dry-run")
    ap.add_argument(
        "--bare-strip-preamble",
        action="store_true",
        help="strip a 'Write only Python' preamble from the objective for the `bare` arm only",
    )
    ap.add_argument(
        "--no-learning",
        action="store_true",
        help="ETHER_LEARNING=0 for the run, so the bandit does not drift between arms",
    )
    return ap


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.model:
        os.environ["ETHER_PRIMARY_MODEL"] = args.model
    if args.no_learning:
        os.environ["ETHER_LEARNING"] = "0"

    try:
        arms = [ARMS[name.strip()] for name in args.arms.split(",") if name.strip()]
    except KeyError as e:
        print(f"unknown arm {e}; known: {', '.join(ARMS)}", file=sys.stderr)
        return 2
    if not arms:
        print("no arms selected", file=sys.stderr)
        return 2

    if args.seeds.strip():
        seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    else:
        seeds = DEFAULT_SEEDS[: args.samples] if args.samples <= len(DEFAULT_SEEDS) else list(
            range(1, args.samples + 1)
        )
    if not seeds:
        print("no seeds", file=sys.stderr)
        return 2

    dataset_path = Path(args.dataset) if args.dataset else None
    tasks, dataset_meta = load_dataset(dataset_path)
    if args.limit and args.limit > 0:
        tasks = tasks[: args.limit]
        dataset_meta = {**dataset_meta, "n": len(tasks), "limited_to": args.limit}
    if not tasks:
        print("no tasks", file=sys.stderr)
        return 2

    print(f"dataset: {dataset_meta['id']} via {dataset_meta['source']} ({len(tasks)} tasks)")
    if dataset_meta.get("note"):
        print(f"  note: {dataset_meta['note']}")
    if dataset_meta.get("warning"):
        print(f"  WARNING: {dataset_meta['warning']}")

    # A dataset that hands the model its own answer measures transcription for
    # every arm at once, so refuse before spending a GPU-night on it.
    problems = audit_dataset(tasks)
    if problems:
        print("REFUSING TO RUN — dataset tasks leak their own answers:", file=sys.stderr)
        for p in problems[:20]:
            print(f"  - {p}", file=sys.stderr)
        return 2

    decode = dict(DEFAULT_DECODE)
    decode.update(
        {
            "temperature": args.temperature,
            "top_p": args.top_p,
            "top_k": args.top_k,
            "num_ctx": args.num_ctx,
        }
    )
    model_info = model_fingerprint(probe=not args.no_probe)
    if model_info.get("warning"):
        print(f"  WARNING: {model_info['warning']}")

    ab = Ablation(
        tasks,
        arms,
        seeds,
        decode=decode,
        jsonl_path=Path(args.jsonl),
        out_dir=Path(args.out_dir),
        resume=args.resume,
        dataset_meta=dataset_meta,
        model_info=model_info,
        strip_bare_preamble=args.bare_strip_preamble,
        max_tokens=args.max_tokens,
        resamples=max(10_000, int(args.resamples)),
    )

    plan = ab.plan()
    plan["estimated_seconds"] = ab.estimate_seconds(
        plan["generations_remaining"], secs_per_gen=args.secs_per_gen
    )
    plan["estimated_hms"] = _hms(plan["estimated_seconds"])

    print("")
    print(f"model: {model_info.get('model')} digest={model_info.get('digest') or 'UNKNOWN'}")
    print(f"decode: {json.dumps(decode, sort_keys=True)}  seeds={seeds}")
    print(f"arms: {', '.join(a.name for a in arms)}")
    print(
        f"plan: {len(tasks)} tasks x {len(arms)} arms x {len(seeds)} samples "
        f"= {plan['generations_total']} generations"
    )
    if plan["generations_done"]:
        print(f"  already done (resume): {plan['generations_done']}")
    print(f"  remaining: {plan['generations_remaining']}  est. {plan['estimated_hms']}")
    if plan["preflight_leaks"]:
        print(f"  PREFLIGHT LEAKS: {plan['preflight_leaks']} prompt(s) carry holdout assertions")
        for detail in plan["preflight_detail"][:5]:
            print(f"    - {detail['task_id']}/{detail['arm']}: {detail['leaks']}")
    if plan["instruction_preamble_tasks"]:
        n_pre = plan["instruction_preamble_tasks"]
        if args.bare_strip_preamble:
            print(
                f"  NOTE: {n_pre}/{len(tasks)} objectives carry a 'Write only Python' "
                "instruction; --bare-strip-preamble is removing it for the `bare` arm only, "
                "so bare vs bare+sys is a clean contrast."
            )
        else:
            print(
                f"  NOTE: {n_pre}/{len(tasks)} objectives already contain a 'Write only Python' "
                "instruction, so the `bare` arm is NOT instruction-free — bare vs bare+sys then "
                "measures user-turn vs system-turn placement, not the instruction itself. "
                "Use --bare-strip-preamble for the clean contrast."
            )
    print(f"  power: {min_detectable_effect(len(tasks))['note']}")

    if args.dry_run:
        print("")
        print("DRY RUN — no model was called, no files written.")
        print(json.dumps({k: v for k, v in plan.items() if k != "preflight_detail"}, indent=2))
        return 0

    try:
        summary = ab.run()
    except KeyboardInterrupt:
        print("\ninterrupted — summarising what completed (JSONL is intact; use --resume)")
        summary = ab.summarize()
    paths = write_outputs(summary, Path(args.out_dir))

    print("")
    print(markdown_summary(summary))
    print(f"wrote {paths['json']}")
    print(f"wrote {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
