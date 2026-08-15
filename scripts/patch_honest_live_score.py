"""Apply is_honest_tool_path_pass to live pipeline scoreboard rows.

Prevents generate-fallback / terminal-degraded runs from counting as PASS.
Idempotent. Run: python -m scripts.patch_honest_live_score
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "batch_phase_d.py"

OLD = '''        return {
            "fixture": name,
            "arm": arm,
            "ok": ok,
            "score": score,
            "strategy": strategy,
            "status": status,
            "repo_oracle_ok": repo_ok,
            "elapsed_s": round(elapsed, 3),
            "mode": "live" if live else "scripted",
            "stages": stages,
            "degraded": list(getattr(result, "degraded", []) or [])[:6],
            "model": os.environ.get("ETHER_PRIMARY_MODEL", ""),
        }
'''

NEW = '''        row = {
            "fixture": name,
            "arm": arm,
            "ok": ok,
            "score": score,
            "strategy": strategy,
            "status": status,
            "repo_oracle_ok": repo_ok,
            "elapsed_s": round(elapsed, 3),
            "mode": "live" if live else "scripted",
            "stages": stages,
            "degraded": list(getattr(result, "degraded", []) or [])[:6],
            "model": os.environ.get("ETHER_PRIMARY_MODEL", ""),
        }
        # Honest Phase-1 tool-path gate: generate-fallback / terminal must not count as PASS
        if live and not bare:
            try:
                from core.loop.handlers.tool_runtime_gate import is_honest_tool_path_pass

                if row.get("ok") and not is_honest_tool_path_pass(row):
                    row["ok"] = False
                    row["honest_tool_path"] = False
                    row.setdefault("degraded", []).append("honest_tool_path_reject")
                else:
                    row["honest_tool_path"] = bool(row.get("ok"))
            except Exception:
                row["honest_tool_path"] = None
        return row
'''


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if "honest_tool_path" in text and "is_honest_tool_path_pass" in text:
        print("already_patched")
        return 0
    if OLD not in text:
        print("anchor_missing")
        return 2
    text = text.replace(OLD, NEW, 1)
    compile(text, str(TARGET), "exec")
    TARGET.write_text(text, encoding="utf-8")
    print("patched", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
