"""LRU cache — intentional bugs for hard Phase C tasks.

BUGS:
- put does not evict when over capacity (grows forever)
- get does not mark key as most-recently-used
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Any, Optional


class LRUCache:
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self._data: OrderedDict[Any, Any] = OrderedDict()

    def get(self, key: Any) -> Optional[Any]:
        if key not in self._data:
            return None
        # BUG: should move_to_end(key) so it becomes most-recent
        return self._data[key]

    def put(self, key: Any, value: Any) -> None:
        if key in self._data:
            self._data[key] = value
            self._data.move_to_end(key)
            return
        self._data[key] = value
        # BUG: never evicts — capacity ignored on insert
