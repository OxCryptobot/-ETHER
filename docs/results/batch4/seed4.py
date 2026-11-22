"""Regenerate config/goal_seed.json the way the host scans (short tb, SBFL on), from a scratch copy."""
import json, os, shutil, sys, tempfile, time, xml.etree.ElementTree as ET
from pathlib import Path
src = Path(sys.argv[1]).resolve(); xmlp = str(Path(sys.argv[2]).resolve())
scratch = Path(tempfile.mkdtemp(prefix="ether_seed3_")) / "repo"
shutil.copytree(src, scratch, ignore=shutil.ignore_patterns(".git", "out", "__pycache__", ".pytest_cache", "memory"))
(scratch / "config" / "goal_seed.json").unlink(missing_ok=True)
(scratch / "artifacts" / "goal_index.json").unlink(missing_ok=True)
os.chdir(scratch); sys.path.insert(0, str(scratch))
from core.agent import goal_source as gs
t = ET.parse(xmlp).getroot()
files = sorted({gs.nodeid_of(scratch, tc.get("classname") or "", tc.get("name") or "").split("::")[0]
                for tc in t.iter("testcase") if tc.find("failure") is not None or tc.find("error") is not None})
t0 = time.time()
row = gs.scan(scratch, files=files, timeout=1800)
data = gs.load_index(scratch)
data["cursor"] = 0
data["source"] = "batch4 scan of the failing files (short tb, SBFL hub rank + reply-size gate), 2026-11-20"
data.pop("updated", None)
for g in data["goals"].values():
    g["error"] = g.get("error", "")[-700:]
kinds = {}
for g in data["goals"].values():
    kinds[g["kind"]] = kinds.get(g["kind"], 0) + 1
data["kinds"] = kinds
vias = {}
for g in data["goals"].values():
    vias[g.get("via") or g["kind"]] = vias.get(g.get("via") or g["kind"], 0) + 1
data["vias"] = vias
reasons = {}
for r in data["dropped"].values():
    reasons[r] = reasons.get(r, 0) + 1
out = src / "config" / "goal_seed.json"
out.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps({"scan": row, "kinds": kinds, "vias": vias, "dropped": reasons, "secs": round(time.time() - t0, 1)}, indent=1))
shutil.rmtree(scratch.parent, ignore_errors=True)
