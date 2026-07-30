#!/usr/bin/env python3
"""P3 alert renderers + routing (§4, §7).

- CI annotations: GitHub `::error file=...,line=...::` / `::warning`
- Slack Block Kit payload builder; webhook POST via urllib when
  ETHER_AUDIT_SLACK_WEBHOOK is set, else prints the payload
- Email via smtplib (ETHER_AUDIT_SMTP_HOST/PORT/USER/PASS/FROM/TO)
- Digest dedup: 6h window file; bot-only cycles never notify

Never fails the run on notification errors (P3 §7/B3 alert-fatigue lesson).
Secrets come from env only; payloads truncate long fields to 300 chars
(S-04 unredacted-artifact lesson).
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

TRUNC = 300
DIGEST_WINDOW_S = 6 * 3600

IMMEDIATE_EVENTS = {"true_regression"}


def _t(text, n: int = TRUNC) -> str:
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"


# ---------------------------------------------------------------- CI renderer
def ci_annotations(events: list) -> str:
    """GitHub workflow commands. Gate-failing classes -> ::error."""
    lines = []
    for ev in events:
        sev = "error" if (ev.get("event") == "true_regression"
                          or (ev.get("event") == "new_violation"
                              and ev.get("severity") == "blocker")) \
            else "warning"
        f = ev.get("file", "")
        ln = ev.get("line", 0) or 1
        msg = _t(f"{ev.get('event')} {ev.get('rule_id')} "
                 f"score={ev.get('score')}: {ev.get('message', '')}")
        lines.append(f"::{sev} file={f},line={ln}::{msg}")
    return "\n".join(lines)


# ------------------------------------------------------------- Slack renderer
def slack_payload(events: list, title: str = "ETHER audit") -> dict:
    """Block Kit payload (P3 §4 template)."""
    blocks = [{"type": "header",
               "text": {"type": "plain_text",
                        "text": _t(f":rotating_light: {title}", 150)}}]
    for ev in events[:20]:
        emoji = {"true_regression": ":red_circle:",
                 "pattern_migration": ":large_orange_circle:",
                 "new_violation": ":large_yellow_circle:"}.get(
                     ev.get("event"), ":white_circle:")
        blocks.append({
            "type": "section",
            "fields": [
                {"type": "mrkdwn",
                 "text": f"*Event:* {emoji} {ev.get('event')}"},
                {"type": "mrkdwn",
                 "text": f"*Rule:* {ev.get('rule_id')} "
                         f"(score {ev.get('score')})"},
                {"type": "mrkdwn",
                 "text": f"*Where:* `{ev.get('module')}::"
                         f"{ev.get('context')}`"},
                {"type": "mrkdwn",
                 "text": f"*Findings:* {', '.join(ev.get('finding_ids', []))}"},
            ]})
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn",
                          "text": _t(ev.get("message", ""))}]})
    blocks.append({"type": "actions", "elements": [
        {"type": "button", "text": {"type": "plain_text", "text": "Mark FP"},
         "action_id": "audit_mark_fp"},
        {"type": "button", "text": {"type": "plain_text", "text": "Snooze 7d"},
         "action_id": "audit_snooze"}]})
    return {"blocks": blocks}


def send_slack(payload: dict) -> bool:
    """POST to ETHER_AUDIT_SLACK_WEBHOOK; print when unset. Never raises."""
    hook = os.getenv("ETHER_AUDIT_SLACK_WEBHOOK")
    if not hook:
        print("alerts: ETHER_AUDIT_SLACK_WEBHOOK unset — payload:")
        print(json.dumps(payload, indent=2)[:2000])
        return False
    try:
        req = urllib.request.Request(
            hook, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status < 300
    except Exception as e:  # notification errors never fail the run
        print(f"alerts: slack send failed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return False


# -------------------------------------------------------------- email channel
def send_email(subject: str, body_text: str) -> bool:
    """smtplib sender, env-configured. Never raises."""
    host = os.getenv("ETHER_AUDIT_SMTP_HOST")
    to = os.getenv("ETHER_AUDIT_SMTP_TO")
    if not host or not to:
        print("alerts: ETHER_AUDIT_SMTP_* unset — email skipped")
        return False
    try:
        port = int(os.getenv("ETHER_AUDIT_SMTP_PORT", "587"))
        user = os.getenv("ETHER_AUDIT_SMTP_USER", "")
        pw = os.getenv("ETHER_AUDIT_SMTP_PASS", "")
        sender = os.getenv("ETHER_AUDIT_SMTP_FROM", user or "ether-audit@local")
        msg = (f"From: {sender}\r\nTo: {to}\r\nSubject: {_t(subject, 120)}\r\n"
               f"Content-Type: text/plain; charset=utf-8\r\n\r\n{_t(body_text, 8000)}")
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.starttls()
            if user:
                s.login(user, pw)
            s.sendmail(sender, [to], msg.encode("utf-8"))
        return True
    except Exception as e:
        print(f"alerts: email send failed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return False


# ------------------------------------------------------------ digest + dedup
def digest_due(state_path: Path, now: float | None = None) -> bool:
    """6h digest window (P3 §4: at most one digest per 6h)."""
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    try:
        last = json.loads(state_path.read_text(encoding="utf-8"))
        return (now - float(last.get("last_digest_ts", 0))) >= DIGEST_WINDOW_S
    except (OSError, json.JSONDecodeError, ValueError):
        return True


def mark_digest_sent(state_path: Path, now: float | None = None) -> None:
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"last_digest_ts": now}) + "\n", encoding="utf-8")
    tmp.replace(state_path)


def is_bot_only_cycle(commit_message: str, files_touched: list) -> bool:
    """D-02: flywheel commits touching only FLYWHEEL.md never notify."""
    return (files_touched and all(f == "FLYWHEEL.md" for f in files_touched)
            or commit_message.startswith("flywheel "))


def route_events(events: list, digest_state: Path,
                 bot_cycle: bool = False) -> dict:
    """Route per P3 §7: immediate Slack for true_regression/blocker-class,
    everything else into the 6h digest. Returns what happened."""
    sent = {"immediate": 0, "digest": 0, "annotated": 0, "skipped": 0}
    if bot_cycle:
        sent["skipped"] = len(events)
        return sent
    immediate = [ev for ev in events
                 if ev.get("event") in IMMEDIATE_EVENTS
                 or (ev.get("event") == "new_violation"
                     and ev.get("severity") == "blocker")]
    digest = [ev for ev in events if ev not in immediate]
    if immediate:
        send_slack(slack_payload(immediate, "ETHER audit — immediate"))
        sent["immediate"] = len(immediate)
    if digest and digest_due(digest_state):
        send_slack(slack_payload(digest, "ETHER audit — digest"))
        mark_digest_sent(digest_state)
        sent["digest"] = len(digest)
    ann = ci_annotations(events)
    if ann:
        print(ann)
        sent["annotated"] = len(events)
    return sent


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="P3 alert router")
    ap.add_argument("--events", help="classified-events JSONL "
                    "(regression_tracker --json output or events file)")
    ap.add_argument("--digest-state",
                    default=str(Path(__file__).parent.parent.parent
                                / "state" / "digest_state.json"))
    ap.add_argument("--bot-cycle", action="store_true")
    args = ap.parse_args(argv)
    events = []
    if args.events:
        for line in Path(args.events).read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "rule_id" in obj:
                events.append(obj)
    sent = route_events(events, Path(args.digest_state),
                        bot_cycle=args.bot_cycle)
    print(f"alerts routed: {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
