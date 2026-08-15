"""Wire FAST-first job pick + enrich failure_type from scoreboards.

Idempotent. Run: python -m scripts.patch_host_fast_first
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "host_agent.py"


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if "_sort_pending_fast_first" in text:
        print("already_patched")
        return 0

    helper = '''
def _sort_pending_fast_first(paths: List[Path]) -> List[Path]:
    """Prefer FAST jobs so live timeouts do not starve the queue."""
    try:
        from core.job_class import job_class, FAST, LIVE
    except Exception:
        return paths

    def rank(p: Path) -> tuple:
        try:
            job = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return (1, p.name)
        cls = job_class(job)
        # 0=fast, 1=any, 2=live
        order = 0 if cls == FAST else (2 if cls == LIVE else 1)
        return (order, p.name)

    return sorted(paths, key=rank)


def _enrich_failure_from_scoreboard(envelope: Dict[str, Any]) -> None:
    """If job failed, pull failure_type from newest scoreboard if present."""
    if envelope.get("ok"):
        return
    art = ROOT / "artifacts"
    if not art.exists():
        return
    boards = sorted(art.glob("scoreboard*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for b in boards[:3]:
        try:
            data = json.loads(b.read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in data.get("results") or []:
            deg = " ".join(str(x) for x in (row.get("degraded") or []))
            if "tool_runtime_failed_terminal" in deg or "timeout" in deg.lower():
                envelope.setdefault("failure_type", "timeout")
                envelope["scoreboard"] = b.name
                return
            if row.get("ok") is False and row.get("mode") == "live":
                envelope.setdefault("failure_type", "live_fail")
                envelope["scoreboard"] = b.name
                return


'''
    # Insert helpers before list_pending
    marker = "def list_pending() -> List[Path]:"
    if marker not in text:
        print("list_pending_missing")
        return 2
    text = text.replace(marker, helper + marker, 1)

    old_list = '''def list_pending() -> List[Path]:
    PENDING.mkdir(parents=True, exist_ok=True)
    return sorted([p for p in PENDING.glob("*.json") if p.name != ".gitkeep"], key=lambda p: p.name)
'''
    new_list = '''def list_pending() -> List[Path]:
    PENDING.mkdir(parents=True, exist_ok=True)
    paths = [p for p in PENDING.glob("*.json") if p.name != ".gitkeep"]
    return _sort_pending_fast_first(paths)
'''
    if old_list not in text:
        print("list_body_missing")
        return 3
    text = text.replace(old_list, new_list, 1)

    # Enrich envelope before write
    old_env = '''    LAST_JOB.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
'''
    new_env = '''    _enrich_failure_from_scoreboard(envelope)
    LAST_JOB.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
'''
    if old_env not in text:
        print("envelope_anchor_missing")
        return 4
    text = text.replace(old_env, new_env, 1)

    compile(text, str(TARGET), "exec")
    TARGET.write_text(text, encoding="utf-8")
    print("patched", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
