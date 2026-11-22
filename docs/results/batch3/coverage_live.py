"""Goal coverage the way the host scans: run the failing test files (short tb), optionally with SBFL."""
import json, sys, collections, time, xml.etree.ElementTree as ET
from pathlib import Path
root = Path(sys.argv[1]).resolve(); xmlp = sys.argv[2]; out = sys.argv[3]; sbfl = sys.argv[4] == "1"
sys.path.insert(0, str(root))
from core.agent import goal_source as gs
t = ET.parse(xmlp).getroot()
files = sorted({gs.nodeid_of(root, tc.get("classname") or "", tc.get("name") or "").split("::")[0]
                for tc in t.iter("testcase") if tc.find("failure") is not None or tc.find("error") is not None})
t0 = time.time()
res = gs.run_pytest(root, files, timeout=1800, sbfl=sbfl)
rows = []
for nid, text in res["fail"].items():
    goal, reason = gs.classify_failure(root, nid, text, res.get("spectra") if sbfl else None)
    rows.append({"nodeid": nid, "reason": reason, "file": goal and goal["file"], "symbol": goal and goal["symbol"],
                 "via": goal and goal.get("via"), "suspicion": goal and goal.get("suspicion")})
c = collections.Counter(r["reason"] for r in rows)
v = collections.Counter(r["via"] for r in rows if r["file"])
summ = {"files": len(files), "failing": len(rows), "goalable": sum(1 for r in rows if r["file"]), "by_reason": c,
        "by_via": v, "secs": round(time.time() - t0, 1), "sbfl": sbfl}
print(json.dumps(summ, indent=1))
json.dump({"summary": summ, "rows": rows}, open(out, "w"), indent=1)
