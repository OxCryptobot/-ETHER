"""Tag foreman steady jobs with class=fast|live for FAST-first host.

Idempotent. Run: python -m scripts.patch_foreman_job_class
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "foreman.py"


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if 'job["class"]' in text or "job['class']" in text:
        print("already_tagged")
        return 0

    old = '''        job = {
            "id": jid,
            "note": tmpl.get("note", "steady"),
            "source": "foreman_steady",
            "created": _now(),
            "steps": tmpl["steps"],
        }
        if tmpl.get("continue_on_fail"):
            job["continue_on_fail"] = True
'''
    new = '''        job = {
            "id": jid,
            "note": tmpl.get("note", "steady"),
            "source": "foreman_steady",
            "created": _now(),
            "steps": tmpl["steps"],
            "class": "live" if tmpl.get("live") else "fast",
        }
        if tmpl.get("continue_on_fail"):
            job["continue_on_fail"] = True
'''
    if old not in text:
        print("anchor_missing")
        return 2
    text = text.replace(old, new, 1)
    compile(text, str(TARGET), "exec")
    TARGET.write_text(text, encoding="utf-8")
    print("patched", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
