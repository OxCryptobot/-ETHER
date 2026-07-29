"""Generate → verify → repair → select. The loop the pipeline never had.

`docs/FINDINGS.md` measured why this file exists:

  §5  The repair loop fired only on a non-zero sandbox exit. A wrong answer
      usually runs fine, so it never fired: `ether` and `ether-no-repair` were
      bit-identical, p = 1.0. **This loop iterates on the verifier, not on
      crashes.**
  §1  On the 35B run the repair loop's net contribution was MINUS one task,
      because the pipeline unconditionally overwrites attempt 1 with attempt 2.
      **This loop keeps every candidate and returns the best-scoring one. It
      cannot regress.**
  §3  10 of 120 ether samples errored where the bare call did not, several
      because markdown fences reached the sandbox as Python. **Extraction here
      is tested against real messy output shapes.**
  §8  Best-of-N with verifier selection, static analysis in the loop, and a
      repair prompt showing the code that actually ran are the three
      mechanisms with published evidence that were never in this system.

The correctness signal comes from `core/verifier.py`, which needs no holdout —
there is no holdout in production, only in the benchmark.

`holdout_test`, when supplied, **scores the result and nothing else**. It never
enters a prompt. Passing it changes no decision the loop makes; a leak here is
raised, loudly, as `HoldoutLeak`.

`generate_fn(prompt, temperature, seed) -> str` is injected, so the whole loop
is testable without a model.
"""

from __future__ import annotations

import re
import textwrap
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

import ast

DEFAULT_TEMPERATURES: Sequence[float] = (0.2, 0.7, 0.9, 1.0)

# Below this verifier score a candidate is not worth patching: the model is
# better served by a fresh, hotter draw than by being asked to edit something
# fundamentally broken. Above it, repair keeps the parts that already work.
REPAIR_FLOOR = 0.35


class HoldoutLeak(RuntimeError):
    """The holdout reached a prompt. Raised, never swallowed.

    Six of the seven leak channels in `docs/FINDINGS.md` §2 were found *after*
    the previous one was declared fixed, and every one of them made a result
    look good. A leak is not a degraded mode to continue in.
    """


# ---------------------------------------------------------------------------
# code extraction
# ---------------------------------------------------------------------------

_FENCE_RE = re.compile(
    r"```[ \t]*([A-Za-z0-9_+-]*)[ \t]*\r?\n(.*?)(?:\r?\n[ \t]*```|\Z)",
    re.DOTALL,
)
_NON_PYTHON_LANGS = {
    "bash", "sh", "shell", "console", "text", "output", "json", "yaml", "yml",
    "toml", "ini", "diff", "patch", "javascript", "js", "ts", "html", "css",
    "sql", "make", "makefile", "log", "traceback", "pytest",
}
_CODE_START_RE = re.compile(
    r"^\s*(from\s+\S+\s+import\b|import\s+\w|def\s+\w|async\s+def\s+\w|class\s+\w|@\w"
    r"|if\s+__name__|#!|#\s*-\*-)"
)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _parses(text: str) -> bool:
    if not (text or "").strip():
        return False
    try:
        ast.parse(text)
        return True
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return False


def _strip_reasoning(text: str) -> str:
    """Drop <think> blocks. A reasoning model's scratchpad is not the answer."""
    out = _THINK_RE.sub("", text)
    # Unbalanced tags: a truncated stream leaves one side behind.
    if "</think>" in out:
        out = out.rsplit("</think>", 1)[1]
    if "<think>" in out:
        out = out.split("<think>", 1)[0]
    return out


def _block_rank(block: str) -> tuple:
    """Sort key: parseable first, then defines something, then longer."""
    ok = _parses(block)
    defines = bool(re.search(r"^\s*(def|class)\s+\w", block, re.MULTILINE))
    return (1 if ok else 0, 1 if defines else 0, len(block))


def _best_parseable_span(text: str) -> str:
    """Largest contiguous run of lines that parses, preferring an early start.

    Handles the two shapes that actually cost samples: a prose preamble
    ("Sure! Here's the code:") and a trailing explanation after the code.
    """
    lines = text.splitlines()
    if not lines:
        return ""
    starts = [i for i, ln in enumerate(lines) if _CODE_START_RE.match(ln)]
    if 0 not in starts:
        starts = [0] + starts
    best = ""
    budget = 3000  # bounded work: pathological output must not hang the loop
    for start in starts[:40]:
        end = len(lines)
        while end > start and budget > 0:
            budget -= 1
            chunk = "\n".join(lines[start:end])
            if chunk.strip() and _parses(chunk):
                if len(chunk) > len(best):
                    best = chunk
                break
            end -= 1
    return best


def extract_code(text: str) -> str:
    """Pull runnable Python out of whatever the model actually emitted.

    Markdown fences (including an unterminated one), a language tag, prose
    before and after, several blocks, `<think>` scratchpads, and a wholly
    indented answer. `docs/FINDINGS.md` §3: unstripped fences reached the
    sandbox as Python and cost samples the bare call never lost.

    Returns the best candidate; if nothing parses it returns the most
    code-like text found, so the verifier reports a real SyntaxError instead
    of an empty string.
    """
    if not text:
        return ""
    raw = _strip_reasoning(str(text)).strip()
    if not raw:
        return ""

    blocks: List[str] = []
    for lang, body in _FENCE_RE.findall(raw):
        if lang.lower() in _NON_PYTHON_LANGS:
            continue
        body = body.strip("\n")
        if body.strip():
            blocks.append(body)

    if blocks:
        parseable = [b for b in blocks if _parses(b)]
        if len(parseable) > 1:
            joined = "\n\n".join(parseable)
            if _parses(joined):
                return joined.strip()
        best = sorted(blocks, key=_block_rank)[-1]
        if _parses(best):
            return best.strip()
        span = _best_parseable_span(best)
        if span:
            return span.strip()
        dedented = textwrap.dedent(best)
        if _parses(dedented):
            return dedented.strip()
        return best.strip()

    if _parses(raw):
        return raw
    dedented = textwrap.dedent(raw)
    if _parses(dedented):
        return dedented.strip()
    span = _best_parseable_span(raw)
    if span:
        return span.strip()
    span = _best_parseable_span(dedented)
    if span:
        return span.strip()
    return raw


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------


@dataclass
class LoopBudget:
    """Attempts AND wall clock AND tokens — whichever binds first.

    A fixed attempt count is the wrong control: attempt 4 on a 35B that has
    already spent 280s is not free, and `num_predict=4096` on a reasoning
    model produced 147 timeouts in one 360-sample run (FINDINGS §4).
    """

    max_attempts: int = 4
    wall_clock_s: float = 300.0
    max_tokens: int = 32_000

    def exceeded(self, *, attempts: int, elapsed: float, tokens: int) -> str:
        if self.max_attempts is not None and attempts >= self.max_attempts:
            return f"attempt budget exhausted ({attempts}/{self.max_attempts})"
        if self.wall_clock_s is not None and elapsed >= self.wall_clock_s:
            return f"wall clock exhausted ({elapsed:.1f}s/{self.wall_clock_s:.0f}s)"
        if self.max_tokens is not None and tokens >= self.max_tokens:
            return f"token budget exhausted ({tokens}/{self.max_tokens})"
        return ""


def estimate_tokens(text: str) -> int:
    """~4 chars/token. Replaceable via `token_counter=` when a real one exists."""
    return max(0, len(text or "")) // 4


# ---------------------------------------------------------------------------
# records
# ---------------------------------------------------------------------------


@dataclass
class Attempt:
    index: int
    kind: str  # "initial" | "repair" | "resample"
    temperature: float
    seed: int
    prompt: str = ""
    raw_output: str = ""
    code: str = ""
    score: float = 0.0
    normalized: float = 0.0
    coverage: float = 0.0
    signals: Dict[str, float] = field(default_factory=dict)
    applicable: Dict[str, bool] = field(default_factory=dict)
    diagnostics: List[str] = field(default_factory=list)
    consistency: float = 0.0
    consistency_applicable: bool = False
    final_score: float = 0.0
    error: str = ""
    tokens: int = 0
    elapsed_s: float = 0.0

    def to_dict(self, include_prompt: bool = False) -> Dict[str, Any]:
        d = {
            "index": self.index,
            "kind": self.kind,
            "temperature": self.temperature,
            "seed": self.seed,
            "code_chars": len(self.code),
            "score": self.score,
            "normalized": self.normalized,
            "coverage": self.coverage,
            "signals": dict(self.signals),
            "applicable": dict(self.applicable),
            "diagnostics": list(self.diagnostics),
            "consistency": self.consistency,
            "consistency_applicable": self.consistency_applicable,
            "final_score": self.final_score,
            "error": self.error,
            "tokens": self.tokens,
            "elapsed_s": round(self.elapsed_s, 3),
        }
        if include_prompt:
            d["prompt"] = self.prompt
        return d


@dataclass
class LoopResult:
    objective: str
    attempts: List[Attempt] = field(default_factory=list)
    selected_index: int = -1
    code: str = ""
    score: float = 0.0
    selection_reason: str = "no candidate produced"
    stop_reason: str = ""
    consistency: Dict[str, Any] = field(default_factory=dict)
    holdout_ok: Optional[bool] = None
    holdout_reason: str = ""
    tokens_used: int = 0
    elapsed_s: float = 0.0

    @property
    def attempts_used(self) -> int:
        return len(self.attempts)

    @property
    def selected(self) -> Optional[Attempt]:
        for a in self.attempts:
            if a.index == self.selected_index:
                return a
        return None

    def to_dict(self, include_prompts: bool = False) -> Dict[str, Any]:
        return {
            "objective": self.objective,
            "attempts": [a.to_dict(include_prompts) for a in self.attempts],
            "selected_index": self.selected_index,
            "score": self.score,
            "selection_reason": self.selection_reason,
            "stop_reason": self.stop_reason,
            "consistency": {
                k: v for k, v in self.consistency.items() if k != "outputs"
            },
            "holdout_ok": self.holdout_ok,
            "holdout_reason": self.holdout_reason,
            "tokens_used": self.tokens_used,
            "elapsed_s": round(self.elapsed_s, 3),
            "attempts_used": self.attempts_used,
        }


# ---------------------------------------------------------------------------
# prompts
# ---------------------------------------------------------------------------

_OUTPUT_RULE = (
    "Return ONLY the complete Python module. No markdown fences, no commentary, "
    "no example session."
)


def build_initial_prompt(objective: str, extra_context: str = "") -> str:
    parts = [f"Write Python code for the following task.\n\nTask:\n{objective.strip()}\n"]
    if extra_context.strip():
        parts.append(extra_context.strip() + "\n")
    parts.append(
        "Requirements:\n"
        "- Define the function(s) the task asks for, at module level.\n"
        "- Use only the Python standard library.\n"
        "- Handle empty and single-element input without raising.\n"
        "- Do not mutate the caller's arguments.\n"
    )
    parts.append(_OUTPUT_RULE)
    return "\n".join(parts)


def build_repair_prompt(objective: str, attempt: Attempt, extra_context: str = "") -> str:
    """Show the model the EXACT source that ran, and the real diagnostics.

    The pipeline's `core/repair.py` shows the pre-harness original beside a
    traceback produced by the harnessed, assert-synthesized, possibly
    multifile-split version — line numbers referring to a file the model never
    saw (FINDINGS §8). `attempt.code` is byte-for-byte what the verifier
    executed, and every line below it is an observation of that execution.
    """
    diagnostics = attempt.diagnostics or ["(no diagnostics were produced)"]
    signal_line = ", ".join(
        f"{k}={attempt.signals.get(k, 0.0):.2f}" for k in sorted(attempt.signals)
    )
    parts = [
        "Your previous attempt did not pass verification.\n",
        f"Task:\n{objective.strip()}\n",
    ]
    if extra_context.strip():
        parts.append(extra_context.strip() + "\n")
    parts.append(
        "This is the EXACT source that was executed — it is what you produced, "
        "unmodified:\n"
        "-----\n"
        f"{attempt.code.rstrip()}\n"
        "-----\n"
    )
    parts.append(
        "What the verifier observed while running that exact source:\n"
        + "\n".join(f"- {d}" for d in diagnostics)
        + "\n"
    )
    parts.append(f"Verifier score {attempt.score:.2f} ({signal_line}).\n")
    parts.append(
        "Fix the specific problems listed above. Keep everything that already "
        "works. Do not rename the function.\n"
    )
    parts.append(_OUTPUT_RULE)
    return "\n".join(parts)


def build_resample_prompt(objective: str, attempt: Attempt, extra_context: str = "") -> str:
    """A fresh draw, told only what to avoid — used when repair is hopeless."""
    worst = [
        d
        for d in attempt.diagnostics
        if "FAILED" in d or "lint[critical]" in d or "raised" in d or "not_stub" in d
    ] or list(attempt.diagnostics) or [attempt.error or "it did not verify"]
    parts = [build_initial_prompt(objective, extra_context)]
    parts.insert(
        1,
        "A previous, different solution failed like this — take another "
        "approach:\n" + "\n".join(f"- {d}" for d in worst[:6]) + "\n",
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# leak guard
# ---------------------------------------------------------------------------


def _normalize(text: str) -> str:
    return " ".join((text or "").split())


def assert_no_holdout(prompt: str, holdout_test: str) -> None:
    """The holdout scores the result. It is never an input. Raises on contact."""
    if not (holdout_test or "").strip():
        return
    normal_prompt = _normalize(prompt)
    normal_holdout = _normalize(holdout_test)
    if normal_holdout and normal_holdout in normal_prompt:
        raise HoldoutLeak(
            "the holdout test appeared in a prompt — the result would be void "
            "(docs/FINDINGS.md §2)"
        )
    # Also catch a partial leak: any single held-out assertion line.
    for line in (holdout_test or "").splitlines():
        line = line.strip()
        if len(line) > 12 and line.startswith("assert") and _normalize(line) in normal_prompt:
            raise HoldoutLeak(f"a held-out assertion appeared in a prompt: {line[:80]!r}")


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------


def _call_generate(
    generate_fn: Callable[..., str], prompt: str, temperature: float, seed: int
) -> str:
    """Call the injected generator, keyword-first, positional as a fallback."""
    try:
        return generate_fn(prompt, temperature=temperature, seed=seed)
    except TypeError as e:
        if "keyword" not in str(e) and "argument" not in str(e):
            raise
        return generate_fn(prompt, temperature, seed)


def run_loop(
    objective: str,
    generate_fn: Callable[..., str],
    *,
    budget: Optional[LoopBudget] = None,
    holdout_test: str = "",
    score_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    consistency_fn: Optional[Callable[..., Dict[str, Any]]] = None,
    temperatures: Optional[Sequence[float]] = None,
    confidence_threshold: float = 0.95,
    min_coverage: float = 0.75,
    consistency_weight: float = 0.25,
    seed: int = 1234,
    token_counter: Optional[Callable[[str], int]] = None,
    verify_timeout: int = 25,
    extra_context: str = "",
    on_attempt: Optional[Callable[[Attempt], None]] = None,
) -> LoopResult:
    """Generate candidates, verify each, repair, and return the best one.

    Properties this guarantees, each one a measured failure of the pipeline it
    replaces:

    * Every candidate is kept and the highest-scoring one is returned, so the
      loop can only improve on its first attempt or tie it — never regress.
    * Iteration is driven by the verifier score, not by the process exit code.
    * Temperature rises across attempts, so attempt 2 is a genuinely different
      draw rather than a second sample from the same near-greedy distribution.
    * The repair prompt contains the exact source that was executed.
    * `holdout_test` is used only after selection, to report `holdout_ok`. It
      influences nothing. Any contact with a prompt raises `HoldoutLeak`.

    Early stopping needs the evidence to be strong AND broad: `normalized >=
    confidence_threshold` over `coverage >= min_coverage`. A candidate whose
    only live signals are "it ran" and "ruff is happy" scores normalized 1.0
    on 0.70 coverage, and stopping there would forfeit exactly the best-of-N
    gain this loop exists to capture.
    """
    budget = budget or LoopBudget()
    temps = list(temperatures) if temperatures else list(DEFAULT_TEMPERATURES)
    if not temps:
        temps = [0.2]
    counter = token_counter or estimate_tokens

    if score_fn is None:
        from core.verifier import score as _verifier_score

        def _score(code: str, obj: str) -> Dict[str, Any]:
            return _verifier_score(code, obj, timeout=verify_timeout)
    else:
        _score = score_fn  # type: ignore[assignment]

    _consistency: Optional[Callable[..., Dict[str, Any]]] = consistency_fn
    if consistency_fn is None and consistency_weight > 0:
        from core.verifier import consistency as _verifier_consistency

        def _consistency_default(codes: Sequence[str], obj: str) -> Dict[str, Any]:
            return _verifier_consistency(codes, obj, timeout=verify_timeout, seed=seed)

        _consistency = _consistency_default

    result = LoopResult(objective=objective)
    started = time.perf_counter()
    tokens = 0
    index = 0

    while True:
        elapsed = time.perf_counter() - started
        stop = budget.exceeded(attempts=index, elapsed=elapsed, tokens=tokens)
        if stop:
            result.stop_reason = stop
            break

        best_so_far = _best_attempt(result.attempts)
        if best_so_far is None:
            kind = "initial"
            prompt = build_initial_prompt(objective, extra_context)
        elif best_so_far.score >= REPAIR_FLOOR:
            kind = "repair"
            prompt = build_repair_prompt(objective, best_so_far, extra_context)
        else:
            # Too broken to patch: spend the attempt on a different approach.
            kind = "resample"
            prompt = build_resample_prompt(objective, best_so_far, extra_context)

        # Fail loud rather than produce a number that is quietly void.
        assert_no_holdout(prompt, holdout_test)

        temperature = float(temps[min(index, len(temps) - 1)])
        attempt_seed = seed + index
        attempt = Attempt(
            index=index,
            kind=kind,
            temperature=temperature,
            seed=attempt_seed,
            prompt=prompt,
        )
        t0 = time.perf_counter()
        try:
            raw = _call_generate(generate_fn, prompt, temperature, attempt_seed)
            attempt.raw_output = raw if isinstance(raw, str) else str(raw or "")
        except HoldoutLeak:
            raise
        except Exception as e:
            attempt.error = f"generator failed: {type(e).__name__}: {e}"

        attempt.tokens = counter(prompt) + counter(attempt.raw_output)
        tokens += attempt.tokens

        if not attempt.error:
            attempt.code = extract_code(attempt.raw_output)
            if not attempt.code.strip():
                attempt.error = "generator returned no extractable code"
                attempt.diagnostics.append(
                    "extraction: the response contained no Python — "
                    f"{attempt.raw_output[:120]!r}"
                )

        if attempt.code.strip():
            try:
                verdict = _score(attempt.code, objective)
            except Exception as e:
                verdict = {
                    "score": 0.0,
                    "normalized": 0.0,
                    "signals": {},
                    "applicable": {},
                    "diagnostics": [f"verifier raised {type(e).__name__}: {e}"],
                }
            attempt.score = float(verdict.get("score") or 0.0)
            # A score_fn that reports no `normalized`/`coverage` (a test fake,
            # or a future scorer) is treated as fully covered at face value.
            norm = verdict.get("normalized")
            attempt.normalized = attempt.score if norm is None else float(norm)
            cov = verdict.get("coverage")
            attempt.coverage = 1.0 if cov is None else float(cov)
            attempt.signals = dict(verdict.get("signals") or {})
            attempt.applicable = dict(verdict.get("applicable") or {})
            attempt.diagnostics.extend(list(verdict.get("diagnostics") or []))

        attempt.final_score = attempt.score
        attempt.elapsed_s = time.perf_counter() - t0
        result.attempts.append(attempt)
        if on_attempt:
            try:
                on_attempt(attempt)
            except Exception:
                pass
        index += 1

        if (
            attempt.code.strip()
            and attempt.normalized >= confidence_threshold
            and attempt.coverage >= min_coverage
        ):
            result.stop_reason = (
                f"verifier confident on attempt {attempt.index} "
                f"(normalized {attempt.normalized:.2f} >= {confidence_threshold:.2f} "
                f"at coverage {attempt.coverage:.2f})"
            )
            break

    # ---- selection -------------------------------------------------------
    scored = [a for a in result.attempts if a.code.strip()]
    if scored and consistency_weight > 0 and _consistency and len(scored) > 1:
        try:
            cons = _consistency([a.code for a in scored], objective)
        except Exception as e:
            cons = {
                "scores": [0.0] * len(scored),
                "applicable": False,
                "diagnostics": [f"consistency raised {type(e).__name__}: {e}"],
            }
        result.consistency = cons
        if cons.get("applicable"):
            values = list(cons.get("scores") or [])
            for pos, a in enumerate(scored):
                a.consistency = float(values[pos]) if pos < len(values) else 0.0
                a.consistency_applicable = True
                a.final_score = round(
                    (1.0 - consistency_weight) * a.score
                    + consistency_weight * a.consistency,
                    4,
                )

    best = _best_attempt(result.attempts, key="final_score")
    if best is not None:
        result.selected_index = best.index
        result.code = best.code
        result.score = best.final_score
        others = [
            f"#{a.index}={a.final_score:.3f}" for a in result.attempts if a is not best
        ]
        why = (
            f"attempt #{best.index} scored {best.final_score:.3f} "
            f"(verifier {best.score:.3f}"
            + (f", consistency {best.consistency:.3f}" if best.consistency_applicable else "")
            + ")"
        )
        if others:
            why += "; beat " + ", ".join(others)
        else:
            why += "; only candidate"
        result.selection_reason = why
    if not result.stop_reason:
        result.stop_reason = "loop ended"
    result.tokens_used = tokens
    result.elapsed_s = time.perf_counter() - started

    # ---- holdout: SCORING THE RESULT ONLY --------------------------------
    # Deliberately after selection. Nothing above this line has seen it, and
    # removing this block changes no returned code.
    if holdout_test and result.code:
        try:
            from core.holdout import grade_against_holdout

            graded = grade_against_holdout(result.code, holdout_test, timeout=verify_timeout)
            result.holdout_ok = bool(graded.get("ok"))
            result.holdout_reason = str(graded.get("reason") or "")
        except Exception as e:
            result.holdout_ok = False
            result.holdout_reason = f"holdout grading failed: {type(e).__name__}: {e}"

    return result


def _best_attempt(attempts: Sequence[Attempt], key: str = "score") -> Optional[Attempt]:
    """Highest score wins; ties go to the EARLIER attempt.

    The tie-break is the never-regress rule in miniature: a later attempt has
    to actually beat the incumbent to replace it. The pipeline this replaces
    overwrote attempt 1 with attempt 2 unconditionally, and on the 35B run
    that cost a task (FINDINGS §1).
    """
    live = [a for a in attempts if a.code.strip()]
    if not live:
        return None
    return max(live, key=lambda a: (getattr(a, key), -a.index))
