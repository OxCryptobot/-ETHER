from __future__ import annotations
from typing import List, TypeVar

T = TypeVar("T")


def merge_sorted(a: List[T], b: List[T]) -> List[T]:
    if a is None or b is None:
        raise TypeError("inputs must be lists")
    out: List[T] = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            out.append(a[i])
            i += 1
        else:
            out.append(b[j])
            j += 1
    if i < len(a):
        out.extend(a[i:])
    if j < len(b):
        out.extend(b[j:])
    return out
