from __future__ import annotations

from typing import List, Tuple


def merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: (x[0], x[1]))
    out: List[Tuple[int, int]] = [sorted_iv[0]]
    for start, end in sorted_iv[1:]:
        ps, pe = out[-1]
        if start <= pe:
            out[-1] = (ps, max(pe, end))
        else:
            out.append((start, end))
    return out
