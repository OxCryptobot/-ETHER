"""Tool: reconcile quarantine vs persistent tools."""
from tools._lib import emit, parse_payload
from core.tool_reconcile import reconcile


def main(payload):
    dry = bool(payload.get("dry_run", False))
    threshold = float(payload.get("threshold", 0.82))
    report = reconcile(promote_threshold=threshold, dry_run=dry, max_promote=int(payload.get("max_promote", 25)))
    return {
        "ok": True,
        "promoted": report["promoted"],
        "discarded": report["discarded"],
        "kept": report["kept"],
        "actions": report["actions"][:40],
    }


if __name__ == "__main__":
    emit(main(parse_payload()))
