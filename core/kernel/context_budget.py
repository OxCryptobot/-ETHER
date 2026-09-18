"""4B context budget. No magic 3500 without a token model."""
from __future__ import annotations
import os

def context_char_budget(model_ctx: int | None = None) -> int:
    ctx = model_ctx or int(os.getenv("ETHER_MODEL_CTX") or "8192")
    tokens = min(int(ctx * 0.35), 1800)
    return max(800, tokens * 4)
