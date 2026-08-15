"""Unify dual dashboards: embed collect_host_agent into collect_snapshot.

Idempotent. Run: python -m scripts.patch_collector_unify
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "dashboard" / "collector.py"

HELPER = '''
def _host_agent_block() -> Dict[str, Any]:
    """Unify dual dashboard: Control Matrix snapshot embeds host agent collector."""
    try:
        from dashboard.collector_host_agent import collect_host_agent

        return collect_host_agent()
    except Exception as e:
        return {"error": str(e)[:160]}


'''


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    if "def _host_agent_block" in text and '"host_agent": _host_agent_block()' in text:
        print("already_unified")
        return 0
    if "def _host_agent_block" not in text:
        marker = "def collect_snapshot() -> Dict[str, Any]:"
        if marker not in text:
            print("marker_missing")
            return 2
        text = text.replace(marker, HELPER + marker, 1)
    old = '        "latest": latest,\n        "last_fail": last_fail,\n    }\n'
    new = (
        '        "latest": latest,\n'
        '        "last_fail": last_fail,\n'
        '        "host_agent": _host_agent_block(),\n'
        "    }\n"
    )
    if '"host_agent": _host_agent_block()' not in text:
        if old not in text:
            print("return_anchor_missing")
            return 3
        text = text.replace(old, new, 1)
    compile(text, str(TARGET), "exec")
    TARGET.write_text(text, encoding="utf-8")
    print("unified", TARGET)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
