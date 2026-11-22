"""Batch 6: goalable failing tests per classifier configuration (production path, reply gate on).

    python docs/results/batch6/goalable6.py <repo> <tests.xml> <out.json>

Same as batch5/goalable5.py plus: span goals, target concentration (largest share of one
function among goals), and the reason histogram for ETHER_SPAN_EDIT=0 (span ablation).

Runs the failing test files once with the SBFL plugin on a scratch copy of <repo>, then
classifies every failure with ETHER_MULTI_EDIT=0 and =1. Counts goals, drop reasons, vias,
multi-place goals and single goals that carry escalation places (alt_targets). Read-only.
"""
import json, os, shutil, sys, tempfile, time, xml.etree.ElementTree as ET
from pathlib import Path

src, xmlp, outp = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve()
scratch = Path(tempfile.mkdtemp(prefix="ether_goal6_")) / "repo"
shutil.copytree(src, scratch, ignore=shutil.ignore_patterns(".git", "out", "__pycache__", ".pytest_cache", "memory"))
os.chdir(scratch)
sys.path.insert(0, str(scratch))
from core.agent import goal_source as gs  # noqa: E402

t = ET.parse(xmlp).getroot()
files = sorted({gs.nodeid_of(scratch, tc.get("classname") or "", tc.get("name") or "").split("::")[0]
                for tc in t.iter("testcase") if tc.find("failure") is not None or tc.find("error") is not None})
files = [f for f in files if (scratch / f).is_file()]
t0 = time.time()
res = gs.run_pytest(scratch, files, timeout=1800, sbfl=True)
doc = {"repo": str(src), "failing": len(res["fail"]), "run_secs": round(time.time() - t0, 1), "configs": {}}
for flag, span in (("0", "1"), ("1", "1"), ("0", "0")):
    os.environ["ETHER_MULTI_EDIT"] = flag
    os.environ["ETHER_SPAN_EDIT"] = span
    spans, tgt = 0, {}
    reasons, vias, multi, alts, rows, budget = {}, {}, 0, 0, {}, {}
    for nid, text in sorted(res["fail"].items()):
        goal, reason = gs.classify_failure(scratch, nid, text, res.get("spectra"))
        if goal is not None and not gs.fits_reply(scratch, goal):
            goal, reason = None, "too_large"
        reasons[reason] = reasons.get(reason, 0) + 1
        if goal is None:
            rows[nid] = reason
            continue
        vias[goal.get("via")] = vias.get(goal.get("via"), 0) + 1
        spans += int(bool(goal.get("span")))
        key = goal["file"] + "::" + goal["symbol"]
        tgt[key] = tgt.get(key, 0) + 1
        multi += int(bool(goal.get("targets")))
        alts += int(bool(goal.get("alt_targets")))
        if flag == "1" and (goal.get("targets") or goal.get("alt_targets")):
            from core.agent import multi_edit
            from core.kernel.context_budget import context_char_budget

            for ctx in ("2048", "4096", "8192"):
                os.environ["ETHER_MODEL_CTX"] = ctx
                places = multi_edit.targets_of(goal, tries=1)
                prompt, kept = multi_edit.build_prompt(scratch, goal, places)
                b = budget.setdefault(ctx, {"prompts": 0, "over_budget": 0, "dropped_to_single": 0,
                                            "places_kept": 0, "max_chars": 0, "budget": context_char_budget()})
                b["prompts"] += 1
                b["over_budget"] += int(len(prompt) > context_char_budget())
                b["dropped_to_single"] += int(not prompt)
                b["places_kept"] += len(kept)
                b["max_chars"] = max(b["max_chars"], len(prompt))
            os.environ.pop("ETHER_MODEL_CTX", None)
        rows[nid] = f"{goal.get('via')}:{goal['file']}::{goal['symbol']}" + (
            f" +{len(goal.get('alt_targets') or [])}alt" if goal.get("alt_targets") else "") + (
            f" places={len(goal['targets'])}" if goal.get("targets") else "") + (
            f" span={goal['span']['start']}-{goal['span']['end']}" if goal.get("span") else "")
    top = max(tgt.items(), key=lambda kv: kv[1]) if tgt else ("", 0)
    doc["configs"]["multi_" + flag + ("" if span == "1" else "_nospan")] = {
                                       "goals": reasons.get("goal", 0), "reasons": reasons, "vias": vias,
                                       "span_goals": spans, "distinct_targets": len(tgt),
                                       "top_target": top[0], "top_target_share": round(top[1] / max(1, sum(tgt.values())), 3),
                                       "multi_place_goals": multi, "goals_with_escalation_places": alts,
                                       "multi_prompt_budget": budget, "rows": rows}
os.environ.pop("ETHER_MULTI_EDIT", None)
os.environ.pop("ETHER_SPAN_EDIT", None)
outp.parent.mkdir(parents=True, exist_ok=True)
outp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "rows"} for k, v in doc["configs"].items()}, indent=1))
shutil.rmtree(scratch.parent, ignore_errors=True)
