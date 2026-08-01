"""Merge overlapping intervals — intentional bugs.

BUGS:
- does not sort first (assumes pre-sorted)
- merges only when fully contained, not when overlapping
"""
from __future__ import annotations

from typing import List, Tuple


def merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Merge overlapping [start, end] intervals. End is inclusive."""
    if not intervals:
        return []
    # BUG: no sort
    out: List[Tuple[int, int]] = []
    for start, end in intervals:
        if not out:
            out.append((start, end))
            continue
        ps, pe = out[-1]
        # BUG: only skips fully contained; misses overlap/touch merge
        if start <= pe and end <= pe:
            continue
        out.append((start, end))
    return out
