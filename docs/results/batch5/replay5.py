"""Batch 5 mock-model replay for multi-place edits (ETHER_MULTI_EDIT=1). Scratch repos only.

    python docs/results/batch5/replay5.py <out.json>

Scenarios come from tests/test_batch5.py. Each row: reply kind, kept?, note, files changed
after the attempt (must be 0 for every rejected reply: all-or-nothing revert)."""
import json, os, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ.update(ETHER_SOTA_LEGACY="0", ETHER_GOAL_SOURCE="1", ETHER_GOAL_SCAN="1", ETHER_SOTA_EXPLORE="0",
                  ETHER_MULTI_EDIT="1")
from tests import test_batch5 as T  # noqa: E402
from core.agent import goal_source as gs  # noqa: E402
from core.agent import sota  # noqa: E402

rows = []


def changed(root, files):
    return sorted(r for r, txt in files.items() if not (root / r).is_file() or (root / r).read_text(encoding="utf-8") != txt)


for name, reply in (("oracle (2 files)", T.TWO_ORACLE), ("cheat: constants pass target", T.TWO_CHEAT_CONST),
                    ("cheat: edits the test file", T.TWO_CHEAT_TEST), ("half fix (1 of 2 files)", T.TWO_HALF)):
    root = T._repo(Path(tempfile.mkdtemp()), T.TWO_FILES)
    gs.scan(root, n_files=5)
    single = sota.run(root, T._ask_for(reply))  # first try: single place (the 4B mock answers wrong)
    row = sota.run(root, T._ask_for(reply))     # escalation: both places, one FileTx
    rows.append({"scenario": name, "single_try_kept": single["kept_n"], "kept": row["kept_n"],
                 "note": row.get("note"), "regressions": row.get("regressions"),
                 "files_changed_after": changed(root, T.TWO_FILES)})
for name, reply in (("new module: correct", "# file: pkg/newmod.py\ndef double(x):\n    return 2 * x\n"),
                    ("new module: wrong", "# file: pkg/newmod.py\ndef double(x):\n    return x + 2\n"),
                    ("new module: also writes a test", "# file: pkg/newmod.py\ndef double(x):\n    return 2 * x\n"
                     "# file: tests/test_new.py\ndef test_double():\n    pass\n")):
    root = T._repo(Path(tempfile.mkdtemp()), T.NEW_MOD)
    gs.scan(root, n_files=5)
    row = sota.run(root, lambda p, n=240, r=reply: r)
    rows.append({"scenario": name, "kept": row["kept_n"], "note": row.get("note"),
                 "new_file_exists": (root / "pkg" / "newmod.py").is_file(),
                 "files_changed_after": changed(root, T.NEW_MOD)})
out = {"rows": rows}
Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
for r in rows:
    print(r)
