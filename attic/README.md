# attic/ (batch 10 item 1)

Unreachable code moved out of the live tree, not deleted. Nothing under `attic/` is imported,
collected by pytest (`testpaths = ["tests"]`), scanned for goals, or offered to the refactor loop.

* `MANIFEST.json` lists every file: original path, attic path, line count.
* Restore one file: `git mv attic/<path> <path>` (paths under attic/ mirror the original layout).
* Restore everything: `python scripts/attic_restore.py --all` (or `git revert` the batch 10 item 1 commit).

Selection (conservative): a module is moved only when it is unreachable from the 177 entry roots in
the import graph AND its dotted name / path appears in no operational file outside the moved set.
Modules named in any live file, config, or by a test that also covers live code stayed in place
(see docs/QUARANTINE_CANDIDATES.md for the larger, unmoved candidate list).
