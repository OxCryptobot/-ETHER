"""Merge two sorted lists — intentional bugs.

BUGS:
- drops remainder of longer list when one side exhausts early
- empty inputs return the other list by identity (must copy)
"""
from __future__ import annotations

from typing import List, TypeVar

T = TypeVar("T")


def merge_sorted(a: List[T], b: List[T]) -> List[T]:
    """Return a new sorted list containing all elements of a and b.

    Preconditions: a and b are each sorted ascending.
    """
    if a is None or b is None:
        raise TypeError("inputs must be lists")
    if not a and not b:
        return []
    if not a:
        return b  # BUG: should return list(b)
    if not b:
        return a  # BUG: should return list(a)

    out: List[T] = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            out.append(a[i])
            i += 1
        else:
            out.append(b[j])
            j += 1
    # BUG: should also out.extend(b[j:])
    if i < len(a):
        out.extend(a[i:])
    return out

