"""Batch 10 item 5: a 1650-safe proposer swarm. ETHER_SWARM=1 (default off).

Doctrine (PRODUCT.md: one writer, one model, 4 GB): this is not a multi-writer swarm.
  * K proposers share the ONE loaded model. Every model call goes through `model_lock()`
    (a process lock plus a cross-process lock file), so there is never more than one
    generation on the GPU at a time, whoever calls.
  * CPU workers (ETHER_SWARM_WORKERS, default 2) screen each reply while the next one is being
    generated: extract the edit, build the new file text in memory (never written), compile it,
    run the security gem pre-check, and drop replies the gate already reverted or that repeat
    another candidate. Workers never touch the repo.
  * The single writer (sota._attempt_real) applies only the best surviving candidate and sends it
    through the unchanged honest gate. One gate run per try, as before; the swarm only spends extra
    model calls (K per try) to give that gate run a better candidate.
Candidates differ by sampling temperature (candidate 0 = the normal schedule, the rest
ETHER_SWARM_TEMP) when the model client accepts one; otherwise K=1 (identical replies are useless).
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional

_LOCK = threading.Lock()
LOCK_FILE = "artifacts/model.lock"


def enabled() -> bool:
    return os.getenv("ETHER_SWARM", "0") == "1"


def _int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(os.getenv(name, str(default)))))
    except ValueError:
        return default


def k() -> int:
    return _int("ETHER_SWARM_K", 3, 1, 4)


def workers() -> int:
    return _int("ETHER_SWARM_WORKERS", 2, 1, 4)


def swarm_temp() -> float:
    try:
        return max(0.05, min(1.5, float(os.getenv("ETHER_SWARM_TEMP", "0.7"))))
    except ValueError:
        return 0.7


@contextmanager
def model_lock(root: Optional[Path] = None, timeout_s: float = 900.0, stale_s: float = 1800.0) -> Iterator[None]:
    """One generation at a time: in-process lock + an O_EXCL lock file other processes honour.
    A lock file older than stale_s (crashed holder) is broken."""
    with _LOCK:
        path = Path(root or ".") / LOCK_FILE
        fd = None
        t0 = time.monotonic()
        if root is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            while True:
                try:
                    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.write(fd, str(os.getpid()).encode())
                    break
                except FileExistsError:
                    try:
                        if time.time() - path.stat().st_mtime > stale_s:
                            path.unlink()
                            continue
                    except OSError:
                        continue
                    if time.monotonic() - t0 > timeout_s:
                        raise TimeoutError("model lock busy")
                    time.sleep(0.5)
        try:
            yield
        finally:
            if fd is not None:
                os.close(fd)
                try:
                    path.unlink()
                except OSError:
                    pass


def serialized(ask: Callable[..., str], root: Optional[Path] = None) -> Callable[..., str]:
    def call(prompt: str, n: int = 240, **kw: Any) -> str:
        with model_lock(root):
            return ask(prompt, n=n, **kw)

    call.accepts_temperature = getattr(ask, "accepts_temperature", None)  # type: ignore[attr-defined]
    if call.accepts_temperature is None:  # type: ignore[attr-defined]
        from core.agent.sampling import accepts_temperature

        call.accepts_temperature = accepts_temperature(ask)  # type: ignore[attr-defined]
    return call


def screen(root: Path, goal: Dict[str, Any], text: str, current: str, baseline: Dict[str, str]) -> Dict[str, Any]:
    """CPU-only check of one reply. Never writes. ok=False says why the gate would be wasted on it."""
    from core.agent import goal_source as gs
    from core.agent import sampling

    edit = gs.extract_edit(text, goal)
    if not edit.get("function") and not edit.get("assigns") and not edit.get("span"):
        return {"ok": False, "why": "no edit", "hash": ""}
    h = sampling.edit_hash(edit)
    fh = sampling.file_hash(current, baseline)
    if sampling.reverted_before(root, goal["id"], h, fh):
        return {"ok": False, "why": "reverted before", "hash": h}
    if edit.get("function") and not edit.get("assigns") and not edit.get("span"):
        res = gs.apply_function(root, goal, edit["function"], write=False, base=current)
        if not res.get("ok"):
            return {"ok": False, "why": str(res.get("reason") or "does not apply"), "hash": h}
        try:
            from core.agent import pillars

            pg = pillars.pregate(current, res["new"])
            if not pg.get("ok", True):
                return {"ok": False, "why": "gem: " + ",".join(pg.get("added") or []), "hash": h}
        except Exception:
            pass
    return {"ok": True, "why": "", "hash": h}


def propose(root: Path, goal: Dict[str, Any], ask: Callable[..., str], prompt: str, n: int,
            base_temp: float, current: str, baseline: Dict[str, str],
            generate: Optional[Callable[[Callable[..., str], str, int], str]] = None) -> Dict[str, Any]:
    """K serialized generations, screened in parallel on CPU. Returns the reply to gate and a trace."""
    from core.agent import sampling

    gen = generate or (lambda a, p, m: a(p, n=m))
    lock_root = Path(root) if os.getenv("ETHER_SWARM_LOCKFILE", "1") == "1" else None
    can_temp = sampling.accepts_temperature(ask)
    kk = k() if can_temp else 1
    t0 = time.monotonic()
    texts: List[str] = []
    futures: List[cf.Future] = []
    with cf.ThreadPoolExecutor(max_workers=workers(), thread_name_prefix="ether-swarm") as pool:
        for j in range(kk):
            temp = base_temp if j == 0 else swarm_temp()
            ask_j = serialized(sampling.with_temp(ask, temp), lock_root)
            try:
                text = gen(ask_j, prompt, n) or ""
            except Exception:
                if j == 0:
                    raise  # an outage on the first call is the caller's infra path
                break
            texts.append(text)
            futures.append(pool.submit(screen, root, goal, text, current, baseline))
        verdicts = [f.result() for f in futures]
    seen: set = set()
    pick = None
    for j, v in enumerate(verdicts):
        if v["ok"] and v["hash"] not in seen and pick is None:
            pick = j
        if v["hash"]:
            seen.add(v["hash"])
    chosen = 0 if pick is None else pick
    trace = {"k": len(texts), "valid": sum(1 for v in verdicts if v["ok"]),
             "distinct": len({v["hash"] for v in verdicts if v["hash"]}), "picked": chosen,
             "why": [v["why"] for v in verdicts], "secs": round(time.monotonic() - t0, 1)}
    return {"text": texts[chosen] if texts else "", "trace": trace}
