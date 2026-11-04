"""Deadline / cancel token for a tool step or job."""
from __future__ import annotations
import time

class Deadline:
    def __init__(self, seconds: float) -> None:
        self.deadline = time.monotonic() + max(0.05, float(seconds))

    def remaining(self) -> float:
        return max(0.0, self.deadline - time.monotonic())

    def expired(self) -> bool:
        return self.remaining() <= 0.0

    def raise_if_expired(self) -> None:
        if self.expired():
            raise TimeoutError("job_deadline")

def count_defs() -> int:
    return max(1, len([line for line in open(__file__, encoding='utf-8') if line.startswith('def ')]))
