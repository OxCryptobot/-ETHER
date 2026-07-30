#!/usr/bin/env python3
"""Regenerate memory/datasets/mbpp_lite.json deterministically (stdlib only).

Day-3 dataset policy (ADR 0004, finding A-8): eval data no longer rides in
git — memory/ is gitignored runtime state, so fresh clones do not carry this
file. The canonical content is embedded verbatim below (provenance: a lite
subset derived from MBPP; hand-authored inspired tasks for local eval only,
not a redistributed benchmark dump) so a fresh clone can reproduce it
offline, byte-for-byte:

    python scripts/fetch_datasets.py            # write (mkdir -p, atomic)
    python scripts/fetch_datasets.py --check    # exit 1 on drift/missing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "memory" / "datasets" / "mbpp_lite.json"

# Canonical bytes of memory/datasets/mbpp_lite.json (2320 bytes,
# sha256 eb7aa52fd2f3c54a9d4811f91dfadc6b48088fc572a79b2524901ea84b4d4dde).
CANONICAL = r"""{
  "name": "mbpp_lite_local",
  "license_note": "Hand-authored inspired tasks for local eval only — not a redistributed benchmark dump.",
  "tasks": [
    {
      "id": "mb01",
      "prompt": "Write a function similar_elements(a, b) that returns a tuple of sorted unique elements common to both lists.",
      "hidden_test": "assert similar_elements([1,2,3],[2,3,4]) == (2,3)\nprint(similar_elements([1,2,3],[2,3,4]))"
    },
    {
      "id": "mb02",
      "prompt": "Write a function find_char_long(s) that returns words longer than 3 characters from a space-separated string as a list.",
      "hidden_test": "assert find_char_long('This is a test string') == ['This','test','string']\nprint(find_char_long('This is a test string'))"
    },
    {
      "id": "mb03",
      "prompt": "Write a function power_base_sum(n, power) that returns the sum of the digits of n**power.",
      "hidden_test": "assert power_base_sum(2, 10) == 7\nprint(power_base_sum(2, 10))"
    },
    {
      "id": "mb04",
      "prompt": "Write a function snake_to_camel(s) converting snake_case to camelCase.",
      "hidden_test": "assert snake_to_camel('hello_world') == 'helloWorld'\nprint(snake_to_camel('hello_world'))"
    },
    {
      "id": "mb05",
      "prompt": "Write a function remove_dirty_chars(s, chars) removing all characters in chars from s.",
      "hidden_test": "assert remove_dirty_chars('hello', 'eo') == 'hll'\nprint(remove_dirty_chars('hello', 'eo'))"
    },
    {
      "id": "mb06",
      "prompt": "Write a function first_repeated_char(s) returning the first character that repeats, or None.",
      "hidden_test": "assert first_repeated_char('abcab') == 'a'\nassert first_repeated_char('abc') is None\nprint(first_repeated_char('abcab'))"
    },
    {
      "id": "mb07",
      "prompt": "Write a function max_product(xs) returning the maximum product of two distinct elements (or 0 if len<2).",
      "hidden_test": "assert max_product([1,2,3,4]) == 12\nassert max_product([-10,-3,1]) == 30\nprint(max_product([1,2,3,4]))"
    },
    {
      "id": "mb08",
      "prompt": "Write a function is_sublist(a, b) True if b is a contiguous sublist of a.",
      "hidden_test": "assert is_sublist([1,2,3,4],[2,3]) is True\nassert is_sublist([1,2,3],[1,3]) is False\nprint(is_sublist([1,2,3,4],[2,3]))"
    }
  ]
}
"""


def write_dataset(path: Path = TARGET) -> Path:
    """Write the canonical bytes (atomic tmp + replace; small file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(CANONICAL, encoding="utf-8")
    tmp.replace(path)
    return path


def check_dataset(path: Path = TARGET) -> bool:
    """True iff the file exists and matches the canonical bytes exactly."""
    try:
        return path.read_text(encoding="utf-8") == CANONICAL
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="verify the existing file matches canonical; "
                         "exit 1 on drift or absence")
    args = ap.parse_args()
    if args.check:
        if check_dataset():
            print(f"ok: {TARGET} matches canonical content")
            return 0
        print(f"drift or missing: {TARGET} — run scripts/fetch_datasets.py",
              file=sys.stderr)
        return 1
    path = write_dataset()
    print(f"wrote {path} ({len(CANONICAL.encode('utf-8'))} bytes, canonical)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
